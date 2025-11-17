import json
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from authors.github import sync_github_events
from authors.models import Author, Follow
from entries.models import Entry
from nodes.models import Node

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


class SignupExtraApprovalTests(APITestCase):
    """
    Additional non-intrusive tests for US 8.3.1.
    These complement existing SignupApprovalTests without replacing them.
    """

    def setUp(self):
        # Ensure a local node exists if Author requires node FK.
        self.node, _ = Node.objects.get_or_create(
            is_local=True, defaults={"host_url": "http://testserver"}
        )

    def test_signup_creates_pending_author_row(self):
        payload = {
            "username": "pending_user_extra",
            "display_name": "Pending User Extra",
            "password": "Aa123456!",
            "password2": "Aa123456!",
            "node": self.node.id,
        }
        url = "/api/authors/register/"
        res = self.client.post(url, data=payload, format="json")
        self.assertIn(res.status_code, (status.HTTP_201_CREATED, status.HTTP_200_OK))
        # status should be "pending" and no tokens
        self.assertEqual(res.data.get("status"), "pending")
        self.assertNotIn("access", res.data)
        self.assertNotIn("refresh", res.data)
        # row exists and is unapproved
        u = User.objects.get(username="pending_user_extra")
        self.assertFalse(getattr(u, "approved", False))

    def test_login_rejects_unapproved_403(self):
        u = User.objects.create_user(
            username="u_pending_extra", password="Aa123456!", node=self.node
        )
        self.assertFalse(getattr(u, "approved", False))

        res = self.client.post(
            "/api/authors/login/",
            data={"username": "u_pending_extra", "password": "Aa123456!"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        # body mentions pending
        try:
            body = res.json()
        except Exception:
            body = {}
        self.assertIn("pending", str(body.get("error", "")).lower())

    def test_login_approved_returns_tokens_json_format(self):
        u = User.objects.create_user(username="u_ok_extra", password="temp", node=self.node)
        u.set_password("Aa123456!")
        u.is_active = True
        u.approved = True
        u.save(update_fields=["password", "is_active", "approved"])

        res = self.client.post(
            "/api/authors/login/",
            data={"username": "u_ok_extra", "password": "Aa123456!"},
            format="json",  # avoid DRF Invalid format issue seen earlier
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = res.json() if hasattr(res, "json") else {}
        self.assertIn("access", body)
        self.assertIn("refresh", body)

    def test_unapproved_blocked_on_follow_api(self):
        follower = User.objects.create_user(
            username="follower_extra", password="Aa123456!", node=self.node
        )
        followee = User.objects.create_user(
            username="followee_extra", password="Aa123456!", node=self.node
        )
        followee.approved = True
        followee.save(update_fields=["approved"])

        # simulate auth without granting approval
        self.client.force_authenticate(follower)
        url = reverse("authors:follow-request", args=[followee.id])
        res = self.client.post(url, data={}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class UnfollowAPITests(APITestCase):
    """
    Tests for unfollow functionality.

    User Story 1: As an author, I want to unfollow authors I am following,
                  so that I don't have to see their entries anymore.

    User Story 2: As an author, I want to unfriend other authors by unfollowing them,
                  so that they can no longer see my friends-only entries.

    Endpoint: DELETE /api/authors/<author_id>/follow/
    """

    def setUp(self):
        # Create local node
        self.node, _ = Node.objects.get_or_create(
            is_local=True, defaults={"host_url": "http://testserver"}
        )

        # Create test users
        self.alice = User.objects.create_user(
            username="alice", password="alicepass", display_name="Alice", node=self.node
        )
        self.bob = User.objects.create_user(
            username="bob", password="bobpass", display_name="Bob", node=self.node
        )
        self.charlie = User.objects.create_user(
            username="charlie", password="charliepass", display_name="Charlie", node=self.node
        )

        # Mark all users as approved
        for u in (self.alice, self.bob, self.charlie):
            u.approved = True
            u.save(update_fields=["approved"])

        self.client = APIClient()

    def url_unfollow(self, followee):
        """Helper to get the unfollow URL"""
        return reverse("authors:follow-request", args=[followee.id])

    # ---- Basic unfollow tests ----

    def test_unfollow_requires_authentication(self):
        """Unauthenticated users cannot unfollow"""
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cannot_unfollow_self(self):
        """Users cannot unfollow themselves"""
        self.client.force_authenticate(self.alice)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot unfollow yourself", res.data.get("detail", "").lower())

    def test_unfollow_pending_request_success(self):
        """User can cancel/unfollow a pending follow request"""
        # Bob sends a follow request to Alice (pending)
        Follow.objects.create(follower=self.bob, following=self.alice, approved=False, status=Follow.PENDING)

        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        # Verify the follow relationship is deleted
        self.assertFalse(Follow.objects.filter(follower=self.bob, following=self.alice).exists())

    def test_unfollow_accepted_relationship_success(self):
        """User can unfollow an accepted follow relationship"""
        # Bob follows Alice (accepted)
        Follow.objects.create(follower=self.bob, following=self.alice, approved=True, status=Follow.ACCEPTED)

        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        # Verify the follow relationship is deleted
        self.assertFalse(Follow.objects.filter(follower=self.bob, following=self.alice).exists())

    def test_unfollow_non_existent_relationship_returns_404(self):
        """Attempting to unfollow when no relationship exists returns 404"""
        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("no follow relationship found", res.data.get("detail", "").lower())

    # ---- Unfollowing tests (User Story 1) ----

    def test_unfollow_removes_from_following_list(self):
        """After unfollowing, the user should no longer be in the follower's following list"""
        # Bob follows Alice (accepted)
        Follow.objects.create(follower=self.bob, following=self.alice, approved=True, status=Follow.ACCEPTED)

        # Verify Bob is following Alice
        self.assertTrue(Follow.objects.filter(follower=self.bob, following=self.alice, approved=True).exists())

        # Bob unfollows Alice
        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        # Verify Bob is no longer following Alice
        self.assertFalse(Follow.objects.filter(follower=self.bob, following=self.alice).exists())

    def test_unfollow_does_not_affect_other_relationships(self):
        """Unfollowing one author doesn't affect relationships with other authors"""
        # Bob follows both Alice and Charlie
        Follow.objects.create(follower=self.bob, following=self.alice, approved=True, status=Follow.ACCEPTED)
        Follow.objects.create(follower=self.bob, following=self.charlie, approved=True, status=Follow.ACCEPTED)

        # Bob unfollows Alice
        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        # Verify Bob is no longer following Alice
        self.assertFalse(Follow.objects.filter(follower=self.bob, following=self.alice).exists())
        # Verify Bob still follows Charlie
        self.assertTrue(Follow.objects.filter(follower=self.bob, following=self.charlie, approved=True).exists())

    def test_unfollow_does_not_affect_reverse_relationship(self):
        """Unfollowing doesn't affect if the other person follows you"""
        # Bob follows Alice
        Follow.objects.create(follower=self.bob, following=self.alice, approved=True, status=Follow.ACCEPTED)
        # Alice follows Bob
        Follow.objects.create(follower=self.alice, following=self.bob, approved=True, status=Follow.ACCEPTED)

        # Bob unfollows Alice
        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        # Verify Bob is no longer following Alice
        self.assertFalse(Follow.objects.filter(follower=self.bob, following=self.alice).exists())
        # Verify Alice still follows Bob
        self.assertTrue(Follow.objects.filter(follower=self.alice, following=self.bob, approved=True).exists())

    # ---- Unfriending tests (User Story 2) ----

    def test_unfriend_by_unfollowing_breaks_friendship(self):
        """Unfollowing a friend breaks the mutual friendship"""
        # Create mutual follow relationship (friends)
        Follow.objects.create(follower=self.bob, following=self.alice, approved=True, status=Follow.ACCEPTED)
        Follow.objects.create(follower=self.alice, following=self.bob, approved=True, status=Follow.ACCEPTED)

        # Verify they are friends (mutual followers)
        alice_friends = Follow.get_friends(self.alice)
        bob_friends = Follow.get_friends(self.bob)
        self.assertIn(self.bob, alice_friends)
        self.assertIn(self.alice, bob_friends)

        # Bob unfollows Alice
        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        # Verify they are no longer friends
        alice_friends = Follow.get_friends(self.alice)
        bob_friends = Follow.get_friends(self.bob)
        self.assertNotIn(self.bob, alice_friends)
        self.assertNotIn(self.alice, bob_friends)

    def test_unfriend_removes_from_both_friends_lists(self):
        """When unfollowing a friend, both users lose each other from friends list"""
        # Create mutual follow relationship (friends)
        Follow.objects.create(follower=self.bob, following=self.alice, approved=True, status=Follow.ACCEPTED)
        Follow.objects.create(follower=self.alice, following=self.bob, approved=True, status=Follow.ACCEPTED)

        # Get initial friend counts
        alice_friends_before = Follow.get_friends(self.alice)
        bob_friends_before = Follow.get_friends(self.bob)
        self.assertEqual(alice_friends_before.count(), 1)
        self.assertEqual(bob_friends_before.count(), 1)

        # Bob unfollows Alice
        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        # Get friend counts after unfollowing
        alice_friends_after = Follow.get_friends(self.alice)
        bob_friends_after = Follow.get_friends(self.bob)
        self.assertEqual(alice_friends_after.count(), 0)
        self.assertEqual(bob_friends_after.count(), 0)

    def test_unfriend_preserves_one_way_follow(self):
        """After unfollowing a friend, the reverse follow relationship persists"""
        # Create mutual follow relationship (friends)
        Follow.objects.create(follower=self.bob, following=self.alice, approved=True, status=Follow.ACCEPTED)
        Follow.objects.create(follower=self.alice, following=self.bob, approved=True, status=Follow.ACCEPTED)

        # Bob unfollows Alice
        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        # Verify Bob no longer follows Alice
        self.assertFalse(Follow.objects.filter(follower=self.bob, following=self.alice).exists())
        # Verify Alice still follows Bob (one-way relationship)
        self.assertTrue(Follow.objects.filter(follower=self.alice, following=self.bob, approved=True).exists())

    def test_multiple_unfriends_with_third_party(self):
        """Unfriending one friend doesn't affect friendships with other friends"""
        # Create a triangle: Alice-Bob, Bob-Charlie, Alice-Charlie (all mutual)
        # Alice <-> Bob
        Follow.objects.create(follower=self.alice, following=self.bob, approved=True, status=Follow.ACCEPTED)
        Follow.objects.create(follower=self.bob, following=self.alice, approved=True, status=Follow.ACCEPTED)
        # Bob <-> Charlie
        Follow.objects.create(follower=self.bob, following=self.charlie, approved=True, status=Follow.ACCEPTED)
        Follow.objects.create(follower=self.charlie, following=self.bob, approved=True, status=Follow.ACCEPTED)

        # Verify Bob is friends with both Alice and Charlie
        bob_friends = Follow.get_friends(self.bob)
        self.assertEqual(bob_friends.count(), 2)
        self.assertIn(self.alice, bob_friends)
        self.assertIn(self.charlie, bob_friends)

        # Bob unfollows Alice
        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

        # Verify Bob is no longer friends with Alice
        bob_friends = Follow.get_friends(self.bob)
        self.assertNotIn(self.alice, bob_friends)
        # Verify Bob is still friends with Charlie
        self.assertIn(self.charlie, bob_friends)

    # ---- Edge cases ----

    def test_unfollow_denied_request(self):
        """User can unfollow/delete a denied follow request"""
        # Bob's request to follow Alice was denied
        Follow.objects.create(follower=self.bob, following=self.alice, approved=False, status=Follow.DENIED)

        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        # Verify the follow relationship is deleted
        self.assertFalse(Follow.objects.filter(follower=self.bob, following=self.alice).exists())

    def test_cannot_unfollow_as_different_user(self):
        """Users can only unfollow relationships where they are the follower"""
        # Bob follows Alice
        Follow.objects.create(follower=self.bob, following=self.alice, approved=True, status=Follow.ACCEPTED)

        # Charlie tries to unfollow Alice (but Charlie doesn't follow Alice)
        self.client.force_authenticate(self.charlie)
        url = self.url_unfollow(self.alice)
        res = self.client.delete(url)

        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        # Verify Bob's follow relationship still exists
        self.assertTrue(Follow.objects.filter(follower=self.bob, following=self.alice, approved=True).exists())

    def test_unfollow_idempotency(self):
        """Attempting to unfollow twice returns 404 on second attempt"""
        # Bob follows Alice
        Follow.objects.create(follower=self.bob, following=self.alice, approved=True, status=Follow.ACCEPTED)

        self.client.force_authenticate(self.bob)
        url = self.url_unfollow(self.alice)

        # First unfollow succeeds
        res1 = self.client.delete(url)
        self.assertEqual(res1.status_code, status.HTTP_204_NO_CONTENT)

        # Second unfollow returns 404
        res2 = self.client.delete(url)
        self.assertEqual(res2.status_code, status.HTTP_404_NOT_FOUND)




class SyncGitHubEventsTests(TestCase):
    def setUp(self):
        self.node, _ = Node.objects.get_or_create(
            is_local=True, defaults={"host_url": "http://test.example/"}
        )
        self.author = Author.objects.create_user(
            username="octocat",
            password="password",
            display_name="Mona",
            approved=True,
            is_active=True,
            node=self.node,
        )

    def _mock_response(self, payload):
        response = Mock()
        response.status_code = 200
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        return response

    @patch("authors.github.requests.get")
    def test_creates_entries_from_push_event(self, mock_get):
        event = {
            "id": "evt123",
            "type": "PushEvent",
            "repo": {"name": "octocat/Hello-World"},
            "actor": {"login": "octocat"},
            "created_at": "2024-11-15T00:00:00Z",
            "payload": {
                "commits": [
                    {"sha": "abcdef1", "message": "First"},
                    {"sha": "abcdef2", "message": "Second"},
                ]
            },
        }
        mock_get.return_value = self._mock_response([event])

        result = sync_github_events(self.author, "octocat")

        self.assertEqual(result["created"], 1)
        entry = Entry.objects.get(source_id="evt123")
        self.assertIn("pushed 2 commits", entry.content)
        self.assertEqual(entry.author, self.author)

    @patch("authors.github.requests.get")
    def test_skips_existing_event_ids(self, mock_get):
        Entry.objects.create(
            author=self.author,
            content="already there",
            content_type="markdown",
            visibility="public",
            node=self.author.node,
            source="github",
            source_id="evt-existing",
        )
        event = {
            "id": "evt-existing",
            "type": "WatchEvent",
            "repo": {"name": "octocat/Hello-World"},
            "actor": {"login": "octocat"},
            "created_at": "2024-11-15T00:00:00Z",
            "payload": {},
        }
        mock_get.return_value = self._mock_response([event])

        result = sync_github_events(self.author, "octocat")

        self.assertEqual(result["created"], 0)
        self.assertEqual(Entry.objects.filter(source_id="evt-existing").count(), 1)

    @patch("authors.github.requests.get")
    def test_handles_request_errors(self, mock_get):
        mock_get.side_effect = requests.exceptions.RequestException("Failed to fetch events")

        result = sync_github_events(self.author, "octocat")

        self.assertTrue(result["errors"])
        self.assertEqual(result["created"], 0)

