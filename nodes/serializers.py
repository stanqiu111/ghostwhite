from rest_framework import serializers
from .models import Node


class NodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Node
        fields = [
            "id",
            "host_url",
            "is_local",
        ]
        read_only_fields = ["id"]
