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
    if entry_id:
        return f"{host_url}api/authors/{author_id}/entries/{entry_id}"
    if author_id:
        return f"{host_url}api/authors/{author_id}"
    return f"{host_url}{path}"


def build_entry_url(author_id, entry_id):
    """Helper to build a canonical entry URL."""
    return build_fqid("", author_id=author_id, entry_id=entry_id)


def build_comment_url(comment):
    """
    Build a fully qualified URL for a comment (api/authors/<author>/commented/<id>).
    """
    host_url = _get_local_host_url()
    if not host_url:
        return None
    return f"{host_url}api/authors/{comment.author_id}/commented/{comment.id}"


def build_remote_url(host_url, author_id):
    """Build remote author URL for inbox endpoint."""
    return f"{host_url.rstrip('/')}/api/authors/{author_id}"


def parse_author_fqid(author_fqid):
    """Parse author FQID to extract UUID and node URL."""
    parts = author_fqid.rstrip('/').split('/api/authors/')
    return uuid.UUID(parts[1]), parts[0] + '/'


def parse_entry_fqid(entry_fqid):
    """Parse entry FQID to extract entry UUID, author UUID, and node URL."""
    url = entry_fqid.rstrip('/')
    base_url, entry_uuid_str = url.split('/entries/', 1)
    author_parts = base_url.split('/api/authors/')
    return uuid.UUID(entry_uuid_str), uuid.UUID(author_parts[1]), author_parts[0] + '/'


def find_entry_by_url(entry_url):
    """Find entry by URL using source_url, fallback to parsing."""
    entry = Entry.objects.filter(source_url=entry_url).first()
    if entry:
        return entry
    entry_uuid, author_uuid, _ = parse_entry_fqid(entry_url)
    return Entry.objects.get(id=entry_uuid, author_id=author_uuid)


def find_comment_by_url(comment_url):
    """Find comment by URL using source_url, fallback to parsing."""
    comment = Comment.objects.filter(source_url=comment_url).first()
    if comment:
        return comment
    base, comment_id_str = comment_url.rstrip("/").split("/commented/", 1)
    author_uuid, _ = parse_author_fqid(base + "/")
    return Comment.objects.get(id=int(comment_id_str), author_id=author_uuid)

