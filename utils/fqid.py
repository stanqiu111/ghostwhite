import logging
import uuid

from nodes.models import Node
from entries.models import Entry, Comment

logger = logging.getLogger(__name__)


def get_local_node():
    """Return the configured local node or None if missing."""
    try:
        return Node.objects.get(is_local=True)
    except Node.DoesNotExist:
        logger.error("Local node is not configured")
        return None


def _get_local_host_url():
    local_node = get_local_node()
    if not local_node:
        return None
    return local_node.host_url.rstrip('/') + '/'


def build_fqid(path="", author_id=None, entry_id=None):
    """Build Fully Qualified ID for authors or entries."""
    host_url = _get_local_host_url()
    if not host_url:
        return None
    if author_id:
        author_id = extract_serial_from_fqid(author_id)
    if entry_id:
        return f"{host_url}api/authors/{author_id}/entries/{entry_id}"
    if author_id:
        return f"{host_url}api/authors/{author_id}"
    return f"{host_url}{path}"


def build_entry_url(author_id, entry_id):
    """Helper to build a canonical entry URL."""
    author_id = extract_serial_from_fqid(author_id)
    return build_fqid("", author_id=author_id, entry_id=entry_id)


def build_entry_fqid(author_id, entry_uuid):
    host_url = _get_local_host_url()
    if not host_url:
        return None
    author_id = extract_serial_from_fqid(author_id)
    return f"{host_url}api/authors/{author_id}/entries/{entry_uuid}"


def build_comment_url(comment):
    """
    Build a fully qualified URL for a comment (api/authors/<author>/commented/<id>).
    """
    host_url = _get_local_host_url()
    if not host_url:
        return None
    author_id = extract_serial_from_fqid(comment.author_id)
    return f"{host_url}api/authors/{author_id}/commented/{comment.id}"


def build_comment_fqid(author_id, comment_uuid):
    """Build FQID for a comment (used as comment.id)."""
    host_url = _get_local_host_url()
    if not host_url:
        return None
    author_id = extract_serial_from_fqid(author_id)
    return f"{host_url}api/authors/{author_id}/commented/{comment_uuid}"


def extract_serial_from_fqid(author_fqid_or_id):
    if '/api/authors/' in str(author_fqid_or_id):
        return str(author_fqid_or_id).split('/api/authors/')[-1]
    return str(author_fqid_or_id)


def extract_entry_id_from_fqid(entry_fqid):
    if '/entries/' in str(entry_fqid):
        return str(entry_fqid).split('/entries/')[-1].split('/')[0].split('?')[0]
    return str(entry_fqid)


def extract_comment_id_from_fqid(comment_fqid):
    if '/commented/' in str(comment_fqid):
        return str(comment_fqid).split('/commented/')[-1].split('/')[0].split('?')[0]
    return str(comment_fqid)

def build_remote_url(host_url, author_id):
    """Build remote author URL for inbox endpoint."""
    author_id = extract_serial_from_fqid(author_id)
    return f"{host_url.rstrip('/')}/api/authors/{author_id}"


def parse_author_fqid(author_fqid):
    """
    Parse author FQID to extract full FQID and node URL.
    Returns: (full_fqid, node_url) where full_fqid is the normalized FQID string.
    """
    if not author_fqid:
        raise ValueError("Author FQID is required")

    try:
        normalized_fqid = author_fqid.rstrip('/')
        parts = normalized_fqid.split('/api/authors/')
        if len(parts) != 2:
            raise ValueError(f"Invalid author FQID format: {author_fqid}")
        node_url = parts[0] + '/'
        return normalized_fqid, node_url
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Invalid author FQID format: {author_fqid}") from exc

def is_valid_uuid(uuid_str):
    try:
        uuid.UUID(uuid_str)
        return True
    except ValueError:
        return False

