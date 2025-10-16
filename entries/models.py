from django.db import models
from datetime import datetime

# Create your models here.
class Posting(models.Model):
    posting_text = models.CharField(max_length=200)    # Store the posting in a char field in the database
    pub_date = models.DateTimeField("date published", default=datetime.now)   # Store the published date in a datetime field in the database

class Comment(models.Model):
    # FK to the question (name can be anything; using "question" is clear)
    posting = models.ForeignKey(Posting, on_delete=models.CASCADE, related_name= "comments")
    username = models.CharField(max_length=32)         # ≤ 32 chars
    created_at = models.DateTimeField(auto_now_add=True)
    content = models.TextField()

    def __str__(self):
        return f"{self.username}: {self.content[:20]}"
    
    @property
    def like_count(self) -> int:
        return self.commentlike_set.count()
    
class EntryLike(models.Model):
    posting = models.ForeignKey(Posting, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    fingerprint = models.CharField(max_length=64, db_index=True)
    
    class Meta:
        unique_together = ("Posting", "fingerprint")

class CommentLike(models.Model):
    comment = models.ForeignKey(Comment,on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    fingerprint = models.CharField(max_length=64, db_index=True)
    
    class Meta:
        unique_together = ("comment", "fingerprint")
