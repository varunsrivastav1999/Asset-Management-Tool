import pytest
from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken

from apps.navigation.models import SidebarItem
from apps.notifications.consumers import RealtimeConsumer
from apps.notifications.services import broadcast_dashboard, notify

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]


async def connect():
    comm = WebsocketCommunicator(RealtimeConsumer.as_asgi(), "/ws/realtime/")
    connected, _ = await comm.connect()
    assert connected
    return comm


async def test_rejects_invalid_token():
    comm = await connect()
    await comm.send_json_to({"type": "auth", "token": "garbage"})
    assert (await comm.receive_json_from())["type"] == "auth.error"
    assert (await comm.receive_output())["type"] == "websocket.close"


async def test_messages_before_auth_close_socket():
    comm = await connect()
    await comm.send_json_to({"type": "ping"})
    assert (await comm.receive_output())["type"] == "websocket.close"


async def test_authenticated_user_receives_notifications_and_pong(employee):
    comm = await connect()
    await comm.send_json_to({"type": "auth", "token": str(AccessToken.for_user(employee))})
    ok = await comm.receive_json_from()
    assert ok["type"] == "auth.ok" and ok["user_id"] == employee.id
    await comm.send_json_to({"type": "ping"})
    assert (await comm.receive_json_from())["type"] == "pong"
    await sync_to_async(notify)([employee], title="Ping from server")
    msg = await comm.receive_json_from(timeout=2)
    assert msg["type"] == "notification" and msg["notification"]["title"] == "Ping from server"
    await comm.disconnect()


async def test_only_managers_join_dashboard_group(manager, employee):
    mgr = await connect()
    await mgr.send_json_to({"type": "auth", "token": str(AccessToken.for_user(manager))})
    await mgr.receive_json_from()
    emp = await connect()
    await emp.send_json_to({"type": "auth", "token": str(AccessToken.for_user(employee))})
    await emp.receive_json_from()
    await sync_to_async(broadcast_dashboard)("asset")
    assert (await mgr.receive_json_from(timeout=2))["type"] == "dashboard.update"
    assert await emp.receive_nothing(timeout=0.3)
    await mgr.disconnect()
    await emp.disconnect()


async def test_config_changes_are_broadcast_to_every_role(employee, seeded_config):
    """Sidebar and dashboard-layout edits reach all connected users, not only managers."""
    comm = await connect()
    await comm.send_json_to({"type": "auth", "token": str(AccessToken.for_user(employee))})
    await comm.receive_json_from()

    def edit_sidebar():
        item = SidebarItem.objects.get(name="Scan")
        item.order = 7
        item.save()

    await sync_to_async(edit_sidebar)()
    assert (await comm.receive_json_from(timeout=2))["type"] == "sidebar.update"

    def edit_widget():
        from apps.dashboard.models import DashboardWidget

        w = DashboardWidget.objects.first()
        w.title = "Renamed"
        w.save()

    await sync_to_async(edit_widget)()
    assert (await comm.receive_json_from(timeout=2))["type"] == "dashboard.layout"
    await comm.disconnect()
