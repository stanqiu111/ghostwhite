from rest_framework import serializers
from .models import Entry, Comment, CommentLike, EntryLike
from authors.serializers import AuthorSerializer
from nodes.serializers import NodeSerializer

class CommentLikeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommentLike
        fields = [
            "id",
            "created_at",
        ]
class CommentSerializer(serializers.ModelSerializer):
    author = AuthorSerializer()
    likes = CommentLikeSerializer(many=True, read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    class Meta:
        model = Comment
        fields = [
            "id",
            "author",
            "content",
            "likes",
            "like_count",
            "created_at",
        ]

class EntryLikeSerializer(serializers.ModelSerializer):
    author = AuthorSerializer()
    class Meta:
        model = EntryLike
        fields = [
            "id",
            "created_at",
            "author"
        ]


class EntryRetrieveSerializer(serializers.ModelSerializer):
    author = AuthorSerializer()
    node = NodeSerializer()
    comments = CommentSerializer(many=True)
    likes = EntryLikeSerializer(many=True, read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    image = serializers.SerializerMethodField()
    
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
            "like_count", 
            "likes",
            "comments",    
        ]
    def get_image(self, obj):
        return obj.image.url if obj.image else None


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
