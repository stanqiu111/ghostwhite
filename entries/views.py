from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.utils.http import http_date
from django.utils.timezone import now
from django.db.models import Q, Exists, OuterRef, Prefetch
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from rest_framework.authentication import SessionAuthentication, BasicAuthentication

from authors.models import Follow, Author
from .models import Entry, Comment, EntryLike, CommentLike
from .serializers import EntryRetrieveSerializer, EntryCreateSerializer
from utils.node_communication import (
    send_entry_to_remote_nodes,
    send_comment_to_remote_node,
    send_like_to_remote_node,
    send_comment_like_to_remote_node,
)
from utils.fqid import build_comment_url
import logging

logger = logging.getLogger(__name__)


def with_follow_flags(qs, user):
    i_follow_author = Follow.objects.filter(
        follower=user, following=OuterRef("author_id")
    ).filter(Q(status=Follow.ACCEPTED) | Q(approved=True))
    author_follows_me = Follow.objects.filter(
        follower=OuterRef("author_id"), following=user
    ).filter(Q(status=Follow.ACCEPTED) | Q(approved=True))

    return qs.annotate(
        is_from_following=Exists(i_follow_author),
        is_following_me=Exists(author_follows_me),
    )


def visible_comments_queryset_for(user):
    """
    Build a queryset for comments that enforces:
    - public/unlisted: all comments visible
    - friends_only: visible if viewer is the entry author, OR viewer is the comment author,
      OR viewer and entry author are mutual accepted followers.
    """
    if user and getattr(user, "is_staff", False):
        # Admins can see all comments
        return Comment.objects.select_related("author").order_by("-created_at")

    # Mutual friendship between viewer and the entry author (comment.entry.author)
    i_follow_entry_author = Follow.objects.filter(
        follower=user, following=OuterRef("entry__author_id")
    ).filter(Q(status=Follow.ACCEPTED) | Q(approved=True))

    entry_author_follows_me = Follow.objects.filter(
        follower=OuterRef("entry__author_id"), following=user
    ).filter(Q(status=Follow.ACCEPTED) | Q(approved=True))

    mutual_friends = Exists(i_follow_entry_author) & Exists(entry_author_follows_me)

    # Visibility logic for comments across all entries (works with Prefetch)
    return (
        Comment.objects.select_related("author")
        .order_by("-created_at")
        .filter(
            Q(entry__visibility__in=["public", "unlisted"])
            |
            Q(entry__visibility="friends_only") & (
                Q(entry__author=user)     # entry author sees all comments
                | Q(author=user)          # comment's author sees their own comment
                | mutual_friends          # mutual friends see comments
            )
        )
    )


class EntryImageView(APIView):
    """
    GET /api/authors/<uuid:author_id>/entries/<uuid:pk>/image/
    Returns raw image bytes for an image entry after visibility checks
    """
    permission_classes = [AllowAny]  

    def verify_entry_access(self, user, entry):
        vis = entry.visibility or ""
        if vis in ("public", "unlisted"):
            return True

        if not getattr(user, "is_authenticated", False):
            return False

        if getattr(user, "is_staff", False):
            return True

        if getattr(entry, "author_id", None) == getattr(user, "id", None):
            return True

        if vis == "friends_only":
            return hasattr(user, "is_friend_with") and user.is_friend_with(entry.author)

        return False

    def get(self, request, author_id, pk, *args, **kwargs):
        from utils.fqid import find_entry_by_uuid, build_fqid
        
        author_fqid = author_id
        if '/api/authors/' not in str(author_id):
            author_fqid = build_fqid("", author_id=author_id) or author_id
        
        try:
            entry = find_entry_by_uuid(pk, author_fqid=author_fqid)
        except Entry.DoesNotExist:
            raise Http404()

        # hide soft-deleted content from non-staff
        if getattr(entry, "deleted_at", None) and not (
            request.user.is_authenticated and getattr(request.user, "is_staff", False)
        ):
            raise Http404()
        
        if not self.verify_entry_access(request.user, entry):
            raise Http404()

        # must be an image/*;base64 payload per spec
        ct = (entry.content_type or "").lower()
        if not (ct.startswith("image/") and ct.endswith(";base64")):
            raise Http404()

        # decode base64 body
        import base64
        try:
            raw = base64.b64decode(entry.content or "")
        except Exception:
            raise Http404()

        mime = ct.split(";")[0] or "application/octet-stream"
        resp = HttpResponse(raw, content_type=mime)
        resp["Cache-Control"] = "private, max-age=3600"
        resp["Last-Modified"] = http_date(now().timestamp())
        return resp

