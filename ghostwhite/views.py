from django.shortcuts import render, redirect
from entries.models import Entry, EntryLike
from authors.models import Author, Follow


def home_view(request):
    """
    Home page - shows home.html
    Requires authentication
    """
    if not request.user.is_authenticated:
        return redirect("authors_pages:auth_page")  # Redirect to login

    user = request.user
    entry_count = Entry.objects.filter(author=user, deleted_at__isnull=True).count()
    entries = Entry.objects.filter(deleted_at__isnull=True).order_by('-created_at')

    # Add a field to show whether user has liked each entry
    for entry in entries:
        entry.user_has_liked = EntryLike.objects.filter(entry=entry, author=user).exists()
    
    follower_count = Follow.objects.filter(following=user, approved=True).count()
    following_count = Follow.objects.filter(follower=user, approved=True).count()

    context = {
        'user': user,
        'entry_count': entry_count,
        'follower_count': follower_count,
        'following_count': following_count,
        'entries': entries
    }

    return render(request, "home.html", context)
