# inbox/views.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q, Exists, OuterRef
from authors.models import Author, Follow
from authors.serializers import AuthorSerializer
from entries.models import Entry, EntryLike, Comment, CommentLike
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.shortcuts import render
from nodes.authentication import NodeBasicAuthentication, NodeAuthenticated
from nodes.models import Node
from utils.inbox_parsing import get_remote_author_from_json_data, parse_follow_state_from_payload
from utils.fqid import find_entry_by_url, find_comment_by_url, parse_author_fqid
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


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

class MyNotificationsView(APIView):
    """
    GET /api/inbox/notifications/?limit=20

    -> "내가 쓴 글(Entry)에 대해 다른 사람들이 남긴 like/comment"를
       최신순으로 합쳐서 반환.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        limit = int(request.query_params.get("limit", 20))
        include_self = request.query_params.get("include_self") == "1"

        # 내가 쓴, soft-delete 안 된 글들
        my_entries = Entry.objects.filter(
            author=user,
            deleted_at__isnull=True,
        ).values_list("id", flat=True)

        # 내 글에 달린 좋아요들
        like_qs = (
            EntryLike.objects
            .select_related("author", "entry", "entry__author")
            .filter(entry_id__in=my_entries)
            .order_by("-created_at")
        )

        # 내 글에 달린 댓글들
        comment_qs = (
            Comment.objects
            .select_related("author", "entry", "entry__author")
            .filter(entry_id__in=my_entries)
            .order_by("-created_at")
        )

        # 기본적으로는 내가 자기 글에 자기 좋아요/댓글 단 건 빼주는 게 보통이라서
        if not include_self:
            like_qs = like_qs.exclude(author=user)
            comment_qs = comment_qs.exclude(author=user)

        # 개별로 limit를 걸고
        like_qs = like_qs[:limit]
        comment_qs = comment_qs[:limit]

        items = []

        for lk in like_qs:
            items.append({
                "type": "like",
                "verb": "liked your post",
                "created": lk.created_at.isoformat(),
                "actor": AuthorSerializer(lk.author, context={"request": request}).data,
                "object_id": str(lk.entry.id),
                "object_url": lk.entry.get_absolute_url(),
            })

        for cm in comment_qs:
            items.append({
                "type": "comment",
                "verb": "commented on your post",
                "created": cm.created_at.isoformat(),
                "actor": AuthorSerializer(cm.author, context={"request": request}).data,
                "object_id": str(cm.entry.id),
                "object_url": cm.entry.get_absolute_url(),
                "comment_preview": cm.content[:80],
            })

        # created 기준으로 최신 순 정렬 후 전체 limit 적용
        items.sort(key=lambda x: x["created"], reverse=True)
        items = items[:limit]

        return Response({"type": "notifications", "items": items})
    

class InboxPostView(APIView):
    """POST /api/authors/{author_id}/inbox - Receive from remote nodes"""
    authentication_classes = [NodeBasicAuthentication]
    permission_classes = [NodeAuthenticated]
    
    def post(self, request, author_id):
        """Route incoming inbox activity to appropriate handler, we have 4 types of activity: entry, follow, like, comment"""
        author = Author.objects.get(id=author_id)
        obj_type = request.data.get("type", "").lower()

        handler_map = {
            "entry": self._handle_entry,
            "follow": self._handle_follow,
            "like": self._handle_like,
            "comment": self._handle_comment,
        }
        
        handler = handler_map.get(obj_type)

        if handler:
            return handler(author, request.data)
        
        logger.warning(f"Inbox: Unknown activity type: {obj_type}")
        return Response({"detail": f"Unknown type: {obj_type}"}, status=400)
    
    def _handle_entry(self, author, data):
        """Handle incoming entry activity (create, update, or delete)
        Here the unique key is the entry_fqid, so we can use it to get the entry if it already exists or create a new one
        However, we need to check if the author exists in the local database, else we should return an error
        """
        entry_fqid = data.get("id")
        if not entry_fqid:
            return Response({"detail": "Entry ID missing"}, status=400)
        
        try:
            remote_author = get_remote_author_from_json_data(data.get("author", {}))
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        
        visibility = data.get("visibility", "PUBLIC").upper()
        
        defaults = {
            "author": remote_author,
            "content": data.get("content", ""),
            "content_type": data.get("contentType", "text/plain"),
            "visibility": visibility.lower(),
            "node": remote_author.node,
            "source": "remote",
            "source_id": data.get("image"),
        }
        
        entry, created = Entry.objects.get_or_create(
            source_url=entry_fqid,
            defaults=defaults
        )
        
        if not created:
            entry.content = data.get("content", entry.content)
            entry.content_type = data.get("contentType", entry.content_type)
            entry.visibility = visibility.lower()
            if data.get("image"):
                entry.source_id = data.get("image")

            # If we are deleting the entry, we mark it as deleted ( soft delete )           
            if visibility == "DELETED":
                entry.deleted_at = timezone.now()
            else:
                entry.deleted_at = None
            
            entry.save()
        
        action = "created" if created else "updated" if visibility != "DELETED" else "deleted"
        logger.info(f"Entry {action} from {remote_author.display_name}")
        return Response({"detail": f"Entry {action}"}, status=200)
    
    def _is_decision_notification(self, data, author, desired_status):
        """Check if this is a decision notification (object matches local author and status is ACCEPTED/DENIED)."""
        object_data = data.get("object", {})
        if not object_data or not isinstance(object_data, dict):
            return False
        
        try:
            object_author = get_remote_author_from_json_data(object_data)
            return object_author.id == author.id and desired_status in (Follow.ACCEPTED, Follow.DENIED)
        except (ValueError, KeyError):
            return False
    
    def _update_follow_status(self, follow, desired_status):
        """Update follow relationship status and approved flag"""
        if desired_status == Follow.ACCEPTED:
            follow.status = Follow.ACCEPTED
            follow.approved = True
        elif desired_status == Follow.DENIED:
            follow.status = Follow.DENIED
            follow.approved = False
        else:  # PENDING
            follow.status = Follow.PENDING
            follow.approved = False
        
        follow.save(update_fields=["status", "approved"])
    
    def _handle_follow(self, author, data):
        """Handle incoming follow activity: requests, acceptances, denials, and unfollows
        """
        try:
            remote_author = get_remote_author_from_json_data(data.get("actor", {}))
        except ValueError as e:
            logger.error(f"[INBOX FOLLOW] Failed to get remote author: {e}")
            return Response({"detail": str(e)}, status=400)

        state_str = data.get("state") or Follow.PENDING
        
        if state_str.lower() == "unfollow":
            follow = Follow.objects.filter(follower=remote_author, following=author).first()
            if follow:
                follow.delete()
                logger.info(f"[INBOX FOLLOW] Unfollow processed: {remote_author.display_name} unfollowed {author.display_name}")
                return Response({"detail": "Unfollow processed"}, status=200)
            else:
                logger.warning(f"[INBOX FOLLOW] Unfollow received but no relationship found: {remote_author.id} -> {author.id}")
                return Response({"detail": "No follow relationship found"}, status=200)
        
        desired_status = parse_follow_state_from_payload(state_str)
        
        is_decision = self._is_decision_notification(data, author, desired_status)
        
        if is_decision:
            follow, created = Follow.objects.get_or_create(
                follower=author,
                following=remote_author,
                defaults={"approved": False, "status": Follow.PENDING}
            )
        else:
            follow, created = Follow.objects.get_or_create(
                follower=remote_author,
                following=author,
                defaults={"approved": False, "status": Follow.PENDING}
            )
        
        if desired_status == Follow.PENDING and not created:
            if follow.status in (Follow.ACCEPTED, Follow.DENIED):
                self._update_follow_status(follow, Follow.PENDING)
        elif follow.status != desired_status or follow.approved != (desired_status == Follow.ACCEPTED):
            self._update_follow_status(follow, desired_status)
        
        logger.info(f"[INBOX FOLLOW] Processed: {follow.follower.display_name} -> {follow.following.display_name}, status={follow.status}")
        
        messages = {
            Follow.ACCEPTED: "Follow accepted",
            Follow.DENIED: "Follow denied",
            Follow.PENDING: "Follow received"
        }
        return Response({"detail": messages[desired_status]}, status=200)
    
    def _handle_like(self, author, data):
        """Handle incoming like activity
        Here we can do like actions on entry or comment so we need to check which one are we performing action on"""
        try:
            remote_author = get_remote_author_from_json_data(data.get("author", {}))
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        
        object_url = data.get("object")
        if not object_url:
            return Response({"detail": "Object URL missing"}, status=400)
        
        removed = bool(data.get("removed"))

        try:
            entry = find_entry_by_url(object_url)
            if removed:
                deleted, _ = EntryLike.objects.filter(entry=entry, author=remote_author).delete()
                logger.info(
                    "Entry like removed from %s for entry %s (deleted=%s)",
                    remote_author.id,
                    entry.id,
                    deleted,
                )
                return Response({"detail": "Like removed"}, status=200)
            EntryLike.objects.get_or_create(entry=entry, author=remote_author)
            logger.info(f"Like received from {remote_author.display_name} for entry {entry.id}")
            return Response({"detail": "Like received"}, status=200)
        except Entry.DoesNotExist:
            pass

        try:
            comment = find_comment_by_url(object_url)
        except Comment.DoesNotExist:
            logger.warning(f"Like: Target not found for URL: {object_url}")
            return Response({"detail": "Object not found"}, status=404)

        if removed:
            deleted, _ = CommentLike.objects.filter(comment=comment, author=remote_author).delete()
            logger.info(
                "Comment like removed from %s for comment %s (deleted=%s)",
                remote_author.id,
                comment.id,
                deleted,
            )
            return Response({"detail": "Comment like removed"}, status=200)

        CommentLike.objects.get_or_create(comment=comment, author=remote_author)
        logger.info(f"Comment like received from {remote_author.display_name} for comment {comment.id}")
        return Response({"detail": "Comment like received"}, status=200)
    
    def _handle_comment(self, author, data):
        """Handle incoming comment activity"""
        try:
            remote_author = get_remote_author_from_json_data(data.get("author", {}))
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        state = (data.get("state") or "").lower()
        comment_url = data.get("id")

        if state in {"deleted", "updated"}:
            if not comment_url:
                return Response({"detail": "Comment ID missing"}, status=400)
            try:
                comment = find_comment_by_url(comment_url)
            except Comment.DoesNotExist:
                if state == "deleted":
                    return Response({"detail": "Comment removed"}, status=200)
                return Response({"detail": "Comment not found"}, status=404)

            if state == "deleted":
                comment.delete()
                logger.info("Comment deleted via remote request: %s", comment_url)
                return Response({"detail": "Comment deleted"}, status=200)

            comment.content = data.get("comment", comment.content)
            comment.save(update_fields=["content"])
            logger.info("Comment updated via remote request: %s", comment_url)
            return Response({"detail": "Comment updated"}, status=200)

        entry_url = data.get("entry")
        if not entry_url:
            return Response({"detail": "Entry URL missing"}, status=400)

        try:
            entry = find_entry_by_url(entry_url)
        except Entry.DoesNotExist:
            logger.warning(f"Comment: Entry not found for URL: {entry_url}")
            return Response({"detail": "Entry not found"}, status=404)

        Comment.objects.create(
            entry=entry,
            author=remote_author,
            content=data.get("comment", ""),
            source_url=comment_url,
        )
        logger.info(f"Comment received from {remote_author.display_name} on entry {entry.id}")
        return Response({"detail": "Comment received"}, status=201)


@login_required
def inbox_page(request):
    """Simple inbox page view"""
    return render(request, "inbox/inbox.html", {})