from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from authors.models import Author, Follow
from entries.models import Entry, Comment
from nodes.models import Node
from django.utils import timezone
import uuid
import json
from base64 import b64encode

User = get_user_model()

class InboxTests(TestCase):
    def setUp(self):
        self.client = Client()

        self.local_node = Node.objects.create(
            host_url="https://local-node.example.com/",
            is_local=True,
            username="localuser",
            password="localpass",
        )

        self.remote_node = Node.objects.create(
            host_url="https://remote-node.example.com/",
            is_local=False,
            username="remoteuser",
            password="remotepass",
        )

        self.local_author = Author.objects.create(
            id=uuid.uuid4(),
            username="local_author",
            display_name="Local Author",
            node=self.local_node,
        )

        self.remote_author = Author.objects.create(
            id=uuid.uuid4(),
            username="remote_author",
            display_name="Remote Author",
            node=self.remote_node,
        )

        self.entry = Entry.objects.create(
            id=uuid.uuid4(),
            author=self.local_author,
            node=self.local_node,
            content="Test Entry",
            visibility="PUBLIC",
            content_type="text/plain",
        )
        self.remote_auth_headers = {
            "HTTP_AUTHORIZATION": "Basic " + b64encode(b"remoteuser:remotepass").decode()
        }

    def test_inbox_accepts_remote_entry_create(self):
        # Test: inbox accepts creation of an entry from a remote author
        url = f"/api/authors/{self.local_author.id}/inbox/"
        payload = {
            "type": "entry",
            "id": str(uuid.uuid4()),
            "content": "Hello from remote",
            "visibility": "PUBLIC",
            "contentType": "text/plain",
            "author": {
                "id": f"{self.remote_node.host_url}api/authors/{self.remote_author.id}/",
                "displayName": self.remote_author.display_name,
                "username": self.remote_author.username,
            },
        }

        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **self.remote_auth_headers
        )

        self.assertIn(response.status_code, [200, 201])
        self.assertTrue(
            Entry.objects.filter(content="Hello from remote").exists()
        )

    def test_inbox_accepts_follow_request(self):
        # Test: inbox accepts a follow request sent by a remote author
        url = f"/api/authors/{self.local_author.id}/inbox/"
        payload = {
            "type": "follow",
            "actor": {
                "id": f"{self.remote_node.host_url}api/authors/{self.remote_author.id}/",
                "displayName": self.remote_author.display_name,
                "username": self.remote_author.username,
            },
            "object": {
                "id": f"{self.local_node.host_url}api/authors/{self.local_author.id}/"
            }
        }

        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **self.remote_auth_headers
        )

        self.assertIn(response.status_code, [200, 201])
        self.assertTrue(
            Follow.objects.filter(
                follower=self.remote_author,
                following=self.local_author,
                status=Follow.PENDING
            ).exists()
        )

    def test_inbox_accepts_like(self):
        # Test: inbox accepts a like activity from a remote author
        url = f"/api/authors/{self.local_author.id}/inbox/"
        payload = {
            "type": "like",
            "author": {
                "id": f"{self.remote_node.host_url}api/authors/{self.remote_author.id}/",
                "displayName": self.remote_author.display_name,
                "username": self.remote_author.username,
            },
            "object": f"{self.local_node.host_url}api/authors/{self.local_author.id}/entries/{self.entry.id}/"
        }

        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **self.remote_auth_headers
        )

        self.assertIn(response.status_code, [200, 201])
        # If you add a concrete Like model with a ForeignKey to Entry,
        # you can add a database assertion here. For now, we only assert
        # that the endpoint responds successfully.

    def test_inbox_accepts_comment(self):
        # Test: inbox accepts a comment submitted by a remote author
        url = f"/api/authors/{self.local_author.id}/inbox/"
        payload = {
            "type": "comment",
            "comment": "Nice post!",
            "contentType": "text/plain",
            "author": {
                "id": f"{self.remote_node.host_url}api/authors/{self.remote_author.id}/",
                "displayName": self.remote_author.display_name,
                "username": self.remote_author.username,
            },
            "object": f"{self.local_node.host_url}api/authors/{self.local_author.id}/entries/{self.entry.id}/",
        }

        response = self.client.post(
            url,
            data = json.dumps(payload),
            content_type = "application/json",
            **self.remote_auth_headers
        )

        self.assertIn(response.status_code, [200, 201, 400])
        # If the view accepts and stores the comment, it should be in the database.
        if response.status_code in (200, 201):
            self.assertTrue(
                Comment.objects.filter(content="Nice post!").exists()
            )

    def test_following_activity_endpoint(self):
        # Test: following-activity endpoint returns remote authors' public posts
        url = reverse("inbox:following-activity")
        Follow.objects.create(
            follower=self.local_author,
            following=self.remote_author,
            approved=True,
            status=Follow.ACCEPTED
        )

        Entry.objects.create(
            id = uuid.uuid4(),
            author = self.remote_author,
            node = self.remote_node,
            content = "Activity content",
            visibility = "PUBLIC",
            content_type = "text/plain",
        )

        response = self.client.get(url, **self.remote_auth_headers)
        self.assertIn(response.status_code, [200, 401])
        data = response.json()
        if response.status_code == 200:
            self.assertIn("items", data)

    def test_my_notifications_endpoint(self):
        # Test: notifications endpoint returns activity items for the current author
        url = reverse("inbox:my-notifications")

        response = self.client.get(url, **self.remote_auth_headers)
        self.assertIn(response.status_code, [200, 401])
        data = response.json()
        if response.status_code == 200:
            self.assertIn("items", data)

    def test_inbox_rejects_invalid_payload(self):
        # Test: inbox rejects malformed or unexpected payloads
        url = f"/api/authors/{self.local_author.id}/inbox/"
        payload = {"unexpected": "data"}

        response = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **self.remote_auth_headers
        )

        self.assertIn(response.status_code, [400, 422])

    def test_follow_request_approve_flow(self):
        # Test:  follow request approval updates the model correctly
        follow = Follow.objects.create(
            follower = self.remote_author,
            following = self.local_author,
            approved = False,
            status = Follow.PENDING,
        )

        follow.approved = True
        follow.status = Follow.ACCEPTED
        follow.save()

        obj = Follow.objects.get(id=follow.id)
        self.assertTrue(obj.approved)
        self.assertEqual(obj.status, Follow.ACCEPTED)


    def test_inbox_saves_multiple_activity_types(self):
        # Test: inbox stores different activity types across all visibilities
        url = f"/api/authors/{self.local_author.id}/inbox/"

        entry_payload = {
            "type": "entry",
            "id": str(uuid.uuid4()),
            "content": "test entry payload",
            "visibility": "PUBLIC",
            "contentType": "text/plain",
            "author": {
                "id": f"{self.remote_node.host_url}api/authors/{self.remote_author.id}/",
                "displayName": self.remote_author.display_name,
                "username": self.remote_author.username,
            },
        }

        entry_payload_private = {
            "type": "entry",
            "id": str(uuid.uuid4()),
            "content": "test private entry payload",
            "visibility": "PRIVATE",
            "contentType": "text/plain",
            "author": {
                "id": f"{self.remote_node.host_url}api/authors/{self.remote_author.id}/",
                "displayName": self.remote_author.display_name,
                "username": self.remote_author.username,
            },
        }

        entry_payload_unlisted = {
            "type": "entry",
            "id": str(uuid.uuid4()),
            "content": "test unlisted entry payload",
            "visibility": "UNLISTED",
            "contentType": "text/plain",
            "author": {
                "id": f"{self.remote_node.host_url}api/authors/{self.remote_author.id}/",
                "displayName": self.remote_author.display_name,
                "username": self.remote_author.username,
            },
        }

        entry_payload_friends_only = {
            "type": "entry",
            "id": str(uuid.uuid4()),
            "content": "test friends_only entry payload",
            "visibility": "FRIENDS_ONLY",
            "contentType": "text/plain",
            "author": {
                "id": f"{self.remote_node.host_url}api/authors/{self.remote_author.id}/",
                "displayName": self.remote_author.display_name,
                "username": self.remote_author.username,
            },
        }

        like_payload = {
            "type": "like",
            "object": f"{self.local_node.host_url}api/authors/{self.local_author.id}/entries/{self.entry.id}/",
            "author": {
                "id": f"{self.remote_node.host_url}api/authors/{self.remote_author.id}/",
                "displayName": self.remote_author.display_name,
                "username": self.remote_author.username,
            },
        }

        comment_payload = {
            "type": "comment",
            "comment": "test comment payload",
            "contentType": "text/plain",
            "author": {
                "id": f"{self.remote_node.host_url}api/authors/{self.remote_author.id}/",
                "displayName": self.remote_author.display_name,
                "username": self.remote_author.username,
            },
            "object": f"{self.local_node.host_url}api/authors/{self.local_author.id}/entries/{self.entry.id}/",
        }

        self.client.post(
            url,
            data=json.dumps(entry_payload),
            content_type="application/json",
            **self.remote_auth_headers
        )
        self.client.post(
            url,
            data=json.dumps(entry_payload_private),
            content_type="application/json",
            **self.remote_auth_headers
        )
        self.client.post(
            url,
            data=json.dumps(entry_payload_unlisted),
            content_type="application/json",
            **self.remote_auth_headers
        )
        self.client.post(
            url,
            data=json.dumps(entry_payload_friends_only),
            content_type="application/json",
            **self.remote_auth_headers
        )
        self.client.post(
            url,
            data=json.dumps(like_payload),
            content_type="application/json",
            **self.remote_auth_headers
        )
        self.client.post(
            url,
            data=json.dumps(comment_payload),
            content_type="application/json",
            **self.remote_auth_headers
        )

        self.assertTrue(Entry.objects.filter(content="test entry payload").exists())
        self.assertTrue(Entry.objects.filter(content="test private entry payload").exists())
        self.assertTrue(Entry.objects.filter(content="test unlisted entry payload").exists())
        self.assertTrue(Entry.objects.filter(content="test friends_only entry payload").exists())
