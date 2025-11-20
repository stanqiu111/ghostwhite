from django.urls import path
from . import views

app_name = "entries"
urlpatterns = [
    path("entries/", views.EntryListView.as_view(), name="entry-list"),
    path("entries/create/", views.EntryCreateView.as_view(), name="entry-create"),
    path("entries/<uuid:pk>/", views.EntryRetrieveView.as_view(), name="entry-detail"), 

    path("entries/<uuid:pk>/update/", views.EntryUpdateView.as_view(), name="entry-update"),
    path("entries/<uuid:pk>/delete/", views.EntryDeleteView.as_view(), name="entry-delete"),
    #path("<uuid:pk>/image/", views.EntryImageView.as_view(), name="entry-image-by-id"),
    path("entries/<uuid:pk>/addcomments/", views.CommentCreateView.as_view(), name="add_comment"),
    path("entries/<uuid:pk>/comments/<str:comment_id>/", views.CommentUpdateDeleteView.as_view(),name="comment_update_delete"),

    path("entries/<uuid:pk>/like/", views.EntryLikeToggleView.as_view(), name="like_entry"),
    path("entries/<uuid:pk>/comments/<str:comment_id>/like/", views.CommentLikeToggleView.as_view(),name="like_comment"),
]
