from django.urls import path, include
from . import views


app_name = "authors"


urlpatterns = [
    path("auth/", views.login_view, name="auth_page"),
    path("logout/", views.logout_view, name="logout"),
    path("<str:username>/settings/", views.author_profile_page, name="author_profile_page"),
    path("<str:username>/", views.author_profile_page, name="author_public_profile"),
    #path("<str:username>/entries/", include("entries.page_urls")),
] 

