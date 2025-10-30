from rest_framework import serializers
from .models import Entry, Comment, CommentLike, EntryLike
from authors.serializers import AuthorSerializer
from nodes.serializers import NodeSerializer
from utils.serializers import UrlBuildingMixin
class CommentLikeSerializer(UrlBuildingMixin, serializers.ModelSerializer):
    id = serializers.SerializerMethodField()

    class Meta:
        model = CommentLike
        fields = [
            "id",
            "created_at",
        ]

    def get_id(self, obj):
        return self.build_full_url(f"/api/authors/{obj.author.id}/liked/{obj.id}")

class CommentSerializer(UrlBuildingMixin, serializers.ModelSerializer):
    author = AuthorSerializer()
    likes = CommentLikeSerializer(many=True, read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    user_has_liked_comment = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    serial = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "serial",
            "author",
            "content",
            "likes",
            "like_count",
            "created_at",
            "user_has_liked_comment"
        ]

    def get_id(self, obj):
        return self.build_full_url(f"/api/authors/{obj.author.id}/commented/{obj.id}")

    def get_serial(self, obj):
        return str(obj.id)

    def get_user_has_liked_comment(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(author=request.user).exists()
        return False

class EntryLikeSerializer(UrlBuildingMixin, serializers.ModelSerializer):
    author = AuthorSerializer()
    id = serializers.SerializerMethodField()
    class Meta:
        model = EntryLike
        fields = [
            "id",
            "created_at",
            "author"
        ]

    def get_id(self, obj):
        return self.build_full_url(f"/api/authors/{obj.author.id}/liked/{obj.id}")

class EntryRetrieveSerializer(UrlBuildingMixin, serializers.ModelSerializer):
    author = AuthorSerializer()
    node = NodeSerializer()
    comments = CommentSerializer(many=True)
    likes = EntryLikeSerializer(many=True, read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    id = serializers.SerializerMethodField()
    serial = serializers.SerializerMethodField()

    class Meta:
        model = Entry
        fields = [
            "id",
            "serial",
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

    def get_id(self, obj):
        return self.build_full_url(f"/api/authors/{obj.author.id}/entries/{obj.id}")

    def get_serial(self, obj):
        return str(obj.id)


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
