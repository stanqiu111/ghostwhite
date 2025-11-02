from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseRedirect
from django.urls import reverse
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from .models import Entry, Comment, EntryLike, CommentLike
from .serializers import EntryRetrieveSerializer, EntryCreateSerializer
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Exists, OuterRef, Prefetch
from django.http import Http404
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from rest_framework.views import APIView
from authors.models import Follow


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


class EntryListView(generics.ListAPIView):
    serializer_class = EntryRetrieveSerializer
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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class EntryRetrieveView(generics.RetrieveAPIView):
    """Retrieve a single entry by ID"""

    serializer_class = EntryRetrieveSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class EntryCreateView(generics.CreateAPIView):
    serializer_class = EntryCreateSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(author=self.request.user, node=self.request.user.node)


class EntryUpdateView(generics.UpdateAPIView):
    serializer_class = EntryCreateSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Entry.objects.filter(deleted_at__isnull=True, author=self.request.user)

    def perform_update(self, serializer):
        if self.request.user != serializer.instance.author:
            raise PermissionDenied("Only the author can update their own entry.")
        serializer.save()


class EntryDeleteView(generics.DestroyAPIView):
    queryset = Entry.objects.filter(deleted_at__isnull=True)
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Entry.objects.filter(deleted_at__isnull=True, author=self.request.user)

    def perform_destroy(self, instance):
        if not self.request.user.is_staff and self.request.user != instance.author:
            raise PermissionDenied("Only the author can delete their own entry.")
        instance.soft_delete()


def _are_friends(a, b) -> bool:
    return (
        Follow.objects.filter(follower=a, following=b).filter(Q(status=Follow.ACCEPTED) | Q(approved=True)).exists()
        and
        Follow.objects.filter(follower=b, following=a).filter(Q(status=Follow.ACCEPTED) | Q(approved=True)).exists()
    )


def entry_detail_page(request, pk):
    entry = get_object_or_404(Entry, pk=pk)
    user_has_liked = EntryLike.objects.filter(entry=entry, author=request.user).exists()
    return render(request, "entries/entry_detail.html", {"entry_id": pk, "user_has_liked": user_has_liked, "user": request.user})


def entry_create_page(request):
    return render(request, "entries/create_entry.html")


def entry_edit_page(request, pk):
    entry = get_object_or_404(Entry, pk=pk)
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
        entry = get_object_or_404(Entry, pk=pk)
        content = (request.data.get("content") or "").strip()
        author = request.user

        if not content:
            return Response({"detail": "Content is required."}, status=status.HTTP_400_BAD_REQUEST)

        Comment.objects.create(entry=entry, author=author, content=content)
        return Response({"detail": "Comment added."}, status=status.HTTP_201_CREATED)


class EntryLikeToggleView(generics.DestroyAPIView):
    """
    POST /entries/<uuid:pk>/like/
    Toggle a like on an entry for the current user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        entry = get_object_or_404(Entry, pk=pk)
        author = request.user
        like, created = EntryLike.objects.get_or_create(entry=entry, author=author)
        if not created:
            like.delete()
            return Response({"detail": "Like removed."}, status=status.HTTP_200_OK)
        return Response({"detail": "Like added."}, status=status.HTTP_201_CREATED)


class CommentLikeToggleView(generics.DestroyAPIView):
    """
    POST /entries/<uuid:pk>/comments/<int:comment_id>/like/
    Toggle a like on a comment for the current user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, comment_id, *args, **kwargs):
        comment = get_object_or_404(Comment, pk=comment_id)
        author = request.user
        like, created = CommentLike.objects.get_or_create(comment=comment, author=author)
        if not created:
            like.delete()
            return Response({"detail": "Comment like removed."}, status=status.HTTP_200_OK)
        return Response({"detail": "Comment like added."}, status=status.HTTP_201_CREATED)


class CommentUpdateDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk, comment_id):
        comment = get_object_or_404(Comment, pk=comment_id, entry_id=pk)
        if comment.author_id != request.user.id:
            raise PermissionDenied("You can only edit your own comment.")

        new_text = (request.data.get("content") or "").strip()
        if not new_text:
            return Response({"detail": "Content is required."}, status=400)

        comment.content = new_text
        comment.save(update_fields=["content"])
        return Response({"detail": "Comment updated.", "id": comment.id}, status=200)

    def delete(self, request, pk, comment_id):
        comment = get_object_or_404(Comment, pk=comment_id, entry_id=pk)
        if comment.author_id != request.user.id and not request.user.is_staff:
            raise PermissionDenied("You can only delete your own comment.")
        comment.delete()
        return Response(status=204)

    def put(self, request, pk, comment_id):
        return self.patch(request, pk, comment_id)