from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from .views import AuthorListView, AuthorByUsernameView, AuthorByIdView
from .views import FollowRequestsListView, FollowDecisionView
from django.views.generic import TemplateView
from entries.views import EntryImageView


app_name = "authors"

urlpatterns = [
    path("", AuthorListView.as_view(), name="authors-list"),
    path("login/", views.handle_login, name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("register/", views.AuthorRegistrationView.as_view(), name="register"),
    path("author_profile/", views.AuthorRetrieveUpdateView.as_view(), name="profile"),
    #path("<uuid:author_id>/entries/", include(("entries.urls", "entries"), namespace="authors_entries")),
    path("<uuid:author_id>/entries/<uuid:pk>/image/", EntryImageView.as_view(), name="entry-image-by-id"),
    path("<uuid:author_id>/follow/", views.FollowRequestView.as_view(), name="follow-request"),
    path("follow-requests/", FollowRequestsListView.as_view(), name="follow-requests"),
    path("follows/<uuid:pk>/decision/", FollowDecisionView.as_view(), name="follow-decision"),
    path("<uuid:author_id>/", AuthorByIdView.as_view(), name="author_by_id"),
    path("<str:username>/", AuthorByUsernameView.as_view(), name="author_by_username"),
    path("authors/<str:username>/", TemplateView.as_view(template_name="authors/author_public.html"), name="author_public_page"),
    path("logout/", views.logout_view, name="logout"),
]
