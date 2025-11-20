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
    extract_entry_id_from_fqid,
    extract_serial_from_fqid,
)
from utils.serializers import serialize_author_for_node_communication

logger = logging.getLogger(__name__)


def _validate_and_get_remote_node(target_author, log_prefix=""):
    """Validate and get remote node for sending notifications."""
    logger.info(f"{log_prefix} Validating and getting remote node for target author: {target_author.id}")
    
    try:
        target_author = Author.objects.select_related('node').get(pk=target_author.pk)
        logger.info(f"{log_prefix} Loaded author from DB: {target_author.id}, node_id: {target_author.node_id}, node: {target_author.node}")
    except Author.DoesNotExist:
        logger.error(f"{log_prefix} Target author {target_author.id} not found in database")
        return None, None
    
    local_node = get_local_node()
    if not local_node:
        logger.warning(f"{log_prefix} Local node not configured, aborting")
        return None, None
    
    logger.info(f"{log_prefix} Local node: {local_node.id} (host: {local_node.host_url}), is_local: {local_node.is_local}")
    
    if not target_author.node:
        logger.warning(f"{log_prefix} Target author {target_author.id} has no node set, aborting")
        return None, None
    
    logger.info(f"{log_prefix} Author node: {target_author.node.id} (host: {target_author.node.host_url}), is_local: {target_author.node.is_local}")
    logger.info(f"{log_prefix} Node comparison: target_author.node.id={target_author.node.id}, local_node.id={local_node.id}, equal={target_author.node.id == local_node.id}")
    logger.info(f"{log_prefix} Node host comparison: target_author.node.host_url={target_author.node.host_url}, local_node.host_url={local_node.host_url}")
    logger.info(f"{log_prefix} Node object comparison: target_author.node == local_node = {target_author.node == local_node}")
    
    # Check if author is local by comparing both node ID and host URL
    is_local = (
        target_author.node.id == local_node.id or 
        target_author.node.host_url.rstrip('/') == local_node.host_url.rstrip('/') or
        target_author.node.is_local
    )
    
    if is_local:
        logger.info(f"{log_prefix} Target author {target_author.id} is local (node ID: {target_author.node.id}, host: {target_author.node.host_url}), skipping remote notification")
        return None, None
    
    remote_node = target_author.node
    if not remote_node.username:
        logger.warning(f"{log_prefix} Remote node {remote_node.id} (host: {remote_node.host_url}) missing credentials (username), aborting")
        return None, None

    logger.info(f"{log_prefix} Remote node found: {remote_node.id} (host: {remote_node.host_url}), sending notification")
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
    author_uuid = extract_serial_from_fqid(author_id)
    base_url = remote_node.host_url.rstrip('/')
    inbox_url = f"{base_url}/api/authors/{author_uuid}/inbox"
    
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
    """Send like to all remote recipients (entry author and other remote likers)."""
    log_prefix = "[SEND LIKE]"
    
    local_node = get_local_node()
    if not local_node:
        logger.info(f"{log_prefix} Local node not configured, skipping inbox notification")
        return
    
    entry_author = Author.objects.select_related('node').get(pk=entry.author.pk)
    
    object_url = None
    if entry.source_url:
        object_url = entry.source_url
        logger.info(f"{log_prefix} Using entry source_url: {object_url}")
    else:
        entry_uuid = extract_entry_id_from_fqid(entry.id)
        author_uuid = extract_serial_from_fqid(entry_author.id)
        entry_author_node = entry_author.node
        if entry_author_node:
            node_host = entry_author_node.host_url.rstrip('/')
            object_url = f"{node_host}/api/authors/{author_uuid}/entries/{entry_uuid}"
            logger.info(f"{log_prefix} Built entry URL from entry ID: {object_url}")
        else:
            logger.warning(f"{log_prefix} Entry {entry.id} has no source_url and entry author has no node - cannot build URL")
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
    """Send comment to all remote recipients (entry author and other remote commenters)."""
    log_prefix = "[SEND COMMENT]"
    
    local_node = get_local_node()
    if not local_node:
        logger.info(f"{log_prefix} Local node not configured, skipping inbox notification")
        return
    
    entry_author = Author.objects.select_related('node').get(pk=entry.author.pk)
    
    entry_url = None
    if entry.source_url:
        entry_url = entry.source_url
        logger.info(f"{log_prefix} Using entry source_url: {entry_url}")
    else:
        entry_uuid = extract_entry_id_from_fqid(entry.id)
        author_uuid = extract_serial_from_fqid(entry_author.id)
        entry_author_node = entry_author.node
        if entry_author_node:
            node_host = entry_author_node.host_url.rstrip('/')
            entry_url = f"{node_host}/api/authors/{author_uuid}/entries/{entry_uuid}"
            logger.info(f"{log_prefix} Built entry URL from entry ID: {entry_url}")
        else:
            logger.warning(f"{log_prefix} Entry {entry.id} has no source_url and entry author has no node - cannot build URL")
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
    
    _, remote_node = _validate_and_get_remote_node(entry_author, log_prefix=log_prefix)
    if remote_node:
        logger.info(f"{log_prefix} Sending to entry author: {entry_author.id}")
        result = send_to_inbox(payload, remote_node, entry_author.id)
        logger.info(f"{log_prefix} Entry author notification result: {'SUCCESS' if result else 'FAILED'}")
    else:
        logger.info(f"{log_prefix} Entry author is local, skipping notification")
    
    other_commenters = (
        Comment.objects.filter(entry=entry)
        .exclude(author=comment.author)
        .exclude(author=entry_author)
        .select_related('author', 'author__node')
        .values_list('author', flat=True)
        .distinct()
    )
    
    # Track which authors we've already notified to avoid duplicates
    notified_authors = set()
    if remote_node:
        notified_authors.add(entry_author.id)
    
    if remote_node:
        excluded_authors = {comment.author.id, entry_author.id}
        
        other_remote_authors = (
            Author.objects.filter(node=remote_node)
            .exclude(id__in=excluded_authors)
            .select_related('node')
        )
        
        logger.info(f"{log_prefix} Found {other_remote_authors.count()} other authors on remote node {remote_node.host_url} to notify")
        
        for author in other_remote_authors:
            if author.id in notified_authors:
                continue
            
            logger.info(f"{log_prefix} Sending to remote author on same node: {author.id}")
            result = send_to_inbox(payload, remote_node, author.id)
            logger.info(f"{log_prefix} Remote author {author.id} notification result: {'SUCCESS' if result else 'FAILED'}")
            notified_authors.add(author.id)
    else:
        logger.info(f"{log_prefix} Entry author is local, no remote authors to notify")


