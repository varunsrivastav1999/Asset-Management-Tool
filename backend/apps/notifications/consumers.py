import asyncio
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from .services import BROADCAST_GROUP, DASHBOARD_GROUP, user_group

logger = logging.getLogger(__name__)

AUTH_TIMEOUT_SECONDS = 10
CLOSE_UNAUTHORIZED = 4401


@database_sync_to_async
def _user_for_token(raw: str):
    try:
        token = AccessToken(raw)
    except TokenError:
        return None
    User = get_user_model()
    claim = settings.SIMPLE_JWT.get("USER_ID_CLAIM", "user_id")
    return User.objects.filter(pk=token.get(claim), is_active=True).first()


@database_sync_to_async
def _unread_count(user) -> int:
    return user.notifications.filter(is_read=False).count()


class RealtimeConsumer(AsyncJsonWebsocketConsumer):
    """Single multiplexed socket per browser tab.

    Protocol: client connects, then must send {"type": "auth", "token": "<access JWT>"} within 10s.
    Tokens are never put in the URL, so they don't end up in proxy access logs.
    """

    user = None
    groups_joined: list[str]

    async def connect(self):
        self.groups_joined = []
        await self.accept()
        self._auth_timer = asyncio.create_task(self._auth_deadline())

    async def _auth_deadline(self):
        await asyncio.sleep(AUTH_TIMEOUT_SECONDS)
        if self.user is None:
            await self.close(code=CLOSE_UNAUTHORIZED)

    async def disconnect(self, code):
        timer = getattr(self, "_auth_timer", None)
        if timer and not timer.done():
            timer.cancel()
        for group in self.groups_joined:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            return
        kind = content.get("type")
        if kind == "auth":
            await self._authenticate(content.get("token") or "")
            return
        if self.user is None:
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        if kind == "ping":
            await self.send_json({"type": "pong"})

    async def _authenticate(self, raw):
        user = await _user_for_token(raw)
        if user is None:
            await self.send_json({"type": "auth.error", "detail": "Invalid or expired token."})
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        if self.user is not None and self.user.pk != user.pk:
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        first = self.user is None
        self.user = user
        if first:
            groups = [user_group(user.pk), BROADCAST_GROUP]
            if user.is_manager:
                groups.append(DASHBOARD_GROUP)
            for group in groups:
                await self.channel_layer.group_add(group, self.channel_name)
            self.groups_joined = groups
        await self.send_json({"type": "auth.ok", "user_id": user.pk, "unread": await _unread_count(user)})

    async def push(self, event):
        await self.send_json(event["payload"])
