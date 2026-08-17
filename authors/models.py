from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
import uuid
import secrets
from nodes.models import Node
from django.utils import timezone
from django.conf import settings
import django.db.transaction as transaction

# Customize User model and Authentication: https://medium.com/django-unleashed/a-quick-way-to-customize-authentication-backends-user-manager-user-and-permissions-in-django-54f9359e31eb
class AuthorManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("Username is required")

        if 'id' not in extra_fields:
            from utils.fqid import build_fqid
            author_uuid = uuid.uuid4()
            fqid = build_fqid(author_id=str(author_uuid))
            if fqid:
                extra_fields['id'] = fqid

        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("approved", True)  

        if "node" not in extra_fields or extra_fields["node"] is None:
            local_node, _ = Node.objects.get_or_create(
                is_local=True,
                defaults={"host_url": "http://127.0.0.1:8000/"},
            )
            extra_fields["node"] = local_node
            
            
        return self.create_user(username, password, **extra_fields)


# How to override User in Django: https://servidorandycode.medium.com/django-overwrite-user-model-b91bcbbbefa2
class Author(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model

    Uses AbstractBaseUser because for Author model, we only need display_name and not First Name and Last name so we don't user AbstractUser
    """

    id = models.CharField(max_length=150, primary_key=True)
    username = models.CharField(max_length=150, unique=True)
    display_name = models.CharField(max_length=255)
    bio = models.TextField(blank=True)
    github_url = models.URLField(blank=True, null=True)
    image = models.ImageField(upload_to="author_images/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="authors")
    approved = models.BooleanField(default=False)
    last_seen_notifications_at = models.DateTimeField(null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    is_email_verified = models.BooleanField(default=False)

    # required by Django Admin
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["display_name"]

    objects = AuthorManager()

    def __str__(self):
        return self.username

    class Meta:
        indexes = [
            models.Index(
                fields=["approved", "is_active"],
                name="author_approved_active_idx",
            ),
            models.Index(
                fields=["is_active", "is_staff", "is_superuser"],
                name="author_active_flags_idx",
            ),
        ]


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
        indexes = [
            models.Index(fields=['following', 'approved'], name='follow_following_approved_idx'),
            models.Index(fields=['follower', 'approved'], name='follow_follower_approved_idx'),
            models.Index(fields=['follower', 'status'], name='follow_follower_status_idx'),
        ]

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
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Follow.approve] Approving follow {self.id}: follower={self.follower_id}, following={self.following_id}, current_status={self.status}")
        if not self.can_be_decided_by(actor_author):
            logger.error(f"[Follow.approve] Permission denied: can_be_decided_by returned False for actor={actor_author.id}")
            raise PermissionError("Not yours to decide or not pending.")
        logger.info(f"[Follow.approve] Permission check passed, updating status to ACCEPTED")
        self.status = self.ACCEPTED
        self.approved = True
        self.save(update_fields=["status", "approved"])
        logger.info(f"[Follow.approve] Follow {self.id} saved with status={self.status}, approved={self.approved}")
        return self

    @transaction.atomic
    def deny(self, actor_author):
        if not self.can_be_decided_by(actor_author):
            raise PermissionError("Not yours to decide or not pending.")
        self.status = self.DENIED
        self.approved = False
        self.save(update_fields=["status", "approved"])
        return self

    @staticmethod
    def pending_for(followee):
        return Follow.objects.select_related("follower").filter(
            following=followee, status=Follow.PENDING
        )
      
    @staticmethod
    def get_friends(author):
        """
        Get all friends (mutual followers) of an author.
        A friend is someone where:
        - Author follows them (status='accepted')
        - They follow author back (status='accepted')
        """
        # Get all authors that the given author follows (and are accepted)
        following_ids = Follow.objects.filter(
            follower=author,
            status=Follow.ACCEPTED
        ).values_list('following_id', flat=True)

        # Get all authors that follow the given author back (and are accepted)
        # Filter to only those who are also in following_ids (mutual)
        friends = Author.objects.filter(
            id__in=Follow.objects.filter(
                follower_id__in=following_ids,
                following=author,
                status=Follow.ACCEPTED
            ).values_list('follower_id', flat=True)
        )

        return friends

class GitHubIntegration(models.Model):
    """
    Stores an author's GitHub linkage
     - github_username: public github usernam to poll
     - last_synced_at: last time successfully polled events
    """

    author = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="github_integration",
    )
    github_username = models.CharField(max_length=255, help_text="Public github username")
    access_token = models.CharField(max_length=255, blank=True, null=True, help_text="Optional: GitHub personal access token for higher rate limits")
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "GitHub integration"
        verbose_name_plural = "GitHub integrations"

    def __str__(self):
        return f"GitHub Integration for {self.author} ({self.github_username})"


class EmailVerificationToken(models.Model):
    author = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verification_token",
    )
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def create_for(cls, author):
        token_str = secrets.token_urlsafe(32)
        obj, _ = cls.objects.update_or_create(
            author=author,
            defaults={"token": token_str},
        )
        return obj

    def __str__(self):
        return f"Verification token for {self.author.username}"
