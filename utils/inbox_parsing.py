import logging

from authors.models import Follow
from utils.node_communication import get_or_create_remote_author

logger = logging.getLogger(__name__)


def parse_follow_state_from_payload(state_str):
    """Parse follow state string to Follow status constant."""
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


def get_remote_author_from_json_data(remote_author_json_data):
    """Get or create remote author from JSON data."""
    author_fqid = remote_author_json_data.get("id", "")
    if not author_fqid:
        raise ValueError("Author ID missing")
    
    try:
        remote_author, _ = get_or_create_remote_author(author_fqid, remote_author_json_data)
        return remote_author
    except ValueError as e:
        logger.error(f"Failed to get/create remote author: {e}")
        raise

