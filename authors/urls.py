from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from .views import AuthorPublicGetUpdate, AuthorListView, AuthorByUsernameView, AuthorEntriesView

app_name = "authors"

urlpatterns = [
    path("", AuthorListView.as_view(), name="authors-list"),
    path("login/", views.handle_login, name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("register/", views.AuthorRegistrationView.as_view(), name="register"),
    path("author_profile/", views.AuthorRetrieveUpdateView.as_view(), name="profile"),
    path("<uuid:author_id>/", AuthorPublicGetUpdate.as_view(), name="author_public"),
    path("<uuid:author_id>/entries/", AuthorEntriesView.as_view(), name="author_entries"),
    path("<str:username>/", AuthorByUsernameView.as_view(), name="author_by_username"),
    path("auth/", views.login_view, name="auth_page"),
    path("logout/", views.logout_view, name="logout"),
]
