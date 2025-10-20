from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
import uuid
from nodes.models import Node
from django.utils import timezone
import django.db.transaction as transaction


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

        if "node" not in extra_fields or extra_fields["node"] is None:
            local_node, _ = Node.objects.get_or_create(is_local=True, defaults={"host": "http://127.0.0.1:8000/"})
            extra_fields["node"] = local_node
            
        return self.create_user(username, password, **extra_fields)


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
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="authors")

    # required by Django Admin
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["display_name"]

    objects = AuthorManager()

    def __str__(self):
        return self.username


class Follow(models.Model):
    """
        follower: the author who is following
        following: the author being followed
        approved: whether the follow request is approved or not
        status: pending, accepted, denied
        created_at: when the follow request was created
        unique_together: prevent duplicate follow requests
    """
        
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    follower = models.ForeignKey(Author, related_name='following', on_delete=models.CASCADE)
    following = models.ForeignKey(Author, related_name='followers', on_delete=models.CASCADE)

    approved = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    PENDING, ACCEPTED, DENIED = "pending", "accepted", "denied"
    STATUS_CHOICES = [(PENDING, "Pending"), (ACCEPTED, "Accepted"), (DENIED, "Denied")]
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)

    class Meta:
        unique_together = ('follower', 'following') #Prevent duplicate follow requests

    def __str__(self):
        return f"{self.follower} follows {self.following}"

    # Check if the follow request can be approved or denied by the actor_author
    # Only the followee can approve or deny the request and only if the request is pending
    def can_be_decided_by(self, actor_author) -> bool:
        return self.following_id == actor_author.id and self.status == self.PENDING


    """
    Using transaction.atomic to ensure that the approve and deny methods are atomic operations.
    This means that if any part of the operation fails, the entire operation is rolled back and
    the database is left in a consistent state.
    """
    @transaction.atomic
    def approve(self, actor_author):
        if not self.can_be_decided_by(actor_author):
            raise PermissionError("Not yours to decide or not pending.")
        self.status = self.ACCEPTED
        self.decided_at = timezone.now()
        self.save(update_fields=["status", "decided_at"])
        return self

    @transaction.atomic
    def deny(self, actor_author):
        if not self.can_be_decided_by(actor_author):
            raise PermissionError("Not yours to decide or not pending.")
        self.status = self.DENIED
        self.decided_at = timezone.now()
        self.save(update_fields=["status", "decided_at"])
        return self

    @staticmethod
    def pending_for(followee):
        return Follow.objects.select_related("follower").filter(
            following=followee, status=Follow.PENDING
        )