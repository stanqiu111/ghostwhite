import uuid
from django.db import models
from django.utils import timezone
from authors.models import Author
from nodes.models import Node

CONTENT_TYPE_CHOICES = [
    ("plain_text", "Plain Text"),
    ("markdown", "Markdown"),
]

VISIBILITY_CHOICES = [
    ("public", "Public"),
    ("unlisted", "Unlisted"),
    ("friends_only", "Friends Only"),
]


# Create your models here.
class Entry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, related_name="entries")
    content = models.TextField()
    content_type = models.CharField(
        max_length=20, choices=CONTENT_TYPE_CHOICES, default="plain_text"
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

    def __str__(self):
        return f"Entry by {self.author.username} at {self.created_at}"

    def soft_delete(self):
        """We are marking the entry as deleted instead of deleting it because we want to keep the entry in the database so admin/is_staff can see it"""
        self.deleted_at = timezone.now()
        self.save()

    def like_count(self):
        return self.entrylike_set.count()


class Comment(models.Model):
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        Author, on_delete=models.CASCADE, related_name="comments"
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.username}: {self.content[:20]}"

    @property
    def like_count(self) -> int:
        return self.commentlike_set.count()


class EntryLike(models.Model):
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE)
    author = models.ForeignKey(
        Author, on_delete=models.CASCADE, related_name="entrylikes"
    )
    created_at = models.DateTimeField(auto_now_add=True)


class CommentLike(models.Model):
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE)
    author = models.ForeignKey(
        Author, on_delete=models.CASCADE, related_name="commentlikes"
    )
    created_at = models.DateTimeField(auto_now_add=True)
