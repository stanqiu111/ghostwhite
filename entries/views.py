from django.shortcuts import get_object_or_404, render
from django.http import HttpResponseRedirect
from django.urls import reverse
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from .models import Entry, Comment, EntryLike, CommentLike
from .serializers import EntryRetrieveSerializer, EntryCreateSerializer
from django.views.decorators.csrf import csrf_exempt


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


@csrf_exempt
def add_comment(request, pk):
    """
    Create a Comment for the given entry and redirect to the entry detail.
    - Only accept POST
    - username and content required; username <= 32
    """
    print("hello")
    entry = get_object_or_404(Entry, pk=pk)

    if request.method != "POST":
        return HttpResponseRedirect(
            reverse("entries:entry-detail", kwargs={"pk": entry.id})
        )

    author = request.user
    content = (request.POST.get("content") or "").strip()

    if content:
        Comment.objects.create(entry=entry, author=author, content=content)

    return HttpResponseRedirect(
        reverse("entries:entry-detail", kwargs={"pk": entry.id})
    )


def like_entry(request, pk):
    entry = get_object_or_404(Entry, pk=pk)
    author = request.user
    like, created = EntryLike.objects.get_or_create(entry=entry, fingerprint=fp)
    if created:
        like.delete()
    else:
        like.save()
    return HttpResponseRedirect(
        reverse("entries:entry-detail", kwargs={"pk": entry.id})
    )


def like_comment(request, pk, comment_id):
    # pk is present in URL for consistency, but we derive the entry from the comment
    comment = get_object_or_404(Comment, pk=comment_id)
    like, created = CommentLike.objects.get_or_create(comment=comment, author=author)
    if created:
        like.delete()
    else:
        like.save()
    return HttpResponseRedirect(
        reverse("entries:entry-detail", kwargs={"pk": comment.entry_id})
    )


# For testing
def entry_detail_page(request, pk):
    entry = get_object_or_404(Entry, pk=pk)
    comments = entry.comments.order_by("-created_at")
    return render(
        request, "entries/detail.html", {"entry": entry, "comments": comments}
    )
