from django.db import models
import uuid


class Node(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host_url = models.URLField()
    is_local = models.BooleanField(
        default=False,
        # unique=True,
    )  # To differentiate between local and external nodes, for every env we only allow one local node
    is_active = models.BooleanField(default=True)
    username = models.CharField(max_length=255, blank=True)  # For remote node auth
    password = models.CharField(max_length=255, blank=True)  # For remote node auth

    def __str__(self):
        return f"{'Local' if self.is_local else 'External'} Node: {self.host_url}"
    
    @property
    def is_authenticated(self):
        """
        Required for DRF's IsAuthenticated permission when using NodeBasicAuthentication.
        Returns True since if a Node object exists, authentication succeeded.
        """
        return True
