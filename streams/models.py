import uuid

from django.db import models
from django.db.models import Q
from django.utils import timezone

from authors.models import Author
from nodes.models import Node

STATUS_CHOICES = [
    ("live", "Live"),
    ("ended", "Ended"),
]


class Stream(models.Model):
    id = models.CharField(max_length=512, primary_key=True)
    owner = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="streams")
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="streams")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="live")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner"],
                condition=Q(status="live"),
                name="unique_live_stream_per_owner",
            )
        ]
        indexes = [
            models.Index(
                fields=["status", "started_at"],
                name="stream_status_started_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.id:
            from utils.fqid import build_stream_fqid
            if self.owner:
                stream_uuid = uuid.uuid4()
                fqid = build_stream_fqid(self.owner.id, str(stream_uuid))
                if fqid:
                    self.id = fqid
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Stream '{self.title}' by {self.owner.username} ({self.status})"

    def end(self):
        """End a live stream. Idempotent: ending an ended stream is a no-op."""
        if self.status == "live":
            self.status = "ended"
            self.ended_at = timezone.now()
            self.save()
        return self

    @property
    def serial(self):
        from utils.fqid import extract_stream_id_from_fqid
        return extract_stream_id_from_fqid(self.id)

    @property
    def is_live(self):
        return self.status == "live"

    def get_absolute_url(self) -> str:
        """Canonical reader URL for the stream detail page."""
        return f"/streams/{self.serial}/"


SIGNAL_DIRECTION_CHOICES = [
    ("to_streamer", "To streamer"),
    ("to_viewer", "To viewer"),
]

SIGNAL_KIND_CHOICES = [
    ("join", "Join"),
    ("offer", "Offer"),
    ("answer", "Answer"),
    ("candidate", "Candidate"),
    ("bye", "Bye"),
]


class StreamSignal(models.Model):
    """Ephemeral WebRTC signaling message relayed between broadcaster and one viewer.

    Rows are deleted when read by their addressee (consume-on-read), purged when
    the stream ends, and TTL-swept after 5 minutes. Never exposed with an FQID —
    signals are transport, not content.
    """

    stream = models.ForeignKey(Stream, on_delete=models.CASCADE, related_name="signals")
    sender = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="+")
    direction = models.CharField(max_length=12, choices=SIGNAL_DIRECTION_CHOICES)
    peer_id = models.CharField(max_length=64)
    kind = models.CharField(max_length=12, choices=SIGNAL_KIND_CHOICES)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]  # handshake messages must arrive in order
        indexes = [
            models.Index(
                fields=["stream", "direction", "peer_id"],
                name="signal_route_idx",
            ),
        ]

    def __str__(self):
        return f"{self.kind} ({self.direction}) for {self.peer_id} on {self.stream_id}"


class StreamBulletMessage(models.Model):
    """One bullet-curtain (danmaku) comment on a stream.

    Persistent content — unlike StreamSignal, rows are never consumed on read,
    never purged when the stream ends, and have no TTL. The auto `id` doubles
    as the polling cursor. No FQID: bullets are page-local overlay content,
    not federated objects.
    """

    stream = models.ForeignKey(Stream, on_delete=models.CASCADE, related_name="bullets")
    sender = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="+")
    content = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]  # insertion order; id is the cursor (no timestamp ties)
        indexes = [
            models.Index(fields=["stream", "id"], name="bullet_cursor_idx"),
        ]

    def __str__(self):
        return f"bullet by {self.sender.username} on {self.stream_id}: {self.content[:30]}"
