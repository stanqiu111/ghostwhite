from django.urls import path, include
from django.views.generic import RedirectView
from . import views
from . import admin_views


app_name = "authors"


urlpatterns = [
    path("auth/", views.login_view, name="auth_page"),
    path("login/", RedirectView.as_view(url="/authors/auth/"), name="login_redirect"),
    path("verify-email/<str:token>/", views.verify_email_view, name="verify_email"),
    path("logout/", views.logout_view, name="logout"),
    path("remote-nodes/", views.remote_nodes_page, name="remote_nodes_page"),
    path("sync-repos/", views.SyncMyGithubReposView.as_view(), name="sync_github_repos_page"),
    path("follow-requests/", views.FollowRequestsListView.as_view(), name="follow-requests_page"),
    path("settings/", views.settings_view, name="settings_page"),
    # Must stay above the "<str:username>/" catch-all below.
    path("staff/", admin_views.admin_portal_page, name="admin_portal"),
    path("<str:username>/settings/", views.author_profile_page, name="author_profile_page"),
    path("<str:username>/", views.author_profile_page, name="author_public_profile"),
    #path("<str:username>/entries/", include("entries.page_urls")),
] 

