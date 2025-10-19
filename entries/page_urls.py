from django.urls import path
from django.views.generic import TemplateView
from .views import view_entry_detail

app_name = "entries_pages"

urlpatterns = [
    path(
        "entries/create/",
        TemplateView.as_view(template_name="entries/create_entry.html"),
        name="create-entry-page",
    ),
    path(
        "entries/<uuid:pk>/view/", view_entry_detail, name="entry-detail-html"
    ),  # HTML page
]
