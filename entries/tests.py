# entries/tests.py
import tempfile
from django.urls import reverse
from django.test import override_settings
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
import os
from nodes.models import Node
from entries.models import Entry, Comment, EntryLike, CommentLike

User = get_user_model()

# Use a temp MEDIA_ROOT for tests that upload files
_TMP_MEDIA = tempfile.mkdtemp()

@override_settings(MEDIA_ROOT=_TMP_MEDIA)
class EntryAPITests(APITestCase):
    def setUp(self):
        # Create local node; your schema makes Node required on Author
        self.node, _ = Node.objects.get_or_create(
            is_local=True,
            defaults={"host_url": "http://localhost:8000"},
        )

        # IMPORTANT: attach node=self.node when creating users
        self.author = User.objects.create_user(
            username="author",
            password="pass123",
            display_name="Author",
            node=self.node,
        )
        self.other = User.objects.create_user(
            username="other",
            password="pass123",
            display_name="Other",
            node=self.node,
        )


        # Seed entry owned by author
        self.entry = Entry.objects.create(
            author=self.author,
            node=self.node,
            content="Hello world",
            content_type="plain_text",
            visibility="public",
        )

        self.client = APIClient()

    def auth(self, user):
        self.client.force_authenticate(user=user)

    # ---------- List ----------
    def test_entry_list_requires_auth(self):
        url = reverse("entries:entry-list")

        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        self.auth(self.author)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(len(res.json()) >= 1)

    # ---------- Retrieve ----------
    def test_entry_retrieve_allow_any(self):
        url = reverse("entries:entry-detail", args=[self.entry.id])
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["id"], str(self.entry.id))

    # ---------- Create ----------
    def test_entry_create_requires_auth(self):
        url = reverse("entries:entry-create")
        data = {
            "content": "new entry",
            "content_type": "markdown",
            "visibility": "public",
        }

        # Unauth -> 401
        res = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Auth -> 201
        self.auth(self.author)
        res = self.client.post(url, data)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Entry.objects.filter(content="new entry").exists())

    # ---------- Update (author only) ----------
    def test_entry_update_author_only(self):
        url = reverse("entries:entry-update", args=[self.entry.id])
        payload = {
            "content": "Edited content",
            "content_type": "plain_text",
            "visibility": "public",
        }

        # Other user -> 404 or 403 depending on queryset filter; with your queryset it should be 404
        self.auth(self.other)
        res = self.client.put(url, payload)
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        # Author -> 200
        self.auth(self.author)
        res = self.client.put(url, payload)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.content, "Edited content")

    # ---------- Update with image (multipart) ----------
    def test_entry_update_with_image(self):
        self.auth(self.author)  # however you log in your test user
        url = reverse("entries:entry-update", kwargs={"pk": str(self.entry.id)})

        # ✅ use your real static image
        image_path = os.path.join("authors", "static", "authors", "avatar1.jpg")
        with open(image_path, "rb") as f:
            image_file = SimpleUploadedFile("avatar1.jpg", f.read(), content_type="image/jpeg")

        res = self.client.patch(
            url,
            data={"image": image_file},
            format="multipart",
        )

        print("DEBUG RESPONSE:", res.status_code, getattr(res, "data", None))  # optional
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.entry.refresh_from_db()
        self.assertTrue(bool(self.entry.image))
        
    # ---------- Soft delete ----------
    def test_entry_delete_soft(self):
        url = reverse("entries:entry-delete", args=[self.entry.id])

        # Other user -> 404/403
        self.auth(self.other)
        res = self.client.delete(url)
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

        # Author -> 204 and deleted_at set
        self.auth(self.author)
        res = self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.entry.refresh_from_db()
        self.assertIsNotNone(self.entry.deleted_at)

    # ---------- Comment create ----------
    def test_comment_create(self):
        url = reverse("entries:add_comment", args=[self.entry.id])

        # Unauth -> 401
        res = self.client.post(url, {"content": "hi"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Auth -> 201
        self.auth(self.other)
        res = self.client.post(url, {"content": "hi"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Comment.objects.filter(entry=self.entry, content="hi").exists())

    # ---------- Like entry toggle ----------
    def test_like_entry_toggle(self):
        url = reverse("entries:like_entry", args=[self.entry.id])
        self.auth(self.other)

        # First -> create like
        res = self.client.post(url)
        self.assertIn(res.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        self.assertTrue(EntryLike.objects.filter(entry=self.entry, author=self.other).exists())

        # Second -> remove like
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(EntryLike.objects.filter(entry=self.entry, author=self.other).exists())

    # ---------- Like comment toggle ----------
    def test_like_comment_toggle(self):
        comment = Comment.objects.create(
            entry=self.entry, author=self.author, content="Nice"
        )
        url = reverse("entries:like_comment", args=[self.entry.id, comment.id])
        self.auth(self.other)

        # First -> like
        res = self.client.post(url)
        self.assertIn(res.status_code, [status.HTTP_201_CREATED, status.HTTP_200_OK])
        self.assertTrue(CommentLike.objects.filter(comment=comment, author=self.other).exists())

        # Second -> unlike
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(CommentLike.objects.filter(comment=comment, author=self.other).exists())