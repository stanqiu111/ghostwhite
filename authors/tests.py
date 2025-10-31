from django.urls import reverse
from django.test import override_settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
import json

from nodes.models import Node
from authors.models import Follow

User = get_user_model()


@override_settings(MEDIA_ROOT="/tmp/test-media")
class FollowAPITests(APITestCase):
    """
    Tests for your current Follow model (approved: bool)
      POST /api/authors/<author_id>/follow/            -> create pending (approved=False)
      GET  /api/authors/follow-requests/               -> list my pending
      POST /api/authors/follows/<id>/decision/         -> accept/deny
    """

    def setUp(self):
        # Single local node
        self.node, _ = Node.objects.get_or_create(
            is_local=True, defaults={"host_url": "http://testserver"}
        )

        self.alice = User.objects.create_user(
            username="alice", password="alicepass", display_name="Alice", node=self.node
        )
        self.bob = User.objects.create_user(
            username="bob", password="bobpass", display_name="Bob", node=self.node
        )

        # mark test users as approved so IsApproved permission doesn't block follow APIs
        for u in (self.alice, self.bob):
            u.approved = True
            u.save(update_fields=["approved"])

        self.client = APIClient()

    # URL helpers
    def url_follow_request(self, followee):
        return reverse("authors:follow-request", args=[followee.id])

    def url_follow_requests_list(self):
        return reverse("authors:follow-requests")

    def url_follow_decision(self, follow_obj):
        return reverse("authors:follow-decision", kwargs={"pk": str(follow_obj.id)})

    # ---- create ----
    def test_unauthenticated_cannot_create_request(self):
        url = self.url_follow_request(self.alice)
        res = self.client.post(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cannot_follow_self(self):
        self.client.force_authenticate(self.alice)
        url = self.url_follow_request(self.alice)
        res = self.client.post(url)
        self.assertIn(res.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT))

    def test_create_follow_request_success(self):
        self.client.force_authenticate(self.bob)
        url = self.url_follow_request(self.alice)
        res = self.client.post(url, data={}, format="json")
        self.assertIn(res.status_code, (status.HTTP_201_CREATED, status.HTTP_200_OK))

        self.assertTrue(
            Follow.objects.filter(follower=self.bob, following=self.alice, approved=False).exists()
        )

    def test_create_follow_request_duplicate_rejected(self):
        self.client.force_authenticate(self.bob)
        url = self.url_follow_request(self.alice)

        r1 = self.client.post(url, data={}, format="json")
        self.assertIn(r1.status_code, (status.HTTP_201_CREATED, status.HTTP_200_OK))

        r2 = self.client.post(url, data={}, format="json")
        self.assertIn(r2.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT))

        self.assertEqual(
            Follow.objects.filter(follower=self.bob, following=self.alice).count(), 1
        )

    # ---- list pending ----
    def test_unauthenticated_cannot_list_pending(self):
        url = self.url_follow_requests_list()
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_pending_only_for_me_and_disappears_after_accept(self):
        pending = Follow.objects.create(
            follower=self.bob, following=self.alice, approved=False
        )

        self.client.force_authenticate(self.alice)
        url = self.url_follow_requests_list()
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids_before = {str(item.get("id")) for item in res.data}
        self.assertIn(str(pending.id), ids_before)

        # accept -> no longer in pending list
        url_dec = self.url_follow_decision(pending)
        r2 = self.client.post(url_dec, data={"decision": "accept"}, format="json")
        self.assertIn(r2.status_code, (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT))

        pending.refresh_from_db()
        self.assertTrue(pending.approved)

        res2 = self.client.get(self.url_follow_requests_list())
        ids_after = {str(item.get("id")) for item in res2.data}
        self.assertNotIn(str(pending.id), ids_after)

    # ---- decision ----
    def test_decision_requires_auth(self):
        f = Follow.objects.create(
            follower=self.bob, following=self.alice, approved=False
        )
        url = self.url_follow_decision(f)
        res = self.client.post(url, data={"decision": "accept"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_only_followee_can_accept(self):
        f = Follow.objects.create(
            follower=self.bob, following=self.alice, approved=False
        )
        url = self.url_follow_decision(f)

        self.client.force_authenticate(self.bob)  # follower tries
        r1 = self.client.post(url, data={"decision": "accept"}, format="json")
        self.assertIn(r1.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

        self.client.force_authenticate(self.alice)  # followee accepts
        r2 = self.client.post(url, data={"decision": "accept"}, format="json")
        self.assertIn(r2.status_code, (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT))
        f.refresh_from_db()
        self.assertTrue(f.approved)

    def test_deny_deletes_pending(self):
        f = Follow.objects.create(
            follower=self.bob, following=self.alice, approved=False
        )
        self.client.force_authenticate(self.alice)
        url = self.url_follow_decision(f)
        r = self.client.post(url, data={"decision": "deny"}, format="json")
        self.assertIn(r.status_code, (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT))
        self.assertFalse(Follow.objects.filter(id=f.id).exists())

class SignupApprovalTests(APITestCase):
    """
    US 8.3.1
    - Anyone can sign up, but account remains pending until admin approval.
    - Unapproved accounts cannot log in or use node functionality.
    - After approval, login succeeds and tokens are returned.
    """
    def setUp(self):
        # Local node (if Author requires node FK)
        self.node, _ = Node.objects.get_or_create(
            is_local=True, defaults={"host_url": "http://testserver"}
        )

    def test_signup_returns_pending_without_tokens(self):
        payload = {
            "username": "pending_user",
            "display_name": "Pending User",
            # include all common password field names to satisfy different serializers
            "password": "Aa123456!",
            "password2": "Aa123456!",
            # if your Author requires node via serializer, include it as id
            "node": self.node.id,
        }
        url = "/api/authors/register/"
        res = self.client.post(url, data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data.get("status"), "pending")
        # no tokens should be issued on signup
        self.assertNotIn("access", res.data)
        self.assertNotIn("refresh", res.data)

    def test_login_before_approval_is_403(self):
        # create user programmatically; approved defaults to False
        u = User.objects.create_user(
            username="u1", password="Aa123456!", node=self.node
        )
        self.assertFalse(getattr(u, "approved", False))
        res = self.client.post(
            "/api/authors/login/",
            data={"username": "u1", "password": "Aa123456!"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        body = res.json() if hasattr(res, "json") else {}
        self.assertIn("pending", str(body.get("error", "")).lower())

    def test_login_after_approval_returns_tokens(self):
        u = User.objects.create_user(username="u2", password="temp12345", node=self.node)

        u.set_password("Aa123456!")
        u.is_active = True
        u.approved = True
        u.save(update_fields=["password", "is_active", "approved"])

        res = self.client.post(
            "/api/authors/login/",
            data=json.dumps({"username": "u2", "password": "Aa123456!"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.json() if hasattr(res, "json") else {}
        self.assertIn("access", body)
        self.assertIn("refresh", body)

    def test_unapproved_user_blocked_on_follow_api(self):
        # follower is unapproved; followee is approved
        follower = User.objects.create_user(
            username="follower_x", password="Aa123456!", node=self.node
        )
        followee = User.objects.create_user(
            username="followee_x", password="Aa123456!", node=self.node
        )
        followee.approved = True
        followee.save(update_fields=["approved"])

        # force_authenticate bypasses login but preserves request.user
        # IsApproved should still block because follower.approved == False
        self.client.force_authenticate(follower)
        url = reverse("authors:follow-request", args=[followee.id])
        res = self.client.post(url, data={}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
