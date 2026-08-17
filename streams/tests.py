# streams/tests.py
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from authors.models import Author as User
from nodes.models import Node
from streams.models import Stream, StreamBulletMessage, StreamSignal


class StreamTestBase(TestCase):
    def setUp(self):
        # Local node required for FK on Author and Stream
        self.node, _ = Node.objects.get_or_create(
            is_local=True, defaults={"host_url": "http://testserver"}
        )
        # is_active=True required for session logins (ModelBackend drops inactive users)
        self.streamer = User.objects.create_user(
            username="alice", password="pass1234", node=self.node,
            display_name="alice", is_active=True, approved=True,
        )
        self.viewer = User.objects.create_user(
            username="bob", password="pass5678", node=self.node,
            display_name="bob", is_active=True, approved=True,
        )
        self.client = APIClient()

    def make_stream(self, owner=None, **kwargs):
        return Stream.objects.create(
            owner=owner or self.streamer,
            node=self.node,
            title=kwargs.pop("title", "Test stream"),
            **kwargs,
        )


# ---------------- MODEL (Foundational) ----------------

class StreamModelTests(StreamTestBase):
    def test_fqid_pk_generated_on_save(self):
        stream = self.make_stream()
        self.assertIn("/streams/", stream.id)
        self.assertIn("/api/authors/", stream.id)

    def test_serial_extracts_uuid_from_fqid(self):
        stream = self.make_stream()
        serial = stream.serial
        self.assertNotIn("/", serial)
        self.assertTrue(stream.id.endswith(f"/streams/{serial}"))

    def test_new_stream_is_live(self):
        stream = self.make_stream()
        self.assertEqual(stream.status, "live")
        self.assertTrue(stream.is_live)
        self.assertIsNotNone(stream.started_at)
        self.assertIsNone(stream.ended_at)

    def test_end_sets_status_and_ended_at(self):
        stream = self.make_stream()
        stream.end()
        stream.refresh_from_db()
        self.assertEqual(stream.status, "ended")
        self.assertIsNotNone(stream.ended_at)

    def test_end_is_idempotent(self):
        stream = self.make_stream()
        stream.end()
        first_ended_at = stream.ended_at
        stream.end()
        stream.refresh_from_db()
        self.assertEqual(stream.ended_at, first_ended_at)

    def test_db_blocks_second_live_stream_per_owner(self):
        self.make_stream()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_stream(title="Second live")

    def test_ended_stream_allows_new_live_stream(self):
        self.make_stream().end()
        second = self.make_stream(title="Back online")
        self.assertTrue(second.is_live)

    def test_get_absolute_url(self):
        stream = self.make_stream()
        self.assertEqual(stream.get_absolute_url(), f"/streams/{stream.serial}/")


# ---------------- US1: Start a stream ----------------

