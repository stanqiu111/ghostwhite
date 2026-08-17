from django.urls import path
from .views import stream_list_page, stream_create_page, stream_detail_page

app_name = "streams_pages"

urlpatterns = [
    path(
        "streams/",
        stream_list_page,
        name="stream-list-page",
    ),
    path(
        "streams/create/",
        stream_create_page,
        name="stream-create-page",
    ),
    path(
        "streams/<uuid:pk>/",
        stream_detail_page,
        name="stream-detail-page",
    ),
]
