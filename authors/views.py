import json
import re
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import IntegrityError
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings as django_settings
from django.urls import reverse

from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.parsers import MultiPartParser, JSONParser, FormParser
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import PermissionDenied

from entries.models import Entry
from .models import Author, Follow, GitHubIntegration, EmailVerificationToken
from .serializers import AuthorSerializer, AuthorRegistrationSerializer, FollowRequestSerializer
from .permissions import IsApproved
from .github import sync_github_events
from utils.node_communication import send_follow_request_to_remote_node, send_follow_decision_to_remote_node, send_unfollow_to_remote_node

logger = logging.getLogger(__name__)

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

        if user.email:
            token_obj = EmailVerificationToken.create_for(user)
            verify_path = reverse("authors_pages:verify_email", args=[token_obj.token])
            base_url = getattr(django_settings, "FRONTEND_URL", request.build_absolute_uri("/").rstrip("/"))
            verification_url = f"{base_url}{verify_path}"
            send_mail(
                subject="Verify your ÉTHÉRÉ email address",
                message=(
                    f"Hi {user.display_name},\n\n"
                    f"Click the link below to verify your email address:\n{verification_url}\n\n"
                    "This link expires once used. If you did not sign up, ignore this email."
                ),
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f0f0f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f0f0;padding:40px 16px;">
    <tr><td align="center">
      <table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">

        <!-- Logo header -->
        <tr>
          <td align="center" style="padding-bottom:24px;">
            <span style="font-size:28px;font-weight:800;letter-spacing:-0.5px;color:#111;">ÉTHÉRÉ</span>
          </td>
        </tr>

        <!-- Card -->
        <tr>
          <td style="background:#ffffff;border-radius:16px;padding:48px 40px;box-shadow:0 4px 24px rgba(0,0,0,0.07);">

            <!-- Greeting -->
            <p style="margin:0 0 8px;font-size:22px;font-weight:700;color:#111;">
              Confirm your email address
            </p>
            <p style="margin:0 0 28px;font-size:15px;color:#555;line-height:1.6;">
              Hi <strong>{user.display_name}</strong>,<br>
              Thanks for joining ÉTHÉRÉ! Click the button below to verify your email address and activate your account.
            </p>

            <!-- CTA button -->
            <table cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
              <tr>
                <td align="center" style="background:#0d9488;border-radius:10px;">
                  <a href="{verification_url}"
                     style="display:inline-block;padding:14px 36px;font-size:16px;font-weight:700;
                            color:#ffffff;text-decoration:none;border-radius:10px;
                            background:#0d9488;">
                    Verify my email
                  </a>
                </td>
              </tr>
            </table>

            <!-- Fallback link -->
            <p style="margin:0 0 6px;font-size:13px;color:#888;">
              Button not working? Copy and paste this link into your browser:
            </p>
            <p style="margin:0 0 28px;font-size:12px;word-break:break-all;">
              <a href="{verification_url}" style="color:#0d9488;">{verification_url}</a>
            </p>

            <hr style="border:none;border-top:1px solid #f0f0f0;margin:0 0 24px;">

            <p style="margin:0;font-size:12px;color:#aaa;line-height:1.6;">
              This link can only be used once. If you did not create an account on ÉTHÉRÉ, you can safely ignore this email.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td align="center" style="padding-top:24px;">
            <p style="margin:0;font-size:12px;color:#aaa;">
              © 2026 ÉTHÉRÉ &nbsp;·&nbsp; You're receiving this because you signed up at ÉTHÉRÉ.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>""",
                fail_silently=True,
            )

        return Response(
            {"status": "pending_verification", "user": AuthorSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class AuthorRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = AuthorSerializer

    def get_object(self):
        return self.request.user

@csrf_exempt
@require_POST
def handle_login(request):
    """Handle login - creates BOTH session so the next time we load the front end, if user is authenticated, they will be redirected to home and returns JWT"""
    if request.method == "POST":
        data = json.loads(request.body)
        username = data.get("username")
        password = data.get("password")  
        try:
            author_obj = Author.objects.get(username=username)
        except Author.DoesNotExist:
            author_obj = None
        if author_obj is not None:
            if author_obj.email and not author_obj.is_email_verified:
                return JsonResponse(
                    {"error": "Please verify your email address before logging in. Check your inbox."},
                    status=403,
                )
            if not getattr(author_obj, "approved", False):
                return JsonResponse({"error": "Account pending admin approval."}, status=403)

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
    """Display login page. If already authenticated, show who is logged in."""
    already_logged_in = request.user.is_authenticated
    return render(request, "authors/login.html", {
        "already_logged_in": already_logged_in,
        "logged_in_username": getattr(request.user, "username", "") if already_logged_in else "",
    })


def verify_email_view(request, token):
    """GET /authors/verify-email/<token>/ — verify email address from link in email"""
    try:
        token_obj = EmailVerificationToken.objects.select_related("author").get(token=token)
        author = token_obj.author
        if not author.is_email_verified:
            author.is_email_verified = True
            author.save(update_fields=["is_email_verified"])
        token_obj.delete()
        return render(request, "authors/verify_email.html", {"success": True, "username": author.username})
    except EmailVerificationToken.DoesNotExist:
        return render(request, "authors/verify_email.html", {"success": False})


def logout_view(request):
    """
    Logout user:
    - remove django session
    """
    logout(request)
    return redirect("authors_pages:auth_page")

@login_required
def remote_nodes_page(request):
    """Simple page to show all remote nodes and remote users with follow/unfollow buttons."""
    from nodes.models import Node
    from django.db.models import Q
    
    remote_nodes = Node.objects.filter(is_local=False, is_active=True).order_by('host_url')
    
    remote_authors = Author.objects.filter(
        node__is_local=False,
        node__is_active=True,
        is_active=True
    ).select_related('node').order_by('display_name', 'username')
    
    user = request.user
    follow_status_map = {}
    follows = Follow.objects.filter(follower=user).select_related('following')
    for follow in follows:
        follow_status_map[follow.following.id] = {
            'status': follow.status,
            'approved': follow.approved,
            'is_following': True
        }
    
    for author in remote_authors:
        author_follow_info = follow_status_map.get(author.id, {'is_following': False})
        author.follow_status = author_follow_info.get('status', None)
        author.follow_approved = author_follow_info.get('approved', False)
        author.is_following = author_follow_info.get('is_following', False)
    
    context = {
        'remote_nodes': remote_nodes,
        'remote_authors': remote_authors,
        'user': user,
    }
    
    return render(request, 'authors/remote_nodes.html', context)


def author_profile_page(request, username):
    author = Author.objects.get(username=username)
    entries = Entry.objects.filter(author=author.id, deleted_at__isnull=True).order_by('-created_at')
    top_5_entries = entries[:5]
    entry_count = entries.count()
    
    request_user_entry_count = 0
    request_user_follower_count = 0
    request_user_following_count = 0
    request_user_friends = []
    request_user_followers = []
    request_user_following = []
    
    if request.user.is_authenticated:
        me = request.user

        request_user_entry_count = Entry.objects.filter(
            author=me,
            deleted_at__isnull=True
        ).count()

        followers_qs = Follow.objects.filter(
            following=me,
            approved=True
        ).select_related('follower')

        following_qs = Follow.objects.filter(
            follower=me,
            approved=True
        ).select_related('following')

        request_user_follower_count = followers_qs.count()
        request_user_following_count = following_qs.count()

        following_ids = set(
            following_qs.values_list("following_id", flat=True)
        )
        follower_ids = set(
            followers_qs.values_list("follower_id", flat=True)
        )
        mutual_ids = following_ids & follower_ids 

        request_user_friends = Author.objects.filter(id__in=mutual_ids)

        request_user_followers = followers_qs.exclude(
            follower_id__in=mutual_ids
        )

        request_user_following = following_qs.exclude(
            following_id__in=mutual_ids
        )
    
    author_follower_count = Follow.objects.filter(following=author.id, approved=True).count()
    author_following_count = Follow.objects.filter(follower=author.id, approved=True).count()
    
    follow_status = None
    if request.user.is_authenticated and request.user.id != author.id:
        try:
            follow = Follow.objects.get(follower=request.user, following=author)
            follow_status = follow.status
        except Follow.DoesNotExist:
            follow_status = None

    author_friends = Follow.get_friends(author)

    # Build followers / following lists for the public profile, excluding mutual friends
    author_all_followers = Follow.objects.filter(following=author, approved=True).select_related('follower')
    author_all_following = Follow.objects.filter(follower=author, approved=True).select_related('following')
    author_friend_ids = set(f.id for f in author_friends)
    author_followers_list = author_all_followers.exclude(follower_id__in=author_friend_ids)
    author_following_list = author_all_following.exclude(following_id__in=author_friend_ids)

    # Profile visibility: withhold detail and social graph from viewers the
    # author has not opened up to. Entries are already filtered by their own
    # per-entry visibility, but a restricted profile should not advertise them
    # either, so the profile page shows nothing but identity + follow button.
    profile_restricted = not author.profile_visible_to(request.user)
    if profile_restricted:
        entries = Entry.objects.none()
        top_5_entries = []
        entry_count = 0
        author_follower_count = 0
        author_following_count = 0
        author_friends = []
        author_followers_list = Follow.objects.none()
        author_following_list = Follow.objects.none()

    if request.path.endswith('/settings/'):
        return render(
            request,
            "authors/profile_page.html",
            {
                'is_own_profile': True,
                'top_5_entries': top_5_entries,
                'entry_count': entry_count,
                'follower_count': request_user_follower_count,
                'following_count': request_user_following_count,
                "request_user_friends": request_user_friends,
                "request_user_followers": request_user_followers,
                "request_user_following": request_user_following,
            }
        )
    else:
        return render(
            request,
            "authors/profile_page.html",
            {
                'is_own_profile': False,
                'author': author,
                "profile_restricted": profile_restricted,
                "profile_visibility": author.profile_visibility,
                "entries": entries,
                "entry_count": entry_count,
                "author_follower_count": author_follower_count,
                "author_following_count": author_following_count,
                "follow_status": follow_status,
                "author_friends": author_friends,
                "author_followers_list": author_followers_list,
                "author_following_list": author_following_list,
            }
        )

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
    # allow anonymous users to GET (public profile) but require authentication for PUT
    permission_classes = [IsAuthenticatedOrReadOnly]
    parser_classes = [JSONParser, MultiPartParser]
    lookup_field = "username"
    lookup_url_kwarg = "username"
    
    def perform_update(self, serializer):
        """Only allow users to update their own profile"""
        author = self.get_object()
        user = self.request.user
        if not (user == author or user.is_staff):
            raise PermissionDenied("You can only update your own profile")
        
        # Create github intergration if github_url is provided
        github_url = self.request.data.get('github_url', None)
        serializer.save()
        
        author.refresh_from_db()
        
        try:
            from utils.node_communication import send_author_update_to_remote_followers
            send_author_update_to_remote_followers(author)
        except Exception as e:
            logger.error(f"Failed to send author update to remote nodes: {e}")
        
        if github_url:
            github_username = github_url
            if github_url.startswith('http'):
                match = re.search(r'github\.com/([^/?#]+)', github_url, re.IGNORECASE)
                if match:
                    github_username = match.group(1)
            
            # Update or create GitHubIntegration
            integration, created = GitHubIntegration.objects.get_or_create(
                author=author,
                defaults={'github_username': github_username}
            )
            if not created:
                # Update existing integration
                integration.github_username = github_username
                integration.save()



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

    lookup_field = "id"                
    lookup_url_kwarg = "author_id"     

    def get_object(self):
        author_id = self.kwargs.get(self.lookup_url_kwarg)
        try:
            return Author.objects.get(id=author_id)
        except Author.DoesNotExist:
            from utils.fqid import extract_serial_from_fqid
            uuid_part = author_id
            authors = Author.objects.all()
            for author in authors:
                if extract_serial_from_fqid(author.id) == uuid_part:
                    return author
            
            try:
                return Author.objects.get(username=author_id)
            except Author.DoesNotExist:
                from rest_framework.exceptions import NotFound
                raise NotFound(f"Author not found with id/username: {author_id}")

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
    serializer_class = AuthorSerializer
    pagination_class = AuthorPagination
    queryset = (
        Author.objects
        .filter(is_active=True, is_staff=False, is_superuser=False, node__is_local=True)
        .order_by('username')
    )

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



class FollowRequestView(APIView):
    permission_classes = [IsAuthenticated, IsApproved]

    def post(self, request, author_id):
        from utils.fqid import extract_serial_from_fqid
        
        author_id = str(author_id)
        
        try:
            followee = Author.objects.get(id=author_id)
        except Author.DoesNotExist:
            uuid_part = author_id
            authors = Author.objects.all()
            for author in authors:
                if extract_serial_from_fqid(author.id) == uuid_part:
                    followee = author
                    break
            else:
                # Fallback: try username lookup
                followee = get_object_or_404(Author, username=author_id)
        
        follower = request.user

        # 1) block self-follow
        if follower.id == followee.id:
            return Response({"detail": "Cannot follow yourself."}, status=status.HTTP_400_BAD_REQUEST)

        # 2) Check existing - allow retry if denied
        existing = Follow.objects.filter(follower=follower, following=followee).first()
        if existing:
            if existing.status == Follow.DENIED:
                existing.status = Follow.PENDING
                existing.approved = False
                existing.decided_at = None
                existing.save(update_fields=['status', 'approved', 'decided_at'])
                send_follow_request_to_remote_node(existing)
                data = {"id": str(existing.id), "follower": str(existing.follower_id), 
                       "following": str(existing.following_id), "approved": existing.approved}
                return Response(data, status=status.HTTP_200_OK)
            return Response({"detail": "Follow request already exists."}, status=status.HTTP_409_CONFLICT)

        # 3) create pending request (approved=False, status='pending')
        try:
            f = Follow.objects.create(follower=follower, following=followee, approved=False, status=Follow.PENDING)
        except IntegrityError:
            return Response({"detail": "Follow request already exists."}, status=status.HTTP_409_CONFLICT)

        send_follow_request_to_remote_node(f)

        # serialize minimal response (id is enough for tests)
        data = {"id": str(f.id), "follower": str(f.follower_id), "following": str(f.following_id), "approved": f.approved}
        return Response(data, status=status.HTTP_201_CREATED)
     
    def delete(self, request, author_id): 
        """ UNFOLLOW (or cancel a pending request): 
        DELETE /api/authors/<author_id>/follow/ Deletes 
        both pending and approved relationships where current user is the follower. 
        """ 
        from utils.fqid import extract_serial_from_fqid
        
        author_id = str(author_id)
        
        try:
            followee = Author.objects.get(id=author_id)
        except Author.DoesNotExist:
            uuid_part = author_id
            authors = Author.objects.all()
            for author in authors:
                if extract_serial_from_fqid(author.id) == uuid_part:
                    followee = author
                    break
            else:
                # Fallback: try username lookup
                followee = get_object_or_404(Author, username=author_id)
        
        follower = request.user 
        if follower.id == followee.id: 
            return Response({"detail": "Cannot unfollow yourself."}, status=status.HTTP_400_BAD_REQUEST) 
        follow = Follow.objects.filter(follower=follower, following=followee).first()
        if not follow:
            return Response({"detail": "No follow relationship found."}, status=status.HTTP_404_NOT_FOUND)
        
        send_unfollow_to_remote_node(follower, followee)
        follow.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class FollowRequestsListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FollowRequestSerializer

    def get_queryset(self):
        # pending for ME (I am the followee), approved == False and status == PENDING
        return Follow.objects.select_related("follower").filter(
            following=self.request.user, 
            approved=False,
            status=Follow.PENDING
        ).order_by("-created_at")

class FollowDecisionView(APIView): 
    """
    I used APIView for FollowDecisionView because 
    this endpoint a model—it's a custom action (“approve” or “deny” a pending follow). 

    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        """
        Accept or deny a follow request.
        decision: "accept" | "deny"
        Only the followee (request.user) can decide.
        """
        logger.info(f"FollowDecisionView: request={request.data}")
        decision = (request.data or {}).get("decision", "").lower()
        logger.info(
            "FollowDecisionView: user=%s follow_id=%s decision=%s payload=%s",
            getattr(request.user, "id", None),
            pk,
            decision,
            request.data,
        )
        try:
            fr = Follow.objects.select_related("follower", "following").get(
                id=pk, following=request.user
            )
            logger.info(
                "FollowDecisionView: loaded follow id=%s follower=%s following=%s status=%s",
                fr.id,
                fr.follower_id,
                fr.following_id,
                fr.status,
            )
        except Follow.DoesNotExist:
            logger.warning(
                "FollowDecisionView: follow id=%s not found for user=%s",
                pk,
                getattr(request.user, "id", None),
            )
            return Response({"detail": "Request not found or already handled."},
                            status=status.HTTP_404_NOT_FOUND)

        # Use the model's approve/deny methods which properly update the status field
        try:
            if decision == "accept":
                fr.approve(request.user)
                fr.refresh_from_db()
                logger.info(f"Follow request approved. Status after approve: {fr.status}, Approved: {fr.approved}, ID: {fr.id}")
                logger.info(f"Sending follow acceptance to follower {fr.follower_id}")
                send_follow_decision_to_remote_node(fr, Follow.ACCEPTED)
                return Response({"detail": "Follow request accepted.", "status": fr.status, "approved": fr.approved}, status=status.HTTP_200_OK)

            if decision == "deny":
                fr.deny(request.user)
                logger.info(f"Sending follow denial to follower {fr.follower_id}")
                send_follow_decision_to_remote_node(fr, Follow.DENIED)
                fr.delete()
                return Response({"detail": "Follow request denied."}, status=status.HTTP_204_NO_CONTENT)
        except PermissionError as e:
            logger.error(f"PermissionError in FollowDecisionView: {str(e)}")
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)

        return Response({"detail": "Invalid decision."}, status=status.HTTP_400_BAD_REQUEST)


class SyncMyGithubReposView(APIView):
    """POST: trigger a sync of the logged-in user's GitHub activity and create Entry objects."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            gi = request.user.github_integration
        except GitHubIntegration.DoesNotExist:
            # Not an error: the request is well formed, there is simply nothing
            # to sync. This used to 400, which logged a console error on every
            # home page load and again every 60s for every user without GitHub
            # connected -- while the neighbouring "no username" case already
            # returned 200. `configured` lets the client stop polling.
            return Response({"created": 0, "configured": False})

        # Check if github_username is empty or blank - if yes we wont call
        if not gi.github_username or not gi.github_username.strip():
            return Response({"created": 0, "configured": False})

        try:
            activity_result = sync_github_events(
                request.user,
                gi.github_username,
                access_token=gi.access_token,
            )
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=500)
        except Exception as exc:
            return Response({"detail": "Failed to sync GitHub activity."}, status=502)

        gi.last_synced_at = timezone.now()
        gi.save(update_fields=['last_synced_at'])

        return Response({
            "created": activity_result["created"],
            "processed_events": activity_result["processed"],
        })


@login_required(login_url="/authors/auth/")
def settings_view(request):
    from .forms import ProfileSettingsForm, EmailChangeForm, PasswordChangeForm as PwChangeForm

    user = request.user
    profile_form = ProfileSettingsForm(instance=user)
    email_form = EmailChangeForm(user=user, initial={"email": user.email or ""})
    password_form = PwChangeForm(user=user)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "profile":
            profile_form = ProfileSettingsForm(request.POST, request.FILES, instance=user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated.")
            else:
                messages.error(request, "Please fix the errors below.")

        elif action == "email":
            email_form = EmailChangeForm(request.POST, user=user)
            if email_form.is_valid():
                user.email = email_form.cleaned_data["email"]
                user.is_email_verified = False
                user.save(update_fields=["email", "is_email_verified"])
                messages.success(request, "Email updated. Please verify your new address.")
            else:
                messages.error(request, "Please fix the errors below.")

        elif action == "password":
            password_form = PwChangeForm(request.POST, user=user)
            if password_form.is_valid():
                user.set_password(password_form.cleaned_data["new_password1"])
                user.save(update_fields=["password"])
                update_session_auth_hash(request, user)
                messages.success(request, "Password changed successfully.")
            else:
                messages.error(request, "Please fix the errors below.")

    return render(request, "authors/settings.html", {
        "profile_form": profile_form,
        "email_form": email_form,
        "password_form": password_form,
    })
