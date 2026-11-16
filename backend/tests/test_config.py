import pytest
from django.conf import settings
from django.test import override_settings

from apps.assets.models import Asset

from .conftest import CategoryFactory


@pytest.mark.django_db
def test_app_config_is_public_and_has_no_secrets(client):
    data = client.get("/api/app-config/").json()
    assert data == {"org_name": settings.ORG_NAME, "currency": "INR", "currency_locale": "en-IN"}


@pytest.mark.django_db
@override_settings(DEFAULT_CURRENCY="EUR")
def test_new_assets_and_receipt_items_use_the_configured_currency(manager_client):
    category = CategoryFactory()
    res = manager_client.post("/api/assets/", {"name": "Desk", "category": category.pk}, format="json")
    assert res.status_code == 201, res.data
    assert Asset.objects.get(pk=res.data["id"]).currency == "EUR"
    assert Asset(name="x").currency == "EUR"


def test_websocket_redis_read_timeout_outlasts_the_blocking_wait():
    """redis-py 8 defaults to a 5 s socket timeout, equal to channels_redis' 5 s BZPOPMIN: idle sockets then crash."""
    from channels_redis.core import RedisChannelLayer

    from config.settings import base  # the real (Redis) layer; tests swap in an in-memory one

    host = base.CHANNEL_LAYERS["default"]["CONFIG"]["hosts"][0]
    assert host["socket_timeout"] > RedisChannelLayer.brpop_timeout + 5


@pytest.mark.django_db
def test_openapi_schema_builds_without_errors_or_warnings(tmp_path):
    """/api/docs/ depends on this; views must not raise while being introspected."""
    from django.core.management import call_command

    call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(tmp_path / "schema.yml"))


def test_database_uses_a_bounded_connection_pool():
    """Under ASGI, per-thread persistent connections exhausted Postgres ("too many clients"); the pool bounds them."""
    from config.settings import base

    db = base.DATABASES["default"]
    assert db["OPTIONS"]["pool"]["max_size"] <= 8 and db["CONN_MAX_AGE"] == 0
