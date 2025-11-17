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
)

logger = logging.getLogger(__name__)


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
    """
    Get or create a remote author from FQID and data.
    
    Args:
        author_fqid: Full URL like "https://node.com/api/authors/uuid"
        author_data: Dict with author info (displayName, github, etc.)
        remote_node: Optional Node object. If None, will be looked up from FQID.
    
    Returns:
        tuple: (author, created) - Author object and whether it was created
    """
    author_uuid, node_url = parse_author_fqid(author_fqid)
    author_uuid_str = str(author_uuid)
    
    # Get remote node if not provided
    if remote_node is None:
        try:
            remote_node = Node.objects.get(host_url=node_url, is_local=False)
        except Node.DoesNotExist:
            raise ValueError(f"Remote node not found: {node_url}")
    
    # Get or create the author
    author, created = Author.objects.get_or_create(
        id=author_uuid,
        defaults={
            "username": f"remote_{author_uuid_str[:8]}",
            "display_name": author_data.get("displayName", ""),
            "node": remote_node,
            "is_active": True,
            "approved": True,
            "github_url": author_data.get("github", "")
        }
    )
    
    # Update existing author with fresh data (in case display name or other info changed)
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
        
        # Update node reference if it changed
        if author.node != remote_node:
            author.node = remote_node
            updated = True
        
        if updated:
            author.save(update_fields=['display_name', 'github_url', 'node'])
    
    return author, created


def serialize_author(author):
    """Serialize author for API"""
    local_node = get_local_node()
    host_url = local_node.host_url.rstrip('/') + '/' if local_node else ""
    
    # Get profile image URL
    profile_image = ""
    if author.image:
        profile_image = f"{host_url.rstrip('/')}{author.image.url}"
    
    return {
        "type": "author",
        "id": build_fqid("", author_id=author.id),
        "host": f"{host_url}api/",
        "displayName": author.display_name or author.username,
        "github": author.github_url or "",
        "profileImage": profile_image,
        "web": f"{host_url}authors/{author.username}/" if author.username else "",
    }


def send_to_inbox(payload, remote_node, author_id):
    """
    Send payload to remote author's inbox.
    """
    remote_author_url = build_remote_url(remote_node.host_url, author_id)
    inbox_url = f"{remote_author_url.rstrip('/')}/inbox/"
    
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
    """Send entry notification to remote followers' inboxes"""
    local_node = get_local_node()
    if not local_node:
        return

    recipients = get_remote_recipients_for_entry(entry, local_node)
    if not recipients:
        return

    host_url = local_node.host_url.rstrip('/')
    entry_web_url = f"{host_url}/entries/{entry.id}/"
    
    payload = {
        "type": "entry",
        "id": build_entry_url(entry.author.id, entry.id),
        "web": entry_web_url,
        "title": "",
        "description": entry.content[:100] if entry.content else "",
        "contentType": entry.content_type,
        "content": entry.content,
        "author": serialize_author(entry.author),
        "published": entry.created_at.isoformat(),
        "visibility": entry.visibility.upper(),
    }
    
    for recipient in recipients:
        remote_node = recipient.node
        if remote_node.username:
            send_to_inbox(payload, remote_node, recipient.id)


def send_like_to_remote_node(like, entry, *, removed=False):
    """Send like notification to entry author's inbox (if remote)"""
    local_node = get_local_node()
    if not local_node or entry.author.node == local_node:
        return
    
    remote_node = entry.author.node
    if not remote_node.username:
        return
    
    object_url = entry.source_url or build_entry_url(entry.author.id, entry.id)
    
    payload = {
        "type": "like",
        "author": serialize_author(like.author),
        "published": like.created_at.isoformat(),
        "id": f"{build_fqid('', author_id=like.author.id)}/liked/{like.id}",
        "object": object_url,
    }
    if removed:
        payload["removed"] = True
    
    send_to_inbox(payload, remote_node, entry.author.id)


def send_comment_to_remote_node(comment, entry, state=None):
    """Send comment notification to entry author's inbox (if remote)
    According to the project description, comments should have the following fields: type, author, comment, contentType, published, id, entry, web, likes
    """
    local_node = get_local_node()
    if not local_node or entry.author.node == local_node:
        return
    
    remote_node = entry.author.node
    if not remote_node.username:
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
        "author": serialize_author(comment.author),
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
    """
    Send a like on a comment to the comment author's node (if remote).
    """
    comment = comment_like.comment
    local_node = get_local_node()
    if not local_node:
        return

    comment_author_node = getattr(comment.author, "node", None)
    if not comment_author_node or comment_author_node == local_node:
        return

    if not comment_author_node.username:
        logger.warning(
            "send_comment_like_to_remote_node: remote node %s missing credentials",
            comment_author_node.host_url,
        )
        return

    object_url = comment.source_url or build_comment_url(comment)
    if not object_url:
        logger.warning("send_comment_like_to_remote_node: missing comment URL")
        return

    payload = {
        "type": "like",
        "summary": f"{comment_like.author.display_name or comment_like.author.username} liked a comment",
        "author": serialize_author(comment_like.author),
        "object": object_url,
    }
    if removed:
        payload["removed"] = True

    send_to_inbox(payload, comment_author_node, comment.author_id)


