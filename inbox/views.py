# inbox/views.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q, Exists, OuterRef
from authors.models import Author, Follow
from authors.serializers import AuthorSerializer
from entries.models import Entry, EntryLike, Comment

def _with_follow_flags(qs, user):
    # 내가 그 글쓴이를 팔로우?
    i_follow = Follow.objects.filter(
        follower=user, following=OuterRef("author_id")
    ).filter(Q(status=Follow.ACCEPTED) | Q(approved=True))
    # 글쓴이가 나를 팔로우?
    follows_me = Follow.objects.filter(
        follower=OuterRef("author_id"), following=user
    ).filter(Q(status=Follow.ACCEPTED) | Q(approved=True))

    return qs.annotate(
        is_from_following=Exists(i_follow),
        is_following_me=Exists(follows_me),
    )

class FollowingActivityView(APIView):
    """
    GET /api/inbox/following-activity/?limit=20
    내가 팔로우(accepted)하는 사람들이 남긴 EntryLike/Comment를
    '내가 볼 수 있는 글' 범위 내에서 최신순으로 집계해 반환.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        limit = int(request.query_params.get("limit", 20))

        # 1) 내가 팔로우 중인 author들
        following_ids = Author.objects.filter(
            followers__follower=user,
            followers__status=Follow.ACCEPTED
        ).values_list("id", flat=True)

        # 2) 내가 볼 수 있는 Entry 범위(소프트삭제 제외 + 가시성 규칙)
        base = Entry.objects.filter(deleted_at__isnull=True).select_related("author", "node")
        vis_qs = _with_follow_flags(base, user).filter(
            Q(author=user)
            | Q(visibility="public")
            | (Q(visibility="unlisted") & Q(is_from_following=True))
            | (Q(visibility="friends_only") & Q(is_from_following=True) & Q(is_following_me=True))
        ).values_list("id", flat=True)

        items = []

        # 3) 좋아요
        for lk in (
            EntryLike.objects
            .select_related("author", "entry", "entry__author")
            .filter(author_id__in=following_ids, entry_id__in=vis_qs)
            .order_by("-created_at")[:limit]
        ):
            items.append({
                "type": "LIKE",
                "verb": "liked a post",
                "created": lk.created_at.isoformat(),
                "actor": AuthorSerializer(lk.author, context={"request": request}).data,
                "object_id": str(lk.entry.id),
                "object_url": lk.entry.get_absolute_url(),
            })

        # 4) 댓글
        for cm in (
            Comment.objects
            .select_related("author", "entry", "entry__author")
            .filter(author_id__in=following_ids, entry_id__in=vis_qs)
            .order_by("-created_at")[:limit]
        ):
            items.append({
                "type": "COMMENT",
                "verb": "commented on a post",
                "created": cm.created_at.isoformat(),
                "actor": AuthorSerializer(cm.author, context={"request": request}).data,
                "object_id": str(cm.entry.id),
                "object_url": cm.entry.get_absolute_url(),
            })

        # 5) 최신순 정렬 후 limit 적용
        items.sort(key=lambda x: x["created"], reverse=True)
        return Response({"type": "notifications", "items": items[:limit]})