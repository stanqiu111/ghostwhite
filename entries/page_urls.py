from django.urls import path
from django.views.generic import TemplateView
from .views import entries_feed_page

app_name = "entries_pages"

urlpatterns = [
    path(
        "entries/create/",
        TemplateView.as_view(template_name="entries/create_entry.html"),
        name="create-entry-page"),
    path("entries/", entries_feed_page, name="entries-feed-page"),
]