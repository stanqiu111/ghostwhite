from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from .views import AuthorPublicGetUpdate, AuthorListView, AuthorByUsernameView
from .views import FollowRequestView, FollowRequestsListView, FollowDecisionView
from .views import SyncMyGithubReposView
from django.views.generic import TemplateView
from entries.views import EntryImageView
from inbox.views import InboxPostView


app_name = "authors"

urlpatterns = [
    path("", AuthorListView.as_view(), name="authors-list"),
    path("login/", views.handle_login, name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("register/", views.AuthorRegistrationView.as_view(), name="register"),
    path("author_profile/", views.AuthorRetrieveUpdateView.as_view(), name="profile"),
    #path("<str:author_id>/entries/", include(("entries.urls", "entries"), namespace="authors_entries")),
    path("<str:author_id>/entries/<uuid:pk>/image/", EntryImageView.as_view(), name="entry-image-by-id"),
    path("<str:author_id>/inbox", InboxPostView.as_view(), name="inbox"),
    path("<str:author_id>/follow/", views.FollowRequestView.as_view(), name="follow-request"),
    path("follow-requests/", FollowRequestsListView.as_view(), name="follow-requests"),
    path("follows/<uuid:pk>/decision/", FollowDecisionView.as_view(), name="follow-decision"),
    path("sync-repos/", views.SyncMyGithubReposView.as_view(), name="sync_github_repos"),
    path("<str:author_id>/", AuthorPublicGetUpdate.as_view(), name="author_public"),
    # static/explicit routes must come before the catch-all username route
    path("logout/", views.logout_view, name="logout"),
    path("<str:username>/", AuthorByUsernameView.as_view(), name="author_by_username"),
    path("authors/<str:username>/", TemplateView.as_view(template_name="authors/author_public.html"), name="author_public_page"),
]
