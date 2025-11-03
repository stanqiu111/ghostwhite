# entries/tests.py
from io import BytesIO
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings, TestCase
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient
from authors.models import Author as User
from nodes.models import Node
from entries.models import Entry, Comment, EntryLike, CommentLike
from rest_framework.test import APITestCase
from authors.models import Author


def make_test_image_bytes(fmt="JPEG", size=(8, 8), color=(255, 0, 0)):
    """Create a tiny valid image in memory for uploads."""
    file = BytesIO()
    Image.new("RGB", size, color).save(file, fmt)
    file.seek(0)
    return file.read()


@override_settings(MEDIA_ROOT="/tmp/test-media")  # isolate test media
class EntryAPITests(TestCase):
    def setUp(self):
        # Local node required for FK on Author
        self.node, _ = Node.objects.get_or_create(
            is_local=True, defaults={"host_url": "http://testserver"}
        )

        self.author = User.objects.create_user(
            username="alice", password="pass1234", node=self.node
        )
        self.other = User.objects.create_user(
            username="bob", password="pass5678", node=self.node
        )

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

        # unauthenticated
        res = self.client.get(url)
        # If SessionAuthentication is enabled, unauthenticated requests may return 403 (CSRF) instead of 401
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

        # authenticated
        self.client.force_authenticate(self.author)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsInstance(res.data, list)

    def test_entry_retrieve_requires_auth(self):
        """
        EntryRetrieveView has IsAuthenticated in views.py,
        so unauthenticated GET must be 401; authed should be 200.
        """
        url = reverse("entries:entry-detail", args=[self.entry.id])

        # unauthenticated -> 401
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # authenticated -> 200
        self.client.force_authenticate(self.author)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # id should be FQID, and serial should be local UUID
        self.assertTrue(str(self.entry.id) in res.data["id"])  
        self.assertTrue(res.data["id"].startswith("http"))
        self.assertEqual(res.data.get("serial"), str(self.entry.id))

    def test_entry_retrieve_with_fqid_in_path_is_invalid(self):
        """ If id was inserted instead of serial, it should be invalid """
        fqid = f"http://testserver/api/authors/{self.author.id}/entries/{self.entry.id}"
        url = reverse("entries:entry-detail", args=[self.entry.id])  # valid
        bad_url = url.replace(str(self.entry.id), fqid)
        res = self.client.get(bad_url)
        # Django URL won't match; expect 404
        self.assertIn(res.status_code, (status.HTTP_404_NOT_FOUND, status.HTTP_400_BAD_REQUEST))

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

        # Other user tries to update -> queryset limits to owner => 404
        self.client.force_authenticate(self.other)
        payload = {
            "content": "Hacked",
            "content_type": "plain_text",
            "visibility": "public",
        }
        res = self.client.put(url, payload)
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Owner updates successfully
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
        """PUT must include all required fields (no partial update)."""
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

    # ---------------- COMMENTS: CREATE / LIKE ----------------

    def test_comment_create(self):
        url = reverse("entries:add_comment", args=[self.entry.id])
        payload = {"content": "Nice post!"}

        # unauthenticated
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # authenticated (other user comments)
        self.client.force_authenticate(self.other)
        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.entry.comments.count(), 1)
        c = self.entry.comments.first()
        self.assertEqual(c.content, "Nice post!")
        self.assertEqual(c.author, self.other)

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
    
    class ImageHostingTests(APITestCase):
        def setUp(self):
            self.author = Author.objects.create_user(
                username="tester", password="pass123", display_name="tester"
            )
            self.client.login(username="tester", password="pass123")

        def generate_image(self):
            img = Image.new("RGB", (50, 50), color="red")
            tmp = BytesIO()
            img.save(tmp, format="PNG")
            tmp.name = "test.png"
            tmp.seek(0)
            return tmp

        def test_image_entry_upload_and_retrieve(self):
            url = reverse("entry-list")  # e.g. /api/entries/
            image_file = self.generate_image()

            data = {
                "author": str(self.author.id),
                "content_type": "image/png;base64",
                "visibility": "public",
                "image": image_file,
            }
            res = self.client.post(url, data, format="multipart")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            entry_id = res.data["id"]

            # GET image endpoint
            image_url = reverse("entry-image-by-id", kwargs={
                "author_id": self.author.id,
                "pk": entry_id
            })
            get_res = self.client.get(image_url)
            self.assertEqual(get_res.status_code, status.HTTP_200_OK)
            self.assertEqual(get_res["Content-Type"], "image/png")

            # Check image URL appears in entry API
            entry_res = self.client.get(reverse("entry-detail", kwargs={"pk": entry_id}))
            self.assertIn("image_url", entry_res.data)
            self.assertTrue(entry_res.data["image_url"].endswith("/image/"))


