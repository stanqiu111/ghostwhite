from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from .views import AuthorPublicGetUpdate, AuthorListView, AuthorByUsernameView


app_name = "authors" 

app_name = "authors"

urlpatterns = [
    path("", AuthorListView.as_view(), name="authors-list"),
    path("login/", views.handle_login, name="login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("register/", views.AuthorRegistrationView.as_view(), name="register"),
    path("author_profile/", views.AuthorRetrieveUpdateView.as_view(), name="profile"),
    #path("<uuid:author_id>/entries/", include("entries.urls")),
    path("<str:username>/", AuthorByUsernameView.as_view(), name="author_by_username"),
    
] 