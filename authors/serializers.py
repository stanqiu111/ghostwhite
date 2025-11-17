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
        # Return absolute API endpoint for this author (e.g., /api/authors/<id>/)
        return self.build_full_url(f"/api/authors/{obj.id}/")

    def get_host(self, obj):
        # Return base API host URL (e.g., /api/)
        return self.build_full_url("/api/")

    def get_web(self, obj):
       # Return absolute frontend URL for author's profile page (e.g., /authors/<username>/)
        return self.build_full_url(f"/authors/{obj.username}/")

    def get_id(self, obj):
        return self.get_full_url(obj)

    def get_serial(self, obj):
        return str(obj.id)

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

    class Meta:
        model = Author
        fields = [
            "type",
            "id",
            "serial",
            "host",
            "username",
            "display_name",
            "bio",
            "github_url",
            "web",
            "image",
            "created_at",
            "updated_at",
            "full_url",
            "follow_status",
        ]
        read_only_fields = ["id", "serial", "created_at", "updated_at", "username", "host", "type", "web", "follow_status"]


class AuthorRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = Author
        fields = [
            "username",
            "display_name",
            "password",
            "password2",
            "bio",
            "github_url",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs["password2"]:
            raise serializers.ValidationError({"password": "Passwords don't match."})
        return attrs

    def create(self, validated_data):
        password2 = validated_data.pop("password2")
        local_node = Node.objects.get(is_local=True)
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