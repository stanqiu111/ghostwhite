from django.shortcuts import render, redirect
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Author
from .serializers import AuthorSerializer, AuthorRegistrationSerializer
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
import json
from django.views.decorators.csrf import csrf_exempt


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


@csrf_exempt
def handle_login(request):
    """Handle login - creates BOTH session so the next time we load the front end, if user is authenticated, they will be redirected to home and returns JWT"""
    if request.method == "POST":
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")

        user = authenticate(request, username=username, password=password)

        if user:
            # create the session, user will be authenticated
            login(request, user)

            refresh = RefreshToken.for_user(user)
            return JsonResponse(
                {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "user_id": user.id,
                }
            )
        else:
            return JsonResponse({"error": "Invalid credentials"}, status=400)


def login_view(request):
    """Display login page OR redirect to home if already logged in"""
    if request.user.is_authenticated:
        return redirect("home")

    return render(request, "authors/login.html")


def logout_view(request):
    """
    Logout user:
    - remove django session
    """
    logout(request)
    return redirect("authors:auth_page")
