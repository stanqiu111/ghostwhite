import logging

import requests
from requests.auth import HTTPBasicAuth

from authors.models import Author, Follow
from entries.models import Entry, EntryLike, Comment, CommentLike
from nodes.models import Node
from utils.fqid import (
    build_entry_url,
    build_fqid,
    build_remote_url,
    get_local_node,
    parse_author_fqid,
    build_comment_url,
    parse_entry_fqid,
    find_entry_by_url,
    find_comment_by_url,
)
from utils.serializers import serialize_author_for_node_communication

logger = logging.getLogger(__name__)


def _validate_and_get_remote_node(target_author, log_prefix=""):
    """Validate and get remote node for sending notifications."""
    logger.info(f"{log_prefix} Validating and getting remote node for target author: {target_author.id}")
    local_node = get_local_node()
    if not local_node:
        logger.warning(f"{log_prefix} Local node not configured, aborting")
        return None, None
    
    if target_author.node == local_node:
        logger.info(f"{log_prefix} Target author {target_author.id} is local, skipping remote notification")
        return None, None
    
    remote_node = target_author.node
    if not remote_node or not remote_node.username:
        logger.warning(f"{log_prefix} Remote node missing or missing credentials, aborting")
        return None, None

    logger.info(f"{log_prefix} Remote node found: {remote_node.id}")
    return local_node, remote_node


