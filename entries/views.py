from django.shortcuts import get_object_or_404, render
from .models import Entry, Comment, EntryLike, CommentLike
from django.http import HttpResponseRedirect
from django.urls import reverse
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone
from .serializers import EntryRetrieveSerializer, EntryCreateSerializer


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
    permission_classes = [AllowAny] # this allows anyone with link can view the entry

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            #  if entry is deleted, admin can still see it
            return Entry.objects.all()

        return Entry.objects.filter(deleted_at__isnull=True)


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

def _ensure_fingerprint(request) -> str:
    """
    Use the session key as a simple per-user fingerprint for like de-duplication.
    """
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key

def add_comment(request, posting_id):
    """
    Create a Comment for the given question and redirect to results.
    Requirements:
    - 404 if question_id invalid
    - Only create when username and content are provided and valid
    - username <= 32 chars (enforced here and by the model)
    - Always redirect back to results page after processing
    """
    posting = get_object_or_404(Entry, pk=posting_id)

    # Only accept POST; otherwise just redirect to results
    if request.method != "POST":
        return HttpResponseRedirect(reverse("entries:detail", args=(posting.id,)))

    username = (request.POST.get("username") or "").strip()
    content = (request.POST.get("content") or "").strip()

    if username and content and len(username) <= 32:
        Comment.objects.create(
            posting=posting,
            username=username,
            content=content,
        )

    # If invalid or missing fields, do NOT create anything — just redirect
    return HttpResponseRedirect(reverse("entries:results", args=(posting.id,)))

def like_entry(request, posting_id):
    posting = get_object_or_404(Entry, pk=posting_id)
    fp = _ensure_fingerprint(request)
    like, created = EntryLike.objects.get_or_create(posting = posting, fingerprint = fp)
    if not created:
        like.delete()
    return HttpResponseRedirect(reverse("entries:detail", args=(posting.id,)))

def like_comment(request, comment_id):
    comment = get_object_or_404(Comment,pk=comment_id)
    fp = _ensure_fingerprint(request)
    like, created = CommentLike.objects.get_or_create(comment = comment, fingerprint = fp)
    if not created:
        like.delete()
    return HttpResponseRedirect(reverse("entries:detail", args=(comment.posting.id,)))

        

