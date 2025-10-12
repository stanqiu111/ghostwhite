from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import Author
from nodes.models import Node


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = [
            "id",
            "username",
            "display_name",
            "bio",
            "github_url",
            "image",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


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
