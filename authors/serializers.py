from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import Author
from nodes.models import Node
from django.conf import settings

class AuthorSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    host = serializers.SerializerMethodField()
    type = serializers.SerializerMethodField()
    web = serializers.SerializerMethodField()
    display_name = serializers.CharField()
    github_url = serializers.URLField(allow_blank=True, required=False)
    bio = serializers.CharField(required=False, allow_blank=True)
    image = serializers.ImageField(required=False, allow_null=True)


    def build_full_url(self, path: str):
        """"""
        if not path:
            return ""
        req = self.context.get("request")
        if req:
            return req.build_absolute_uri(path)
        base = getattr(settings, "HOST_URL", "").rstrip("/")
        if base:
            # base = "http://127.0.0.1:8000"
            # path = "/api/authors/sjdhjak362827/" --> "http://127.0.0.1:8000/api/authors/sjdhjak362827/"
            return f"{base}{path}"
        else:
            # 
            return path

    
    def get_type(self, obj):
        return "author"

    def get_id(self, obj):
       
        return self.build_full_url(f"/api/authors/{obj.id}/")

    def get_host(self, obj):
        return self.build_full_url("/api/")

    def get_web(self, obj):
       
        return self.build_full_url(f"/authors/{obj.username}/")

    def get_profileImage(self, obj):
      
        return self.build_full_url(obj.image.url) if obj.image else ""
    
    class Meta:
        model = Author
        fields = [
            "type",
            "id",
            "host",
            "username",
            "display_name",
            "bio",
            "github_url",
            "web",
            "image",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "username", "host", "type", "web"]


class AuthorRegistrationSerializer(serializers.ModelSerializer):
    # why we need password2? because we need to confirm the password and it matches with django createuser
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

