import os, uuid
import json
from django.shortcuts import render, redirect, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied
from .models import Author
from .serializers import AuthorSerializer, AuthorRegistrationSerializer
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
import json
from django.views.decorators.csrf import csrf_exempt

 
@method_decorator(csrf_exempt, name="dispatch")
class AuthorRegistrationView(generics.CreateAPIView):
    queryset = Author.objects.all()
    authentication_classes = []  # disable SessionAuthentication -> no CSRF required
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

def author_profile_page(request, username):
    return render(request, "authors/profile_page.html")


@csrf_exempt
@require_http_methods(["GET", "PUT"])
def author_profile_json(request, username):
    author = get_object_or_404(Author, username=username)

    if request.method == "PUT":
        # Parse JSON body; allow partial updates for specific fields only
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        for field in ("display_name", "github_url", "bio"):
            if field in data:
                setattr(author, field, data.get(field) or "")
        author.save()

    return JsonResponse({
        "username": author.username,
        "display_name": author.display_name or "",
        "github_url": author.github_url or "",
        "bio": author.bio or "",
        "image": (request.build_absolute_uri(author.image.url) if author.image else "")
    })

@csrf_exempt
@require_http_methods(["POST"])
def author_avatar_upload(request, username):
    """
    Handle avatar upload for a given author.

    - Accepts POST multipart/form-data with a field named "image"
    - Validates file extension (jpg, jpeg, png, gif, webp)
    - Saves image to Author model with unique name
    - Returns a full URL of the uploaded avatar

    Usage:
    POST /api/authors/<username>/avatar/
    """
    
    author = get_object_or_404(Author, username=username)

    f = request.FILES.get("image")
    if not f:
        return JsonResponse({"error": "image file required"}, status=400)

    # Validate extension
    _, ext = os.path.splitext(f.name or "")
    ext = (ext or "").lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        return JsonResponse({"error": "unsupported file type"}, status=400)

    # Generate a safe unique name and save to the model field. ex: a3f9b1e2d45c4f7c8a9b0d12f34e56ab.png
    safe_name = f"{uuid.uuid4().hex}{ext}"
    author.image.save(safe_name, f, save=True)

    return JsonResponse(
        {"image": request.build_absolute_uri(author.image.url)},
        status = 200,
    )

class AuthorPublicGetUpdate(generics.RetrieveUpdateAPIView):
    """
    GET: Anyone can retrieve an author's public info
    PUT: Only the author themself or an admin (staff) can modify the data
    """
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    http_method_names = ["get", "put", "head", "options"]

    lookup_field = "id"                # Author object identified by its UUID or ID
    lookup_url_kwarg = "author_id"     # URL pattern param name expected (e.g., /api/authors/<author_id>/)

    def perform_update(self, serializer):
        author = self.get_object()
        user = self.request.user
        if not (user.is_authenticated and (user == author or user.is_staff)):
            raise PermissionDenied("Forbidden")
        serializer.save()
    

class AuthorPagination(PageNumberPagination):
    # Custom pagination for authors list:
    # - Uses query params ?page=<num>&size=<num> to control pagination
    # - Default page size: 5, max allowed: 100
    
    page_query_param = "page"
    page_size_query_param = "size"
    page_size = 5 
    max_page_size = 100
    
    def get_paginated_response(self, data):
        return Response({
            "type": "authors",
            "authors": data
        })

class AuthorListView(generics.ListAPIView):
    #list all authors with pagination
    queryset = Author.objects.all().order_by("username")
    serializer_class = AuthorSerializer
    pagination_class = AuthorPagination

    def list(self, request, *args, **kwargs):
         # Apply pagination; if a page exists, return paginated data
        page = self.paginate_queryset(self.get_queryset())
        
         # If pagination not applied, return all authors in one response
        if page is not None:
            serializer = self.get_serializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({"type": "authors", 
                         "authors": serializer.data})