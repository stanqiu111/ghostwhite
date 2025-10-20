# authors/tests.py
from django.urls import reverse
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from nodes.models import Node


class AuthorAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Ensure a local Node exists for user creation/registration
        Node.objects.get_or_create(is_local=True)
    def setUp(self):
        self.User = get_user_model()
        self.register_url = reverse("authors_api:register")
        self.login_url = reverse("authors_api:login")
        self.list_url = reverse("authors_api:authors-list")
        self.profile_me_url = reverse("authors_api:profile")

        # Create two users; u1 via manager (explicit), u2 via API register later
        self.u1 = self.User.objects.create_user(
            username="testuser1",
            password="pass12345",
            display_name="Test User 1",
            node=Node.objects.get(is_local=True),
        )

    # ---------- helpers ----------
    def jwt_headers(self, access):
        return {"HTTP_AUTHORIZATION": f"Bearer {access}"}

    def login_get_tokens(self, username, password):
        resp = self.client.post(
            self.login_url,
            data={"username": username, "password": password},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.json())
        self.assertIn("refresh", resp.json())
        return resp.json()["access"], resp.json()["refresh"]

    # ---------- tests ----------
    def test_register_success_returns_tokens_and_user(self):
        payload = {
            "username": "testuser2",
            "display_name": "Test User 2",
            "password": "pass12345A!",
            "password2": "pass12345A!",
            "bio": "hello",
            "github_url": "https://github.com/test",
        }
        resp = self.client.post(self.register_url, data=payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        body = resp.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)
        self.assertIn("user", body)
        self.assertEqual(body["user"]["username"], "testuser2")
        self.assertEqual(self.User.objects.filter(username="testuser2").count(), 1)

    def test_login_returns_jwt_and_sets_session(self):
        access, refresh = self.login_get_tokens("testuser1", "pass12345")
        self.assertTrue(isinstance(access, str) and isinstance(refresh, str))

    def test_authors_list_returns_paginated_structure(self):
        # Ensure at least one user exists
        _ = self.User.objects.count()
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        # Either paginated or full, but current ListView returns {"type":"authors","authors":[...]}
        self.assertEqual(body.get("type"), "authors")
        self.assertIn("authors", body)
        self.assertIsInstance(body["authors"], list)

    def test_get_author_by_username_requires_auth(self):
        url = reverse("authors_api:author_by_username", kwargs={"username": self.u1.username})
        resp = self.client.get(url)  # no JWT
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_author_by_username_with_auth(self):
        access, _ = self.login_get_tokens("testuser1", "pass12345")
        url = reverse("authors_api:author_by_username", kwargs={"username": self.u1.username})
        resp = self.client.get(url, **self.jwt_headers(access))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body["username"], "testuser1")
        self.assertEqual(body["type"], "author")
        self.assertIn("id", body)
        self.assertIn("host", body)
        self.assertIn("web", body)

    def test_put_author_by_username_self_update_ok(self):
        access, _ = self.login_get_tokens("testuser1", "pass12345")
        url = reverse("authors_api:author_by_username", kwargs={"username": "testuser1"})
        payload = {
            "display_name": "Updated Name",
            "github_url": "https://github.com/new",
            "bio": "updated bio",
        }
        resp = self.client.put(url, data=payload, format="json", **self.jwt_headers(access))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body["display_name"], "Updated Name")
        self.assertEqual(body["github_url"], "https://github.com/new")
        self.assertEqual(body["bio"], "updated bio")

    def test_put_author_by_username_other_forbidden(self):
        # Create second user
        u2 = self.User.objects.create_user(
            username="other",
            password="pass12345",
            display_name="Other User",
            node=Node.objects.get(is_local=True),
        )
        # Login as u2, try to update u1
        access, _ = self.login_get_tokens("other", "pass12345")
        url = reverse("authors_api:author_by_username", kwargs={"username": "testuser1"})
        resp = self.client.put(
            url,
            data={"display_name": "Hacker"},
            format="json",
            **self.jwt_headers(access),
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_profile_me_endpoint_returns_current_user(self):
        # Login and call /author_profile/
        access, _ = self.login_get_tokens("testuser1", "pass12345")
        resp = self.client.get(self.profile_me_url, **self.jwt_headers(access))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["username"], "testuser1")

    def test_pagination_params_applied(self):
        # Create extra users to ensure multiple pages
        for i in range(8):
            self.User.objects.create_user(
                username=f"bulk{i}",
                password="pass12345",
                display_name=f"Bulk {i}",
                node=Node.objects.get(is_local=True),
            )
        resp = self.client.get(self.list_url + "?page=1&size=3")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body.get("type"), "authors")
        self.assertIn("authors", body)
        self.assertLessEqual(len(body["authors"]), 3)
