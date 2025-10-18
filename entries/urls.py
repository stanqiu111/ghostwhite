from django.urls import path
from . import views

app_name = "entries"
urlpatterns = [
    path("entries/", views.EntryListView.as_view(), name="entry-list"),
    path("entries/create/", views.EntryCreateView.as_view(), name="entry-create"),
    path("entries/<uuid:pk>/", views.EntryRetrieveView.as_view(), name="entry-detail"),
    path(
        "entries/<uuid:pk>/view/", views.view_entry_detail, name="entry-detail-html"
    ),  # HTML page
    path(
        "entries/<uuid:pk>/update/",
        views.EntryUpdateView.as_view(),
        name="entry-update",
    ),
    path(
        "entries/<uuid:pk>/delete/",
        views.EntryDeleteView.as_view(),
        name="entry-delete",
    ),
]
