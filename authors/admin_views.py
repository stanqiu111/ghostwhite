"""
Staff portal: manage accounts from inside the platform instead of /admin/.

Two surfaces, both staff-only:
  * admin_portal_page  -- the rendered page
  * AdminUserUpdateView -- the API the page's controls call

Guard rails enforced server-side (the UI only mirrors them):
  * staff only, checked on every request rather than by hiding the link
  * only a superuser may grant or revoke staff/superuser
  * nobody may strip their own access, and the last remaining admin cannot be
    demoted or deactivated -- otherwise the portal can lock everyone out
  * every change is written to AdminActionLog
"""

from datetime import timedelta

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone

from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from entries.models import Comment, Entry, EntryView
from streams.models import Stream

from .models import AdminActionLog, Author, Follow

VIEWS_WINDOW = timedelta(days=7)

# Fields the portal may change, and how to coerce the submitted value.
EDITABLE_FIELDS = {
    "display_name": str,
    "email": str,
    "bio": str,
    "github_url": str,
    "profile_visibility": str,
    "is_active": bool,
    "approved": bool,
    "is_email_verified": bool,
    "is_staff": bool,
}
# Changing these is an access-control decision, not account admin.
SUPERUSER_ONLY_FIELDS = {"is_staff"}
# Removing these from yourself, or from the last admin, locks people out.
ACCESS_FIELDS = {"is_staff", "is_active"}


def _is_staff(user):
    return user.is_authenticated and user.is_staff


staff_required = user_passes_test(_is_staff, login_url="/authors/auth/")


def _user_rows(search=""):
    """Every account with the counts the portal displays, in 1 query."""
    since = timezone.now() - VIEWS_WINDOW
    qs = Author.objects.all()
    if search:
        qs = qs.filter(
            Q(username__icontains=search)
            | Q(display_name__icontains=search)
            | Q(email__icontains=search)
        )
    return qs.annotate(
        entry_count=Count(
            "entries", filter=Q(entries__deleted_at__isnull=True), distinct=True
        ),
        follower_count=Count(
            "followers", filter=Q(followers__status=Follow.ACCEPTED), distinct=True
        ),
        following_count=Count(
            "following", filter=Q(following__status=Follow.ACCEPTED), distinct=True
        ),
        views_received=Count(
            "entries__views",
            filter=Q(entries__views__created_at__gte=since),
            distinct=True,
        ),
    ).order_by("-approved", "username")


@login_required(login_url="/authors/auth/")
@staff_required
def admin_portal_page(request):
    search = request.GET.get("q", "").strip()
    users = list(_user_rows(search))
    since = timezone.now() - VIEWS_WINDOW

    stats = {
        "total_users": Author.objects.count(),
        "pending_users": Author.objects.filter(approved=False).count(),
        "inactive_users": Author.objects.filter(is_active=False).count(),
        "staff_users": Author.objects.filter(is_staff=True).count(),
        "restricted_profiles": Author.objects.exclude(
            profile_visibility=Author.PROFILE_PUBLIC
        ).count(),
        "entries": Entry.objects.filter(deleted_at__isnull=True).count(),
        "comments": Comment.objects.count(),
        "live_streams": Stream.objects.filter(status="live").count(),
        "recent_views": EntryView.objects.filter(created_at__gte=since).count(),
        "views_window_days": VIEWS_WINDOW.days,
    }

    return render(
        request,
        "authors/admin_portal.html",
        {
            "users": users,
            "stats": stats,
            "search": search,
            "visibility_choices": Author.PROFILE_VISIBILITY_CHOICES,
            "recent_actions": AdminActionLog.objects.select_related("actor")[:15],
            "can_manage_staff": request.user.is_superuser,
        },
    )


class AdminUserUpdateView(APIView):
    """POST /api/authors/staff/users/<serial>/  {"field": ..., "value": ...}"""

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request, serial):
        field = (request.data or {}).get("field")
        value = (request.data or {}).get("value")

        if field not in EDITABLE_FIELDS:
            return Response({"detail": f"Cannot edit '{field}'."},
                            status=status.HTTP_400_BAD_REQUEST)
        if field in SUPERUSER_ONLY_FIELDS and not request.user.is_superuser:
            return Response({"detail": "Only a superuser can change staff access."},
                            status=status.HTTP_403_FORBIDDEN)

        target = self._get_target(serial)
        if target is None:
            return Response({"detail": "Account not found."},
                            status=status.HTTP_404_NOT_FOUND)

        coerced, error = self._coerce(field, value)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        guard = self._lockout_guard(request.user, target, field, coerced)
        if guard:
            return Response({"detail": guard}, status=status.HTTP_400_BAD_REQUEST)

        old = getattr(target, field)
        if old == coerced:
            return Response({"detail": "No change.", "field": field, "value": coerced})

        setattr(target, field, coerced)
        # Validate only the field being changed (this catches e.g. a duplicate
        # or malformed email); validating the whole instance would fail on
        # unrelated legacy data and turn an edit into a 500.
        try:
            target.full_clean(
                exclude=[f.name for f in target._meta.fields if f.name != field]
            )
        except ValidationError as exc:
            return Response({"detail": "; ".join(exc.messages)},
                            status=status.HTTP_400_BAD_REQUEST)
        target.save(update_fields=[field])

        AdminActionLog.objects.create(
            actor=request.user,
            target_username=target.username,
            field=field,
            old_value=str(old),
            new_value=str(coerced),
        )
        return Response({"detail": "Updated.", "field": field, "value": coerced})

    # ---- helpers ----------------------------------------------------------
    @staticmethod
    def _get_target(serial):
        from utils.fqid import extract_serial_from_fqid

        target = Author.objects.filter(username=serial).first()
        if target:
            return target
        for author in Author.objects.all():
            if extract_serial_from_fqid(author.id) == serial:
                return author
        return None

    @staticmethod
    def _coerce(field, value):
        kind = EDITABLE_FIELDS[field]
        if kind is bool:
            if isinstance(value, bool):
                return value, None
            if isinstance(value, str):
                return value.lower() in ("1", "true", "yes", "on"), None
            return None, f"'{field}' expects true or false."
        value = "" if value is None else str(value).strip()
        if field == "profile_visibility":
            valid = {c[0] for c in Author.PROFILE_VISIBILITY_CHOICES}
            if value not in valid:
                return None, f"Visibility must be one of {sorted(valid)}."
        if field == "display_name" and not value:
            return None, "Display name cannot be empty."
        return value, None

    @staticmethod
    def _lockout_guard(actor, target, field, new_value):
        """
        Refuse changes that would remove the last way back in.

        Self-protection is sufficient here: the API requires is_staff, so the
        caller is always an admin, and revoking someone *else* therefore always
        leaves at least the caller. The only way to reach zero admins is to
        revoke your own access, which is what this blocks. (A "last admin"
        count check would be dead code for the same reason.)
        """
        if field not in ACCESS_FIELDS or new_value:
            return None
        if target.id == actor.id:
            what = "staff access" if field == "is_staff" else "your own account"
            return f"You cannot remove {what} from yourself."
        return None
