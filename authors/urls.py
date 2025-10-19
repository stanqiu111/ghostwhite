from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from .views import AuthorPublicGetUpdate, AuthorListView

app_name = "authors" 

urlpatterns = [
    path("", AuthorListView.as_view(), name="authors-list"),
    path("login/", views.handle_login, name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("register/", views.AuthorRegistrationView.as_view(), name="register"),
    path("author_profile/", views.AuthorRetrieveUpdateView.as_view(), name="profile"),
    path("<uuid:author_id>/", AuthorPublicGetUpdate.as_view(), name="author_public"),
    path("<str:username>/json/", views.author_profile_json, name="author_rofile_json"),
    path("<str:username>/avatar/", views.author_avatar_upload, name="author_avatar_upload"),
    
]