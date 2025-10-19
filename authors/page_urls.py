from django.urls import path
from . import views


app_name = "authors_pages"


urlpatterns = [
    path("auth/", views.login_view, name="auth_page"),
    path("logout/", views.logout_view, name="logout"),
    path("<str:username>/", views.author_profile_page, name="author_profile_page"),
] 