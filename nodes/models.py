from django.db import models
import uuid


# Create your models here.
class Node(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host_url = models.URLField()
    is_local = models.BooleanField(
        default=False,
        unique=True,
    )  # To differentiate between local and external nodes, for every env we only allow one local node
    api_key = models.CharField(max_length=255, blank=True)  # For external API calls

    def __str__(self):
        return f"{'Local' if self.is_local else 'External'} Node: {self.host_url}"
