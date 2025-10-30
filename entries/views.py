from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseRedirect
from django.urls import reverse
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied

from authors.models import Follow
from .models import Entry, Comment, EntryLike, CommentLike
from .serializers import EntryRetrieveSerializer, EntryCreateSerializer
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q, Exists, OuterRef

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

class EntryListView(generics.ListAPIView):
    serializer_class = EntryRetrieveSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        base_qs = Entry.objects.all() if user.is_staff else Entry.objects.filter(deleted_at__isnull=True)

        qs = with_follow_flags(base_qs.select_related('author', 'node'), user)

        visibility_filter = (
            Q(author=user) |  # authors can see their own entries
            (Q(visibility='public')) | # anyone can see public entries
            (Q(visibility='unlisted') & Q(is_from_following=True)) | # unlisted entries can be seen by followers
            (Q(visibility='friends_only') & Q(is_from_following=True) & Q(is_following_me=True)) # following-following
        )
        return qs.filter(visibility_filter)
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context



class EntryRetrieveView(generics.RetrieveAPIView):
    """Retrieve a single entry by ID"""

    serializer_class = EntryRetrieveSerializer
    permission_classes = [IsAuthenticated]  # this allows only authenticated users to view the entry

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Entry.objects.all()

        qs = with_follow_flags(Entry.objects.filter(deleted_at__isnull=True), user)
        visibility_filter = (
            Q(author=user) |  # authors can see their own entries
            (Q(visibility='public')) | 
            (Q(visibility='unlisted')) |
            (Q(visibility='friends_only') & Q(is_from_following=True) & Q(is_following_me=True)) # following-following
        )
        return qs.filter(visibility_filter)

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
            # either author or admin can delete the entry
            raise PermissionDenied("Only the author can delete their own entry.")

        instance.soft_delete()


def entry_detail_page(request, pk):
    # initial entry detail page load
    entry = get_object_or_404(Entry, pk=pk)
    user_has_liked = EntryLike.objects.filter(entry=entry, author=request.user).exists()
    user = request.user
    return render(request, "entries/entry_detail.html", {"entry_id": pk, "user_has_liked": user_has_liked, "user": user})


def entry_create_page(request):
    # Render create entry page
    return render(request, "entries/create_entry.html")


def entry_edit_page(request, pk):
    # Render edit entry page with entry_id
    entry = get_object_or_404(Entry, pk=pk)
    # Check if user owns the entry

    if request.user != entry.author:
        return render(request, "entries/entry_detail.html", {"entry_id": pk})
    return render(request, "entries/create_entry.html", {"entry_id": pk})

# -------------------------------------------------------------------------
# COMMENTS AND LIKES AS DRF VIEWS (API, no direct request.POST)
# -------------------------------------------------------------------------
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
            return Response(
                {"detail": "Content is required."}, status=status.HTTP_400_BAD_REQUEST
            )

        Comment.objects.create(entry=entry, author=author, content=content)
        return Response({"detail": "Comment added."}, status=status.HTTP_201_CREATED)


class EntryLikeToggleView(generics.DestroyAPIView):
    """
    POST /entries/<uuid:pk>/like/
    Toggle a like on an entry for the current user/session.
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
    Toggle a like on a comment for the current user/session.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk, comment_id, *args, **kwargs):
        comment = get_object_or_404(Comment, pk=comment_id)
        author = request.user

        like, created = CommentLike.objects.get_or_create(
            comment=comment, author=author
        )
        if not created:
            like.delete()
            return Response(
                {"detail": "Comment like removed."}, status=status.HTTP_200_OK
            )
        return Response(
            {"detail": "Comment like added."}, status=status.HTTP_201_CREATED
        )
