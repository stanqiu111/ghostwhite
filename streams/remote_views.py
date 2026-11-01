"""Federation endpoints and same-origin home-node viewer endpoints."""
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from nodes.models import Node
from .federation import (
    FederatedStreamAuthentication, MAX_CURSOR, RemoteBulletSerializer,
    RemoteStreamError, RemoteStreamSerializer, polling_response, remote_request,
)
from .ice import ice_configuration
from .serializers import StreamBulletMessageSerializer, StreamSignalSerializer
from .views import StreamListCreateView, StreamRetrieveView, StreamSignalView, StreamBulletView


class FederatedStreamListView(StreamListCreateView):
    authentication_classes = [FederatedStreamAuthentication]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        return super().get_queryset().filter(node__is_local=True)[:100]


class FederatedStreamRetrieveView(StreamRetrieveView):
    authentication_classes = [FederatedStreamAuthentication]

    def get_object(self):
        stream = super().get_object()
        if not stream.node.is_local:
            raise Http404()
        return stream


class FederatedStreamSignalView(StreamSignalView):
    authentication_classes = [FederatedStreamAuthentication]

    def get_stream(self, pk):
        stream = super().get_stream(pk)
        if not stream.node.is_local:
            raise Http404()
        return stream


class FederatedStreamBulletView(StreamBulletView):
    authentication_classes = [FederatedStreamAuthentication]

    def get_live_stream(self, pk):
        stream, gone = super().get_live_stream(pk)
        if not stream.node.is_local:
            raise Http404()
        return stream, gone


def remote_node(node_id):
    node = get_object_or_404(Node, pk=node_id, is_local=False)
    if not node.is_active or node.is_disabled:
        raise DjangoPermissionDenied("This remote node is disabled.")
    return node


class StreamIceView(APIView):
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.node.is_local or not request.user.is_active or not request.user.approved:
            raise PermissionDenied("An approved local account is required.")
        return Response(ice_configuration(), headers={"Cache-Control": "private, no-store"})


def metadata(node, data, pk=None):
    serializer = RemoteStreamSerializer(data=data, context={"node": node})
    if not serializer.is_valid():
        raise RemoteStreamError("The remote node returned incompatible stream metadata.")
    if pk is not None and serializer.validated_data["serial"] != pk:
        raise RemoteStreamError("The remote node returned a different stream.")
    return serializer


class RemoteStreamProxyView(APIView):
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, node_id, pk=None, action=""):
        node = remote_node(node_id)
        params = {}
        if action == "signals":
            if request.query_params.get("role") != "viewer":
                raise PermissionDenied("Remote users can only poll as viewers.")
            peer_id = serializers.CharField(max_length=64).run_validation(request.query_params.get("peer_id"))
            params = {"role": "viewer", "peer_id": peer_id}
        elif action == "bullets":
            if "after" in request.query_params:
                params["after"] = serializers.IntegerField(min_value=0, max_value=MAX_CURSOR).run_validation(request.query_params["after"])
            else:
                params["latest"] = "1"
        suffix = f"{pk}/" if pk else ""
        if action:
            suffix += action + "/"
        try:
            data, status = remote_request(node, request.user, "GET", suffix, params=params)
            if pk is None:
                if data.get("type") != "streams" or not isinstance(data.get("items"), list) or len(data["items"]) > 100:
                    raise RemoteStreamError("The remote node does not support stream discovery.")
                items = []
                for item in data["items"]:
                    item = dict(metadata(node, item).data)
                    item["watchUrl"] = reverse("streams_pages:remote-stream-detail", args=[node.pk, item["serial"]])
                    items.append(item)
                data = {"type": "streams", "items": items}
            elif not action:
                data = metadata(node, data, pk).data
            else:
                data = polling_response(action, data, params)
            return Response(data, status=status)
        except RemoteStreamError as error:
            return Response({"detail": str(error)}, status=error.status)

    def post(self, request, node_id, pk=None, action=""):
        node = remote_node(node_id)
        if not isinstance(request.data, dict):
            raise serializers.ValidationError("A JSON object is required.")
        if action == "signals":
            if request.data.get("direction") != "to_streamer":
                raise PermissionDenied("Remote users cannot broadcast into this stream.")
            serializer = StreamSignalSerializer(data=request.data, context={
                "request": request, "stream": SimpleNamespace(owner=None),
            })
        elif action == "bullets":
            serializer = StreamBulletMessageSerializer(data=request.data)
        else:
            raise PermissionDenied("Remote users cannot create or end streams here.")
        serializer.is_valid(raise_exception=True)
        try:
            data, status = remote_request(node, request.user, "POST", f"{pk}/{action}/", data=serializer.validated_data)
            if action == "signals":
                expected = {"type": "signal", "kind": serializer.validated_data["kind"],
                            "peer_id": serializer.validated_data["peer_id"]}
                if any(data.get(key) != value for key, value in expected.items()):
                    raise RemoteStreamError("The remote node returned an invalid signal acknowledgement.")
                data = expected
            else:
                reply = RemoteBulletSerializer(data=data)
                if not reply.is_valid():
                    raise RemoteStreamError("The remote node returned an invalid chat acknowledgement.")
                data = reply.data
            return Response(data, status=status)
        except RemoteStreamError as error:
            return Response({"detail": str(error)}, status=error.status)


def remote_stream_detail_page(request, node_id, pk):
    if not request.user.is_authenticated:
        return redirect("authors_pages:auth_page")
    node = remote_node(node_id)
    try:
        data, _ = remote_request(node, request.user, "GET", f"{pk}/")
        data = metadata(node, data, pk).validated_data
    except RemoteStreamError as error:
        return render(request, "streams/remote_unavailable.html", {"error": str(error)}, status=error.status)
    stream = SimpleNamespace(
        serial=data["serial"], title=data["title"], description=data["description"],
        status=data["status"], is_live=data["status"] == "live",
        started_at=data["startedAt"], ended_at=data["endedAt"],
        owner=SimpleNamespace(display_name=data["owner"]["displayName"], username="Remote host"),
    )
    return render(request, "streams/stream_detail.html", {
        "stream": stream, "is_owner": False, "user": request.user,
        "remote_origin": node.host_url,
        "stream_api_base": reverse("streams_api:remote-stream", args=[node.pk, pk]),
        "ice_config": ice_configuration(),
    })
