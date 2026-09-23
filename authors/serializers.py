from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import Author
from .models import Follow
from nodes.models import Node
from django.conf import settings
from utils.serializers import UrlBuildingMixin

class AuthorSerializer(UrlBuildingMixin, serializers.ModelSerializer):
    host = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField()
    full_url = serializers.SerializerMethodField()
    follow_status = serializers.SerializerMethodField()
    id = serializers.SerializerMethodField()
    serial = serializers.SerializerMethodField()

    def get_type(self, obj):
        return "author"

    def get_full_url(self, obj):
        return obj.id

    def get_host(self, obj):
        # Return base API host URL (e.g., /api/)
        return self.build_full_url("/api/")

    def get_web(self, obj):
       # Return absolute frontend URL for author's profile page (e.g., /authors/<username>/)
        return self.build_full_url(f"/authors/{obj.username}/")

    def get_id(self, obj):
        return obj.id

    def get_serial(self, obj):
        from utils.fqid import extract_serial_from_fqid
        return extract_serial_from_fqid(obj.id)

    def get_follow_status(self, obj):
        """
        Return the follow status between the current user and this author.
        Returns 'accepted', 'pending', or None
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None

        # Don't check if viewing own profile
        if request.user.id == obj.id:
            return None

        # Check if current user follows this author
        follow_relation = Follow.objects.filter(follower=request.user, following=obj).first()
        if follow_relation:
            return follow_relation.status
        return None

    displayName = serializers.CharField(source="display_name", read_only=True)
    github = serializers.SerializerMethodField()
    
    def get_github(self, obj):
        return obj.github_url or ""
        
    profileImage = serializers.SerializerMethodField()

    def get_profileImage(self, obj):
        """Return profile image URL"""
        if obj.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.image.url)
            from django.conf import settings
            from utils.fqid import get_local_node
            local_node = get_local_node()
            host_url = local_node.host_url.rstrip('/') if local_node else ""
            return f"{host_url}{obj.image.url}" if host_url else obj.image.url
        return ""

    # Detail fields blanked out when the viewer is not allowed to see them.
    # Identity fields (username/displayName/id/web) always stay, so authorship
    # on existing posts and follow buttons keep working.
    RESTRICTED_FIELDS = ("bio", "github", "github_url", "profileImage", "image")

    def _viewer_follows(self, viewer):
        """
        Ids the viewer has an accepted follow of, fetched once per serializer
        instance. When a list of authors is serialised the same child
        serializer handles every item, so this turns what would be one Follow
        query per author into one query for the whole page.
        """
        if not hasattr(self, "_viewer_follow_cache"):
            self._viewer_follow_cache = Author.accepted_follow_ids(viewer)
        return self._viewer_follow_cache

    def to_representation(self, obj):
        data = super().to_representation(obj)
        request = self.context.get("request")
        viewer = getattr(request, "user", None) if request else None
        visible = obj.profile_visible_to(viewer, self._viewer_follows(viewer))
        data["profile_restricted"] = not visible
        # Only the author (or staff) is told which setting is in force --
        # publishing it to everyone advertises who is "private" vs "followers".
        if not (viewer and getattr(viewer, "is_authenticated", False)
                and (viewer.id == obj.id or getattr(viewer, "is_staff", False))):
            data.pop("profile_visibility", None)
        if not visible:
            for f in self.RESTRICTED_FIELDS:
                if f in data:
                    data[f] = "" if f != "image" else None
        return data

    class Meta:
        model = Author
        fields = [
            "type",
            "id",
            "serial",
            "host",
            "username",
            "displayName",
            "display_name", 
            "bio",
            "github",
            "github_url",  
            "profileImage",
            "image",
            "web",
            "created_at",
            "updated_at",
            "full_url",
            "follow_status",
            "profile_visibility",
        ]
        read_only_fields = ["id", "serial", "created_at", "updated_at", "username", "host", "type", "web", "follow_status", "displayName", "github", "profileImage"]


class AuthorRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=True)

    class Meta:
        model = Author
        fields = [
            "username",
            "display_name",
            "email",
            "password",
            "password2",
            "bio",
            "github_url",
        ]

    def validate_email(self, value):
        if Author.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Passwords don't match."})
        return attrs

    def create(self, validated_data):
        from utils.fqid import get_local_node
        validated_data.pop("password2")
        local_node = get_local_node()
        validated_data["node"] = local_node

        return Author.objects.create_user(**validated_data)

class FollowRequestSerializer(serializers.ModelSerializer):
    """
        follower: the author who is following
        following: the author being followed
        approved: whether the follow request is approved or not
    """
    follower_username = serializers.CharField(source="follower.username", read_only=True)
    follower_display  = serializers.CharField(source="follower.display_name", read_only=True)


    class Meta:
        model = Follow
        fields = ['id', 'follower_username', 'follower_display', 'status', 'created_at']
        read_only_fields = fields

    def create(self, validated_data):
        # automatically set the current user as the follower
        request = self.context.get("request")
        validated_data['follower'] = request.user
        return super().create(validated_data)