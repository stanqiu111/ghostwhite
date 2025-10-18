from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views

app_name = "authors" 

urlpatterns = [
    path("login/", views.handle_login, name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("register/", views.AuthorRegistrationView.as_view(), name="register"),
    path("author_profile/", views.AuthorRetrieveUpdateView.as_view(), name="profile"),
    path("auth/", views.login_view, name="auth_page"),
    path("logout/", views.logout_view, name="logout"),
    path("<str:username>/", views.author_profile_page, name="author_profile_page"),
    path("<str:username>/json/", views.author_profile_json, name="pauthor_rofile_json"),
    path("<str:username>/avatar/", views.author_avatar_upload, name="author_avatar_upload"),
]