class StreamCreateTests(StreamTestBase):
    url = "/api/streams/"

    def test_create_stream_success(self):
        self.client.force_authenticate(self.streamer)
        res = self.client.post(
            self.url, {"title": "Friday night coding", "description": "hi"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data["type"], "stream")
        self.assertEqual(data["status"], "live")
        self.assertEqual(data["title"], "Friday night coding")
        self.assertIn("/streams/", data["id"])
        self.assertEqual(data["owner"]["displayName"], "alice")
        self.assertTrue(data["webUrl"].endswith(f"/streams/{data['serial']}/"))

    def test_create_stream_blank_title_rejected(self):
        self.client.force_authenticate(self.streamer)
        res = self.client.post(self.url, {"title": "   "}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Stream.objects.count(), 0)

    def test_create_second_live_stream_rejected(self):
        self.make_stream()
        self.client.force_authenticate(self.streamer)
        res = self.client.post(self.url, {"title": "Another"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already have a live stream", str(res.json()))
        self.assertEqual(Stream.objects.count(), 1)

    def test_create_stream_unauthenticated_rejected(self):
        res = self.client.post(self.url, {"title": "Nope"}, format="json")
        self.assertIn(
            res.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
        self.assertEqual(Stream.objects.count(), 0)

    def test_create_stream_with_jwt(self):
        token = str(RefreshToken.for_user(self.streamer).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        res = self.client.post(self.url, {"title": "JWT stream"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_create_page_requires_login(self):
        res = self.client.get("/streams/create/")
        self.assertEqual(res.status_code, 302)
        self.assertIn("/authors/auth", res["Location"])

    def test_create_page_form_post_redirects_to_detail(self):
        self.client.force_login(self.streamer)
        res = self.client.post(
            "/streams/create/", {"title": "Form stream", "description": "d"}
        )
        stream = Stream.objects.get()
        self.assertRedirects(
            res, f"/streams/{stream.serial}/", fetch_redirect_response=False
        )

    def test_create_page_form_post_blank_title_rerenders_with_error(self):
        self.client.force_login(self.streamer)
        res = self.client.post("/streams/create/", {"title": ""})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Stream.objects.count(), 0)


# ---------------- US2: Discover and watch ----------------

class StreamListDetailTests(StreamTestBase):
    def test_list_returns_only_live_streams(self):
        live = self.make_stream(title="Live one")
        ended = self.make_stream(owner=self.viewer, title="Old one")
        ended.end()
        self.client.force_authenticate(self.viewer)
        res = self.client.get("/api/streams/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["type"], "streams")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["serial"], live.serial)

    def test_retrieve_live_and_ended_stream(self):
        stream = self.make_stream()
        self.client.force_authenticate(self.viewer)
        res = self.client.get(f"/api/streams/{stream.serial}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["status"], "live")

        stream.end()
        res = self.client.get(f"/api/streams/{stream.serial}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["status"], "ended")

    def test_retrieve_unknown_stream_404(self):
        self.client.force_authenticate(self.viewer)
        res = self.client.get("/api/streams/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_requires_auth(self):
        stream = self.make_stream()
        for url in ("/api/streams/", f"/api/streams/{stream.serial}/"):
            res = self.client.get(url)
            self.assertIn(
                res.status_code,
                (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
                url,
            )

    def test_pages_redirect_when_logged_out(self):
        stream = self.make_stream()
        for url in ("/streams/", f"/streams/{stream.serial}/"):
            res = self.client.get(url)
            self.assertEqual(res.status_code, 302, url)
            self.assertIn("/authors/auth", res["Location"])

    def test_pages_render_when_logged_in(self):
        stream = self.make_stream()
        self.client.force_login(self.viewer)

        res = self.client.get("/streams/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, stream.title)

        res = self.client.get(f"/streams/{stream.serial}/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, stream.title)
        self.assertContains(res, "stream-player-placeholder")

    def test_detail_page_unknown_stream_404(self):
        self.client.force_login(self.viewer)
        res = self.client.get("/streams/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(res.status_code, 404)

    def test_detail_page_placeholder_state_is_role_aware(self):
        """'Waiting for streamer' is viewer copy; the owner gets the idle/share state."""
        stream = self.make_stream()

        self.client.force_login(self.viewer)
        res = self.client.get(f"/streams/{stream.serial}/")
        self.assertContains(res, "Waiting for streamer")
        self.assertContains(res, 'data-player-state="waiting"')
        self.assertContains(res, "fullscreenBtn")  # viewer fullscreen control

        self.client.force_login(self.streamer)
        res = self.client.get(f"/streams/{stream.serial}/")
        self.assertNotContains(res, "Waiting for streamer")
        self.assertContains(res, 'data-player-state="idle"')
        self.assertContains(res, "Share screen")

    def test_ended_detail_page_placeholder_state_for_both_roles(self):
        stream = self.make_stream()
        stream.end()
        for user in (self.streamer, self.viewer):
            self.client.force_login(user)
            res = self.client.get(f"/streams/{stream.serial}/")
            self.assertContains(res, 'data-player-state="ended"')
            self.assertNotContains(res, "Waiting for streamer")


# ---------------- US3: End a stream (owner only) ----------------

class StreamEndTests(StreamTestBase):
    def end_url(self, stream):
        return f"/api/streams/{stream.serial}/end/"

    def test_owner_can_end_stream(self):
        stream = self.make_stream()
        self.client.force_authenticate(self.streamer)
        res = self.client.post(self.end_url(stream))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["status"], "ended")
        self.assertIsNotNone(data["endedAt"])

    def test_end_is_idempotent_over_api(self):
        stream = self.make_stream()
        self.client.force_authenticate(self.streamer)
        first = self.client.post(self.end_url(stream)).json()
        second = self.client.post(self.end_url(stream))
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.json()["endedAt"], first["endedAt"])

    def test_non_owner_cannot_end_stream(self):
        stream = self.make_stream()
        self.client.force_authenticate(self.viewer)
        res = self.client.post(self.end_url(stream))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        stream.refresh_from_db()
        self.assertEqual(stream.status, "live")

    def test_unauthenticated_cannot_end_stream(self):
        stream = self.make_stream()
        res = self.client.post(self.end_url(stream))
        self.assertIn(
            res.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
        stream.refresh_from_db()
        self.assertEqual(stream.status, "live")

    def test_end_unknown_stream_404(self):
        self.client.force_authenticate(self.streamer)
        res = self.client.post("/api/streams/00000000-0000-0000-0000-000000000000/end/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_ended_stream_leaves_active_list(self):
        stream = self.make_stream()
        self.client.force_authenticate(self.streamer)
        self.client.post(self.end_url(stream))
        res = self.client.get("/api/streams/")
        self.assertEqual(res.json()["items"], [])

    def test_detail_page_shows_end_button_only_to_owner(self):
        stream = self.make_stream()

        self.client.force_login(self.streamer)
        res = self.client.get(f"/streams/{stream.serial}/")
        self.assertContains(res, "endStreamBtn")

        self.client.force_login(self.viewer)
        res = self.client.get(f"/streams/{stream.serial}/")
        self.assertNotContains(res, "endStreamBtn")

    def test_ended_detail_page_shows_ended_state(self):
        stream = self.make_stream()
        stream.end()
        self.client.force_login(self.streamer)
        res = self.client.get(f"/streams/{stream.serial}/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Ended")
        self.assertNotContains(res, "endStreamBtn")


# ---------------- Signaling: permissions & scoping (Foundational) ----------------

class StreamSignalAPITests(StreamTestBase):
    def signals_url(self, stream):
        return f"/api/streams/{stream.serial}/signals/"

    def post_signal(self, stream, user, kind, direction, peer_id="peer-1", payload=None):
        self.client.force_authenticate(user)
        return self.client.post(
            self.signals_url(stream),
            {"kind": kind, "direction": direction, "peer_id": peer_id,
             "payload": payload if payload is not None else {}},
            format="json",
        )

    # ---- POST permissions (the anti-hijack core) ----

    def test_viewer_can_send_to_streamer_signals(self):
        stream = self.make_stream()
        for kind in ("join", "answer", "candidate", "bye"):
            res = self.post_signal(stream, self.viewer, kind, "to_streamer")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED, kind)

    def test_non_owner_cannot_send_to_viewer_signals(self):
        stream = self.make_stream()
        for kind in ("offer", "candidate", "bye"):
            res = self.post_signal(stream, self.viewer, kind, "to_viewer")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, kind)
        self.assertEqual(StreamSignal.objects.count(), 0)

    def test_owner_can_send_to_viewer_signals(self):
        stream = self.make_stream()
        for kind in ("offer", "candidate", "bye"):
            res = self.post_signal(
                stream, self.streamer, kind, "to_viewer", payload={"sdp": "x"}
            )
            self.assertEqual(res.status_code, status.HTTP_201_CREATED, kind)

    def test_kind_direction_mismatch_rejected(self):
        stream = self.make_stream()
        # offer must be to_viewer
        res = self.post_signal(stream, self.streamer, "offer", "to_streamer")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        # join/answer must be to_streamer
        for kind in ("join", "answer"):
            res = self.post_signal(stream, self.streamer, kind, "to_viewer")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, kind)

    def test_oversized_payload_rejected(self):
        stream = self.make_stream()
        res = self.post_signal(
            stream, self.viewer, "answer", "to_streamer", payload={"sdp": "x" * 40000}
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_kind_rejected(self):
        stream = self.make_stream()
        res = self.post_signal(stream, self.viewer, "hack", "to_streamer")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_rejected(self):
        stream = self.make_stream()
        res = self.client.post(
            self.signals_url(stream),
            {"kind": "join", "direction": "to_streamer", "peer_id": "p"},
            format="json",
        )
        self.assertIn(
            res.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )
        res = self.client.get(self.signals_url(stream), {"role": "viewer", "peer_id": "p"})
        self.assertIn(
            res.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_jwt_auth_works_for_signals(self):
        stream = self.make_stream()
        token = str(RefreshToken.for_user(self.viewer).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        res = self.client.post(
            self.signals_url(stream),
            {"kind": "join", "direction": "to_streamer", "peer_id": "p", "payload": {}},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    # ---- Stream liveness / existence ----

    def test_ended_stream_rejects_signals_with_410(self):
        stream = self.make_stream()
        stream.end()
        res = self.post_signal(stream, self.viewer, "join", "to_streamer")
        self.assertEqual(res.status_code, status.HTTP_410_GONE)
        self.client.force_authenticate(self.streamer)
        res = self.client.get(self.signals_url(stream), {"role": "streamer"})
        self.assertEqual(res.status_code, status.HTTP_410_GONE)

    def test_unknown_stream_404(self):
        self.client.force_authenticate(self.viewer)
        url = "/api/streams/00000000-0000-0000-0000-000000000000/signals/"
        res = self.client.post(
            url, {"kind": "join", "direction": "to_streamer", "peer_id": "p"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        res = self.client.get(url, {"role": "viewer", "peer_id": "p"})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # ---- Poll permissions & consumption ----

    def test_streamer_role_poll_requires_owner(self):
        stream = self.make_stream()
        self.client.force_authenticate(self.viewer)
        res = self.client.get(self.signals_url(stream), {"role": "streamer"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_poll_requires_valid_role_and_peer_id(self):
        stream = self.make_stream()
        self.client.force_authenticate(self.viewer)
        res = self.client.get(self.signals_url(stream))
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        res = self.client.get(self.signals_url(stream), {"role": "bogus"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        res = self.client.get(self.signals_url(stream), {"role": "viewer"})  # no peer_id
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_streamer_poll_consumes_signals(self):
        stream = self.make_stream()
        self.post_signal(stream, self.viewer, "join", "to_streamer", peer_id="p1")
        self.client.force_authenticate(self.streamer)
        res = self.client.get(self.signals_url(stream), {"role": "streamer"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["type"], "signals")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["kind"], "join")
        # consumed: second poll is empty
        res = self.client.get(self.signals_url(stream), {"role": "streamer"})
        self.assertEqual(res.json()["items"], [])

    def test_viewer_poll_scoped_to_peer_id(self):
        stream = self.make_stream()
        self.post_signal(stream, self.streamer, "offer", "to_viewer", peer_id="p1",
                         payload={"sdp": "for-p1"})
        self.post_signal(stream, self.streamer, "offer", "to_viewer", peer_id="p2",
                         payload={"sdp": "for-p2"})
        self.client.force_authenticate(self.viewer)
        res = self.client.get(self.signals_url(stream), {"role": "viewer", "peer_id": "p1"})
        items = res.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["payload"]["sdp"], "for-p1")
        # p2's offer untouched
        self.assertEqual(
            StreamSignal.objects.filter(peer_id="p2").count(), 1
        )

    def test_poll_returns_signals_oldest_first(self):
        """Handshake ordering guarantee: a poll batch is oldest-first, so a
        candidate posted after the offer is never delivered before it."""
        stream = self.make_stream()
        self.post_signal(stream, self.streamer, "offer", "to_viewer", peer_id="p1",
                         payload={"sdp": "o"})
        self.post_signal(stream, self.streamer, "candidate", "to_viewer", peer_id="p1",
                         payload={"candidate": "c1"})
        self.post_signal(stream, self.streamer, "candidate", "to_viewer", peer_id="p1",
                         payload={"candidate": "c2"})
        self.client.force_authenticate(self.viewer)
        res = self.client.get(self.signals_url(stream), {"role": "viewer", "peer_id": "p1"})
        self.assertEqual(
            [i["kind"] for i in res.json()["items"]],
            ["offer", "candidate", "candidate"],
        )

    def test_ending_stream_purges_signals(self):
        stream = self.make_stream()
        self.post_signal(stream, self.viewer, "join", "to_streamer")
        self.assertEqual(StreamSignal.objects.filter(stream=stream).count(), 1)
        self.client.force_authenticate(self.streamer)
        res = self.client.post(f"/api/streams/{stream.serial}/end/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamSignal.objects.filter(stream=stream).count(), 0)


# ---------------- US3: full relay lifecycle ----------------

class StreamSignalLifecycleTests(StreamTestBase):
    def signals_url(self, stream):
        return f"/api/streams/{stream.serial}/signals/"

    def test_full_handshake_relay(self):
        """Simulate the whole join→offer→answer relay through the API alone."""
        stream = self.make_stream()
        url = self.signals_url(stream)

        # 1. viewer joins
        self.client.force_authenticate(self.viewer)
        res = self.client.post(url, {"kind": "join", "direction": "to_streamer",
                                     "peer_id": "peer-A", "payload": {}}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # 2. owner polls, receives the join (and it is consumed)
        self.client.force_authenticate(self.streamer)
        items = self.client.get(url, {"role": "streamer"}).json()["items"]
        self.assertEqual([i["kind"] for i in items], ["join"])
        self.assertEqual(items[0]["peer_id"], "peer-A")

        # 3. owner sends offer to that peer
        res = self.client.post(url, {"kind": "offer", "direction": "to_viewer",
                                     "peer_id": "peer-A", "payload": {"sdp": "offer-sdp"}},
                               format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        # 4. viewer polls with the peer_id, receives the offer
        self.client.force_authenticate(self.viewer)
        items = self.client.get(url, {"role": "viewer", "peer_id": "peer-A"}).json()["items"]
        self.assertEqual([i["kind"] for i in items], ["offer"])
        self.assertEqual(items[0]["payload"]["sdp"], "offer-sdp")

        # 5. viewer answers; owner receives it
        self.client.post(url, {"kind": "answer", "direction": "to_streamer",
                               "peer_id": "peer-A", "payload": {"sdp": "answer-sdp"}},
                         format="json")
        self.client.force_authenticate(self.streamer)
        items = self.client.get(url, {"role": "streamer"}).json()["items"]
        self.assertEqual([i["kind"] for i in items], ["answer"])
        self.assertEqual(items[0]["payload"]["sdp"], "answer-sdp")

        # nothing left anywhere
        self.assertEqual(StreamSignal.objects.count(), 0)

    def test_hijacker_cannot_interfere_mid_handshake(self):
        stream = self.make_stream()
        url = self.signals_url(stream)
        hijacker = User.objects.create_user(
            username="mallory", password="x", node=self.node,
            display_name="mallory", is_active=True, approved=True,
        )
        # viewer joined; owner has an offer out for peer-A
        self.client.force_authenticate(self.viewer)
        self.client.post(url, {"kind": "join", "direction": "to_streamer",
                               "peer_id": "peer-A", "payload": {}}, format="json")
        self.client.force_authenticate(self.streamer)
        self.client.get(url, {"role": "streamer"})
        self.client.post(url, {"kind": "offer", "direction": "to_viewer",
                               "peer_id": "peer-A", "payload": {"sdp": "legit"}}, format="json")

        # hijacker cannot deliver a competing offer to the viewer
        self.client.force_authenticate(hijacker)
        res = self.client.post(url, {"kind": "offer", "direction": "to_viewer",
                                     "peer_id": "peer-A", "payload": {"sdp": "evil"}},
                               format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # hijacker cannot read the streamer's inbound signals
        res = self.client.get(url, {"role": "streamer"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # viewer still receives only the legit offer
        self.client.force_authenticate(self.viewer)
        items = self.client.get(url, {"role": "viewer", "peer_id": "peer-A"}).json()["items"]
        self.assertEqual([i["payload"]["sdp"] for i in items], ["legit"])

    def test_signals_rejected_after_end_and_queued_ones_gone(self):
        stream = self.make_stream()
        url = self.signals_url(stream)
        self.client.force_authenticate(self.viewer)
        self.client.post(url, {"kind": "join", "direction": "to_streamer",
                               "peer_id": "peer-A", "payload": {}}, format="json")

        self.client.force_authenticate(self.streamer)
        self.client.post(f"/api/streams/{stream.serial}/end/")

        # queued signal purged
        self.assertEqual(StreamSignal.objects.filter(stream=stream).count(), 0)
        # all traffic now 410
        self.client.force_authenticate(self.viewer)
        res = self.client.post(url, {"kind": "join", "direction": "to_streamer",
                                     "peer_id": "peer-B", "payload": {}}, format="json")
        self.assertEqual(res.status_code, status.HTTP_410_GONE)
        res = self.client.get(url, {"role": "viewer", "peer_id": "peer-A"})
        self.assertEqual(res.status_code, status.HTTP_410_GONE)

    def test_ttl_sweep_removes_stale_signals(self):
        from datetime import timedelta
        from django.utils import timezone
        stream = self.make_stream()
        url = self.signals_url(stream)
        self.client.force_authenticate(self.viewer)
        self.client.post(url, {"kind": "join", "direction": "to_streamer",
                               "peer_id": "stale-peer", "payload": {}}, format="json")
        # age the row beyond the 5-minute TTL
        StreamSignal.objects.update(created_at=timezone.now() - timedelta(minutes=6))
        # any poll sweeps it (viewer poll for a different peer)
        self.client.get(url, {"role": "viewer", "peer_id": "other-peer"})
        self.assertEqual(StreamSignal.objects.count(), 0)


# ---------------- Bullet curtain: creation, permissions, polling ----------------

class StreamBulletMessageAPITests(StreamTestBase):
    def bullets_url(self, stream):
        return f"/api/streams/{stream.serial}/bullets/"

    def post_bullet(self, stream, user, content):
        self.client.force_authenticate(user)
        return self.client.post(
            self.bullets_url(stream), {"content": content}, format="json"
        )

    # ---- Creation & validation ----

    def test_viewer_can_send_bullet(self):
        stream = self.make_stream()
        res = self.post_bullet(stream, self.viewer, "hello stream!")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data["type"], "bullet")
        self.assertEqual(data["content"], "hello stream!")
        self.assertEqual(data["sender"]["displayName"], "bob")
        self.assertIn("created_at", data)
        bullet = StreamBulletMessage.objects.get()
        self.assertEqual(bullet.stream, stream)
        self.assertEqual(bullet.sender, self.viewer)

    def test_owner_can_send_bullet(self):
        stream = self.make_stream()
        res = self.post_bullet(stream, self.streamer, "owner says hi")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_empty_and_whitespace_content_rejected(self):
        stream = self.make_stream()
        for bad in ("", "   ", "\n\t"):
            res = self.post_bullet(stream, self.viewer, bad)
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, repr(bad))
        self.assertEqual(StreamBulletMessage.objects.count(), 0)

    def test_content_length_limit_120(self):
        stream = self.make_stream()
        res = self.post_bullet(stream, self.viewer, "a" * 120)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        res = self.post_bullet(stream, self.viewer, "a" * 121)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("120", str(res.json()))

    def test_client_supplied_stream_and_sender_ignored(self):
        stream = self.make_stream()
        self.client.force_authenticate(self.viewer)
        res = self.client.post(
            self.bullets_url(stream),
            {"content": "hi", "stream": "evil", "sender": 999, "id": 424242},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        bullet = StreamBulletMessage.objects.get()
        self.assertEqual(bullet.stream, stream)
        self.assertEqual(bullet.sender, self.viewer)

    def test_xss_payload_stored_and_returned_verbatim(self):
        """Sanitization contract: raw text at rest, identical JSON string out,
        rendering safety belongs to the client's textContent (research R4)."""
        stream = self.make_stream()
        payload = '<script>alert(1)</script><b>bold?</b>'
        res = self.post_bullet(stream, self.viewer, payload)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.json()["content"], payload)          # no mutation out
        self.assertEqual(StreamBulletMessage.objects.get().content, payload)  # raw at rest
        # and it round-trips identically through the poll endpoint
        self.client.force_authenticate(self.streamer)
        items = self.client.get(self.bullets_url(stream), {"after": 0}).json()["items"]
        self.assertEqual(items[0]["content"], payload)

    # ---- Auth & lifecycle ----

    def test_unauthenticated_rejected(self):
        stream = self.make_stream()
        res = self.client.post(self.bullets_url(stream), {"content": "hi"}, format="json")
        self.assertIn(res.status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        res = self.client.get(self.bullets_url(stream), {"after": 0})
        self.assertIn(res.status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertEqual(StreamBulletMessage.objects.count(), 0)

    def test_jwt_auth_works_for_bullets(self):
        stream = self.make_stream()
        token = str(RefreshToken.for_user(self.viewer).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        res = self.client.post(self.bullets_url(stream), {"content": "jwt hi"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_session_wins_over_stale_bearer_token(self):
        """A logged-in browser with an expired/garbage JWT in localStorage must
        still succeed via its session cookie — session auth is tried first, so a
        bad Bearer header no longer short-circuits the request (401)."""
        stream = self.make_stream()
        self.client.force_login(self.streamer)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not.a.real.token")
        res = self.client.post(self.bullets_url(stream), {"content": "hi"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        res = self.client.get(self.bullets_url(stream), {"after": 0})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_ended_stream_rejects_bullets_with_410(self):
        stream = self.make_stream()
        stream.end()
        res = self.post_bullet(stream, self.viewer, "too late")
        self.assertEqual(res.status_code, status.HTTP_410_GONE)
        res = self.client.get(self.bullets_url(stream), {"after": 0})
        self.assertEqual(res.status_code, status.HTTP_410_GONE)
        self.assertEqual(StreamBulletMessage.objects.count(), 0)

    def test_unknown_stream_404(self):
        self.client.force_authenticate(self.viewer)
        url = "/api/streams/00000000-0000-0000-0000-000000000000/bullets/"
        res = self.client.post(url, {"content": "hi"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        res = self.client.get(url, {"after": 0})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_ending_stream_keeps_bullets(self):
        """Locked decision: bullets persist as interaction history (contrast:
        signals are purged on end)."""
        stream = self.make_stream()
        self.post_bullet(stream, self.viewer, "keep me")
        self.client.force_authenticate(self.streamer)
        res = self.client.post(f"/api/streams/{stream.serial}/end/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(StreamBulletMessage.objects.filter(stream=stream).count(), 1)

    # ---- Cursor polling ----

    def test_poll_returns_only_newer_rows_ascending(self):
        stream = self.make_stream()
        ids = []
        for text in ("one", "two", "three"):
            ids.append(self.post_bullet(stream, self.viewer, text).json()["id"])
        self.client.force_authenticate(self.streamer)
        res = self.client.get(self.bullets_url(stream), {"after": ids[0]})
        data = res.json()
        self.assertEqual([i["content"] for i in data["items"]], ["two", "three"])
        self.assertEqual(data["cursor"], ids[2])
        # cursor at the tip → empty items, cursor echoed back
        res = self.client.get(self.bullets_url(stream), {"after": ids[2]})
        data = res.json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["cursor"], ids[2])

    def test_poll_is_not_consuming(self):
        """Two watchers polling independently both receive the same message."""
        stream = self.make_stream()
        self.post_bullet(stream, self.viewer, "for everyone")
        for user in (self.streamer, self.viewer):
            self.client.force_authenticate(user)
            items = self.client.get(self.bullets_url(stream), {"after": 0}).json()["items"]
            self.assertEqual([i["content"] for i in items], ["for everyone"], user.username)
        self.assertEqual(StreamBulletMessage.objects.count(), 1)

    def test_poll_capped_at_50(self):
        stream = self.make_stream()
        StreamBulletMessage.objects.bulk_create(
            StreamBulletMessage(stream=stream, sender=self.viewer, content=f"m{i}")
            for i in range(60)
        )
        self.client.force_authenticate(self.viewer)
        data = self.client.get(self.bullets_url(stream), {"after": 0}).json()
        self.assertEqual(len(data["items"]), 50)
        # follow-up poll from the returned cursor gets the remainder
        rest = self.client.get(self.bullets_url(stream), {"after": data["cursor"]}).json()
        self.assertEqual(len(rest["items"]), 10)

    def test_bootstrap_returns_latest_30_ascending(self):
        stream = self.make_stream()
        StreamBulletMessage.objects.bulk_create(
            StreamBulletMessage(stream=stream, sender=self.viewer, content=f"m{i}")
            for i in range(40)
        )
        self.client.force_authenticate(self.viewer)
        data = self.client.get(self.bullets_url(stream), {"latest": 1}).json()
        self.assertEqual(len(data["items"]), 30)
        self.assertEqual(data["items"][0]["content"], "m10")   # oldest of the newest 30
        self.assertEqual(data["items"][-1]["content"], "m39")  # newest last (ascending)
        self.assertEqual(data["cursor"], data["items"][-1]["id"])

    def test_bootstrap_empty_stream(self):
        stream = self.make_stream()
        self.client.force_authenticate(self.viewer)
        data = self.client.get(self.bullets_url(stream), {"latest": 1}).json()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["cursor"], 0)

    def test_poll_scoped_to_stream(self):
        mine = self.make_stream()
        other = self.make_stream(owner=self.viewer, title="Other stream")
        self.post_bullet(other, self.viewer, "elsewhere")
        self.client.force_authenticate(self.viewer)
        data = self.client.get(self.bullets_url(mine), {"after": 0}).json()
        self.assertEqual(data["items"], [])

    def test_invalid_poll_params_400(self):
        stream = self.make_stream()
        self.client.force_authenticate(self.viewer)
        for params in ({}, {"after": "abc"}, {"after": "-1"}):
            res = self.client.get(self.bullets_url(stream), params)
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, params)

    # ---- Template-level rendering ----

    def test_live_page_has_bullet_ui_for_both_roles(self):
        stream = self.make_stream()
        for user in (self.streamer, self.viewer):
            self.client.force_login(user)
            res = self.client.get(f"/streams/{stream.serial}/")
            self.assertContains(res, "bulletOverlay")
            self.assertContains(res, "bulletForm")
            self.assertContains(res, "bulletToggle")

    def test_ended_page_has_no_bullet_form(self):
        stream = self.make_stream()
        stream.end()
        self.client.force_login(self.viewer)
        res = self.client.get(f"/streams/{stream.serial}/")
        self.assertNotContains(res, "bulletForm")
        self.assertNotContains(res, "displayModeSelect")

    def test_viewer_only_controls_not_rendered_for_owner(self):
        stream = self.make_stream()
        self.client.force_login(self.streamer)
        res = self.client.get(f"/streams/{stream.serial}/")
        self.assertNotContains(res, "volumeControls")
        self.assertNotContains(res, "displayModeSelect")

        self.client.force_login(self.viewer)
        res = self.client.get(f"/streams/{stream.serial}/")
        # volume group present but hidden until an audio track exists
        self.assertContains(res, 'id="volumeControls" hidden')
        self.assertContains(res, "displayModeSelect")
