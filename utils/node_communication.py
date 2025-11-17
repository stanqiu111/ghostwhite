import logging

import requests
from requests.auth import HTTPBasicAuth

from authors.models import Author, Follow
from entries.models import Entry, EntryLike, Comment
from nodes.models import Node
from utils.fqid import (
    build_entry_url,
    build_fqid,
    build_remote_url,
    get_local_node,
    parse_author_fqid,
)

logger = logging.getLogger(__name__)


def get_remote_recipients_for_entry(entry, local_node):
    """Return remote authors that should receive an entry notification. The recipients should be all the followers that are not local"""
    if not local_node:
        return []

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


def send_like_to_remote_node(like, entry):
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
    
    send_to_inbox(payload, remote_node, entry.author.id)


def send_comment_to_remote_node(comment, entry):
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
    comment_id_url = f"{build_fqid('', author_id=comment.author.id)}/commented/{comment.id}"
    
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
    
    send_to_inbox(payload, remote_node, entry.author.id)


def send_follow_to_remote_node(follow):
    """Send follow request notification to target author's inbox (if remote)"""
    local_node = get_local_node()
    if not local_node or follow.following.node == local_node:
        return
    
    remote_node = follow.following.node
    if not remote_node.username:
        return
    
    payload = {
        "type": "follow",
        "summary": f"{follow.follower.display_name or follow.follower.username} wants to follow {follow.following.display_name or follow.following.username}",
        "actor": serialize_author(follow.follower),
        "object": serialize_author(follow.following),
    }
    
    send_to_inbox(payload, remote_node, follow.following.id)