def parse_follow_state_from_payload(state_str):
    """
    Parse incoming follow state string from remote node payload to Follow status constant.
    
    Maps various state strings (requesting, pending, accepted, accept, rejected, denied, deny)
    to our internal Follow status constants (PENDING, ACCEPTED, DENIED).
    
    Args:
        state_str: State string from remote node payload
        
    Returns:
        Follow status constant (PENDING, ACCEPTED, or DENIED)
    """
    state_map = {
        "requesting": Follow.PENDING,
        "pending": Follow.PENDING,
        "accepted": Follow.ACCEPTED,
        "accept": Follow.ACCEPTED,
        "rejected": Follow.DENIED,
        "denied": Follow.DENIED,
        "deny": Follow.DENIED,
    }
    return state_map.get(state_str.lower() if state_str else "", Follow.PENDING)


FOLLOW_STATE_TO_SPEC = {
    Follow.PENDING: "requesting",
    Follow.ACCEPTED: "accepted",
    Follow.DENIED: "rejected",
}


def send_follow_request_to_remote_node(follow):
    """
    Send a follow request notification to a remote author's inbox.
    
    This is used when a local user requests to follow a remote author.
    The notification is sent to the followee (the person being followed).
    
    Args:
        follow: Follow model instance with status=PENDING
    """
    logger.info(f"[SEND FOLLOW REQUEST] Starting: follow_id={follow.id}")
    logger.info(f"[SEND FOLLOW REQUEST] Follower: id={follow.follower_id}, name={follow.follower.display_name}, node={follow.follower.node.host_url if follow.follower.node else 'None'}")
    logger.info(f"[SEND FOLLOW REQUEST] Following: id={follow.following_id}, name={follow.following.display_name}, node={follow.following.node.host_url if follow.following.node else 'None'}")
    logger.info(f"[SEND FOLLOW REQUEST] Status: {follow.status}, Approved: {follow.approved}")
    
    local_node = get_local_node()
    if not local_node:
        logger.warning("[SEND FOLLOW REQUEST] Local node not configured, aborting")
        return

    # Notify the followee (person being followed)
    target_author = follow.following
    logger.info(f"[SEND FOLLOW REQUEST] Target author: id={target_author.id}, is_local={target_author.node == local_node}")
    
    if target_author.node == local_node:
        logger.info(
            "[SEND FOLLOW REQUEST] Target author %s is local, skipping remote notification",
            target_author.id,
        )
        return

    remote_node = target_author.node
    if not remote_node.username:
        logger.warning(
            "[SEND FOLLOW REQUEST] Remote node %s missing credentials, aborting",
            remote_node.host_url,
        )
        return

    payload = {
        "type": "follow",
        "summary": f"{follow.follower.display_name or follow.follower.username} wants to follow {follow.following.display_name or follow.following.username}",
        "actor": serialize_author(follow.follower),
        "object": serialize_author(follow.following),
        "state": "requesting",
    }

    logger.info(f"[SEND FOLLOW REQUEST] Payload: {payload}")
    logger.info(
        "[SEND FOLLOW REQUEST] Sending to: node=%s, author_id=%s, inbox_url=%s/api/authors/%s/inbox/",
        remote_node.host_url,
        target_author.id,
        remote_node.host_url,
        target_author.id,
    )

    result = send_to_inbox(payload, remote_node, target_author.id)
    logger.info(f"[SEND FOLLOW REQUEST] Result: {'SUCCESS' if result else 'FAILED'}")


