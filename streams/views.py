from datetime import timedelta

from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from utils.fqid import extract_serial_from_fqid, find_stream_by_uuid
from .models import Stream, StreamSignal
from .serializers import (
    StreamBulletMessageSerializer,
    StreamSerializer,
    StreamSignalSerializer,
)

SIGNAL_TTL = timedelta(minutes=5)
BULLET_POLL_LIMIT = 50
BULLET_BOOTSTRAP_LIMIT = 30


# ---------------- API views ----------------

class StreamListCreateView(generics.ListCreateAPIView):
    """GET: list active (live) streams. POST: start a new stream."""

    serializer_class = StreamSerializer
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Stream.objects.filter(status="live").select_related("owner", "node")

    def list(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({"type": "streams", "items": serializer.data})


class StreamRetrieveView(generics.RetrieveAPIView):
    """Retrieve a single stream (live or ended) by its UUID serial."""

    serializer_class = StreamSerializer
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_object(self):
        try:
            return find_stream_by_uuid(self.kwargs["pk"])
        except Stream.DoesNotExist:
            raise Http404()


class StreamEndView(APIView):
    """POST: end a live stream. Owner only; idempotent."""

    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            stream = find_stream_by_uuid(pk)
        except Stream.DoesNotExist:
            raise Http404()
        if stream.owner != request.user:
            return Response(
                {"detail": "Only the stream owner can end this stream."},
                status=status.HTTP_403_FORBIDDEN,
            )
        stream.end()
        # Ended streams accept no more signaling; drop anything still queued
        stream.signals.all().delete()
        serializer = StreamSerializer(stream, context={"request": request})
        return Response(serializer.data)


class StreamSignalView(APIView):
    """WebRTC signaling relay: POST to send a signal, GET to poll (consume-on-read).

    See specs/003-screen-share/contracts/signaling-api.md.
    """

    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_stream(self, pk):
        try:
            stream = find_stream_by_uuid(pk)
        except Stream.DoesNotExist:
            raise Http404()
        return stream

    def post(self, request, pk):
        stream = self.get_stream(pk)
        if not stream.is_live:
            return Response(
                {"detail": "Stream has ended."}, status=status.HTTP_410_GONE
            )
        serializer = StreamSignalSerializer(
            data=request.data, context={"request": request, "stream": stream}
        )
        serializer.is_valid(raise_exception=True)
        signal = serializer.save()
        return Response(
            {"type": "signal", "kind": signal.kind, "peer_id": signal.peer_id},
            status=status.HTTP_201_CREATED,
        )

    def get(self, request, pk):
        stream = self.get_stream(pk)
        if not stream.is_live:
            return Response(
                {"detail": "Stream has ended."}, status=status.HTTP_410_GONE
            )

        role = request.query_params.get("role")
        peer_id = request.query_params.get("peer_id")
        if role == "streamer":
            if stream.owner != request.user:
                return Response(
                    {"detail": "Only the stream owner can poll as streamer."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            qs = stream.signals.filter(direction="to_streamer")
        elif role == "viewer":
            if not peer_id:
                return Response(
                    {"detail": "peer_id is required for role=viewer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            qs = stream.signals.filter(direction="to_viewer", peer_id=peer_id)
        else:
            return Response(
                {"detail": "role must be 'streamer' or 'viewer'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # TTL sweep: drop stale handshake leftovers for this stream
        stream.signals.filter(created_at__lt=timezone.now() - SIGNAL_TTL).delete()

        # Consume-on-read: return each signal exactly once
        with transaction.atomic():
            signals = list(qs.select_related("sender"))
            items = [
                {
                    "kind": s.kind,
                    "peer_id": s.peer_id,
                    "payload": s.payload,
                    "sender_serial": extract_serial_from_fqid(s.sender.id),
                }
                for s in signals
            ]
            qs.filter(id__in=[s.id for s in signals]).delete()

        return Response({"type": "signals", "items": items})


class StreamBulletView(APIView):
    """Bullet-curtain messages: POST to send, GET to cursor-poll.

    Reads are NON-consuming (bullets are broadcast to every watcher, each
    polling with their own id cursor) — deliberately unlike the signaling
    relay. See specs/004-stream-video-controls/contracts/bullets-api.md.
    """

    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_live_stream(self, pk):
        try:
            stream = find_stream_by_uuid(pk)
        except Stream.DoesNotExist:
            raise Http404()
        if not stream.is_live:
            return stream, Response(
                {"detail": "Stream has ended."}, status=status.HTTP_410_GONE
            )
        return stream, None

    def post(self, request, pk):
        stream, gone = self.get_live_stream(pk)
        if gone:
            return gone
        serializer = StreamBulletMessageSerializer(
            data=request.data, context={"request": request, "stream": stream}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get(self, request, pk):
        stream, gone = self.get_live_stream(pk)
        if gone:
            return gone

        after = request.query_params.get("after")
        if after is not None:
            try:
                after_id = int(after)
            except ValueError:
                after_id = -1
            if after_id < 0:
                return Response(
                    {"detail": "after must be a non-negative integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            bullets = list(
                stream.bullets.filter(id__gt=after_id)
                .select_related("sender")[:BULLET_POLL_LIMIT]
            )
            cursor = bullets[-1].id if bullets else after_id
        elif request.query_params.get("latest"):
            # Bootstrap: the most recent messages, oldest-first, plus the cursor
            bullets = list(
                stream.bullets.select_related("sender")
                .order_by("-id")[:BULLET_BOOTSTRAP_LIMIT]
            )
            bullets.reverse()
            latest_id = stream.bullets.order_by("-id").values_list("id", flat=True).first()
            cursor = latest_id or 0
        else:
            return Response(
                {"detail": "Provide either ?after=<id> or ?latest=1."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        items = StreamBulletMessageSerializer(bullets, many=True).data
        return Response({"type": "bullets", "items": items, "cursor": cursor})


# ---------------- Template page views ----------------

def stream_list_page(request):
    if not request.user.is_authenticated:
        return redirect("authors_pages:auth_page")
    streams = Stream.objects.filter(status="live").select_related("owner")
    return render(
        request,
        "streams/stream_list.html",
        {"streams": streams, "user": request.user},
    )


def stream_create_page(request):
    if not request.user.is_authenticated:
        return redirect("authors_pages:auth_page")
    if request.method == "POST":
        serializer = StreamSerializer(data=request.POST, context={"request": request})
        if serializer.is_valid():
            stream = serializer.save()
            return redirect(stream.get_absolute_url())
        return render(
            request,
            "streams/stream_create.html",
            {
                "errors": serializer.errors,
                "form_data": request.POST,
                "user": request.user,
            },
        )
    return render(request, "streams/stream_create.html", {"user": request.user})


def stream_detail_page(request, pk):
    if not request.user.is_authenticated:
        return redirect("authors_pages:auth_page")
    try:
        stream = find_stream_by_uuid(pk)
    except Stream.DoesNotExist:
        raise Http404()
    return render(
        request,
        "streams/stream_detail.html",
        {
            "stream": stream,
            "is_owner": stream.owner == request.user,
            "user": request.user,
        },
    )
