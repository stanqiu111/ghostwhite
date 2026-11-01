import base64
import hashlib
import hmac
import json
import uuid
from unittest.mock import Mock, patch

import requests
from django.test import override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from authors.models import Author
from nodes.models import Node
from .ice import ice_configuration
from .models import StreamPeer, StreamSignal
from .tests import StreamTestBase


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FederatedStreamTests(StreamTestBase):
    def setUp(self):
        super().setUp()
        self.remote = Node.objects.create(host_url="https://remote.example/", username="remote", password="node-test-secret")
        self.stream = self.make_stream()
        self.base = f"/api/federation/streams/{self.stream.serial}/"
        self.actor = self.remote.host_url + "api/authors/remote-alice"
        self.remote_client = APIClient()
        self.authenticate_remote()

    def authenticate_remote(self, actor=None, password="node-test-secret"):
        basic = base64.b64encode(f"remote:{password}".encode()).decode()
        self.remote_client.credentials(HTTP_AUTHORIZATION=f"Basic {basic}",
                                       HTTP_X_STREAM_AUTHOR=actor or self.actor,
                                       HTTP_X_STREAM_DISPLAY_NAME="Remote%20Alice")

    def join(self, peer="remote-peer"):
        return self.remote_client.post(self.base + "signals/", {
            "kind": "join", "direction": "to_streamer", "peer_id": peer,
        }, format="json")

    def test_discovery_and_metadata_with_no_local_login_account(self):
        response = self.remote_client.get("/api/federation/streams/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["id"], self.stream.id)
        self.assertEqual(self.remote_client.get(self.base).status_code, 200)
        actor = Author.objects.get(pk=self.actor)
        self.assertEqual(actor.node, self.remote)
        self.assertFalse(actor.has_usable_password())
        self.assertFalse(actor.is_active)
        self.assertFalse(actor.approved)

    def test_unknown_bad_disabled_and_inactive_node_credentials(self):
        self.authenticate_remote(password="wrong")
        self.assertEqual(self.remote_client.get(self.base).status_code, 401)
        self.authenticate_remote()
        for field in ("is_disabled", "is_active"):
            setattr(self.remote, field, field == "is_disabled")
            self.remote.save()
            self.assertEqual(self.remote_client.get(self.base).status_code, 401)
            setattr(self.remote, field, field == "is_active")
            self.remote.save()

    def test_missing_malformed_and_local_node_credentials_rejected(self):
        for header in ("", "Basic bad", "Basic " + base64.b64encode(b":").decode()):
            self.remote_client.credentials(HTTP_AUTHORIZATION=header)
            self.assertEqual(self.remote_client.get(self.base).status_code, 401)
        self.node.username, self.node.password = "remote", "node-test-secret"
        self.node.save()
        self.remote.delete()
        self.authenticate_remote()
        self.assertEqual(self.remote_client.get(self.base).status_code, 401)

    def test_attestation_cannot_impersonate_local_or_other_origin(self):
        for actor in (self.streamer.id, "https://remote.example.evil/api/authors/alice",
                      "https://remote.example/api/authors/../alice",
                      "https://remote.example/api/authors/a?x=b",
                      "https://remote.example/api/authors/a%2Fb"):
            self.authenticate_remote(actor)
            self.assertIn(self.remote_client.get(self.base).status_code, (400, 403))

    def test_attestation_cannot_reassign_existing_author(self):
        Author.objects.create_user(username="conflicting", id=self.actor, node=self.node)
        self.assertEqual(self.remote_client.get(self.base).status_code, 403)
        self.assertEqual(Author.objects.get(pk=self.actor).node_id, self.node.pk)

    def test_local_username_cannot_preempt_a_federated_identity(self):
        occupied = "stream_remote_" + hashlib.sha256(self.actor.encode()).hexdigest()
        Author.objects.create_user(username=occupied, node=self.node)
        self.assertEqual(self.remote_client.get(self.base).status_code, 200)
        self.assertNotEqual(Author.objects.get(pk=self.actor).username, occupied)

    def test_node_auth_does_not_grant_local_api_or_lifecycle_access(self):
        self.assertEqual(self.remote_client.post("/api/federation/streams/", {"title": "bad"}).status_code, 405)
        self.assertIn(self.remote_client.post("/api/streams/", {"title": "bad"}).status_code, (401, 403))
        self.assertIn(self.remote_client.post(f"/api/streams/{self.stream.serial}/end/").status_code, (401, 403))
        self.assertEqual(self.remote_client.get(self.base + "signals/", {"role": "streamer"}).status_code, 403)
        self.assertEqual(self.remote_client.post(self.base + "signals/", {
            "kind": "offer", "direction": "to_viewer", "peer_id": "bad",
        }, format="json").status_code, 403)

    def test_remote_handshake_and_mailbox_isolation(self):
        self.assertEqual(self.join().status_code, 201)
        self.client.force_authenticate(self.streamer)
        url = f"/api/streams/{self.stream.serial}/signals/"
        signals = self.client.get(url, {"role": "streamer"}).json()["items"]
        self.assertEqual(signals[0]["kind"], "join")
        self.assertEqual(self.client.post(url, {"kind": "offer", "direction": "to_viewer",
            "peer_id": "remote-peer", "payload": {"sdp": "opaque offer"}}, format="json").status_code, 201)
        self.authenticate_remote(self.remote.host_url + "api/authors/other")
        self.assertEqual(self.remote_client.get(self.base + "signals/", {
            "role": "viewer", "peer_id": "remote-peer"}).status_code, 403)
        self.assertEqual(self.join().status_code, 403)
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(url, {"role": "viewer", "peer_id": "remote-peer"}).status_code, 403)
        self.assertEqual(StreamSignal.objects.filter(direction="to_viewer").count(), 1)
        self.authenticate_remote()
        items = self.remote_client.get(self.base + "signals/", {"role": "viewer", "peer_id": "remote-peer"}).json()["items"]
        self.assertEqual(items[0]["payload"]["sdp"], "opaque offer")
        self.assertEqual(self.remote_client.post(self.base + "signals/", {
            "kind": "answer", "direction": "to_streamer", "peer_id": "remote-peer",
            "payload": {"sdp": "opaque answer"}}, format="json").status_code, 201)

    def test_chat_identity_literal_text_and_revocation(self):
        text = '<script>window.bad=true</script>'
        response = self.remote_client.post(self.base + "bullets/", {"content": text, "sender": self.streamer.id}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["sender"]["displayName"], "Remote Alice")
        self.assertEqual(self.stream.bullets.get().sender_id, self.actor)
        self.assertEqual(self.remote_client.get(self.base + "bullets/", {"latest": 1}).json()["items"][0]["content"], text)
        self.remote.is_disabled = True
        self.remote.save()
        self.assertEqual(self.join().status_code, 401)
        self.assertEqual(self.remote_client.get(self.base + "bullets/", {"latest": 1}).status_code, 401)

    def test_end_clears_mailboxes_and_rejects_remote_writes(self):
        self.join()
        self.client.force_authenticate(self.streamer)
        self.client.post(f"/api/streams/{self.stream.serial}/end/")
        self.assertFalse(StreamPeer.objects.exists())
        self.assertFalse(StreamSignal.objects.exists())
        self.assertEqual(self.join().status_code, 410)
        self.assertEqual(self.remote_client.post(self.base + "bullets/", {"content": "late"}).status_code, 410)
        self.assertEqual(self.remote_client.get("/api/federation/streams/").json()["items"], [])

    def test_owner_poll_revokes_disabled_remote_peers(self):
        self.join()
        self.remote.is_disabled = True
        self.remote.save()
        self.client.force_authenticate(self.streamer)
        response = self.client.get(f"/api/streams/{self.stream.serial}/signals/", {"role": "streamer"})
        self.assertEqual(response.json()["items"], [{"kind": "bye", "peer_id": "remote-peer", "payload": {}, "sender_serial": ""}])
        repeated = self.client.get(f"/api/streams/{self.stream.serial}/signals/", {"role": "streamer"})
        self.assertEqual(repeated.json()["items"], response.json()["items"])
        self.assertTrue(StreamPeer.objects.exists())
        self.assertFalse(StreamSignal.objects.exists())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RemoteProxyTests(StreamTestBase):
    def setUp(self):
        super().setUp()
        self.node.username, self.node.password = "local-node", "local-node-secret"
        self.node.save()
        self.remote = Node.objects.create(host_url="https://remote.example/")
        self.serial = uuid.uuid4()
        self.base = f"/api/remote-nodes/{self.remote.pk}/streams/"
        self.metadata = {"type": "stream", "id": f"https://remote.example/api/authors/a/streams/{self.serial}",
            "serial": str(self.serial), "title": "Remote <studio>", "description": "hello",
            "owner": {"id": "https://remote.example/api/authors/a", "displayName": "Remote host"},
            "status": "live", "startedAt": "2026-11-01T12:00:00Z", "endedAt": None}
        self.client.force_authenticate(self.viewer)

    def response(self, data=None, status=200):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.status_code = status
        response.iter_content.return_value = [json.dumps(data if data is not None else self.metadata).encode()]
        return response

    @patch("streams.federation.requests.request")
    def test_proxy_server_credentials_fixed_destination_and_local_watch_url(self, http):
        http.return_value = self.response({"type": "streams", "items": [self.metadata]})
        response = self.client.get(self.base, {"url": "https://evil.example/"})
        self.assertEqual(response.status_code, 200)
        args, kwargs = http.call_args
        self.assertEqual(args, ("GET", "https://remote.example/api/federation/streams/"))
        self.assertEqual(kwargs["auth"], ("local-node", "local-node-secret"))
        self.assertEqual(kwargs["headers"]["X-Stream-Author"], self.viewer.id)
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["timeout"], (3, 5))
        self.assertNotIn("local-node-secret", response.content.decode())
        self.assertEqual(response.json()["items"][0]["watchUrl"], f"/streams/remote/{self.remote.pk}/{self.serial}/")

    @patch("streams.federation.requests.request")
    def test_remote_page_has_viewer_only_hooks_and_same_origin_transport(self, http):
        http.return_value = self.response()
        self.client.force_login(self.viewer)
        response = self.client.get(f"/streams/remote/{self.remote.pk}/{self.serial}/")
        self.assertContains(response, f'data-api-base="{self.base}{self.serial}/"')
        self.assertContains(response, "Remote &lt;studio&gt;")
        self.assertContains(response, 'id="enableSoundBtn"')
        self.assertNotContains(response, 'id="microphoneBtn"')
        self.assertNotContains(response, 'id="endStreamBtn"')
        self.assertNotContains(response, "local-node-secret")
        self.remote.is_disabled = True
        self.remote.save()
        self.assertEqual(self.client.get(f"/streams/remote/{self.remote.pk}/{self.serial}/").status_code, 403)

    @patch("streams.federation.requests.request")
    def test_session_and_jwt_proxy_csrf(self, http):
        http.return_value = self.response({"type": "signal", "kind": "join", "peer_id": "viewer"}, 201)
        body = {"kind": "join", "direction": "to_streamer", "peer_id": "viewer"}
        url = self.base + str(self.serial) + "/signals/"
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.viewer)
        self.assertEqual(client.post(url, body, format="json").status_code, 403)
        client.logout()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.viewer).access_token}")
        self.assertEqual(client.post(url, body, format="json").status_code, 201)
        self.assertEqual(http.call_args.kwargs["headers"]["X-Stream-Author"], self.viewer.id)

    @patch("streams.federation.requests.request")
    def test_disabled_node_anonymous_and_owner_actions_never_forward(self, http):
        url = self.base + str(self.serial) + "/signals/"
        self.assertEqual(self.client.get(url, {"role": "streamer"}).status_code, 403)
        self.assertEqual(self.client.post(url, {"kind": "offer", "direction": "to_viewer", "peer_id": "x"}).status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.base).status_code, (401, 403))
        self.client.force_authenticate(self.viewer)
        self.remote.is_disabled = True
        self.remote.save()
        self.assertEqual(self.client.get(self.base).status_code, 403)
        http.assert_not_called()

    @patch("streams.federation.requests.request")
    def test_errors_redirect_and_malformed_or_foreign_metadata(self, http):
        for status in (301, 302, 500):
            http.return_value = self.response(status=status)
            self.assertEqual(self.client.get(self.base + str(self.serial) + "/").status_code, 502)
        for status in (401, 403):
            http.return_value = self.response(status=status)
            self.assertEqual(self.client.get(self.base + str(self.serial) + "/").status_code, 403)
        for status in (404, 410):
            http.return_value = self.response(status=status)
            self.assertEqual(self.client.get(self.base + str(self.serial) + "/").status_code, status)
        http.return_value = self.response({**self.metadata, "id": "https://evil.example/streams/a"})
        self.assertEqual(self.client.get(self.base + str(self.serial) + "/").status_code, 502)
        http.return_value = self.response({"items": "wrong"})
        self.assertEqual(self.client.get(self.base).status_code, 502)
        http.side_effect = requests.Timeout()
        self.assertEqual(self.client.get(self.base).status_code, 502)

    @patch("streams.federation.requests.request")
    def test_large_response_and_unapproved_actor_rejected(self, http):
        response = self.response()
        response.iter_content.return_value = [b"x" * (1024 * 1024 + 1)]
        http.return_value = response
        self.assertEqual(self.client.get(self.base).status_code, 502)
        self.viewer.approved = False
        self.viewer.save()
        http.reset_mock()
        self.assertEqual(self.client.get(self.base).status_code, 403)
        http.assert_not_called()

    @patch("streams.federation.requests.request")
    def test_malformed_poll_cannot_poison_browser_cursor_or_signal_peer(self, http):
        url = self.base + str(self.serial) + "/"
        for data in ({"type": "bullets", "items": [{"id": 1}], "cursor": 1},
                     {"type": "bullets", "items": [], "cursor": 2**60},
                     {"type": "bullets", "items": [], "cursor": "Infinity"},
                     {"type": "bullets", "items": [], "cursor": 0}):
            http.return_value = self.response(data)
            self.assertEqual(self.client.get(url + "bullets/", {"after": 10}).status_code, 502)
        http.return_value = self.response({"type": "signals", "items": [{"kind": "offer",
            "peer_id": "someone-else", "payload": {}, "sender_serial": "host"}]})
        self.assertEqual(self.client.get(url + "signals/", {"role": "viewer", "peer_id": "me"}).status_code, 502)
        self.assertEqual(self.client.post(url + "signals/", [], format="json").status_code, 400)

    @patch("streams.federation.requests.request")
    def test_long_local_description_and_invalid_json_from_remote(self, http):
        http.return_value = self.response({**self.metadata, "description": "x" * 20001})
        self.assertEqual(self.client.get(self.base + str(self.serial) + "/").status_code, 200)
        for raw in (b'{"items":NaN}', b'[' * 2000 + b']' * 2000):
            response = self.response()
            response.iter_content.return_value = [raw]
            http.return_value = response
            self.assertEqual(self.client.get(self.base).status_code, 502)

    def test_ice_endpoint_requires_approved_local_auth_and_disables_caching(self):
        response = self.client.get('/api/streams/ice/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
        self.viewer.approved = False
        self.viewer.save()
        self.assertEqual(self.client.get('/api/streams/ice/').status_code, 403)

    @override_settings(STREAM_ICE_SERVERS=[{"urls": "stun:stun.example:3478"}],
                       STREAM_TURN_URLS=["turn:turn.example:3478"], STREAM_TURN_SHARED_SECRET="turn-test-only")
    @patch("streams.ice.time.time", return_value=10000)
    def test_turn_credentials_expire_and_do_not_expose_shared_secret(self, clock):
        config = ice_configuration()
        turn = config["iceServers"][1]
        self.assertEqual(turn["username"], "13600")
        expected = base64.b64encode(hmac.new(b"turn-test-only", b"13600", hashlib.sha1).digest()).decode()
        self.assertEqual(turn["credential"], expected)
        self.assertNotIn("turn-test-only", json.dumps(config))
