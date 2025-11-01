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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)  # for soft delete
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="entries")

    class Meta:
        ordering = [
            "-created_at"
        ]  # we are showing most recent first because in the requirement, we have to display the most recent post

    def is_image_entry(self):
        """Return True if this entry represents a base64 image"""
        return self.content_type in (
            "image/png;base64",
            "image/jpeg;base64",
            "application/base64",
        )
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
            elif name.endswith(".gif"):
                mime = "image/gif"
            elif name.endswith(".webp"):
                mime = "image/webp"
            else:
                mime = "image/jpeg"  # sensible default

            try:
                f = self.image.file
                f.seek(0)
                b = f.read()
                self.content = base64.b64encode(b).decode("ascii")
                self.content_type = f"{mime};base64"
                f.seek(0)
            except Exception:
                # If anything goes wrong, keep the record saveable
                pass
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Entry by {self.author.username} at {self.created_at}"

    def soft_delete(self):
        """We are marking the entry as deleted instead of deleting it because we want to keep the entry in the database so admin/is_staff can see it"""
        self.deleted_at = timezone.now()
        self.save()

    @property
    def like_count(self):
        return self.likes.count()



class Comment(models.Model):
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="comments")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.author.username}: {self.content[:20]}"

    @property
    def like_count(self):
        return self.likes.count()


class EntryLike(models.Model):
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="likes")
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="entrylikes")
    created_at = models.DateTimeField(auto_now_add=True)


class CommentLike(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="likes")
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="commentlikes")
    created_at = models.DateTimeField(auto_now_add=True)
