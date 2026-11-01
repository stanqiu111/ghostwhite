from django.urls import path
from . import views
from . import remote_views

app_name = "streams"
urlpatterns = [
    path("streams/ice/", remote_views.StreamIceView.as_view(), name="stream-ice"),
    path("federation/streams/", remote_views.FederatedStreamListView.as_view(), name="federated-stream-list"),
    path("federation/streams/<uuid:pk>/", remote_views.FederatedStreamRetrieveView.as_view(), name="federated-stream"),
    path("federation/streams/<uuid:pk>/signals/", remote_views.FederatedStreamSignalView.as_view(), name="federated-signals"),
    path("federation/streams/<uuid:pk>/bullets/", remote_views.FederatedStreamBulletView.as_view(), name="federated-bullets"),
    path("remote-nodes/<uuid:node_id>/streams/", remote_views.RemoteStreamProxyView.as_view(), name="remote-stream-list"),
    path("remote-nodes/<uuid:node_id>/streams/<uuid:pk>/", remote_views.RemoteStreamProxyView.as_view(), name="remote-stream"),
    path("remote-nodes/<uuid:node_id>/streams/<uuid:pk>/signals/", remote_views.RemoteStreamProxyView.as_view(), {"action": "signals"}, name="remote-signals"),
    path("remote-nodes/<uuid:node_id>/streams/<uuid:pk>/bullets/", remote_views.RemoteStreamProxyView.as_view(), {"action": "bullets"}, name="remote-bullets"),
    path("streams/", views.StreamListCreateView.as_view(), name="stream-list-create"),
    path("streams/<uuid:pk>/", views.StreamRetrieveView.as_view(), name="stream-detail"),
    path("streams/<uuid:pk>/end/", views.StreamEndView.as_view(), name="stream-end"),
    path("streams/<uuid:pk>/signals/", views.StreamSignalView.as_view(), name="stream-signals"),
    path("streams/<uuid:pk>/bullets/", views.StreamBulletView.as_view(), name="stream-bullets"),
]
