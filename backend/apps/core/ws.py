"""WebSocket origin check that follows the same host rules as HTTP (configured hosts + private network)."""

from channels.security.websocket import OriginValidator

from .hosts import host_allowed


class HostOriginValidator(OriginValidator):
    """Rejects WebSocket handshakes whose Origin isn't an allowed host (missing Origin is rejected too)."""

    def __init__(self, application):
        super().__init__(application, allowed_origins=[])

    def valid_origin(self, parsed_origin):
        return parsed_origin is not None and host_allowed(parsed_origin.hostname or "")
