from django.urls import path
from . import views

app_name = "streams"
urlpatterns = [
    path("streams/", views.StreamListCreateView.as_view(), name="stream-list-create"),
    path("streams/<uuid:pk>/", views.StreamRetrieveView.as_view(), name="stream-detail"),
    path("streams/<uuid:pk>/end/", views.StreamEndView.as_view(), name="stream-end"),
    path("streams/<uuid:pk>/signals/", views.StreamSignalView.as_view(), name="stream-signals"),
    path("streams/<uuid:pk>/bullets/", views.StreamBulletView.as_view(), name="stream-bullets"),
]
