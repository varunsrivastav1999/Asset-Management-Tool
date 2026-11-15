import pytest
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import override_settings

from apps.assets.models import Asset
from apps.core.hosts import frontend_url, host_allowed, is_private_host
from config.asgi import application

PUBLIC = override_settings(TRUSTED_HOSTS=["assets.example.com"], ALLOW_PRIVATE_NETWORK_HOSTS=True, FRONTEND_URL="")


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "127.0.0.1",
        "192.168.1.45",
        "10.0.0.7",
        "172.20.3.4",
        "[::1]",
        "fe80::1",
        "fd12::3",
        "office-pc",
        "mac.local",
        "nas.lan",
    ],
)
def test_private_addresses_are_recognised(host):
    assert is_private_host(host)


@pytest.mark.parametrize("host", ["8.8.8.8", "evil.com", "assets.example.com.evil.com", "", "bad host", "172.32.0.1"])
def test_public_addresses_are_not_private(host):
    assert not is_private_host(host)


@PUBLIC
def test_host_rules():
    assert host_allowed("assets.example.com")
    assert host_allowed("192.168.1.45")
    assert not host_allowed("evil.com")
    with override_settings(ALLOW_PRIVATE_NETWORK_HOSTS=False):
        assert not host_allowed("192.168.1.45")


@pytest.mark.django_db
@PUBLIC
def test_lan_ip_is_served_without_configuration(client):
    assert client.get("/api/health/", HTTP_HOST="192.168.7.20:2025").status_code == 200
    assert client.get("/api/health/", HTTP_HOST="assets.example.com").status_code == 200
    assert client.get("/api/health/", HTTP_HOST="evil.com").status_code == 400


@pytest.mark.django_db
@PUBLIC
def test_links_follow_the_address_the_user_came_in_on(client, settings):
    cache.clear()
    assert frontend_url() == "http://localhost:2025"  # nothing seen yet
    client.get("/api/health/", HTTP_HOST="192.168.7.20:2025")
    # Background jobs (emails, reminders) reuse the last LAN/public address someone used.
    assert frontend_url() == "http://192.168.7.20:2025"
    assert Asset(asset_tag="AST-1").qr_payload == "http://192.168.7.20:2025/a/AST-1"
    client.get("/api/health/", HTTP_HOST="localhost:2025")  # loopback visits don't overwrite it
    assert frontend_url() == "http://192.168.7.20:2025"
    settings.FRONTEND_URL = "https://assets.example.com"
    assert frontend_url() == "https://assets.example.com"  # an explicit setting always wins


@pytest.mark.django_db(transaction=True)
@PUBLIC
@pytest.mark.parametrize(("origin", "accepted"), [("http://192.168.7.20:2025", True), ("http://evil.com", False), (None, False)])
async def test_websocket_origin_follows_host_rules(origin, accepted):
    headers = [(b"origin", origin.encode())] if origin else []
    comm = WebsocketCommunicator(application, "/ws/realtime/", headers=headers)
    connected, _ = await comm.connect()
    assert connected is accepted
    await comm.disconnect()
