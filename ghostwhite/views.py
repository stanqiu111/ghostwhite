from datetime import timedelta

from django.shortcuts import render, redirect
from django.utils import timezone
from entries.models import Entry, EntryLike, EntryView
from authors.models import Author, Follow
from entries.views import with_follow_flags
from django.db.models import Q, Count


# How far back "recently" reaches for the Trending tab, and how many entries
# it shows.
TRENDING_WINDOW = timedelta(days=3)
TRENDING_LIMIT = 20


def landing_view(request):
    """
    Public front door. Signed-in visitors have no use for the pitch, so they
    go straight to their feed; everyone else gets the marketing page.
    """
    if request.user.is_authenticated:
        return redirect("home")
    return render(request, "landing.html")


def network_view(request):
    """
    Public explainer for the distributed architecture. The "this node" panel
    is live data, not illustration: on an instance with no peers it says so
    rather than implying a network that does not exist.
    """
    from nodes.models import Node

    local = Node.objects.filter(is_local=True).first()
    peers = Node.objects.filter(is_local=False)
    context = {
        "local_host": (local.host_url.rstrip("/") if local else request.build_absolute_uri("/").rstrip("/")),
        "peer_count": peers.filter(is_active=True, is_disabled=False).count(),
        "disabled_peer_count": peers.filter(is_disabled=True).count(),
        "peer_hosts": list(
            peers.filter(is_active=True, is_disabled=False)
            .values_list("host_url", flat=True)[:6]
        ),
        "local_authors": Author.objects.filter(node__is_local=True, is_active=True).count(),
        "remote_authors": Author.objects.filter(node__is_local=False).count(),
        "local_entries": Entry.objects.filter(node__is_local=True, deleted_at__isnull=True).count(),
        "remote_entries": Entry.objects.filter(node__is_local=False, deleted_at__isnull=True).count(),
    }
    return render(request, "network.html", context)


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
        entry.serial = entry.id

        follow_relation = Follow.objects.filter(follower=user, following=entry.author).first()
        if follow_relation:
            entry.follow_status = follow_relation.status
        else:
            entry.follow_status = None
    
    # An author who has restricted their profile should not have their avatar
    # rendered in the feed either -- the serializer already blanks it on every
    # API surface, and this keeps the feed from being the one place it leaks.
    # One query for the whole page via the precomputed follow set.
    viewer_follow_ids = Author.accepted_follow_ids(user)
    for entry in entries:
        entry.show_author_avatar = entry.author.profile_visible_to(user, viewer_follow_ids)

    # The card's Followers / Following counts open a list of those people.
    # Build the lists with the same filters the counts used and derive the
    # counts from them, so the number shown can never disagree with the list.
    followers_list = [
        f.follower
        for f in Follow.objects.filter(following=user, approved=True)
        .select_related("follower").order_by("-created_at")
    ]
    following_list = [
        f.following
        for f in Follow.objects.filter(follower=user, approved=True)
        .select_related("following").order_by("-created_at")
    ]
    for person in followers_list + following_list:
        # same rule as feed avatars: restricted profiles show the placeholder
        person.show_author_avatar = person.profile_visible_to(user, viewer_follow_ids)
    follower_count = len(followers_list)
    following_count = len(following_list)

    excluded_ids = Follow.objects.filter(follower=user).values_list('following', flat=True)
    suggestions = Author.objects.exclude(id=user.id).exclude(id__in=excluded_ids)[:5]
    
    for suggestion in suggestions:
        # same rule as the feed: a restricted profile does not show its avatar
        suggestion.show_author_avatar = suggestion.profile_visible_to(user, viewer_follow_ids)
        follow_relation = Follow.objects.filter(follower=user, following=suggestion).first()
        if follow_relation:
            suggestion.follow_status = follow_relation.status
        else:
            suggestion.follow_status = None

    # ---- Trending ----
    # Ranked by views in the last TRENDING_WINDOW only, so the feed reflects
    # what is being read now rather than whatever is oldest and most total-
    # viewed. Restricted to entries this user is already allowed to see, so
    # trending can never surface something the normal feed would hide.
    # Annotate the already-visibility-filtered queryset directly rather than
    # collecting its ids and feeding them back as an IN (...) list -- the feed
    # is unpaginated, and past ~999 rows that list exceeds SQLite's bind-
    # variable limit (and is a needless second round trip on any backend).
    trending_since = timezone.now() - TRENDING_WINDOW
    trending_rows = (
        entries.annotate(
            recent_views=Count(
                "views", filter=Q(views__created_at__gte=trending_since), distinct=True
            )
        )
        .filter(recent_views__gt=0)
        .order_by("-recent_views", "-created_at")[:TRENDING_LIMIT]
    )
    trending_counts = {e.id: e.recent_views for e in trending_rows}
    trending_order = {eid: i for i, eid in enumerate(trending_counts)}

    # Stamp every card so the client-side tab filter can show/order the
    # trending subset without a second request.
    for e in entries:
        e.recent_views = trending_counts.get(e.id, 0)
        e.trending_rank = trending_order.get(e.id)

    context = {
        'user': user,
        'trending_window_hours': int(TRENDING_WINDOW.total_seconds() // 3600),
        'entry_count': entry_count,
        'follower_count': follower_count,
        'following_count': following_count,
        'followers_list': followers_list,
        'following_list': following_list,
        'entries': entries,
        'suggestions': suggestions
    }

    return render(request, "home.html", context)
