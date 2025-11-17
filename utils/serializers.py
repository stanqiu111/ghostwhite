from django.conf import settings
from utils.fqid import build_fqid, get_local_node

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
    local_node = get_local_node()
    host_url = local_node.host_url.rstrip('/') + '/' if local_node else ""
    
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