from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseRedirect
from django.urls import reverse
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from .models import Entry, Comment, EntryLike, CommentLike
from .serializers import EntryRetrieveSerializer, EntryCreateSerializer 
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Exists, OuterRef
from django.http import Http404
from django.core.paginator import Paginator
from django.shortcuts import render
from django.db.models import Prefetch
from django.contrib.auth.decorators import login_required
from rest_framework.views import APIView
from authors.models import Follow


class EntryListView(generics.ListAPIView):
    serializer_class = EntryRetrieveSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            # admin can see all entries, including the deleted ones
            return Entry.objects.all()

        queryset = Entry.objects.filter(deleted_at__isnull=True)

        return queryset


class EntryRetrieveView(generics.RetrieveAPIView):
    """Retrieve a single entry by ID"""

    serializer_class = EntryRetrieveSerializer
    permission_classes = [AllowAny]  # this allows anyone with link can view the entry

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            return Entry.objects.all()

        base = Entry.objects.filter(deleted_at__isnull=True)
        return base.select_related("author", "node").prefetch_related(
            Prefetch("comments", queryset=Comment.objects.select_related("author").order_by("-created_at")),
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
            # either author or admin can delete the entry
            raise PermissionDenied("Only the author can delete their own entry.")

        instance.soft_delete()

def _are_friends(a, b) -> bool:
    return (
        Follow.objects.filter(follower=a, followee=b, status="accepted").exists()
        and
        Follow.objects.filter(follower=b, followee=a, status="accepted").exists()
    )
    
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

class CommentUpdateDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk, comment_id):
        comment = get_object_or_404(Comment, pk=comment_id, entry_id=pk)
        if comment.author_id != request.user.id:
            raise PermissionDenied("You can only edit your own comment.")

        new_text = (request.data.get("content") or "").strip()  # <- strip(), not trim()
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

    # optional: let PUT behave like PATCH so accidental PUTs still work
    def put(self, request, pk, comment_id):
        return self.patch(request, pk, comment_id)