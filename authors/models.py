from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
import uuid


# Customize User model and Authentication: https://medium.com/django-unleashed/a-quick-way-to-customize-authentication-backends-user-manager-user-and-permissions-in-django-54f9359e31eb
class AuthorManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("Username is required")

        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        return self.create_user(username, password, **extra_fields)


# Create your models here.
# How to override User in Django: https://servidorandycode.medium.com/django-overwrite-user-model-b91bcbbbefa2
class Author(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model

    Uses AbstractBaseUser because for Author model, we only need display_name and not First Name and Last name so we don't user AbstractUser
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    display_name = models.CharField(max_length=255)
    bio = models.TextField(blank=True)
    github_url = models.URLField(blank=True)
    image = models.ImageField(upload_to="author_images/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # required by Django Admin
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["display_name"]

    objects = AuthorManager()

    def __str__(self):
        return self.username
