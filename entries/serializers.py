from rest_framework import serializers
from .models import Entry
from authors.serializers import AuthorSerializer
from nodes.serializers import NodeSerializer


class EntryRetrieveSerializer(serializers.ModelSerializer):
    author = AuthorSerializer()
    node = NodeSerializer()

    class Meta:
        model = Entry
        fields = [
            "id",
            "author",
            "content",
            "content_type",
            "visibility",
            "image",
            "created_at",
            "updated_at",
            "deleted_at",
            "node",
        ]


class EntryCreateSerializer(serializers.ModelSerializer):
    """Having a separate serializer for creating because we don't need all info for creating an entry"""

    class Meta:
        model = Entry
        fields = [
            "id",
            "content",
            "content_type",
            "visibility",
            "image",
        ]