def send_follow_decision_to_remote_node(follow, decision):
    """
    Send a follow decision (accept/deny) notification to a remote author's inbox.
    
    This is used when a local user accepts or denies a follow request from a remote user.
    The notification is sent to the follower (the person who made the request).
    
    Args:
        follow: Follow model instance
        decision: Either Follow.ACCEPTED or Follow.DENIED constant
    """
    logger.info(f"[SEND FOLLOW DECISION] Starting: follow_id={follow.id}, decision={decision}")
    
    if decision not in (Follow.ACCEPTED, Follow.DENIED):
        logger.error(f"[SEND FOLLOW DECISION] Invalid decision {decision}, must be ACCEPTED or DENIED, aborting")
        return
    
    logger.info(f"[SEND FOLLOW DECISION] Follower: id={follow.follower_id}, name={follow.follower.display_name}, node={follow.follower.node.host_url if follow.follower.node else 'None'}")
    logger.info(f"[SEND FOLLOW DECISION] Following: id={follow.following_id}, name={follow.following.display_name}, node={follow.following.node.host_url if follow.following.node else 'None'}")
    logger.info(f"[SEND FOLLOW DECISION] Current status: {follow.status}, Approved: {follow.approved}")
    
    local_node = get_local_node()
    if not local_node:
        logger.warning("[SEND FOLLOW DECISION] Local node not configured, aborting")
        return

    # Notify the follower (person who made the request)
    target_author = follow.follower
    logger.info(f"[SEND FOLLOW DECISION] Target author: id={target_author.id}, is_local={target_author.node == local_node}")
    
    if target_author.node == local_node:
        logger.info(
            "[SEND FOLLOW DECISION] Target author %s is local, skipping remote notification",
            target_author.id,
        )
        return

    remote_node = target_author.node
    if not remote_node.username:
        logger.warning(
            "[SEND FOLLOW DECISION] Remote node %s missing credentials, aborting",
            remote_node.host_url,
        )
        return

    payload_state = FOLLOW_STATE_TO_SPEC.get(decision, "requesting")
    logger.info(f"[SEND FOLLOW DECISION] Payload state: {payload_state}")
    
    payload = {
        "type": "follow",
        "summary": f"{follow.following.display_name or follow.following.username} {'accepted' if decision == Follow.ACCEPTED else 'rejected'} your follow request",
        "actor": serialize_author(follow.following),
        "object": serialize_author(follow.follower),
        "state": payload_state,
    }

    logger.info(f"[SEND FOLLOW DECISION] Payload: {payload}")
    logger.info(
        "[SEND FOLLOW DECISION] Sending to: node=%s, author_id=%s, inbox_url=%s/api/authors/%s/inbox/",
        remote_node.host_url,
        target_author.id,
        remote_node.host_url,
        target_author.id,
    )

    result = send_to_inbox(payload, remote_node, target_author.id)
    logger.info(f"[SEND FOLLOW DECISION] Result: {'SUCCESS' if result else 'FAILED'}")


def get_remote_author_from_json_data(remote_author_json_data):
    """
    Get or create remote author from JSON data (used in inbox handlers).
    
    This is a convenience wrapper around get_or_create_remote_author that
    extracts the author FQID from the JSON author data dict.
    
    Args:
        remote_author_json_data: Dict with author info including 'id' field (the FQID).
                                 This is the JSON representation of a remote author from
                                 the 'actor' or 'author' field in inbox payloads.
        
    Returns:
        Author object
        
    Raises:
        ValueError: If author_fqid is missing or invalid
    """
    author_fqid = remote_author_json_data.get("id", "")
    if not author_fqid:
        raise ValueError("Author ID missing")
    
    try:
        remote_author, _ = get_or_create_remote_author(author_fqid, remote_author_json_data)
        return remote_author
    except ValueError as e:
        logger.error(f"Failed to get/create remote author: {e}")
        raise


def find_entry_by_url(entry_url):
    """
    Find entry by URL, trying source_url first, then parsing ID from URL.
    
    This utility function is used by inbox handlers to resolve remote entry
    references to local Entry objects.
    
    Args:
        entry_url: Entry FQID URL
        
    Returns:
        Entry object
        
    Raises:
        Entry.DoesNotExist: If entry cannot be found
    """
    # Try source_url first (for remote entries)
    try:
        return Entry.objects.get(source_url=entry_url)
    except Entry.DoesNotExist:
        pass
    
    # Fallback: parse entry ID from URL
    try:
        entry_uuid, author_uuid, _ = parse_entry_fqid(entry_url)
        return Entry.objects.get(id=entry_uuid, author_id=author_uuid)
    except (ValueError, Entry.DoesNotExist):
        raise Entry.DoesNotExist(f"Entry not found for URL: {entry_url}")


def find_comment_by_url(comment_url):
    """
    Find a comment by its source URL or by parsing the local FQID.
    
    This utility function is used by inbox handlers to resolve remote comment
    references to local Comment objects.
    
    Args:
        comment_url: Comment URL (either source_url or FQID format)
        
    Returns:
        Comment object
        
    Raises:
        Comment.DoesNotExist: If comment cannot be found
    """
    if not comment_url:
        raise Comment.DoesNotExist("Comment URL missing")

    # Try source_url first (for remote comments)
    comment = Comment.objects.filter(source_url=comment_url).first()
    if comment:
        return comment

    # Fallback: parse comment ID from URL format like /api/authors/{uuid}/commented/{id}
    url = comment_url.rstrip("/")
    if "/commented/" in url:
        base, comment_id_str = url.split("/commented/", 1)
        try:
            comment_id = int(comment_id_str)
        except ValueError as exc:
            raise Comment.DoesNotExist(f"Invalid comment URL: {comment_url}") from exc
        try:
            author_uuid, _ = parse_author_fqid(base + "/")
        except ValueError as exc:
            raise Comment.DoesNotExist(f"Invalid comment URL: {comment_url}") from exc
        return Comment.objects.get(id=comment_id, author_id=author_uuid)

    raise Comment.DoesNotExist(f"Comment not found for URL: {comment_url}")