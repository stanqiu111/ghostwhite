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
from entries.models import Entry
from entries.serializers import EntryRetrieveSerializer
 
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

def author_profile_page(request, username):
    author = Author.objects.get(username=username)
    top_5_entries = Entry.objects.filter(author=author.id, deleted_at__isnull=True).order_by('-created_at')[:5]
    return render(request, "authors/profile_page.html", {'top_5_entries': top_5_entries})


class AuthorByUsernameView(generics.RetrieveUpdateAPIView):
    """
    GET/PUT author by username
    - GET: Retrieve author profile
    - PUT: Update author profile (including avatar upload)
    - we are using json parser because we are sending json data in the body
    - we are using multi part parser because we are sending file data ( image) in the body
    """
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser]
    lookup_field = "username"
    lookup_url_kwarg = "username"
    
    def perform_update(self, serializer):
        """Only allow users to update their own profile"""
        author = self.get_object()
        user = self.request.user
        if not (user == author or user.is_staff):
            raise PermissionDenied("You can only update your own profile")
        serializer.save()



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

class AuthorEntriesView(generics.ListAPIView):
    erializer_class = EntryRetrieveSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Entry.objects.filter(author=self.request.user, deleted_at__isnull=True)