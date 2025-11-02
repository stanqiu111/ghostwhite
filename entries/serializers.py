from rest_framework import serializers
from .models import Entry, Comment, CommentLike, EntryLike
from authors.serializers import AuthorSerializer
from nodes.serializers import NodeSerializer
from django.urls import reverse

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
    user_has_liked_comment = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            "id",
            "author",
            "content",
            "likes",
            "like_count",
            "created_at",
            "user_has_liked_comment"
        ]

    def get_user_has_liked_comment(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Use a more efficient approach - check if the user's ID is in the likes
            return obj.likes.filter(author=request.user).exists()
        return False

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
    is_image = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Entry
        fields = [
            "id",
            "author",
            "content",
            "content_type",
            "visibility",
            "created_at",
            "updated_at",
            "deleted_at",
            "node",
            "like_count", 
            "likes",
            "comments",
            "is_image",
            "image_url",    
        ]

    def get_is_image(self, obj):
        return bool(getattr(obj, "is_image_entry") and obj.is_image_entry())

    def get_image_url(self, obj):
        # Only expose the proxy image URL for base64 image entries
        if not (getattr(obj, "is_image_entry") and obj.is_image_entry()):
            return None
        request = self.context.get("request")
        url = reverse(
            "authors:entry-image-by-id",
            kwargs={"author_id": obj.author.id, "pk": obj.id}
        )
        return request.build_absolute_uri(url) if request else url



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
        extra_kwargs = {
            "content_type": {"required": False},
            "content": {"required": False, "allow_blank": True},
            "image": {"required": False},
        }

    def validate(self, attrs):
        """
        Creation: require at least one of content or image
        Update: allow clearing content if there's an existing image on the instance or a new image in attrs
        """
        content = attrs.get("content")
        image = attrs.get("image")

        # Update case: self.instance is present
        if getattr(self, "instance", None) is not None:
            # If no new image provided and content is empty/None, permit update as long as the instance already has an image
            has_existing_image = bool(getattr(self.instance, "image", None))
            content_empty = (content is None) or (isinstance(content, str) and content.strip() == "")
            if content_empty and not image and not has_existing_image:
                raise serializers.ValidationError("Either 'content' or 'image' must be provided.")
            return attrs

        # Create case
        if (content is None or (isinstance(content, str) and content.strip() == "")) and not image:
            raise serializers.ValidationError("Either 'content' or 'image' must be provided.")
        return attrs

    def create(self, validated_data):
        return super().create(validated_data)
