"""Context available to every template, so the shared header can render
correctly no matter which view produced the page."""

from streams.models import Stream


def nav(request):
    """Data the shared header partial needs on every page."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"live_stream_count": 0}
    return {"live_stream_count": Stream.objects.filter(status="live").count()}
