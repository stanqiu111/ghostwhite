from django.shortcuts import render
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Author
from .serializers import AuthorSerializer, AuthorRegistrationSerializer


# Create your views here.
class AuthorRegistrationView(generics.CreateAPIView):
    queryset = Author.objects.all()
    permission_classes = [
        AllowAny
    ]  # anyone can access this instead of just authenticated users
    serializer_class = AuthorRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)  # create refresh token for the user

        return Response(
            {
                "user": AuthorSerializer(user).data,
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            },
            status=status.HTTP_201_CREATED,
        )


class AuthorRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AuthorSerializer

    def get_object(self):
        return self.request.user
