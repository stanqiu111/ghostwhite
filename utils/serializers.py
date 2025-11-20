from django.conf import settings
from utils.fqid import build_fqid, get_local_node
import logging

class UrlBuildingMixin:
    def build_full_url(self, path: str) -> str:
        """ Build a full unique url from given path"""
        if not path:
            return ""
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(path)
        base = getattr(settings, "HOST_URL", "").rstrip("/")
        return f"{base}{path}" if base else path


def serialize_author_for_node_communication(author):
    """Serialize author for node-to-node communication payloads."""
    from authors.models import Author
    logger = logging.getLogger(__name__)
    
    local_node = get_local_node()
    host_url = local_node.host_url.rstrip('/') + '/' if local_node else ""
    
    # Get fresh copy from database to ensure we have the latest id value
    # refresh_from_db doesn't work for primary keys, so we need to re-fetch
    print(f"[SERIALIZE] [DEBUG] Original author.id: {author.id}")
    print(f"[SERIALIZE] [DEBUG] Original author.pk: {author.pk}")
    try:
        fresh_author = Author.objects.get(pk=author.pk)
        author_fqid = fresh_author.id
        print(f"[SERIALIZE] [DEBUG] Fresh author.id from DB: {author_fqid}")
    except Author.DoesNotExist:
        # Fallback to original author if not found
        author_fqid = author.id
        print(f"[SERIALIZE] [DEBUG] Author not found in DB, using original: {author_fqid}")
    
    logger.info(f"[SERIALIZE] Author {author.username} ID: {author_fqid}")
    print(f"[SERIALIZE] [DEBUG] Final author_fqid: {author_fqid}")
    
    if '/api/' in author_fqid:
        author_host_url = author_fqid.split('/api/')[0] + '/'
    else:
        author_host_url = host_url
    
    profile_image = ""
    if author.image:
        profile_image = f"{host_url.rstrip('/')}{author.image.url}"
    
    return {
        "type": "author",
        "id": author_fqid,
        "host": f"{author_host_url}api/",
        "displayName": author.display_name or author.username,
        "github": author.github_url or "",
        "profileImage": profile_image,
        "web": f"{author_host_url}authors/{author.username}/" if author.username else "",
    }