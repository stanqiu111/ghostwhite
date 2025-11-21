from rest_framework import serializers
from .models import Entry, Comment, CommentLike, EntryLike
from authors.serializers import AuthorSerializer
from nodes.serializers import NodeSerializer
from django.urls import reverse
from utils.serializers import UrlBuildingMixin
class CommentLikeSerializer(UrlBuildingMixin, serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    author = AuthorSerializer()
    published = serializers.DateTimeField(source="created_at", read_only=True)
    object = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "like"
    
    def get_object(self, obj):
        """Return the URL of the object that was liked (the comment)"""
        return obj.comment.id

    class Meta:
        model = CommentLike
        fields = [
            "type",
            "id",
            "author",
            "published",
            "object",
        ]

    def get_id(self, obj):
        """Return the like ID using the author's FQID as the base"""
        # obj.author.id is already a FQID like "http://nodeaaaa/api/authors/111"
        # obj.id is the integer serial from the database
        # Result: "http://nodeaaaa/api/authors/111/liked/166"
        author_base = obj.author.id.rstrip('/')
        return f"{author_base}/liked/{obj.id}"

class CommentSerializer(UrlBuildingMixin, serializers.ModelSerializer):
    author = AuthorSerializer()
    likes = serializers.SerializerMethodField()
    like_count = serializers.IntegerField(read_only=True)
    user_has_liked_comment = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    serial = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    comment = serializers.CharField(source="content", read_only=True)
    contentType = serializers.SerializerMethodField()
    published = serializers.DateTimeField(source="created_at", read_only=True)
    entry = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "comment"
    
    def get_contentType(self, obj):
        """Return content type, defaulting to text/plain if not set"""
        return getattr(obj, 'content_type', 'text/plain')
    
    def get_entry(self, obj):
        """Return the entry URL"""
        return obj.entry.id
    
    def get_web(self, obj):
        """Return the web URL for the comment"""
        from utils.fqid import extract_entry_id_from_fqid
        entry_id = extract_entry_id_from_fqid(obj.entry.id)
        return self.build_full_url(f"/authors/{obj.entry.author.username}/entries/{entry_id}/")
    
    def get_likes(self, obj):
        """Return likes object with pagination"""
        request = self.context.get('request')
        likes_qs = obj.likes.select_related('author').order_by('-created_at')[:5]
        likes_data = CommentLikeSerializer(likes_qs, many=True, context=self.context).data
        
        return {
            "type": "likes",
            "id": f"{obj.id}/likes",
            "web": self.get_web(obj),
            "page_number": 1,
            "size": 50,
            "count": obj.likes.count(),
            "src": likes_data,
        }

    class Meta:
        model = Comment
        fields = [
            "type",
            "id",
            "serial",
            "author",
            "comment",
            "contentType",
            "published",
            "entry",
            "web",
            "likes",
            "like_count",
            "user_has_liked_comment"
        ]

    def get_id(self, obj):
        return obj.id

    def get_serial(self, obj):
        from utils.fqid import extract_comment_id_from_fqid
        return extract_comment_id_from_fqid(obj.id)

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
    type = serializers.SerializerMethodField()
    published = serializers.DateTimeField(source="created_at", read_only=True)
    object = serializers.SerializerMethodField()
    
    def get_type(self, obj):
        return "like"
    
    def get_object(self, obj):
        """Return the URL of the object that was liked (the entry)"""
        return obj.entry.id
    
    class Meta:
        model = EntryLike
        fields = [
            "type",
            "id",
            "author",
            "published",
            "object"
        ]

    def get_id(self, obj):
        """Return the like ID using the author's FQID as the base"""
        # obj.author.id is already a FQID like "http://nodeaaaa/api/authors/111"
        # obj.id is the integer serial from the database
        # Result: "http://nodeaaaa/api/authors/111/liked/166"
        author_base = obj.author.id.rstrip('/')
        return f"{author_base}/liked/{obj.id}"

class EntryRetrieveSerializer(UrlBuildingMixin, serializers.ModelSerializer):
    author = AuthorSerializer()
    node = NodeSerializer()
    comments = serializers.SerializerMethodField()
    likes = serializers.SerializerMethodField()
    like_count = serializers.IntegerField(read_only=True)
    is_image = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    image = serializers.ImageField(read_only=True)
    visibility = serializers.SerializerMethodField()

    id = serializers.SerializerMethodField()
    serial = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    contentType = serializers.CharField(source="content_type", read_only=True)
    published = serializers.DateTimeField(source="created_at", read_only=True)
    web = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "entry"
    
    def get_title(self, obj):
        """Return title - can be empty string or derived from content"""
        return ""
    
    def get_description(self, obj):
        """Return brief description of the entry"""
        if obj.content:
            return obj.content[:100] if len(obj.content) > 100 else obj.content
        return ""
    
    def get_web(self, obj):
        """Return the web URL for the entry"""
        from utils.fqid import extract_entry_id_from_fqid
        entry_id = extract_entry_id_from_fqid(obj.id)
        return self.build_full_url(f"/authors/{obj.author.username}/entries/{entry_id}/")
    
    def get_likes(self, obj):
        """Return likes object with pagination"""
        request = self.context.get('request')
        # Spec says ~5 likes per entry to reduce API calls, but size is 50 for pagination
        likes_qs = obj.likes.select_related('author').order_by('-created_at')[:5]
        likes_data = EntryLikeSerializer(likes_qs, many=True, context=self.context).data
        
        return {
            "type": "likes",
            "id": f"{obj.id}/likes",
            "web": self.get_web(obj),
            "page_number": 1,
            "size": 50,
            "count": obj.likes.count(),
            "src": likes_data,
        }

    class Meta:
        model = Entry
        fields = [
            "type",
            "id",
            "serial",
            "title",
            "description",
            "web",
            "author",
            "content",
            "contentType",
            "published",
            "visibility",
            "comments",
            "likes",
            "like_count",
        ]
    def get_comments(self, obj: Entry):
        """Return comments object with pagination"""
        request = self.context.get("request")
        qs = obj.comments.select_related("author").order_by("-created_at")

        # Staff can see everything
        if request and getattr(request.user, "is_staff", False):
            pass
        else:
            visibility = (obj.visibility or "").lower()
            if visibility == "friends_only":
                if not request or not request.user.is_authenticated:
                    return {
                        "type": "comments",
                        "id": f"{obj.id}/comments",
                        "web": self.get_web(obj),
                        "page_number": 1,
                        "size": 5,
                        "count": 0,
                        "src": [],
                    }

                viewer = request.user
                # Author sees all
                if viewer == obj.author:
                    pass
                # Friends see all
                elif self._is_friend(obj.author, viewer):
                    pass
                else:
                    qs = qs.filter(author=viewer)

        # Get first page of comments (5 per page)
        comments_page = qs[:5]
        comments_data = CommentSerializer(comments_page, many=True, context=self.context).data
        
        return {
            "type": "comments",
            "id": f"{obj.id}/comments",
            "web": self.get_web(obj),
            "page_number": 1,
            "size": 5,
            "count": qs.count(),
            "src": comments_data,
        }

    @staticmethod
    def _is_friend(owner, viewer) -> bool:
        """
        Mutual accepted follow == friends.
        Adjust import/model/field names to your project if needed.
        """
        # Delay import to avoid circulars if your Follow model is in another app
        from authors.models import Follow  # <-- change path if different
        return (
            Follow.objects.filter(follower=viewer, following=owner, status="accepted").exists()
            and
            Follow.objects.filter(follower=owner, following=viewer, status="accepted").exists()
        )

    def get_id(self, obj):
        return obj.id

    def get_serial(self, obj):
        from utils.fqid import extract_entry_id_from_fqid
        return extract_entry_id_from_fqid(obj.id)

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
        from utils.fqid import extract_entry_id_from_fqid
        request = self.context.get("request")
        entry_uuid = extract_entry_id_from_fqid(obj.id)
        url = reverse(
            "authors:entry-image-by-id",
            kwargs={"author_id": obj.author.id, "pk": entry_uuid}
        )
        return request.build_absolute_uri(url) if request else url

    def get_visibility(self, obj):
        """Return visibility in uppercase format as per spec"""
        request = self.context.get("request")
        if request and getattr(request.user, "is_staff", False):
            vis = obj.visibility
        elif obj.visibility == "DELETED":
            vis = "DELETED"
        else:
            vis = obj.visibility
        
        if vis:
            vis_upper = vis.upper()
            if vis_upper == "FRIENDS_ONLY":
                return "FRIENDS"
            return vis_upper
        return vis

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
        read_only_fields = ["id"]
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
        return Entry.objects.create(**validated_data)

class EntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Entry
        fields = ["id", "content", "author", "created_at", "visibility", "source", "source_url"]
        read_only_fields = ["source", "source_id", "source_url"]
