import uuid
from django.db import models
from django.utils import timezone
from authors.models import Author
from nodes.models import Node

CONTENT_TYPE_CHOICES = [
    ("plain_text", "Plain Text"),
    ("markdown", "Markdown"),
    ("image/png;base64", "Image PNG (base64)"),
    ("image/jpeg;base64", "Image JPEG (base64)"),
    ("application/base64", "Base64 (other image)"),
]

VISIBILITY_CHOICES = [
    ("public", "Public"),
    ("unlisted", "Unlisted"),
    ("friends_only", "Friends Only"),
    ("DELETED", "Deleted"),  # for soft delete
]


class Entry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="entries")
    content = models.TextField(blank=True)
    content_type = models.CharField(
        max_length=64, choices=CONTENT_TYPE_CHOICES, default="plain_text"
    )
    visibility = models.CharField(
        max_length=20, choices=VISIBILITY_CHOICES, default="public"
    )
    image = models.ImageField(upload_to="entry_images/", null=True, blank=True)
    # Source metadata (for third-party origins such as GitHub)
    source = models.CharField(max_length=50, default="manual", db_index=True, blank=True, null=True)
    source_id = models.CharField(max_length=255, null=True, blank=True)
    source_url = models.CharField(max_length=512, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)  # for soft delete
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="entries")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_id"],
                name="unique_source_sourceid"
            )
        ]
        indexes = [
            models.Index(
                fields=["author", "deleted_at"],
                name="entry_author_deleted_idx",
            ),
            models.Index(
                fields=["visibility", "created_at"],
                name="entry_visibility_created_idx",
            ),
        ]

    def is_image_entry(self):
        """Return True if this entry represents a base64 image"""
        return self.content_type in (
            "image/png;base64",
            "image/jpeg;base64",
            "application/base64",
        )
    
    @property
    def remote_image_url(self):
        """Remote image URL for remote entries."""
        if self.source == "remote" and self.source_id:
            return self.source_id
        return None
    
    @remote_image_url.setter
    def remote_image_url(self, value):
        """Set remote image URL."""
        if self.source == "remote":
            self.source_id = value
    @property
    def image_mime(self):
        """Return MIME type part (e.g. image/png)"""
        if self.content_type and ";" in self.content_type:
            return self.content_type.split(";", 1)[0]
        return None
    
    def save(self, *args, **kwargs):
        # If a file was uploaded and we don't yet have a base64 payload, generate it
        if self.image and not self.content:
            import base64
            name = (self.image.name or "").lower()
            if name.endswith((".jpg", ".jpeg")):
                mime = "image/jpeg"
            elif name.endswith(".png"):
                mime = "image/png"
            else:
                mime = "application/base64"  

            try:
                f = self.image.file
                f.seek(0)
                b = f.read()
                self.content = base64.b64encode(b).decode("ascii")
                self.content_type = f"{mime};base64"
                f.seek(0)
            except Exception as e:
                print("Base64 encode failed:", e)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Entry by {self.author.username} at {self.created_at}"

    def soft_delete(self):
        """We are marking the entry as deleted instead of deleting it because we want to keep the entry in the database so admin/is_staff can see it"""
        self.visibility = "DELETED"
        self.deleted_at = timezone.now()
        self.save()

    @property
    def like_count(self):
        return self.likes.count()
    
    def get_absolute_url(self) -> str:
        """Canonical reader URL (used by 'Copy link')."""
        # if you have a named URL, prefer reverse("entry-detail", args=[self.id])
        return f"/entries/{self.id}/"

    @property
    def is_shareable(self) -> bool:
        """Publicly viewable by URL only (public/unlisted)."""
        return (self.visibility or "").lower() in {"public", "unlisted"}

    def absolute_url(self, request=None) -> str:
        """
        Optional: full URL with scheme+host when you have a request.
        Use in emails, API, etc.
        """
        path = self.get_absolute_url()
        if request is None:
            return path
        scheme = "https" if request.is_secure() else "http"
        return f"{scheme}://{request.get_host()}{path}"




class Comment(models.Model):
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="comments")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    source_url = models.URLField(blank=True, null=True)

    def __str__(self):
        return f"{self.author.username}: {self.content[:20]}"

    @property
    def like_count(self):
        return self.likes.count()

    class Meta:
        indexes = [
            models.Index(
                fields=["entry", "created_at"],
                name="comment_entry_created_idx",
            )
        ]


class EntryLike(models.Model):
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="likes")
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="entrylikes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "author"],
                name="unique_entry_author_like",
            )
        ]
        indexes = [
            models.Index(
                fields=["author", "created_at"],
                name="entrylike_author_created_idx",
            )
        ]


class CommentLike(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="likes")
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="commentlikes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["comment", "author"],
                name="unique_comment_author_like",
            )
        ]
        indexes = [
            models.Index(
                fields=["author", "created_at"],
                name="commentlike_author_created_idx",
            )
        ]