def parse_entry_fqid(entry_fqid):
    """
    Parse entry FQID to extract entry UUID, author FQID, and node URL.
    Returns: (entry_uuid, author_fqid, node_url)
    """
    if not entry_fqid:
        raise ValueError("Entry FQID is required")

    try:
        url = entry_fqid.rstrip('/')
        if '/entries/' not in url:
            raise ValueError(f"Invalid entry FQID format: {entry_fqid}")
        base_url, entry_uuid_str = url.split('/entries/', 1)
        entry_uuid = uuid.UUID(entry_uuid_str)

        author_parts = base_url.split('/api/authors/')
        if len(author_parts) != 2:
            raise ValueError(f"Invalid entry FQID format: {entry_fqid}")

        node_url = author_parts[0] + '/'
        author_fqid = base_url
        return entry_uuid, author_fqid, node_url
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Invalid entry FQID format: {entry_fqid}") from exc


def find_entry_by_url(entry_url):
    """Find entry by URL, trying source_url first, then parsing ID from URL."""
    try:
        return Entry.objects.select_related('author', 'author__node').get(source_url=entry_url)
    except Entry.DoesNotExist:
        pass
    
    try:
        entry_uuid, author_fqid, _ = parse_entry_fqid(entry_url)
        entries = Entry.objects.filter(author_id=author_fqid).select_related('author', 'author__node')
        for entry in entries:
            if extract_entry_id_from_fqid(entry.id) == str(entry_uuid):
                return entry
        raise Entry.DoesNotExist(f"Entry not found for URL: {entry_url}")
    except (ValueError, Entry.DoesNotExist):
        raise Entry.DoesNotExist(f"Entry not found for URL: {entry_url}")


def find_entry_by_uuid(entry_uuid, author_fqid=None):
    if author_fqid:
        entries = Entry.objects.filter(author_id=author_fqid).select_related('author', 'author__node')
    else:
        entries = Entry.objects.all().select_related('author', 'author__node')
    
    for entry in entries:
        extracted_uuid = extract_entry_id_from_fqid(entry.id)
        if extracted_uuid == str(entry_uuid):
            return entry
    
    raise Entry.DoesNotExist(f"Entry not found with UUID: {entry_uuid}")


def find_comment_by_url(comment_url):
    """Find comment by URL, trying source_url first, then parsing ID from URL."""
    if not comment_url:
        raise Comment.DoesNotExist("Comment URL missing")

    comment = Comment.objects.filter(source_url=comment_url).select_related('author', 'author__node').first()
    if comment:
        return comment
    
    try:
        return Comment.objects.select_related('author', 'author__node').get(id=comment_url)
    except Comment.DoesNotExist:
        pass
    
    url = comment_url.rstrip("/")
    if "/commented/" in url:
        base, comment_uuid_str = url.split("/commented/", 1)
        comment_uuid = comment_uuid_str.split('/')[0].split('?')[0]
        try:
            author_fqid, _ = parse_author_fqid(base + "/")
        except ValueError as exc:
            raise Comment.DoesNotExist(f"Invalid comment URL: {comment_url}") from exc
        
        comments = Comment.objects.filter(author_id=author_fqid).select_related('author', 'author__node')
        for comment in comments:
            if extract_comment_id_from_fqid(comment.id) == comment_uuid:
                return comment

    raise Comment.DoesNotExist(f"Comment not found for URL: {comment_url}")


def find_comment_by_uuid(comment_uuid, entry_id=None):
    if entry_id:
        entry = find_entry_by_uuid(entry_id)
        comments = Comment.objects.filter(entry=entry).select_related('author', 'author__node')
    else:
        comments = Comment.objects.all().select_related('author', 'author__node')
    
    for comment in comments:
        extracted_uuid = extract_comment_id_from_fqid(comment.id)
        if extracted_uuid == str(comment_uuid):
            return comment
    
    raise Comment.DoesNotExist(f"Comment not found with UUID: {comment_uuid}")