def get_remote_recipients_for_entry(entry, local_node):
    """Return remote authors that should receive an entry notification. The recipients should be all the followers that are not local"""
    if not local_node:
        return []

    # For deleted entries, send to all followers (they already received it before)
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
    """
    Send payload to remote author's inbox.
    
    """
    remote_author_url = build_remote_url(remote_node.host_url, author_id)
    inbox_url = f"{remote_author_url.rstrip('/')}/inbox"
    
    logger.info(f"[SEND TO INBOX] Target: {inbox_url}")
    logger.info(f"[SEND TO INBOX] Payload type: {payload.get('type', 'unknown')}")
    
    try:
        local_node = get_local_node()
        if not local_node:
            logger.error("[SEND TO INBOX] Local node not configured")
            return False
        
        if not local_node.username or not local_node.password:
            logger.error("[SEND TO INBOX] Local node credentials not set")
            return False
        
        logger.info(f"[SEND TO INBOX] Using credentials: username={local_node.username}")
        logger.info(f"[SEND TO INBOX] Sending POST request...")
        
        response = requests.post(
            inbox_url,
            json=payload,
            auth=HTTPBasicAuth(local_node.username, local_node.password),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        logger.info(f"[SEND TO INBOX] Response status: {response.status_code}")
        
        response.raise_for_status()
        logger.info(f"[SEND TO INBOX] SUCCESS: Sent to {inbox_url}")
        return True
    except requests.RequestException as e:
        logger.error(f"[SEND TO INBOX] FAILED: {inbox_url} - {type(e).__name__}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"[SEND TO INBOX] Response status: {e.response.status_code}")
            logger.error(f"[SEND TO INBOX] Response body: {e.response.text[:500]}")
        return False

def send_entry_to_remote_nodes(entry):
    """Send entry to remote followers' inboxes."""
    from utils.fqid import extract_entry_id_from_fqid
    local_node = get_local_node()
    if not local_node:
        return

    recipients = get_remote_recipients_for_entry(entry, local_node)
    if not recipients:
        return

    host_url = local_node.host_url.rstrip('/')
    entry_uuid = extract_entry_id_from_fqid(entry.id)
    entry_web_url = f"{host_url}/entries/{entry_uuid}/"
    
    payload = {
        "type": "entry",
        "id": build_entry_url(entry.author.id, entry.id),
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
    """Send like to entry author's inbox if remote."""
    local_node, remote_node = _validate_and_get_remote_node(entry.author)
    if not remote_node:
        return
    
    object_url = entry.source_url or build_entry_url(entry.author.id, entry.id)
    
    payload = {
        "type": "like",
        "author": serialize_author_for_node_communication(like.author),
        "published": like.created_at.isoformat(),
        "id": f"{build_fqid('', author_id=like.author.id)}/liked/{like.id}",
        "object": object_url,
    }
    if removed:
        payload["removed"] = True
    
    send_to_inbox(payload, remote_node, entry.author.id)


def send_comment_to_remote_node(comment, entry, state=None):
    """Send comment to entry author's inbox if remote."""
    local_node, remote_node = _validate_and_get_remote_node(entry.author)
    if not remote_node:
        return
    
    entry_url = entry.source_url or build_entry_url(entry.author.id, entry.id)
    host_url = local_node.host_url.rstrip('/')
    entry_web_url = f"{host_url}/entries/{entry.id}/"
    like_count = comment.likes.count()
    comment_id_url = comment.source_url or build_comment_url(comment)
    if not comment_id_url:
        logger.warning("send_comment_to_remote_node: missing comment ID URL")
        return
    
    payload = {
        "type": "comment",
        "author": serialize_author_for_node_communication(comment.author),
        "comment": comment.content,
        "contentType": getattr(comment, 'content_type', 'text/plain'),  # Comment model doesn't have content_type, default to text/plain
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
    
    send_to_inbox(payload, remote_node, entry.author.id)


def send_comment_like_to_remote_node(comment_like, *, removed=False):
    """Send comment like to comment author's inbox if remote."""
    comment = comment_like.comment
    local_node, remote_node = _validate_and_get_remote_node(comment.author)
    if not remote_node:
        return

    object_url = comment.source_url or build_comment_url(comment)
    if not object_url:
        logger.warning("send_comment_like_to_remote_node: missing comment URL")
        return

    payload = {
        "type": "like",
        "summary": f"{comment_like.author.display_name or comment_like.author.username} liked a comment",
        "author": serialize_author_for_node_communication(comment_like.author),
        "object": object_url,
    }
    if removed:
        payload["removed"] = True

    send_to_inbox(payload, remote_node, comment.author_id)


FOLLOW_STATE_TO_SPEC = {
    Follow.PENDING: "requesting",
    Follow.ACCEPTED: "accepted",
    Follow.DENIED: "rejected",
}


def send_follow_request_to_remote_node(follow):
    """Send follow request to remote author's inbox."""
    log_prefix = "[SEND FOLLOW REQUEST]"
    logger.info(f"{log_prefix} Starting: follow_id={follow.id}")
    
    target_author = follow.following
    local_node, remote_node = _validate_and_get_remote_node(target_author, log_prefix)
    if not remote_node:
        logger.error(f"{log_prefix} No remote node found, aborting")
        return

    # Debug: Log the author IDs before serialization
    print(f"{log_prefix} [DEBUG] Following author ID before serialize: {follow.following.id}")
    print(f"{log_prefix} [DEBUG] Following author username: {follow.following.username}")
    print(f"{log_prefix} [DEBUG] Follower author ID before serialize: {follow.follower.id}")
    print(f"{log_prefix} [DEBUG] Follower author username: {follow.follower.username}")
    logger.info(f"{log_prefix} Following author ID before serialize: {follow.following.id}")
    logger.info(f"{log_prefix} Follower author ID before serialize: {follow.follower.id}")
    
    # Get fresh copies to ensure we have latest data
    following_author = Author.objects.get(pk=follow.following.pk)
    follower_author = Author.objects.get(pk=follow.follower.pk)
    print(f"{log_prefix} [DEBUG] Fresh following author ID: {following_author.id}")
    print(f"{log_prefix} [DEBUG] Fresh follower author ID: {follower_author.id}")
    
    payload = {
        "type": "follow",
        "summary": f"{follow.follower.display_name or follow.follower.username} wants to follow {follow.following.display_name or follow.following.username}",
        "actor": serialize_author_for_node_communication(follower_author),
        "object": serialize_author_for_node_communication(following_author),
        "state": "requesting",
    }
    
    print(f"{log_prefix} [DEBUG] Serialized object ID: {payload['object']['id']}")
    print(f"{log_prefix} [DEBUG] Serialized actor ID: {payload['actor']['id']}")

    logger.info(f"{log_prefix} Payload: {payload}")
    result = send_to_inbox(payload, remote_node, target_author.id)
    logger.info(f"{log_prefix} Result: {'SUCCESS' if result else 'FAILED'}")


def send_follow_decision_to_remote_node(follow, decision):
    """Send follow decision (accept/deny) to remote author's inbox."""
    log_prefix = "[SEND FOLLOW DECISION]"
    logger.info(f"{log_prefix} Starting: follow_id={follow.id}, decision={decision}")
    
    if decision not in (Follow.ACCEPTED, Follow.DENIED):
        logger.error(f"{log_prefix} Invalid decision {decision}, must be ACCEPTED or DENIED, aborting")
        return

    target_author = follow.follower
    local_node, remote_node = _validate_and_get_remote_node(target_author, log_prefix)
    if not remote_node:
        return

    payload_state = FOLLOW_STATE_TO_SPEC.get(decision, "requesting")
    payload = {
        "type": "follow",
        "summary": f"{follow.following.display_name or follow.following.username} {'accepted' if decision == Follow.ACCEPTED else 'rejected'} your follow request",
        "actor": serialize_author_for_node_communication(follow.following),
        "object": serialize_author_for_node_communication(follow.follower),
        "state": payload_state,
    }

    logger.info(f"{log_prefix} Payload: {payload}")
    result = send_to_inbox(payload, remote_node, target_author.id)
    logger.info(f"{log_prefix} Result: {'SUCCESS' if result else 'FAILED'}")


def send_unfollow_to_remote_node(follower, followee):
    """Send unfollow notification to remote author's inbox."""
    log_prefix = "[SEND UNFOLLOW]"
    logger.info(f"{log_prefix} Starting: follower={follower.id}, followee={followee.id}")
    
    target_author = followee
    local_node, remote_node = _validate_and_get_remote_node(target_author, log_prefix)
    if not remote_node:
        return

    payload = {
        "type": "follow",
        "summary": f"{follower.display_name or follower.username} unfollowed {followee.display_name or followee.username}",
        "actor": serialize_author_for_node_communication(follower),
        "object": serialize_author_for_node_communication(followee),
        "state": "unfollow",
    }

    logger.info(f"{log_prefix} Payload: {payload}")
    result = send_to_inbox(payload, remote_node, target_author.id)
    logger.info(f"{log_prefix} Result: {'SUCCESS' if result else 'FAILED'}")

