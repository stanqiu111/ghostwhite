from django.shortcuts import render, redirect
from entries.models import Entry


def home_view(request):
    """
    Home page - shows home.html
    Requires authentication
    """
    if not request.user.is_authenticated:
        return redirect("authors:auth_page")  # Redirect to login

    user = request.user
    entry_count = Entry.objects.filter(author=user, deleted_at__isnull=True).count()
    
    follower_count = 0
    following_count = 0

    context = {
        'user': user,
        'entry_count': entry_count,
        'follower_count': follower_count,
        'following_count': following_count,
    }

    return render(request, "home.html", context)
