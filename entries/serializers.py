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

class EntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Entry
        fields = ["id", "content", "author", "created_at", "visibility", "source", "source_url"]
        read_only_fields = ["source", "source_id", "source_url"]