class EntryListView(generics.ListAPIView):
    serializer_class = EntryRetrieveSerializer
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        base_qs = Entry.objects.all() if user.is_staff else Entry.objects.filter(deleted_at__isnull=True)
        qs = with_follow_flags(base_qs.select_related('author', 'node'), user)

        visibility_filter = (
            Q(author=user)  # authors can see their own entries
            | Q(visibility='public')  # anyone (authed) can see public entries
            | (Q(visibility='unlisted') & Q(is_from_following=True))  # your previous list semantics
            | (Q(visibility='friends_only') & Q(is_from_following=True) & Q(is_following_me=True))  # mutual
        )

        # Prefetch only the comments visible to this viewer
        return qs.filter(visibility_filter).prefetch_related(
            Prefetch("comments", queryset=visible_comments_queryset_for(user)),
            "likes",
            "comments__likes",
        )


class EntryRetrieveView(generics.RetrieveAPIView):
    """Retrieve a single entry by ID"""

    serializer_class = EntryRetrieveSerializer
    permission_classes = [AllowAny]
    
    def get_object(self):
        from utils.fqid import find_entry_by_uuid
        pk = self.kwargs['pk']
        try:
            return find_entry_by_uuid(pk)
        except Entry.DoesNotExist:
            raise Http404()
    
    def get_queryset(self):
        user = self.request.user
        
        # if user is anonymouse - when user clicks on public link , we should still show the entry
        if not user.is_authenticated:
            return Entry.objects.filter(visibility='public').select_related("author", "node")

        base = Entry.objects.filter(deleted_at__isnull=True).select_related("author", "node")

        if user.is_staff:
            # Admins: no filtering
            return base.prefetch_related(
                Prefetch("comments", queryset=Comment.objects.select_related("author").order_by("-created_at")),
                "likes",
                "comments__likes",
            )

        # Apply entry visibility rules (note: retrieve allows 'unlisted' by link)
        qs = with_follow_flags(base, user)
        visibility_filter = (
            Q(author=user)
            | Q(visibility='public')
            | Q(visibility='unlisted')  # link-based access for retrieve
            | (Q(visibility='friends_only') & Q(is_from_following=True) & Q(is_following_me=True))
        )
        
        return qs.filter(visibility_filter).prefetch_related(
            Prefetch("comments", queryset=visible_comments_queryset_for(user)),
            "likes",
            "comments__likes",
        )


class EntryCreateView(generics.CreateAPIView):
    serializer_class = EntryCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        entry = serializer.save(author=self.request.user, node=self.request.user.node)
        send_entry_to_remote_nodes(entry)


class EntryUpdateView(generics.UpdateAPIView):
    serializer_class = EntryCreateSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser] 
    lookup_field = "pk" 
    
    def get_object(self):
        from utils.fqid import find_entry_by_uuid
        pk = self.kwargs['pk']
        try:
            return find_entry_by_uuid(pk)
        except Entry.DoesNotExist:
            raise Http404()

    def get_queryset(self):
        return Entry.objects.filter(deleted_at__isnull=True, author=self.request.user)
    
    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True  # allow missing fields from form
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        if self.request.user != serializer.instance.author:
            raise PermissionDenied("Only the author can update their own entry.")
        entry = serializer.save()
        # Notify remote nodes about the entry update
        try:
            send_entry_to_remote_nodes(entry)
        except Exception as e:
            logger.error(f"Failed to send entry update to remote nodes: {e}")


class EntryDeleteView(generics.DestroyAPIView):
    queryset = Entry.objects.filter(deleted_at__isnull=True)
    permission_classes = [IsAuthenticated]

    def get_object(self):
        from utils.fqid import find_entry_by_uuid
        pk = self.kwargs['pk']
        try:
            return find_entry_by_uuid(pk)
        except Entry.DoesNotExist:
            raise Http404()

    def get_queryset(self):
        return Entry.objects.filter(deleted_at__isnull=True, author=self.request.user)

    def perform_destroy(self, instance):
        if not self.request.user.is_staff and self.request.user != instance.author:
            raise PermissionDenied("Only the author can delete their own entry.")
        instance.soft_delete()
        # Notify remote nodes about the entry deletion
        # Refresh from DB to get updated visibility
        instance.refresh_from_db()
        try:
            send_entry_to_remote_nodes(instance, force_all_remote=True)
        except Exception as e:
            logger.error(f"Failed to send entry deletion to remote nodes: {e}")


def _are_friends(a, b) -> bool:
    return (
        Follow.objects.filter(follower=a, following=b).filter(Q(status=Follow.ACCEPTED) | Q(approved=True)).exists()
        and
        Follow.objects.filter(follower=b, following=a).filter(Q(status=Follow.ACCEPTED) | Q(approved=True)).exists()
    )


def entry_detail_page(request, pk):
    from utils.fqid import find_entry_by_uuid
    entry = find_entry_by_uuid(pk)
    if request.user.is_authenticated:
        user_has_liked = EntryLike.objects.filter(entry=entry, author=request.user).exists()
    else:
        user_has_liked = False
        
    return render(request, "entries/entry_detail.html", {"entry_id": pk, "user_has_liked": user_has_liked, "user": request.user})


