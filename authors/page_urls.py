from django.urls import path, include
from . import views


app_name = "authors"


urlpatterns = [
    path("auth/", views.login_view, name="auth_page"),
    path("logout/", views.logout_view, name="logout"),
    # explicit page for linking GitHub account (must come before the username catch-all)
    path("link_github/", views.link_github_view, name="link_github"),
    path("<str:username>/", views.author_profile_page, name="author_profile_page"),
    #path("<str:username>/entries/", include("entries.page_urls")),
] 

