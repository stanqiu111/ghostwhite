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
        """Route incoming inbox activity to appropriate handler."""
        from utils.fqid import extract_serial_from_fqid
        
        try:
            author = Author.objects.select_related('node').get(id=author_id)
        except Author.DoesNotExist:
            serial = extract_serial_from_fqid(author_id)
            author = Author.objects.select_related('node').filter(
                id__endswith=f'/api/authors/{serial}'
            ).first()
            
            if not author:
                logger.error(f"[INBOX] Author not found: {author_id}")
                return Response({"detail": "Object not found"}, status=404)
        
        obj_type = request.data.get("type", "").lower()

        handler_map = {
            "entry": self._handle_entry,
            "follow": self._handle_follow,
            "like": self._handle_like,
            "comment": self._handle_comment,
            "author": self._handle_author_update,
        }
        
        handler = handler_map.get(obj_type)

        if handler:
            return handler(author, request.data, request.user)
        
        logger.warning(f"Inbox: Unknown activity type: {obj_type}")
        return Response({"detail": f"Unknown type: {obj_type}"}, status=400)
    
    def _handle_entry(self, author, data, sending_node):
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

        if remote_author.node != sending_node:
            logger.warning(
                f"[INBOX ENTRY] Author node mismatch: claimed {remote_author.node.host_url}, "
                f"authenticated as {sending_node.host_url}"
            )
            return Response({"detail": "Author node does not match authenticated node"}, status=403)
        
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
            # Update entry fields
            entry.content = data.get("content", entry.content)
            entry.content_type = data.get("contentType", entry.content_type)
            entry.visibility = visibility.lower()
            if data.get("image"):
                entry.source_id = data.get("image")

            if entry.author != remote_author:
                logger.warning(f"[INBOX ENTRY] Updating entry author from {entry.author.id} to {remote_author.id}")
                entry.author = remote_author
            if entry.node != remote_author.node:
                logger.warning(f"[INBOX ENTRY] Updating entry node from {entry.node.id if entry.node else 'None'} to {remote_author.node.id}")
                entry.node = remote_author.node

            # If we are deleting the entry, we mark it as deleted ( soft delete )           
            if visibility == "DELETED":
                entry.deleted_at = timezone.now()
            else:
                entry.deleted_at = None
            
            entry.save()
        
        action = "created" if created else "updated" if visibility != "DELETED" else "deleted"
        logger.info(f"Entry {action} from {remote_author.display_name}")
        return Response({"detail": f"Entry {action}"}, status=200)
    
    def _is_decision_notification(self, desired_status):
        return desired_status in (Follow.ACCEPTED, Follow.DENIED)
    
    def _update_follow_status(self, follow, desired_status):
        """Update follow relationship status and approved flag"""
        logger.info(f"[INBOX FOLLOW] Updating follow status to {desired_status} for {follow.follower.display_name} -> {follow.following.display_name}")
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
    
    def _handle_follow(self, author, data, sending_node):
        """Handle incoming follow activity: requests, acceptances, denials, and unfollows
        """
        logger.info(f"[INBOX FOLLOW] Handling follow activity: {data}")
        try:
            remote_author = get_remote_author_from_json_data(data.get("actor", {}))
        except ValueError as e:
            logger.error(f"[INBOX FOLLOW] Failed to get remote author: {e}")
            return Response({"detail": str(e)}, status=400)

        if remote_author.node != sending_node:
            logger.warning(
                f"[INBOX FOLLOW] Actor node mismatch: claimed {remote_author.node.host_url}, "
                f"authenticated as {sending_node.host_url}"
            )
            return Response({"detail": "Actor node does not match authenticated node"}, status=403)

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

        logger.info(f"[INBOX FOLLOW] Desired status: {desired_status}")
        is_decision = self._is_decision_notification(desired_status)
        logger.info(f"[INBOX FOLLOW] Is decision notification: {is_decision}, author={author.id}, remote_author={remote_author.id if remote_author else 'None'}")
        
        if is_decision:
            logger.info(f"[INBOX FOLLOW] Searching for follow: follower={author.id}, following={remote_author.id}")
            follow = Follow.objects.filter(
                follower=author,
                following=remote_author
            ).first()
            
            if not follow:
                logger.warning(f"[INBOX FOLLOW] Follow not found, creating new one: follower={author.id}, following={remote_author.id}")
                follow, created = Follow.objects.get_or_create(
                    follower=author,
                    following=remote_author,
                    defaults={"approved": False, "status": Follow.PENDING}
                )
                logger.warning(f"[INBOX FOLLOW] Follow not found, created new: {follow.follower.display_name} -> {follow.following.display_name}, status={follow.status}")
            else:
                created = False
                logger.info(f"[INBOX FOLLOW] Found existing follow: {follow.follower.display_name} -> {follow.following.display_name}, current_status={follow.status}, approved={follow.approved}")
        else:
            follow, created = Follow.objects.get_or_create(
                follower=remote_author,
                following=author,
                defaults={"approved": False, "status": Follow.PENDING}
            )
            logger.info(f"[INBOX FOLLOW] Follow created: {follow.follower.display_name} -> {follow.following.display_name}, status={follow.status}")
        
        logger.info(f"[INBOX FOLLOW] Before update check: status={follow.status}, desired={desired_status}, approved={follow.approved}, should_be_approved={desired_status == Follow.ACCEPTED}, created={created}")
        
        if desired_status == Follow.PENDING and not created:
            logger.info(f"[INBOX FOLLOW] Updating follow status to pending: {follow.follower.display_name} -> {follow.following.display_name}, status={follow.status}")
            if follow.status in (Follow.ACCEPTED, Follow.DENIED):
                self._update_follow_status(follow, Follow.PENDING)
        elif follow.status != desired_status or follow.approved != (desired_status == Follow.ACCEPTED):
            logger.info(f"[INBOX FOLLOW] Updating follow status to {desired_status}: {follow.follower.display_name} -> {follow.following.display_name}, current_status={follow.status}, current_approved={follow.approved}")
            self._update_follow_status(follow, desired_status)
            # Refresh to get updated status
            follow.refresh_from_db()
            logger.info(f"[INBOX FOLLOW] After update: {follow.follower.display_name} -> {follow.following.display_name}, status={follow.status}, approved={follow.approved}")
        else:
            logger.info(f"[INBOX FOLLOW] No update needed: status already {follow.status}, approved already {follow.approved}")
        
        logger.info(f"[INBOX FOLLOW] Processed: {follow.follower.display_name} -> {follow.following.display_name}, status={follow.status}")
        
        messages = {
            Follow.ACCEPTED: "Follow accepted",
            Follow.DENIED: "Follow denied",
            Follow.PENDING: "Follow received"
        }
        return Response({"detail": messages[desired_status]}, status=200)
    
    def _handle_author_update(self, author, data, sending_node):
        """Handle incoming author profile update - create or update remote author."""
        logger.info(f"[INBOX AUTHOR] Received author update. Author data: {data.get('id', 'MISSING')}")
        
        try:
            remote_author, created = get_remote_author_from_json_data(data, return_created=True)
            
            updated_fields = []
            
            if "profileImage" in data:
                profile_image_url = data["profileImage"]
                if profile_image_url:
                    logger.debug(f"[INBOX AUTHOR] Profile image URL received: {profile_image_url}")
            
            if created:
                logger.info(f"[INBOX AUTHOR] Created remote author: {remote_author.id}, display_name: {remote_author.display_name}")
            else:
                logger.info(f"[INBOX AUTHOR] Updated remote author: {remote_author.id}, display_name: {remote_author.display_name}")
            
            return Response({"detail": "Author update processed"}, status=200)
            
        except ValueError as e:
            logger.error(f"[INBOX AUTHOR] Failed to process author update: {e}")
            return Response({"detail": str(e)}, status=400)
    
    def _handle_like(self, author, data, sending_node):
        """Handle incoming like activity
        Here we can do like actions on entry or comment so we need to check which one are we performing action on"""
        try:
            remote_author = get_remote_author_from_json_data(data.get("author", {}))
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        if remote_author.node != sending_node:
            logger.warning(
                f"[INBOX LIKE] Author node mismatch: claimed {remote_author.node.host_url}, "
                f"authenticated as {sending_node.host_url}"
            )
            return Response({"detail": "Author node does not match authenticated node"}, status=403)
        
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
    
    def _handle_comment(self, author, data, sending_node):
        """Handle incoming comment activity"""
        logger.info(f"[COMMENT HANDLER] Received comment activity. Full payload keys: {list(data.keys())}")
        logger.info(f"[COMMENT HANDLER] Comment author data: {data.get('author', {})}")
        logger.info(f"[COMMENT HANDLER] Comment ID: {data.get('id', 'MISSING')}")
        logger.info(f"[COMMENT HANDLER] Entry URL: {data.get('entry', 'MISSING')}")
        logger.info(f"[COMMENT HANDLER] State: {data.get('state', 'none')}")
        
        try:
            remote_author = get_remote_author_from_json_data(data.get("author", {}))
            logger.info(f"[COMMENT HANDLER] Parsed remote author: {remote_author.id}, display_name: {remote_author.display_name}")
        except ValueError as e:
            logger.error(f"[COMMENT HANDLER] Failed to parse remote author: {e}")
            return Response({"detail": str(e)}, status=400)

        if remote_author.node != sending_node:
            logger.warning(
                f"[COMMENT HANDLER] Author node mismatch: claimed {remote_author.node.host_url}, "
                f"authenticated as {sending_node.host_url}"
            )
            return Response({"detail": "Author node does not match authenticated node"}, status=403)

        state = (data.get("state") or "").lower()
        comment_url = data.get("id")

        if state in {"deleted", "updated"}:
            logger.info(f"[COMMENT HANDLER] Processing {state} comment")
            if not comment_url:
                return Response({"detail": "Comment ID missing"}, status=400)
            try:
                comment = find_comment_by_url(comment_url)
                logger.info(f"[COMMENT HANDLER] Found comment: {comment.id}")
            except Comment.DoesNotExist:
                logger.warning(f"[COMMENT HANDLER] Comment not found for URL: {comment_url}")
                if state == "deleted":
                    return Response({"detail": "Comment removed"}, status=200)
                return Response({"detail": "Comment not found"}, status=404)

            if state == "deleted":
                if comment.author != remote_author:
                    logger.warning(f"[COMMENT HANDLER] Delete rejected: sender is not comment author")
                    return Response({"detail": "Permission denied"}, status=403)
                comment.delete()
                logger.info("Comment deleted via remote request: %s", comment_url)
                return Response({"detail": "Comment deleted"}, status=200)

            if comment.author != remote_author:
                logger.warning(f"[COMMENT HANDLER] Update rejected: sender is not comment author")
                return Response({"detail": "Permission denied"}, status=403)
            comment.content = data.get("comment", comment.content)
            comment.save(update_fields=["content"])
            logger.info("Comment updated via remote request: %s", comment_url)
            return Response({"detail": "Comment updated"}, status=200)

        entry_url = data.get("entry")
        if not entry_url:
            logger.error("[COMMENT HANDLER] Entry URL missing from payload")
            return Response({"detail": "Entry URL missing"}, status=400)

        logger.info(f"[COMMENT HANDLER] Attempting to find entry for URL: {entry_url}")
        try:
            entry = find_entry_by_url(entry_url)
            logger.info(f"[COMMENT HANDLER] Found entry: {entry.id}, author: {entry.author.id}")
        except Entry.DoesNotExist as e:
            logger.error(f"[COMMENT HANDLER] Entry not found for URL: {entry_url}")
            logger.error(f"[COMMENT HANDLER] Error: {e}")
            return Response({"detail": "Entry not found locally"}, status=200)

        _, created = Comment.objects.get_or_create(
            source_url=comment_url,
            defaults={
                "entry": entry,
                "author": remote_author,
                "content": data.get("comment", ""),
            },
        )
        status_code = 201 if created else 200
        logger.info(f"Comment {'received' if created else 'already exists'} from {remote_author.display_name} on entry {entry.id}")
        return Response({"detail": "Comment received"}, status=status_code)


@login_required
def inbox_page(request):
    """Simple inbox page view"""
    return render(request, "inbox/inbox.html", {})