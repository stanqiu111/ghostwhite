"""Node-to-node communication utilities"""
import requests
from requests.auth import HTTPBasicAuth
from nodes.models import Node
from authors.models import Author, Follow
from entries.models import Entry, EntryLike, Comment
import logging

logger = logging.getLogger(__name__)


def build_fqid(path, author_id=None, entry_id=None):
    """Build Fully Qualified ID"""
    local_node = Node.objects.get(is_local=True)
    if not local_node:
        return None
    host_url = local_node.host_url.rstrip('/') + '/'
    if entry_id:
        return f"{host_url}api/authors/{author_id}/entries/{entry_id}"
    elif author_id:
        return f"{host_url}api/authors/{author_id}"
    return f"{host_url}{path}"


def serialize_author(author):
    """Serialize author for API"""
    local_node = Node.objects.get(is_local=True)
    host_url = local_node.host_url.rstrip('/') + '/' if local_node else ""
    
    # Get profile image URL
    profile_image = ""
    if author.image:
        profile_image = f"{host_url.rstrip('/')}{author.image.url}"
    
    return {
        "type": "author",
        "id": build_fqid(author_id=author.id),
        "host": f"{host_url}api/",
        "displayName": author.display_name or author.username,
        "github": author.github_url or "",
        "profileImage": profile_image,
        "web": f"{host_url}authors/{author.username}/" if author.username else "",
    }


def send_to_inbox(remote_author_url, payload, remote_node):
    """Send payload to remote author's inbox"""
    inbox_url = f"{remote_author_url.rstrip('/')}/inbox"
    try:
        response = requests.post(
            inbox_url,
            json=payload,
            auth=HTTPBasicAuth(remote_node.username, remote_node.password),
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
    local_node = Node.objects.get(is_local=True)
    if not local_node:
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
        "id": build_fqid(author_id=entry.author.id, entry_id=entry.id),
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
    local_node = Node.objects.get(is_local=True)
    if not local_node or entry.author.node == local_node:
        return
    
    remote_node = entry.author.node
    if not remote_node.username:
        return
    
    payload = {
        "type": "like",
        "author": serialize_author(like.author),
        "published": like.created_at.isoformat(),
        "id": f"{build_fqid(author_id=like.author.id)}/liked/{like.id}",
        "object": build_fqid(author_id=entry.author.id, entry_id=entry.id),
    }
    
    remote_url = f"{remote_node.host_url.rstrip('/')}/api/authors/{entry.author.id}"
    send_to_inbox(remote_url, payload, remote_node)


def send_comment_to_remote_node(comment, entry):
    """Send comment notification to entry author's inbox (if remote)"""
    local_node = Node.objects.get(is_local=True)
    if not local_node or entry.author.node == local_node:
        return
    
    remote_node = entry.author.node
    if not remote_node.username:
        return
    
    payload = {
        "type": "comment",
        "author": serialize_author(comment.author),
        "comment": comment.content,
        "contentType": comment.content_type,
        "published": comment.created_at.isoformat(),
        "id": f"{build_fqid(author_id=comment.author.id)}/commented/{comment.id}",
        "entry": build_fqid(author_id=entry.author.id, entry_id=entry.id),
    }
    
    remote_url = f"{remote_node.host_url.rstrip('/')}/api/authors/{entry.author.id}"
    send_to_inbox(remote_url, payload, remote_node)


def send_follow_to_remote_node(follow):
    """Send follow request notification to target author's inbox (if remote)"""
    local_node = Node.objects.get(is_local=True)
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
    
    remote_url = f"{remote_node.host_url.rstrip('/')}/api/authors/{follow.following.id}"
    send_to_inbox(remote_url, payload, remote_node)

