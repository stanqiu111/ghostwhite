from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse, Http404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied
from .models import Entry, Comment, EntryLike, CommentLike
from .serializers import EntryRetrieveSerializer, EntryCreateSerializer
from django.utils.http import http_date
from django.utils.timezone import now
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication, BasicAuthentication


class EntryListView(generics.ListAPIView):
    serializer_class = EntryRetrieveSerializer
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    permission_classes = [IsAuthenticated]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            # admin can see all entries, including the deleted ones
            return Entry.objects.all()

        queryset = Entry.objects.filter(deleted_at__isnull=True).exclude(visibility="DELETED")

        return queryset


class EntryRetrieveView(generics.RetrieveAPIView):
    """Retrieve a single entry by ID"""

    serializer_class = EntryRetrieveSerializer
    permission_classes = [AllowAny]  # this allows anyone with link can view the entry

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_staff:
            #  if entry is deleted, admin can still see it
            return Entry.objects.all()

        return Entry.objects.filter(deleted_at__isnull=True).exclude(visibility="DELETED")
    
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


def get_mime_type(name: str) -> str | None:
    name = name.lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".jpg") or name.endswith(".jpeg"):
        return "image/jpeg"
    if name.endswith(".gif"):
        return "image/gif"
    if name.endswith(".webp"):
        return "image/webp"
    return None


class EntryImageView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication, BasicAuthentication]
    queryset = Entry.objects.all()

    def get(self, request, pk, *args, **kwargs):
        entry = get_object_or_404(Entry, pk=pk)

        # hide deleted images from non-staff
        if getattr(entry, "deleted_at", None) and not (
            request.user.is_authenticated and request.user.is_staff
        ):
            raise Http404()

        # visibility check
        if not self.verify_entry_access(request.user, entry):
            raise Http404()

        # Only image entries are supported here per spec
        if not hasattr(entry, "is_image_entry") or not entry.is_image_entry():
            raise Http404()

        # Decode base64 content into binary
        import base64
        try:
            raw = base64.b64decode(entry.content or "")
        except Exception:
            raise Http404()

        mime = getattr(entry, "image_mime", None) or "application/octet-stream"

        resp = HttpResponse(raw, content_type=mime)
        resp["Cache-Control"] = "private, max-age=3600"
        resp["Last-Modified"] = http_date(now().timestamp())
        return resp

    def verify_entry_access(self, user, entry):
        # Normalize to model choices: public / unlisted / friends_only
        vis = entry.visibility or ""

        # Public and unlisted are viewable by anyone with the link
        if vis in ("public", "unlisted"):
            return True

        # From here we require authentication
        if not getattr(user, "is_authenticated", False):
            return False

        # Staff can always view
        if getattr(user, "is_staff", False):
            return True

        # Owners can always view their own content
        if getattr(entry, "author_id", None) == getattr(user, "id", None):
            return True

        # Friends-only needs a friendship check; accept both snake/hyphen for tolerance
        if vis == "friends_only":
            return hasattr(user, "is_friend_with") and user.is_friend_with(entry.author)

        # Unknown/unsupported visibility -> hide
        return False


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
