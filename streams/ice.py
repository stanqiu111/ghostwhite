"""ICE configuration; a TURN REST shared secret never leaves the server."""
import base64
import copy
import hashlib
import hmac
import time

from django.conf import settings


def ice_configuration():
    servers = copy.deepcopy(settings.STREAM_ICE_SERVERS)
    config = {"iceServers": servers}
    if settings.STREAM_TURN_URLS and settings.STREAM_TURN_SHARED_SECRET:
        config["expiresAt"] = int(time.time()) + 3600
        username = str(config["expiresAt"])
        credential = base64.b64encode(hmac.new(
            settings.STREAM_TURN_SHARED_SECRET.encode(), username.encode(), hashlib.sha1,
        ).digest()).decode()
        servers.append({"urls": settings.STREAM_TURN_URLS,
                        "username": username, "credential": credential})
    return config
