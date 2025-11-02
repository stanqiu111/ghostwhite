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
from rest_framework.views import APIView
from django.utils import timezone
from .models import Follow
from .serializers import FollowRequestSerializer
from rest_framework import permissions
from .models import Author
from .serializers import AuthorSerializer, AuthorRegistrationSerializer
from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
import json
from django.views.decorators.csrf import csrf_exempt
from entries.models import Entry
from entries.serializers import EntryRetrieveSerializer
from django.db import IntegrityError
 
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
    return redirect("authors_pages:auth_page")

def author_profile_page(request, username):
    author = Author.objects.get(username=username)
    entries = Entry.objects.filter(author=author.id, deleted_at__isnull=True).order_by('-created_at')
    top_5_entries = entries[:5]
    entry_count = entries.count()
    
    request_user_entry_count = Entry.objects.filter(author=request.user.id, deleted_at__isnull=True).count()
    request_user_follower_count = Follow.objects.filter(following=request.user.id, approved=True).count()
    request_user_following_count = Follow.objects.filter(follower=request.user.id, approved=True).count()
    
    author_follower_count = Follow.objects.filter(following=author.id, approved=True).count()
    author_following_count = Follow.objects.filter(follower=author.id, approved=True).count()
    
    # Check follow status if user is authenticated
    follow_status = None
    if request.user.is_authenticated and request.user.id != author.id:
        try:
            follow = Follow.objects.get(follower=request.user, following=author)
            follow_status = follow.status
        except Follow.DoesNotExist:
            follow_status = None

    # Get friends (mutual followers) - limit to 5 for display
    author_friends = Follow.get_friends(author)[:5]
    request_user_friends = Follow.get_friends(request.user)[:5]

    if request.path.endswith('/settings/'):
        # this we dont have to show the full list of entries, only return top 5
        # we only have to show the follower and following count for the request user
        return render(request, "authors/profile_page.html", {'top_5_entries': top_5_entries, 'entry_count': entry_count, 'follower_count': request_user_follower_count, 'following_count': request_user_following_count, "request_user_friends": request_user_friends})
    else:
        # Public profile page - use author_public.html, here we yave to show the full list of entries
        return render(request, "authors/author_public.html", {'author': author, "entries": entries, "entry_count": entry_count, "request_user_entry_count": request_user_entry_count, "request_user_follower_count": request_user_follower_count, "request_user_following_count": request_user_following_count, "author_follower_count": author_follower_count, "author_following_count": author_following_count, "follow_status": follow_status, "author_friends": author_friends, "request_user_friends": request_user_friends})


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



class FollowRequestViewww(generics.CreateAPIView):
    queryset = Follow.objects.all()
    serializer_class = FollowRequestSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        following_author = get_object_or_404(Author, id=self.kwargs['author_id'])
        serializer.save(follower=self.request.user, following=following_author)

class FollowRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, author_id):
        followee = get_object_or_404(Author, id=author_id)
        follower = request.user

        # 1) block self-follow
        if follower.id == followee.id:
            return Response({"detail": "Cannot follow yourself."}, status=status.HTTP_400_BAD_REQUEST)

        # 2) if already exists, return 409
        if Follow.objects.filter(follower=follower, following=followee).exists():
            return Response({"detail": "Follow request already exists."}, status=status.HTTP_409_CONFLICT)

        # 3) create pending request (approved=False, status='pending')
        try:
            f = Follow.objects.create(follower=follower, following=followee, approved=False, status=Follow.PENDING)
        except IntegrityError:
            # race-safe fallback
            return Response({"detail": "Follow request already exists."}, status=status.HTTP_409_CONFLICT)

        # serialize minimal response (id is enough for tests)
        data = {"id": str(f.id), "follower": str(f.follower_id), "following": str(f.following_id), "approved": f.approved}
        return Response(data, status=status.HTTP_201_CREATED)
     
    def delete(self, request, author_id): 
        """ UNFOLLOW (or cancel a pending request): 
        DELETE /api/authors/<author_id>/follow/ Deletes 
        both pending and approved relationships where current user is the follower. 
        """ 
        followee = get_object_or_404(Author, id=author_id) 
        follower = request.user 
        if follower.id == followee.id: 
            return Response({"detail": "Cannot unfollow yourself."}, status=status.HTTP_400_BAD_REQUEST) 
        qs = Follow.objects.filter(follower=follower, following=followee) 
        deleted, _ = qs.delete() 
        if deleted == 0: 
            return Response({"detail": "No follow relationship found."}, status=status.HTTP_404_NOT_FOUND) 
        return Response(status=status.HTTP_204_NO_CONTENT)

class FollowRequestsListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FollowRequestSerializer

    def get_queryset(self):
        # pending for ME (I am the followee), approved == False
        return Follow.objects.select_related("follower").filter(
            following=self.request.user, approved=False
        )

class FollowRequestsListViewwww(APIView):
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        following_author = get_object_or_404(Author, id=self.kwargs['author_id'])
        follower = request.user

        # 1) block self-follow
        if follower.id == following_author.id:
            return Response({"detail": "Cannot follow yourself."}, status=status.HTTP_400_BAD_REQUEST)

        # 2) if already exists, return 409 (or 400 if you prefer)
        existing = Follow.objects.filter(follower=follower, following=following_author).first()
        if existing:
            # you can include approved flag in the payload if you want
            return Response(
                {"detail": "Follow request already exists.", "approved": existing.approved},
                status=status.HTTP_409_CONFLICT,
            )

        # 3) create pending request
        serializer = self.get_serializer(data={})
        serializer.is_valid(raise_exception=True)
        try:
            instance = serializer.save(follower=follower, following=following_author)
        except IntegrityError:
            # race-safe
            return Response({"detail": "Follow request already exists."}, status=status.HTTP_409_CONFLICT)

        headers = self.get_success_headers(serializer.data)
        return Response(
            {
                "id": str(instance.id),
                "follower": str(instance.follower_id),
                "following": str(instance.following_id),
                "approved": instance.approved,
            },
            status=status.HTTP_201_CREATED,
            headers=headers,
        )

class FollowDecisionView(APIView): 
    """
    I used APIView for FollowDecisionView because 
    this endpoint a model—it's a custom action (“approve” or “deny” a pending follow). 

    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        """
        Accept or deny a follow request.
        decision: "accept" | "deny"
        Only the followee (request.user) can decide.
        """
        decision = (request.data or {}).get("decision", "").lower()
        try:
            fr = Follow.objects.select_related("follower", "following").get(
                id=pk, following=request.user
            )
        except Follow.DoesNotExist:
            return Response({"detail": "Request not found or already handled."},
                            status=status.HTTP_404_NOT_FOUND)

        # Use the model's approve/deny methods which properly update the status field
        try:
            if decision == "accept":
                print(f"[DEBUG] Before approve - Status: {fr.status}, Approved: {fr.approved}")
                fr.approve(request.user)
                print(f"[DEBUG] After approve - Status: {fr.status}, Approved: {fr.approved}")
                # Refresh from database to confirm the save worked
                fr.refresh_from_db()
                print(f"[DEBUG] After refresh - Status: {fr.status}, Approved: {fr.approved}")
                return Response({"detail": "Follow request accepted.", "status": fr.status, "approved": fr.approved}, status=status.HTTP_200_OK)

            if decision == "deny":
                fr.deny(request.user)
                fr.refresh_from_db()
                return Response({"detail": "Follow request denied.", "status": fr.status}, status=status.HTTP_200_OK)
        except PermissionError as e:
            print(f"[DEBUG] PermissionError: {str(e)}")
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)

        return Response({"detail": "Invalid decision."}, status=status.HTTP_400_BAD_REQUEST)