class FQIDIntegrationTests(APITestCase):
    def setUp(self):
        self.node, _ = Node.objects.get_or_create(is_local=True, defaults={'host_url': 'http://testserver'})

        self.testUser1 = Author.objects.create_user(
            username="testUser1", password="pw", display_name="Test User 1", node=self.node
        )
        self.testUser2 = Author.objects.create_user(
            username="testUser2", password="pw", display_name="Test User 2", node=self.node
        )

        self.entry = Entry.objects.create(
            author=self.testUser1, node=self.node, content="Hi", content_type="plain_text", visibility="public"
        )

        self.client = APIClient()

    def test_entry_detail_uses_fqid_and_serial(self):
        url = reverse("entries:entry-detail", args=[self.entry.id])
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # id returned from the api is a FQID instead of UUID like the local id
        self.assertTrue(res.data["id"].startswith("http"))
        self.assertIn(str(self.entry.id), res.data["id"])
        self.assertEqual(res.data.get("serial"), str(self.entry.id))

    def test_like_and_comment_keep_fqid_in_response(self):
        # testUser2 likes testUser1's entry
        self.client.force_authenticate(self.testUser2)
        like_url = reverse("entries:like_entry", args=[self.entry.id])
        res = self.client.post(like_url)
        self.assertIn(res.status_code, (status.HTTP_201_CREATED, status.HTTP_200_OK))

        # testUser2 comments on testUser1's entry
        comment_url = reverse("entries:add_comment", args=[self.entry.id])
        res = self.client.post(comment_url, {"content": "Nice!"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # Fetch entry detail and verify each comment's id is a FQID instead of UUID
        detail_url = reverse("entries:entry-detail", args=[self.entry.id])
        res = self.client.get(detail_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        for c in res.data.get("comments", []):
            self.assertTrue(c["id"].startswith("http"))
        for l in res.data.get("likes", []):
            self.assertTrue(l["id"].startswith("http"))

    # ---------------- COMMENTS: PATCH / PUT / DELETE ----------------
    # Hit the REST path directly to avoid relying on a missing URL name.

    def _comment_detail_url(self, entry_id, comment_id):
        # Matches CommentUpdateDeleteView docstring:
        #   /api/entries/<uuid:pk>/comments/<int:comment_id>/
        return f"/api/entries/{entry_id}/comments/{comment_id}/"

    def test_comment_patch_requires_auth(self):
        comment = Comment.objects.create(entry=self.entry, author=self.other, content="hi")
        url = self._comment_detail_url(self.entry.id, comment.id)

        # unauthenticated -> 401
        res = self.client.patch(url, {"content": "edited"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_comment_patch_only_author_can_edit(self):
        comment = Comment.objects.create(entry=self.entry, author=self.other, content="orig")
        url = self._comment_detail_url(self.entry.id, comment.id)

        # not author -> 403
        self.client.force_authenticate(self.author)  # entry owner but NOT comment author
        res = self.client.patch(url, {"content": "hacked"}, format="json")
        call_status = res.status_code
        self.assertIn(call_status, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        # If your URL conf additionally enforces entry binding and returns 404 for non-author, accept that too.

        # author -> 200 and content changes
        self.client.force_authenticate(self.other)
        res = self.client.patch(url, {"content": "edited by author"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.content, "edited by author")

    def test_comment_patch_empty_content_400(self):
        comment = Comment.objects.create(entry=self.entry, author=self.other, content="not empty")
        url = self._comment_detail_url(self.entry.id, comment.id)

        self.client.force_authenticate(self.other)
        res = self.client.patch(url, {"content": "   "}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", res.data)

    def test_comment_put_behaves_like_patch(self):
        comment = Comment.objects.create(entry=self.entry, author=self.other, content="orig")
        url = self._comment_detail_url(self.entry.id, comment.id)

        self.client.force_authenticate(self.other)
        res = self.client.put(url, {"content": "put update"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        comment.refresh_from_db()
        self.assertEqual(comment.content, "put update")

    def test_comment_delete_permissions(self):
        comment = Comment.objects.create(entry=self.entry, author=self.other, content="bye")
        url = self._comment_detail_url(self.entry.id, comment.id)

        # not author and not staff -> 403 (or 404 if URL conf hides existence)
        self.client.force_authenticate(self.author)  # owner of entry, not comment author
        res = self.client.delete(url)
        self.assertIn(res.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_comment_delete_staff_allowed(self):
        comment = Comment.objects.create(entry=self.entry, author=self.other, content="bye")
        url = self._comment_detail_url(self.entry.id, comment.id)

        staff = User.objects.create_user(
            username="admin", password="root", node=self.node, is_staff=True
        )
        self.client.force_authenticate(staff)
        res = self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Comment.objects.filter(pk=comment.id).exists())