import logging

import requests
from requests.auth import HTTPBasicAuth

from authors.models import Author, Follow
from entries.models import Entry, EntryLike, Comment, CommentLike
from nodes.models import Node
from utils.fqid import (
    build_entry_url,
    build_fqid,
    get_local_node,
    parse_author_fqid,
    build_comment_url,
    extract_entry_id_from_fqid,
    extract_serial_from_fqid,
    get_entry_url,
)
from utils.serializers import serialize_author_for_node_communication

logger = logging.getLogger(__name__)


def _validate_and_get_remote_node(target_author, log_prefix=""):
    """Validate and get remote node for sending notifications."""
    try:
        target_author = Author.objects.select_related('node').get(pk=target_author.pk)
    except Author.DoesNotExist:
        logger.error(f"{log_prefix} Target author {target_author.id} not found")
        return None, None
    
    if not target_author.node:
        logger.warning(f"{log_prefix} Target author {target_author.id} has no node set")
        return None, None
    
    local_node = get_local_node()
    
    is_local = (
        target_author.node.id == local_node.id or 
        target_author.node.host_url.rstrip('/') == local_node.host_url.rstrip('/') or
        target_author.node.is_local
    )
    
    if is_local:
        return None, None
    
    remote_node = target_author.node
    if not remote_node.username:
        logger.warning(f"{log_prefix} Remote node {remote_node.host_url} missing credentials")
        return None, None

    return local_node, remote_node


def get_remote_recipients_for_entry(entry, local_node):
    """Return remote authors that should receive an entry notification."""
    if entry.visibility == "DELETED":
        followers = (
            Follow.objects.filter(
                following=entry.author,
                approved=True,
                status=Follow.ACCEPTED,
            )
            .select_related("follower", "follower__node")
        )
        return [follow.follower for follow in followers if follow.follower.node != local_node]
    
    if entry.visibility == "friends_only":
        friends = Follow.get_friends(entry.author)
        return [friend for friend in friends if friend.node != local_node]
    
    followers = (
        Follow.objects.filter(
            following=entry.author,
            approved=True,
            status=Follow.ACCEPTED,
        )
        .select_related("follower", "follower__node")
    )
    return [follow.follower for follow in followers if follow.follower.node != local_node]

def notify_all_remote_authors(payload, local_node, author_id):
    """Notify all remote nodes (excluding local node) about an activity."""
    remote_nodes = Node.objects.filter(is_local=False).exclude(id=local_node.id)
    for remote_node in remote_nodes:
        if remote_node.username:
            send_to_inbox(payload, remote_node, author_id)

def get_or_create_remote_author(author_fqid, author_data, remote_node=None):
    """Get or create remote author from FQID and data."""
    full_fqid, node_url = parse_author_fqid(author_fqid)
    author_id_part = full_fqid.split('/api/authors/')[-1]
    username_suffix = author_id_part[:8] if len(author_id_part) >= 8 else author_id_part
    
    if remote_node is None:
        try:
            remote_node = Node.objects.get(host_url=node_url, is_local=False)
        except Node.DoesNotExist:
            raise ValueError(f"Remote node not found: {node_url}")
    
    author, created = Author.objects.get_or_create(
        id=full_fqid,
        defaults={
            "username": f"remote_{username_suffix}",
            "display_name": author_data.get("displayName", ""),
            "node": remote_node,
            "is_active": True,
            "approved": True,
            "github_url": author_data.get("github", "")
        }
    )
    
    if not created:
        updated = False
        new_display_name = author_data.get("displayName", "")
        if new_display_name and author.display_name != new_display_name:
            author.display_name = new_display_name
            updated = True
        
        new_github = author_data.get("github", "")
        if new_github and author.github_url != new_github:
            author.github_url = new_github
            updated = True
        
        if author.node != remote_node:
            author.node = remote_node
            updated = True
        
        if updated:
            author.save(update_fields=['display_name', 'github_url', 'node'])
    
    return author, created


