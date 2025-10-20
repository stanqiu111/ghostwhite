from django.urls import path
from .views import entry_detail_page, entry_create_page, entry_edit_page

app_name = "entries_pages"

urlpatterns = [
    path(
        "entries/create/",
        entry_create_page,
        name="create-entry-page",
    ),
    path(
        "entries/<uuid:pk>/",
        entry_detail_page,
        name="entry-detail-html"
    ),
    path(
        "entries/<uuid:pk>/edit/",
        entry_edit_page,
        name="entry-edit-page"
    ),
]
