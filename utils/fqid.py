import logging
import uuid

from nodes.models import Node

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
    """
    Parse author FQID to extract UUID and node URL.
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
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Invalid author FQID format: {author_fqid}") from exc


def parse_entry_fqid(entry_fqid):
    """
    Parse entry FQID to extract entry UUID, author UUID, and node URL.
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
        author_uuid = uuid.UUID(author_parts[1])
        return entry_uuid, author_uuid, node_url
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Invalid entry FQID format: {entry_fqid}") from exc

