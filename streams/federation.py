"""Server-only node authentication and bounded HTTP transport for streams."""
import re
import uuid
from urllib.parse import quote, unquote, urlsplit

import requests
from django.conf import settings
from django.contrib.auth.hashers import make_password
from rest_framework import serializers
from rest_framework.authentication import BasicAuthentication
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from authors.models import Author
from nodes.models import Node


class RemoteActorSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=150)
    displayName = serializers.CharField(max_length=255, allow_blank=True, default="")

    def validate_id(self, value):
        prefix = self.context["node"].host_url.rstrip("/") + "/api/authors/"
        if not value.startswith(prefix) or not re.fullmatch(r"[A-Za-z0-9_-]+", value[len(prefix):]):
            raise PermissionDenied("Author must belong to the authenticated node.")
        return value

    def create(self, data):
        actor, _ = Author.objects.get_or_create(
            id=data["id"], defaults={
                "node": self.context["node"],
                "username": "stream_remote_" + uuid.uuid4().hex,
                "display_name": data["displayName"] or data["id"].rsplit("/", 1)[-1],
                "password": make_password(None), "is_active": False, "approved": False,
            },
        )
        if actor.node_id != self.context["node"].pk:
            raise PermissionDenied("Author is already associated with another node.")
        return actor


class FederatedStreamAuthentication(BasicAuthentication):
    """Only this API accepts node attestations; never a browser login session."""

    def authenticate_credentials(self, userid, password, request=None):
        if not userid or not password:
            raise AuthenticationFailed("Node credentials are required.")
        try:
            node = Node.objects.get(username=userid, password=password)
        except (Node.DoesNotExist, Node.MultipleObjectsReturned):
            raise AuthenticationFailed("Invalid node credentials.")
        if node.is_local or not node.is_active or node.is_disabled:
            raise AuthenticationFailed("Remote node is not enabled.")
        actor = RemoteActorSerializer(data={
            "id": request.headers.get("X-Stream-Author", ""),
            "displayName": unquote(request.headers.get("X-Stream-Display-Name", "")),
        }, context={"node": node})
        actor.is_valid(raise_exception=True)
        return actor.save(), node


class RemoteStreamSerializer(serializers.Serializer):
    """Validate only the public metadata needed by the local viewer template."""

    id = serializers.CharField(max_length=512)
    serial = serializers.UUIDField()
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(allow_blank=True, default="")
    status = serializers.ChoiceField(choices=["live", "ended"])
    startedAt = serializers.DateTimeField()
    endedAt = serializers.DateTimeField(allow_null=True, default=None)
    owner = serializers.DictField()

    def validate(self, data):
        prefix = self.context["node"].host_url.rstrip("/") + "/api/authors/"
        owner = data["owner"]
        owner_id = owner.get("id", "")
        if (not isinstance(owner_id, str) or not owner_id.startswith(prefix)
                or not re.fullmatch(r"[A-Za-z0-9_-]+", owner_id[len(prefix):])):
            raise serializers.ValidationError("Invalid stream owner origin.")
        if data["id"] != f'{owner_id}/streams/{data["serial"]}':
            raise serializers.ValidationError("Invalid stream identity.")
        name = owner.get("displayName") or owner.get("username") or "Remote host"
        if not isinstance(name, str) or len(name) > 255:
            raise serializers.ValidationError("Invalid host name.")
        data["owner"] = {"id": owner_id, "displayName": name}
        return data


class RemoteStreamError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


MAX_CURSOR = 2**53 - 1  # Browser polling cursors must be exact JavaScript integers.


class RemoteBulletSenderSerializer(serializers.Serializer):
    serial = serializers.CharField(max_length=150)
    displayName = serializers.CharField(max_length=255)


class RemoteBulletSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["bullet"])
    id = serializers.IntegerField(min_value=1, max_value=MAX_CURSOR)
    content = serializers.CharField(max_length=120, trim_whitespace=False)
    sender = RemoteBulletSenderSerializer()
    created_at = serializers.DateTimeField()


class RemoteSignalSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["offer", "candidate", "bye"])
    peer_id = serializers.CharField(max_length=64)
    payload = serializers.DictField()
    sender_serial = serializers.CharField(max_length=150)

    def validate(self, data):
        import json
        try:
            size = len(json.dumps(data["payload"], allow_nan=False))
        except (ValueError, RecursionError):
            raise serializers.ValidationError("Invalid signal payload.")
        if data["peer_id"] != self.context["peer_id"] or size > 32 * 1024:
            raise serializers.ValidationError("Invalid signal recipient or payload.")
        return data


def polling_response(action, data, params):
    items = data.get("items")
    limit = 1000 if action == "signals" else (50 if "after" in params else 30)
    if data.get("type") != action or not isinstance(items, list) or len(items) > limit:
        raise RemoteStreamError("The remote node returned an invalid polling response.")
    serializer = (RemoteSignalSerializer if action == "signals" else RemoteBulletSerializer)(
        data=items, many=True, context=params,
    )
    if not serializer.is_valid():
        raise RemoteStreamError("The remote node returned invalid messages.")
    result = {"type": action, "items": serializer.data}
    if action == "bullets":
        try:
            cursor = serializers.IntegerField(min_value=0, max_value=MAX_CURSOR).run_validation(data.get("cursor"))
        except serializers.ValidationError:
            raise RemoteStreamError("The remote node returned an invalid chat cursor.")
        previous = params.get("after", 0)
        for item in serializer.validated_data:
            if not previous < item["id"] <= cursor:
                raise RemoteStreamError("The remote node returned unordered messages.")
            previous = item["id"]
        if cursor < previous:
            raise RemoteStreamError("The remote node returned a stale chat cursor.")
        result["cursor"] = cursor
    return result


def remote_request(node, actor, method, suffix="", *, params=None, data=None):
    """Never accept a client URL, forward browser credentials, or follow redirects."""
    if node.is_local or not node.is_active or node.is_disabled:
        raise RemoteStreamError("This remote node is unavailable.", 404)
    local = Node.objects.filter(is_local=True).first()
    if not local or not local.username or not local.password:
        raise RemoteStreamError("Local node credentials are not configured.", 503)
    if actor.node_id != local.pk or not actor.is_active or not actor.approved:
        raise RemoteStreamError("An approved local account is required.", 403)
    target = urlsplit(node.host_url)
    if (target.scheme not in ("https", "http") or not target.hostname
            or target.username or target.password or target.query or target.fragment
            or (target.scheme != "https" and not settings.DEBUG)):
        raise RemoteStreamError("The remote node must have a valid HTTPS address.", 503)
    url = node.host_url.rstrip("/") + "/api/federation/streams/" + suffix
    try:
        with requests.request(
            method, url, params=params, json=data,
            auth=(local.username, local.password),
            headers={"Accept": "application/json", "X-Stream-Author": actor.id,
                     "X-Stream-Display-Name": quote(actor.display_name or actor.username, safe="")},
            timeout=(3, 5), allow_redirects=False, stream=True,
        ) as response:
            if response.status_code in (401, 403):
                raise RemoteStreamError("The remote node refused access. Check the node connection.", 403)
            if response.status_code == 404:
                raise RemoteStreamError("Remote stream or streaming API was not found.", 404)
            if response.status_code == 410:
                raise RemoteStreamError("Stream has ended.", 410)
            if response.status_code not in (200, 201, 400):
                raise RemoteStreamError("The remote streaming service is unavailable.")
            body = bytearray()
            for chunk in response.iter_content(16384):
                body.extend(chunk)
                if len(body) > 1024 * 1024:
                    raise RemoteStreamError("Remote response exceeded the size limit.")
            import json
            def invalid_constant(value):
                raise ValueError("Non-finite JSON number")
            result = json.loads(body, parse_constant=invalid_constant)
            if not isinstance(result, dict):
                raise RemoteStreamError("Invalid response from the remote node.")
            if response.status_code == 400:
                raise RemoteStreamError("The remote node rejected the request.", 400)
            return result, response.status_code
    except (requests.RequestException, ValueError, RecursionError):
        raise RemoteStreamError("Could not reach the remote streaming service.")
