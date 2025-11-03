from django.shortcuts import render, redirect
from entries.models import Entry, EntryLike
from authors.models import Author, Follow
from entries.views import with_follow_flags
from django.db.models import Q


def home_view(request):
    """
    Home page - shows home.html
    Requires authentication
    """
    if not request.user.is_authenticated:
        return redirect("authors_pages:auth_page")  # Redirect to login

    user = request.user
    entry_count = Entry.objects.filter(author=user, deleted_at__isnull=True).count()
    base_qs = Entry.objects.filter(deleted_at__isnull=True).select_related("author", "node")
    qs = with_follow_flags(base_qs, user)
    entries = qs.filter(
        Q(author=user) |
        Q(visibility="public") |
        (Q(visibility="unlisted") & Q(is_from_following=True)) |
        (Q(visibility="friends_only") & Q(is_from_following=True) & Q(is_following_me=True))
    ).order_by("-created_at")
    
    
    for entry in entries:
        entry.user_has_liked = EntryLike.objects.filter(entry=entry, author=user).exists()
        
        follow_relation = Follow.objects.filter(follower=user, following=entry.author).first()
        if follow_relation:
            entry.follow_status = follow_relation.status
        else:
            entry.follow_status = None
    
    follower_count = Follow.objects.filter(following=user, approved=True).count()
    following_count = Follow.objects.filter(follower=user, approved=True).count()

    already_following = Follow.objects.filter(follower=user, approved=True).values_list('following', flat=True)
    suggestions = Author.objects.exclude(id=user.id).exclude(id__in=already_following)[:5]
    
    for suggestion in suggestions:
        follow_relation = Follow.objects.filter(follower=user, following=suggestion).first()
        if follow_relation:
            suggestion.follow_status = follow_relation.status
        else:
            suggestion.follow_status = None

    context = {
        'user': user,
        'entry_count': entry_count,
        'follower_count': follower_count,
        'following_count': following_count,
        'entries': entries,
        'suggestions': suggestions
    }

    return render(request, "home.html", context)
