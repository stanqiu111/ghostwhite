# entries/tests.py
from io import BytesIO
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from authors.models import Author
from nodes.models import Node
from entries.models import Entry, Comment, EntryLike, CommentLike


def make_test_image_bytes(fmt="JPEG", size=(8, 8), color=(255, 0, 0)):
    """
    Create a tiny valid image in memory for uploads.
    Requires Pillow (already needed by ImageField).
    """
    file = BytesIO()
    Image.new("RGB", size, color).save(file, fmt)
    file.seek(0)
    return file.read()


@override_settings(MEDIA_ROOT="/tmp/test-media")  # isolate test media
class EntryAPITests(APITestCase):
    def setUp(self):
        # One local node (unique is_local)
        self.node = Node.objects.create(host_url="http://testserver", is_local=True)

        # Users
        self.author = Author.objects.create_user(
            username="author",
            password="pass1234",
            display_name="Author User",
            node=self.node,
        )
        self.other = Author.objects.create_user(
            username="other",
            password="pass1234",
            display_name="Other User",
            node=self.node,
        )

        # One entry owned by author
        self.entry = Entry.objects.create(
            author=self.author,
            node=self.node,
            content="Original content",
            content_type="plain_text",
            visibility="public",
        )

        self.client = APIClient()

    # ---------------- LIST / RETRIEVE ----------------

    def test_entry_list_requires_auth(self):
        url = reverse("entries:entry-list")
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(self.author)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data, list)

    def test_entry_retrieve_allow_any(self):
        url = reverse("entries:entry-detail", args=[self.entry.id])
        # No auth required
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], str(self.entry.id))

    # ---------------- CREATE ----------------

    def test_entry_create_requires_auth(self):
        url = reverse("entries:entry-create")
        data = {
            "content": "Hello world",
            "content_type": "plain_text",
            "visibility": "public",
        }
        # unauthenticated
        res = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # authenticated
        self.client.force_authenticate(self.author)
        res = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["content"], "Hello world")

    # ---------------- UPDATE (PUT ONLY, NO PARTIAL) ----------------

    def test_entry_update_author_only(self):
        url = reverse("entries:entry-update", args=[self.entry.id])

        # Other user tries to update
        self.client.force_authenticate(self.other)
        payload = {
            "content": "Hacked",
            "content_type": "plain_text",
            "visibility": "public",
        }
        res = self.client.put(url, payload)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)  # queryset limited to author

        # Owner updates
        self.client.force_authenticate(self.author)
        payload = {
            "content": "Updated by owner",
            "content_type": "plain_text",
            "visibility": "public",
        }
        res = self.client.put(url, payload)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.content, "Updated by owner")

    def test_entry_update_with_image(self):
        """
        PUT must include all required fields (no partial update).
        """
        url = reverse("entries:entry-update", args=[self.entry.id])
        self.client.force_authenticate(self.author)

        img_bytes = make_test_image_bytes()
        image = SimpleUploadedFile("test.jpg", img_bytes, content_type="image/jpeg")

        data = {
            "content": "Updated content with image",
            "content_type": "plain_text",
            "visibility": "public",
            "image": image,
        }
        res = self.client.put(url, data, format="multipart")
        self.assertEqual(
            res.status_code,
            status.HTTP_200_OK,
            f"Expected 200, got {res.status_code}: {getattr(res, 'data', None)}",
        )

        self.entry.refresh_from_db()
        self.assertEqual(self.entry.content, "Updated content with image")
        self.assertTrue(bool(self.entry.image))


    # ---------------- DELETE (SOFT) ----------------

    def test_entry_delete_soft(self):
        url = reverse("entries:entry-delete", args=[self.entry.id])

        # other user cannot delete
        self.client.force_authenticate(self.other)
        res = self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # owner deletes (soft)
        self.client.force_authenticate(self.author)
        res = self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        self.entry.refresh_from_db()
        self.assertIsNotNone(self.entry.deleted_at)

    # ---------------- COMMENTS ----------------

    def test_comment_create(self):
        url = reverse("entries:add_comment", args=[self.entry.id])
        payload = {"content": "Nice post!"}

        # unauthenticated
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # authenticated
        self.client.force_authenticate(self.other)
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        self.assertEqual(self.entry.comments.count(), 1)
        c = self.entry.comments.first()
        self.assertEqual(c.content, "Nice post!")
        self.assertEqual(c.author, self.other)

    # ---------------- LIKES ----------------

    def test_like_entry_toggle(self):
        url = reverse("entries:like_entry", args=[self.entry.id])

        # Must be authed
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(self.other)

        # First like -> created (201)
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(EntryLike.objects.filter(entry=self.entry, author=self.other).exists())

        # Second like -> removed (200)
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(EntryLike.objects.filter(entry=self.entry, author=self.other).exists())

    def test_like_comment_toggle(self):
        # Prepare a comment
        comment = Comment.objects.create(entry=self.entry, author=self.author, content="Owner comment")

        url = reverse("entries:like_comment", args=[self.entry.id, comment.id])

        # unauthenticated
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # authenticated (other likes)
        self.client.force_authenticate(self.other)
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(CommentLike.objects.filter(comment=comment, author=self.other).exists())

        # toggle off
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(CommentLike.objects.filter(comment=comment, author=self.other).exists())