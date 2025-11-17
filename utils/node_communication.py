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
    
    try:
        local_node = get_local_node()
        if not local_node:
            return False
        
        if not local_node.username or not local_node.password:
            logger.error("Local node credentials not set, cannot send to inbox")
            return False
        
        response = requests.post(
            inbox_url,
            json=payload,
            auth=HTTPBasicAuth(local_node.username, local_node.password),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Sent to {inbox_url}")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send to {inbox_url}: {e}")
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


FOLLOW_STATE_TO_SPEC = {
    Follow.PENDING: "requesting",
    Follow.ACCEPTED: "accepted",
    Follow.DENIED: "rejected",
}


def send_follow_to_remote_node(follow, *, state=None, target="following"):
    """
    Send follow notification/decision to a remote author's inbox.
    
    Args:
        follow: Follow model instance
        state: Optional override for follow status (use Follow constants)
        target: "following" to notify the followee (default for new requests),
                "follower" to notify the follower (used when decision is made)
    """
    logger.info(f"Sending follow notification to remote node: {follow.id}")
    local_node = get_local_node()
    if not local_node:
        logger.warning("send_follow_to_remote_node: local node not configured")
        return

    target_author = follow.following if target == "following" else follow.follower
    if target_author.node == local_node:
        logger.info(
            "send_follow_to_remote_node: target author %s is local, skipping",
            target_author.id,
        )
        return

    remote_node = target_author.node
    if not remote_node.username:
        logger.warning(
            "send_follow_to_remote_node: remote node %s missing credentials",
            remote_node.host_url,
        )
        return

    state_value = (state or follow.status or Follow.PENDING).lower()
    payload_state = FOLLOW_STATE_TO_SPEC.get(state_value, FOLLOW_STATE_TO_SPEC[Follow.PENDING])

    logger.info(
        "send_follow_to_remote_node: sending state=%s target=%s follower=%s following=%s to %s",
        payload_state,
        target,
        follow.follower_id,
        follow.following_id,
        remote_node.host_url,
    )

    payload = {
        "type": "follow",
        "summary": f"{follow.follower.display_name or follow.follower.username} wants to follow {follow.following.display_name or follow.following.username}",
        "actor": serialize_author(follow.follower),
        "object": serialize_author(follow.following),
        "state": payload_state,
    }

    send_to_inbox(payload, remote_node, target_author.id)