def entry_create_page(request):
    return render(request, "entries/create_entry.html")


def entry_edit_page(request, pk):
    from utils.fqid import find_entry_by_uuid
    entry = find_entry_by_uuid(pk)
    if request.user != entry.author:
        return render(request, "entries/entry_detail.html", {"entry_id": pk})
    return render(request, "entries/create_entry.html", {"entry_id": pk})


# -----------------------------
# COMMENTS & LIKES (API)
# -----------------------------
class CommentCreateView(generics.CreateAPIView):
    """
    POST /entries/<uuid:pk>/comments/
    Create a new comment for a specific entry.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        from utils.fqid import find_entry_by_uuid
        entry = find_entry_by_uuid(pk)
        content = (request.data.get("content") or "").strip()
        author = request.user

        if not content:
            return Response({"detail": "Content is required."}, status=status.HTTP_400_BAD_REQUEST)

        comment = Comment.objects.create(entry=entry, author=author, content=content)
        comment.source_url = build_comment_url(comment)
        comment.save(update_fields=["source_url"])
        
        logger.info(f"[COMMENT CREATE] Comment created on entry {entry.id}")
        logger.info(f"[COMMENT CREATE] Entry author: {entry.author.id}, author node: {entry.author.node_id if entry.author.node_id else 'None'}")
        logger.info(f"[COMMENT CREATE] Comment author: {comment.author.id}, author node: {comment.author.node_id if comment.author.node_id else 'None'}")
        
        try:
            send_comment_to_remote_node(comment, entry)
        except Exception as e:
            logger.error(f"Failed to send comment to remote node: {e}")
        return Response({"detail": "Comment added."}, status=status.HTTP_201_CREATED)


class EntryLikeToggleView(generics.DestroyAPIView):
    """
    POST /entries/<uuid:pk>/like/
    Toggle a like on an entry for the current user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        from utils.fqid import find_entry_by_uuid
        entry = find_entry_by_uuid(pk)
        author = request.user
        like, created = EntryLike.objects.get_or_create(entry=entry, author=author)
        if not created:
            try:
                send_like_to_remote_node(like, entry, removed=True)
            except Exception as e:
                logger.error(f"Failed to send like removal to remote node: {e}")
            like.delete()
            return Response({"detail": "Like removed."}, status=status.HTTP_200_OK)
        try:
            send_like_to_remote_node(like, entry)
        except Exception as e:
            logger.error(f"Failed to send like to remote node: {e}")
        return Response({"detail": "Like added."}, status=status.HTTP_201_CREATED)


class CommentLikeToggleView(generics.DestroyAPIView):
    """
    POST /entries/<uuid:pk>/comments/<int:comment_id>/like/
    Toggle a like on a comment for the current user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, comment_id, *args, **kwargs):
        from utils.fqid import find_comment_by_uuid
        comment = find_comment_by_uuid(comment_id, entry_id=pk)
        author = request.user
        like, created = CommentLike.objects.get_or_create(comment=comment, author=author)
        if not created:
            try:
                send_comment_like_to_remote_node(like, removed=True)
            except Exception as e:
                logger.error(f"Failed to send comment like removal to remote node: {e}")
            like.delete()
            return Response({"detail": "Comment like removed."}, status=status.HTTP_200_OK)
        try:
            send_comment_like_to_remote_node(like)
        except Exception as e:
            logger.error(f"Failed to send comment like to remote node: {e}")
        return Response({"detail": "Comment like added."}, status=status.HTTP_201_CREATED)


class CommentUpdateDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk, comment_id):
        from utils.fqid import find_comment_by_uuid
        comment = find_comment_by_uuid(comment_id, entry_id=pk)
        if comment.author_id != request.user.id:
            raise PermissionDenied("You can only edit your own comment.")

        new_text = (request.data.get("content") or "").strip()
        if not new_text:
            return Response({"detail": "Content is required."}, status=400)

        comment.content = new_text
        comment.save(update_fields=["content"])
        try:
            send_comment_to_remote_node(comment, comment.entry, state="updated")
        except Exception as e:
            logger.error(f"Failed to send comment update to remote node: {e}")
        return Response({"detail": "Comment updated.", "id": comment.id}, status=200)

    def delete(self, request, pk, comment_id):
        from utils.fqid import find_comment_by_uuid
        comment = find_comment_by_uuid(comment_id, entry_id=pk)
        if comment.author_id != request.user.id and not request.user.is_staff:
            raise PermissionDenied("You can only delete your own comment.")
        entry = comment.entry
        try:
            send_comment_to_remote_node(comment, entry, state="deleted")
        except Exception as e:
            logger.error(f"Failed to send comment deletion to remote node: {e}")
        comment.delete()
        return Response(status=204)

    def put(self, request, pk, comment_id):
        return self.patch(request, pk, comment_id)