"""Node-to-node communication utilities"""
import requests
from requests.auth import HTTPBasicAuth
from nodes.models import Node
from authors.models import Author, Follow
from entries.models import Entry, EntryLike, Comment
import logging
import uuid

logger = logging.getLogger(__name__)


def build_fqid(path, author_id=None, entry_id=None):
    """Build Fully Qualified ID"""
    try:
        local_node = Node.objects.get(is_local=True)
    except Node.DoesNotExist:
        return None
    host_url = local_node.host_url.rstrip('/') + '/'
    if entry_id:
        return f"{host_url}api/authors/{author_id}/entries/{entry_id}"
    elif author_id:
        return f"{host_url}api/authors/{author_id}"
    return f"{host_url}{path}"


def parse_author_fqid(author_fqid):
    """
    Parse author FQID to extract UUID and node URL.
    
    Args:
        author_fqid: Full URL like "https://node.com/api/authors/uuid"
    
    Returns:
        tuple: (author_uuid, node_url) or raises ValueError
    """
    if not author_fqid:
        raise ValueError("Author FQID is required")
    
    try:
        parts = author_fqid.rstrip('/').split('/api/authors/')
        if len(parts) != 2:
            raise ValueError(f"Invalid author FQID format: {author_fqid}")
        node_url = parts[0] + '/'
        author_uuid_str = parts[1]
        author_uuid = uuid.UUID(author_uuid_str)
        return author_uuid, node_url
    except (ValueError, IndexError) as e:
        raise ValueError(f"Invalid author FQID format: {author_fqid}") from e


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
    try:
        local_node = Node.objects.get(is_local=True)
        host_url = local_node.host_url.rstrip('/') + '/'
    except Node.DoesNotExist:
        host_url = ""
    
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


def send_to_inbox(remote_author_url, payload, remote_node):
    """
    Send payload to remote author's inbox.
    """
    inbox_url = f"{remote_author_url.rstrip('/')}/inbox/"
    try:
        try:
            local_node = Node.objects.get(is_local=True)
        except Node.DoesNotExist:
            logger.error("Local node not found, cannot send to inbox")
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
    try:
        local_node = Node.objects.get(is_local=True)
    except Node.DoesNotExist:
        return
    
    if entry.visibility == "friends_only":
        friends = Follow.get_friends(entry.author)
        recipients = [f for f in friends if f.node != local_node]
    else:
        followers = Follow.objects.filter(
            following=entry.author,
            approved=True,
            status=Follow.ACCEPTED
        ).select_related('follower', 'follower__node')
        recipients = [f.follower for f in followers if f.follower.node != local_node]
    
    if not recipients:
        return
    
    payload = {
        "type": "entry",
        "id": build_fqid("", author_id=entry.author.id, entry_id=entry.id),
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
        remote_url = f"{remote_node.host_url.rstrip('/')}/api/authors/{recipient.id}"
        if remote_node.username:
            send_to_inbox(remote_url, payload, remote_node)


def send_like_to_remote_node(like, entry):
    """Send like notification to entry author's inbox (if remote)"""
    try:
        local_node = Node.objects.get(is_local=True)
    except Node.DoesNotExist:
        return
    if entry.author.node == local_node:
        return
    
    remote_node = entry.author.node
    if not remote_node.username:
        return
    
    if entry.source_url:
        object_url = entry.source_url
    else:
        object_url = build_fqid("", author_id=entry.author.id, entry_id=entry.id)
    
    payload = {
        "type": "like",
        "author": serialize_author(like.author),
        "published": like.created_at.isoformat(),
        "id": f"{build_fqid('', author_id=like.author.id)}/liked/{like.id}",
        "object": object_url,
    }
    
    remote_url = f"{remote_node.host_url.rstrip('/')}/api/authors/{entry.author.id}"
    send_to_inbox(remote_url, payload, remote_node)


def send_comment_to_remote_node(comment, entry):
    """Send comment notification to entry author's inbox (if remote)"""
    try:
        local_node = Node.objects.get(is_local=True)
    except Node.DoesNotExist:
        return
    if entry.author.node == local_node:
        return
    
    remote_node = entry.author.node
    if not remote_node.username:
        return
    
    if entry.source_url:
        entry_url = entry.source_url
    else:
        entry_url = build_fqid("", author_id=entry.author.id, entry_id=entry.id)
    
    payload = {
        "type": "comment",
        "author": serialize_author(comment.author),
        "comment": comment.content,
        "contentType": getattr(comment, 'content_type', 'text/plain'),  # Comment model doesn't have content_type, default to text/plain
        "published": comment.created_at.isoformat(),
        "id": f"{build_fqid('', author_id=comment.author.id)}/commented/{comment.id}",
        "entry": entry_url,
    }
    
    remote_url = f"{remote_node.host_url.rstrip('/')}/api/authors/{entry.author.id}"
    send_to_inbox(remote_url, payload, remote_node)


def send_follow_to_remote_node(follow):
    """Send follow request notification to target author's inbox (if remote)"""
    try:
        local_node = Node.objects.get(is_local=True)
    except Node.DoesNotExist:
        return
    if follow.following.node == local_node:
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
    
    remote_url = f"{remote_node.host_url.rstrip('/')}/api/authors/{follow.following.id}"
    send_to_inbox(remote_url, payload, remote_node)


def fetch_and_create_remote_author(author_fqid):
    """
    Fetch author from remote node API and create locally.
    
    Args:
        author_fqid: Full URL like "https://remote-node.com/api/authors/uuid"
    
    Returns:
        Author: The created or existing remote author
    """
    # Parse FQID to get UUID and node URL
    try:
        author_uuid, node_url = parse_author_fqid(author_fqid)
    except ValueError as e:
        raise ValueError(f"Invalid author FQID: {e}")
    
    # Check if author already exists
    try:
        existing_author = Author.objects.get(id=author_uuid)
        logger.info(f"Author {author_uuid} already exists")
        return existing_author
    except Author.DoesNotExist:
        pass
    
    # Find the remote node
    try:
        remote_node = Node.objects.get(host_url=node_url, is_local=False)
    except Node.DoesNotExist:
        raise ValueError(f"Remote node not found: {node_url}. Add it first via Django admin or shell.")
    
    if not remote_node.username or not remote_node.password:
        raise ValueError(f"Remote node credentials not set for {node_url}")
    
    # Fetch author from remote API
    try:
        response = requests.get(
            author_fqid,
            auth=HTTPBasicAuth(remote_node.username, remote_node.password),
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()
        author_data = response.json()
    except requests.RequestException as e:
        raise ValueError(f"Failed to fetch author from {author_fqid}: {e}")
    
    # Create the author locally using the utility function
    author, created = get_or_create_remote_author(author_fqid, author_data, remote_node)
    
    logger.info(f"Created remote author: {author.display_name} (ID: {author.id})")
    return author

