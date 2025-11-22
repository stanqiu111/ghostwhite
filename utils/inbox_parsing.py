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


def get_remote_author_from_json_data(remote_author_json_data, return_created=False):
    """Get or create remote author from JSON data.
    
    Args:
        remote_author_json_data: Dict containing author data with 'id' field
        return_created: If True, returns (author, created) tuple, else just author
    
    Returns:
        Author object, or (Author, bool) tuple if return_created=True
    """
    author_fqid = remote_author_json_data.get("id", "")
    if not author_fqid:
        raise ValueError("Author ID missing")
    
    try:
        remote_author, created = get_or_create_remote_author(author_fqid, remote_author_json_data)
        if return_created:
            return remote_author, created
        return remote_author
    except ValueError as e:
        logger.error(f"Failed to get/create remote author: {e}")
        raise