def send_comment_like_to_remote_node(comment_like, *, removed=False):
    """Send comment like to all remote recipients (comment author and entry author)."""
    log_prefix = "[SEND COMMENT LIKE]"
    comment = comment_like.comment
    entry = comment.entry
    
    # Get both potential recipients
    comment_author = Author.objects.select_related('node').get(pk=comment.author.pk)
    entry_author = Author.objects.select_related('node').get(pk=entry.author.pk)
    
    local_node = get_local_node()
    if not local_node:
        logger.info(f"{log_prefix} Local node not configured, skipping inbox notification")
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

    # Send to comment author if remote
    _, remote_node = _validate_and_get_remote_node(comment_author, log_prefix=log_prefix)
    if remote_node:
        logger.info(f"{log_prefix} Sending to comment author: {comment_author.id}")
        send_to_inbox(payload, remote_node, comment_author.id)
    
    # Send to entry author if remote (and different from comment author)
    if entry_author.id != comment_author.id:
        _, remote_node = _validate_and_get_remote_node(entry_author, log_prefix=log_prefix)
        if remote_node:
            logger.info(f"{log_prefix} Sending to entry author: {entry_author.id}")
            send_to_inbox(payload, remote_node, entry_author.id)


FOLLOW_STATE_TO_SPEC = {
    Follow.PENDING: "requesting",
    Follow.ACCEPTED: "accepted",
    Follow.DENIED: "rejected",
}


def send_follow_request_to_remote_node(follow):
    """Send follow request to all remote recipients (the followee if remote)."""
    log_prefix = "[SEND FOLLOW REQUEST]"
    logger.info(f"{log_prefix} Starting: follow_id={follow.id}")
    
    # Get fresh copies to ensure we have latest data
    following_author = Author.objects.select_related('node').get(pk=follow.following.pk)
    follower_author = Author.objects.select_related('node').get(pk=follow.follower.pk)
    
    # Debug: Log the author IDs before serialization
    print(f"{log_prefix} [DEBUG] Following author ID before serialize: {following_author.id}")
    print(f"{log_prefix} [DEBUG] Following author username: {following_author.username}")
    print(f"{log_prefix} [DEBUG] Follower author ID before serialize: {follower_author.id}")
    print(f"{log_prefix} [DEBUG] Follower author username: {follower_author.username}")
    logger.info(f"{log_prefix} Following author ID before serialize: {following_author.id}")
    logger.info(f"{log_prefix} Follower author ID before serialize: {follower_author.id}")
    
    print(f"{log_prefix} [DEBUG] Fresh following author ID: {following_author.id}")
    print(f"{log_prefix} [DEBUG] Fresh follower author ID: {follower_author.id}")
    
    payload = {
        "type": "follow",
        "summary": f"{follower_author.display_name or follower_author.username} wants to follow {following_author.display_name or following_author.username}",
        "actor": serialize_author_for_node_communication(follower_author),
        "object": serialize_author_for_node_communication(following_author),
        "state": "requesting",
    }
    
    print(f"{log_prefix} [DEBUG] Serialized object ID: {payload['object']['id']}")
    print(f"{log_prefix} [DEBUG] Serialized actor ID: {payload['actor']['id']}")

    logger.info(f"{log_prefix} Payload: {payload}")
    
    # Send to followee (the person being followed) if remote
    local_node, remote_node = _validate_and_get_remote_node(following_author, log_prefix)
    if remote_node:
        logger.info(f"{log_prefix} Sending to followee: {following_author.id}")
        result = send_to_inbox(payload, remote_node, following_author.id)
        logger.info(f"{log_prefix} Result: {'SUCCESS' if result else 'FAILED'}")
    else:
        logger.info(f"{log_prefix} Followee is local, skipping remote notification")


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

