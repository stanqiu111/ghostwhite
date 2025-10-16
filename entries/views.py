from django.shortcuts import get_object_or_404, render
from .models import Posting, Comment, EntryLike, CommentLike
from django.http import HttpResponseRedirect
from django.urls import reverse

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
    posting = get_object_or_404(Posting, pk=posting_id)

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
    posting = get_object_or_404(Posting, pk=posting_id)
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

        

