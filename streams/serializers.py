import json

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from authors.serializers import AuthorSerializer
from utils.fqid import extract_serial_from_fqid, extract_stream_id_from_fqid
from .models import Stream, StreamBulletMessage, StreamPeer, StreamSignal

MAX_SIGNAL_PAYLOAD_BYTES = 32 * 1024
MAX_BULLET_CONTENT_CHARS = 120


class StreamSerializer(serializers.ModelSerializer):
    type = serializers.SerializerMethodField()
    serial = serializers.SerializerMethodField()
    owner = AuthorSerializer(read_only=True)
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    startedAt = serializers.DateTimeField(source="started_at", read_only=True)
    endedAt = serializers.DateTimeField(source="ended_at", read_only=True)
    webUrl = serializers.SerializerMethodField()

    class Meta:
        model = Stream
        fields = [
            "type",
            "id",
            "serial",
            "owner",
            "title",
            "description",
            "status",
            "startedAt",
            "endedAt",
            "webUrl",
        ]
        read_only_fields = ["id", "status"]

    def get_type(self, obj):
        return "stream"

    def get_serial(self, obj):
        return extract_stream_id_from_fqid(obj.id)

    def get_webUrl(self, obj):
        request = self.context.get("request")
        path = obj.get_absolute_url()
        return request.build_absolute_uri(path) if request else path

    def validate_title(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Title is required.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if self.instance is None and user and user.is_authenticated:
            if Stream.objects.filter(owner=user, status="live").exists():
                raise serializers.ValidationError("You already have a live stream.")
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        return Stream.objects.create(
            owner=request.user,
            node=request.user.node,
            status="live",
            **validated_data,
        )


class StreamPeerSerializer(serializers.Serializer):
    peer_id = serializers.CharField(max_length=64)

    def create(self, validated_data):
        peer, _ = StreamPeer.objects.get_or_create(
            stream=self.context["stream"], peer_id=validated_data["peer_id"],
            defaults={"viewer": self.context["request"].user},
        )
        if peer.viewer_id != self.context["request"].user.pk:
            raise PermissionDenied("This peer belongs to another viewer.")
        return peer

    @staticmethod
    def revoke_disabled_nodes(stream):
        from django.db.models import Q
        peers = stream.peers.filter(viewer__node__is_local=False).filter(
            Q(viewer__node__is_disabled=True) | Q(viewer__node__is_active=False)
        )
        revoked = list(peers.values_list("peer_id", flat=True))
        stream.signals.filter(peer_id__in=revoked).delete()
        # Retain the binding until end: if a poll response is lost, the next
        # owner poll must repeat the teardown instruction. Closing is idempotent.
        return [{"kind": "bye", "peer_id": peer_id, "payload": {}, "sender_serial": ""}
                for peer_id in revoked]


class StreamSignalSerializer(serializers.ModelSerializer):
    """WebRTC signaling message. All rules live here (constitution IV).

    `stream` and `sender` are injected server-side via context — never client-writable.
    """

    payload = serializers.JSONField(required=False, default=dict)

    class Meta:
        model = StreamSignal
        fields = ["kind", "direction", "peer_id", "payload"]

    def validate_payload(self, value):
        if len(json.dumps(value)) > MAX_SIGNAL_PAYLOAD_BYTES:
            raise serializers.ValidationError("Payload too large.")
        return value

    def validate(self, attrs):
        kind = attrs.get("kind")
        direction = attrs.get("direction")

        # Kind/direction coherence
        if kind == "offer" and direction != "to_viewer":
            raise serializers.ValidationError("Offers must be addressed to a viewer.")
        if kind in ("join", "answer") and direction != "to_streamer":
            raise serializers.ValidationError(f"'{kind}' must be addressed to the streamer.")

        # Direction rule (anti-hijack): only the owner may address viewers
        stream = self.context["stream"]
        sender = self.context["request"].user
        if direction == "to_viewer" and sender != stream.owner:
            raise PermissionDenied(
                "Only the stream owner can send signals to viewers."
            )
        return attrs

    def create(self, validated_data):
        if validated_data["direction"] == "to_streamer":
            peer = StreamPeerSerializer(
                data={"peer_id": validated_data["peer_id"]}, context=self.context,
            )
            peer.is_valid(raise_exception=True)
            peer.save()
        return StreamSignal.objects.create(
            stream=self.context["stream"],
            sender=self.context["request"].user,
            **validated_data,
        )


class StreamBulletMessageSerializer(serializers.ModelSerializer):
    """Bullet-curtain comment. Content is stored as the raw text the user typed
    (length-capped); rendering safety is the client's textContent duty.

    `stream` and `sender` are injected server-side via context — never client-writable.
    """

    type = serializers.SerializerMethodField()
    sender = serializers.SerializerMethodField()
    # Declared explicitly so the strip-then-validate order is ours, not CharField's
    content = serializers.CharField(trim_whitespace=True, allow_blank=False)

    class Meta:
        model = StreamBulletMessage
        fields = ["type", "id", "content", "sender", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_type(self, obj):
        return "bullet"

    def get_sender(self, obj):
        return {
            "serial": extract_serial_from_fqid(obj.sender.id),
            "displayName": obj.sender.display_name or obj.sender.username,
        }

    def validate_content(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Message cannot be empty.")
        if len(value) > MAX_BULLET_CONTENT_CHARS:
            raise serializers.ValidationError(
                f"Message is too long (max {MAX_BULLET_CONTENT_CHARS} characters)."
            )
        return value

    def create(self, validated_data):
        return StreamBulletMessage.objects.create(
            stream=self.context["stream"],
            sender=self.context["request"].user,
            **validated_data,
        )
