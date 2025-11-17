from rest_framework import serializers
from .models import Entry, Comment, CommentLike, EntryLike
from authors.serializers import AuthorSerializer
from nodes.serializers import NodeSerializer
from django.urls import reverse
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
        if obj.source_url:
            return obj.source_url
        return self.build_full_url(f"/api/authors/{obj.author.id}/commented/{obj.id}")

    def get_serial(self, obj):
        return str(obj.id)

    def get_user_has_liked_comment(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.likes.filter(author=request.user).exists()
        return False

class CommentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ["id", "content"]  # keep it minimal

    def validate_content(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Comment cannot be empty.")
        return value
    
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
    is_image = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    image = serializers.ImageField(read_only=True)
    visibility = serializers.SerializerMethodField()

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
            "created_at",
            "updated_at",
            "deleted_at",
            "node",
            "like_count", 
            "likes",
            "comments",
            "image",
            "is_image",
            "image_url",    
            "comments",    
            "source",
            "source_url",
        ]
    def get_comments(self, obj: Entry):
        request = self.context.get("request")
        # start with a selectable, ordered queryset for efficiency/consistency
        qs = obj.comments.select_related("author").order_by("-created_at")

        # Staff can see everything
        if request and getattr(request.user, "is_staff", False):
            return CommentSerializer(qs, many=True, context=self.context).data

        visibility = (obj.visibility or "").lower()
        if visibility == "friends_only":
            # Anonymous: hide all
            if not request or not request.user.is_authenticated:
                return []

            viewer = request.user
            # Author sees all
            if viewer == obj.author:
                pass  # keep qs
            # Friends see all
            elif self._is_friend(obj.author, viewer):
                pass  # keep qs
            else:
                # Not a friend: show only viewer's own comments
                qs = qs.filter(author=viewer)

        # public/unlisted: no extra filtering
        return CommentSerializer(qs, many=True, context=self.context).data

    @staticmethod
    def _is_friend(owner, viewer) -> bool:
        """
        Mutual accepted follow == friends.
        Adjust import/model/field names to your project if needed.
        """
        # Delay import to avoid circulars if your Follow model is in another app
        from authors.models import Follow  # <-- change path if different
        return (
            Follow.objects.filter(follower=viewer, followee=owner, status="accepted").exists()
            and
            Follow.objects.filter(follower=owner, followee=viewer, status="accepted").exists()
        )

    def get_id(self, obj):
        return self.build_full_url(f"/api/authors/{obj.author.id}/entries/{obj.id}")

    def get_serial(self, obj):
        return str(obj.id)

    def get_is_image(self, obj):
        """
        Need to determine if this entry is an image since entries store images either as uploaded files (entry.image)
        or as base64-encoded str in entry.content
        """
        if getattr(obj, "image", None):
            return True

        ctype = (getattr(obj, "content_type", "") or "").lower()
        if "base64" in ctype or ctype.startswith("image/"):
            return True

        if hasattr(obj, "is_image_entry") and callable(obj.is_image_entry):
            try:
                return bool(obj.is_image_entry())
            except Exception:
                pass

        return False


    def get_image_url(self, obj):
        if obj.remote_image_url:
            return obj.remote_image_url
        # Only expose the proxy image URL for base64 image entries
        if not (getattr(obj, "is_image_entry") and obj.is_image_entry()):
            return None
        request = self.context.get("request")
        url = reverse(
            "authors:entry-image-by-id",
            kwargs={"author_id": obj.author.id, "pk": obj.id}
        )
        return request.build_absolute_uri(url) if request else url

    def get_visibility(self, obj):
        request = self.context.get("request")
        if request and getattr(request.user, "is_staff", False):
            return obj.visibility
        if obj.visibility == "DELETED":
            return "private"
        return obj.visibility

class EntryCreateSerializer(serializers.ModelSerializer):
    """Having a separate serializer  for creating because we don't need all info for creating an entry"""

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

        if getattr(self, "instance", None) is not None:
            # If no new image provided and content is empty/None, permit update as long as the instance already has an image
            has_existing_image = bool(getattr(self.instance, "image", None))
            content_empty = (content is None) or (isinstance(content, str) and content.strip() == "")
            if content_empty and not image and not has_existing_image:
                raise serializers.ValidationError("Either 'content' or 'image' must be provided.")
            return attrs

        if (content is None or (isinstance(content, str) and content.strip() == "")) and not image:
            raise serializers.ValidationError("Either 'content' or 'image' must be provided.")
        return attrs

    def create(self, validated_data):
        return super().create(validated_data)

class EntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Entry
        fields = ["id", "content", "author", "created_at", "visibility", "source", "source_url"]
        read_only_fields = ["source", "source_id", "source_url"]