def send_to_inbox(payload, remote_node, author_id):
    """Send payload to remote author's inbox."""
    author_serial = extract_serial_from_fqid(author_id)
    base_url = remote_node.host_url.rstrip('/')
    inbox_url = f"{base_url}/api/authors/{author_serial}/inbox"
    
    logger.info(f"[SEND TO INBOX] {payload.get('type', 'unknown')} -> {inbox_url}")
    
    try:
        local_node = get_local_node()
        if not local_node.username or not local_node.password:
            logger.error("[SEND TO INBOX] Local node credentials not set")
            return False

        logger.info(f"[SEND TO INBOX] Payload: {payload} inbox_url: {inbox_url}")
        
        response = requests.post(
            inbox_url,
            json=payload,
            auth=HTTPBasicAuth(local_node.username, local_node.password),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        response.raise_for_status()
        logger.info(f"[SEND TO INBOX] SUCCESS: {inbox_url}")
        return True
    except requests.RequestException as e:
        logger.error(f"[SEND TO INBOX] FAILED: {inbox_url} - {type(e).__name__}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"[SEND TO INBOX] Response: {e.response.status_code} - {e.response.text[:200]}")
        return False

def send_entry_to_remote_nodes(entry):
    """Send entry to remote followers' inboxes."""
    from utils.fqid import extract_entry_id_from_fqid
    local_node = get_local_node()
    recipients = get_remote_recipients_for_entry(entry, local_node)
    if not recipients:
        return

    host_url = local_node.host_url.rstrip('/')
    entry_uuid = extract_entry_id_from_fqid(entry.id)
    entry_web_url = f"{host_url}/entries/{entry_uuid}/"
    
    payload = {
        "type": "entry",
        "id": build_entry_url(entry.author.id, entry_uuid),
        "web": entry_web_url,
        "title": "",
        "description": entry.content[:100] if entry.content else "",
        "contentType": entry.content_type,
        "content": entry.content,
        "author": serialize_author_for_node_communication(entry.author),
        "published": entry.created_at.isoformat(),
        "visibility": entry.visibility.upper(),
    }
    
    if entry.image:
        payload["image"] = f"{host_url}{entry.image.url}"
    
    for recipient in recipients:
        remote_node = recipient.node
        if remote_node.username:
            send_to_inbox(payload, remote_node, recipient.id)


def send_like_to_remote_node(like, entry, *, removed=False):
    """Send like to entry author and other remote likers."""
    log_prefix = "[SEND LIKE]"
    entry_author = Author.objects.select_related('node').get(pk=entry.author.pk)
    
    object_url = get_entry_url(entry, entry_author)
    if not object_url:
        return
    
    payload = {
        "type": "like",
        "author": serialize_author_for_node_communication(like.author),
        "published": like.created_at.isoformat(),
        "id": f"{build_fqid('', author_id=like.author.id)}/liked/{like.id}",
        "object": object_url,
    }
    if removed:
        payload["removed"] = True
    
    _, remote_node = _validate_and_get_remote_node(entry_author, log_prefix=log_prefix)
    if remote_node:
        logger.info(f"{log_prefix} Sending to entry author: {entry_author.id}")
        send_to_inbox(payload, remote_node, entry_author.id)
    
    other_likers = (
        EntryLike.objects.filter(entry=entry)
        .exclude(author=like.author)
        .exclude(author=entry_author)
        .select_related('author', 'author__node')
        .values_list('author', flat=True)
        .distinct()
    )
    
    for liker_id in other_likers:
        try:
            liker = Author.objects.select_related('node').get(pk=liker_id)
            _, remote_node = _validate_and_get_remote_node(liker, log_prefix=log_prefix)
            if remote_node:
                logger.info(f"{log_prefix} Sending to remote liker: {liker.id}")
                send_to_inbox(payload, remote_node, liker.id)
        except Author.DoesNotExist:
            continue


def send_comment_to_remote_node(comment, entry, state=None):
    """Send comment to entry author and other remote recipients."""
    log_prefix = "[SEND COMMENT]"
    local_node = get_local_node()
    entry_author = Author.objects.select_related('node').get(pk=entry.author.pk)
    
    entry_url = get_entry_url(entry, entry_author)
    if not entry_url:
        return
    
    host_url = local_node.host_url.rstrip('/')
    entry_web_url = f"{host_url}/entries/{entry.id}/"
    like_count = comment.likes.count()
    comment_id_url = comment.source_url or build_comment_url(comment)
    if not comment_id_url:
        logger.warning(f"{log_prefix} Missing comment ID URL")
        return
    
    payload = {
        "type": "comment",
        "author": serialize_author_for_node_communication(comment.author),
        "comment": comment.content,
        "contentType": getattr(comment, 'content_type', 'text/plain'),  
        "published": comment.created_at.isoformat(),
        "id": comment_id_url,
        "entry": entry_url,
        "web": entry_web_url,  
        "likes": {
            "type": "likes",
            "id": f"{comment_id_url}/likes",
            "web": f"{host_url}/entries/{entry.id}/",  
            "page_number": 1,
            "size": 50,
            "count": like_count,
            "src": [],
        },
    }
    if state:
        payload["state"] = state
    
    _, remote_node = _validate_and_get_remote_node(entry_author, log_prefix=log_prefix)
    if remote_node:
        send_to_inbox(payload, remote_node, entry_author.id)
    else:
        notify_all_remote_authors(payload, local_node, entry_author.id)

def send_comment_like_to_remote_node(comment_like, *, removed=False):
    """Send comment like to comment author and entry author if remote."""
    log_prefix = "[SEND COMMENT LIKE]"
    comment = comment_like.comment
    entry = comment.entry
    
    comment_author = Author.objects.select_related('node').get(pk=comment.author.pk)
    entry_author = Author.objects.select_related('node').get(pk=entry.author.pk)

    object_url = comment.source_url or build_comment_url(comment)
    if not object_url:
        logger.warning(f"{log_prefix} Missing comment URL")
        return

    payload = {
        "type": "like",
        "summary": f"{comment_like.author.display_name or comment_like.author.username} liked a comment",
        "author": serialize_author_for_node_communication(comment_like.author),
        "object": object_url,
    }
    if removed:
        payload["removed"] = True

    _, remote_node = _validate_and_get_remote_node(comment_author, log_prefix=log_prefix)
    if remote_node:
        send_to_inbox(payload, remote_node, comment_author.id)
    
    if entry_author.id != comment_author.id:
        _, remote_node = _validate_and_get_remote_node(entry_author, log_prefix=log_prefix)
        if remote_node:
            send_to_inbox(payload, remote_node, entry_author.id)


FOLLOW_STATE_TO_SPEC = {
    Follow.PENDING: "requesting",
    Follow.ACCEPTED: "accepted",
    Follow.DENIED: "rejected",
}


def send_follow_request_to_remote_node(follow):
    """Send follow request to followee if remote."""
    log_prefix = "[SEND FOLLOW REQUEST]"
    following_author = Author.objects.select_related('node').get(pk=follow.following.pk)
    follower_author = Author.objects.select_related('node').get(pk=follow.follower.pk)
    
    payload = {
        "type": "follow",
        "summary": f"{follower_author.display_name or follower_author.username} wants to follow {following_author.display_name or following_author.username}",
        "actor": serialize_author_for_node_communication(follower_author),
        "object": serialize_author_for_node_communication(following_author),
        "state": "requesting",
    }
    
    _, remote_node = _validate_and_get_remote_node(following_author, log_prefix)
    if remote_node:
        send_to_inbox(payload, remote_node, following_author.id)


def send_follow_decision_to_remote_node(follow, decision):
    """Send follow decision (accept/deny) to remote author's inbox."""
    log_prefix = "[SEND FOLLOW DECISION]"
    
    if decision not in (Follow.ACCEPTED, Follow.DENIED):
        logger.error(f"{log_prefix} Invalid decision {decision}, must be ACCEPTED or DENIED")
        return

    target_author = follow.follower
    _, remote_node = _validate_and_get_remote_node(target_author, log_prefix)
    if not remote_node:
        return

    payload = {
        "type": "follow",
        "summary": f"{follow.following.display_name or follow.following.username} {'accepted' if decision == Follow.ACCEPTED else 'rejected'} your follow request",
        "actor": serialize_author_for_node_communication(follow.following),
        "object": serialize_author_for_node_communication(follow.follower),
        "state": FOLLOW_STATE_TO_SPEC.get(decision, "requesting"),
    }

    send_to_inbox(payload, remote_node, target_author.id)


def send_unfollow_to_remote_node(follower, followee):
    """Send unfollow notification to followee if remote."""
    log_prefix = "[SEND UNFOLLOW]"
    _, remote_node = _validate_and_get_remote_node(followee, log_prefix)
    if not remote_node:
        return

    payload = {
        "type": "follow",
        "summary": f"{follower.display_name or follower.username} unfollowed {followee.display_name or followee.username}",
        "actor": serialize_author_for_node_communication(follower),
        "object": serialize_author_for_node_communication(followee),
        "state": "unfollow",
    }

    send_to_inbox(payload, remote_node, followee.id)

