from django.conf import settings

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