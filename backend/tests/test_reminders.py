import datetime
import zoneinfo

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.navigation.models import SidebarItem, TableColumn
from apps.notifications.models import Notification
from apps.reminders import providers, tasks
from apps.reminders.engine import compute_next_run, queue_rule, signed_link
from apps.reminders.models import (
    ChannelConfig,
    ContactSettings,
    NotificationPreference,
    ReminderLog,
    ReminderRule,
    ReminderTemplate,
)
from apps.reminders.templating import render, render_html, render_subject, sms_text

from .conftest import AssetFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("seeded_config")]
UTC = datetime.UTC


class FakeSMS:
    sent: list = []
    fail_times = 0

    def send(self, to, text, sender):
        if FakeSMS.fail_times > 0:
            FakeSMS.fail_times -= 1
            raise providers.DeliveryError("provider down")
        FakeSMS.sent.append((to, text))
        return f"fake-{len(FakeSMS.sent)}"


@pytest.fixture(autouse=True)
def fake_sms(monkeypatch):
    FakeSMS.sent, FakeSMS.fail_times = [], 0
    monkeypatch.setattr(tasks, "get_sms_provider", lambda name: FakeSMS())
    monkeypatch.setattr("apps.reminders.views.get_sms_provider", lambda name: FakeSMS())
    config = ChannelConfig.load()
    config.sms_enabled = True
    config.save()
    return FakeSMS


@pytest.fixture
def real_retries(monkeypatch):
    """Let Celery's eager mode re-run retried tasks instead of propagating the Retry exception."""
    from config.celery import app

    monkeypatch.setitem(app.conf, "task_eager_propagates", False)


@pytest.fixture
def assets_page():
    return SidebarItem.objects.get(route="/assets")


@pytest.fixture
def template():
    return ReminderTemplate.objects.create(
        name="T",
        subject="Warranty {{asset_tag}} ends {{due_date}}",
        body="Hi {{recipient_name}},\n\n{{asset_name}} <b>ends</b> in {{days_left}} days.",
        sms_text="{{asset_tag}} warranty {{days_left}}d",
    )


def make_rule(section, template, **kw):
    defaults = dict(
        name="Warranty",
        section=section,
        trigger="warranty_expiry",
        trigger_config={"days": [7]},
        channels=["email"],
        recipients={"types": ["holder"], "user_ids": [], "emails": [], "phones": []},
        schedule={"kind": "daily", "time": "09:00", "timezone": "UTC"},
        template=template,
        is_active=True,
    )
    defaults.update(kw)
    return ReminderRule.objects.create(**defaults)


@pytest.fixture
def due_asset(category, employee):
    return AssetFactory(
        category=category,
        name="ThinkPad",
        status="assigned",
        assigned_to=employee,
        warranty_expiry=timezone.localdate() + datetime.timedelta(days=7),
        custom_data={"ram_gb": 1},
    )


# --- scheduling -------------------------------------------------------------------------
def test_compute_next_run_daily_weekly_once_manual():
    now = datetime.datetime(2026, 11, 16, 10, 0, tzinfo=UTC)  # Monday
    assert compute_next_run({"kind": "daily", "time": "09:00", "timezone": "UTC"}, now) == datetime.datetime(
        2026, 11, 17, 9, 0, tzinfo=UTC
    )
    assert compute_next_run({"kind": "daily", "time": "11:30", "timezone": "UTC"}, now) == datetime.datetime(
        2026, 11, 16, 11, 30, tzinfo=UTC
    )
    assert compute_next_run({"kind": "weekly", "weekday": 0, "time": "09:00", "timezone": "UTC"}, now).date() == datetime.date(
        2026, 11, 23
    )
    assert compute_next_run({"kind": "weekly", "weekday": 2, "time": "09:00", "timezone": "UTC"}, now).date() == datetime.date(
        2026, 11, 18
    )
    assert compute_next_run(
        {"kind": "once", "date": "2026-12-01", "time": "08:00", "timezone": "UTC"}, now
    ).date() == datetime.date(2026, 12, 1)
    assert compute_next_run({"kind": "once", "date": "2026-01-01", "time": "08:00"}, now) is None
    assert compute_next_run({"kind": "manual"}, now) is None
    kolkata = compute_next_run({"kind": "daily", "time": "09:00", "timezone": "Asia/Kolkata"}, now)
    assert kolkata.astimezone(zoneinfo.ZoneInfo("Asia/Kolkata")).hour == 9


def test_scan_claims_due_rules_once(assets_page, template, due_asset, django_capture_on_commit_callbacks):
    rule = make_rule(assets_page, template, next_run_at=timezone.now() - datetime.timedelta(minutes=1))
    with django_capture_on_commit_callbacks(execute=True):
        assert tasks.scan_reminder_rules.apply().get() == 1
    rule.refresh_from_db()
    assert rule.next_run_at > timezone.now() and rule.last_run_at is not None
    assert tasks.scan_reminder_rules.apply().get() == 0  # already claimed
    assert ReminderLog.objects.filter(rule=rule, status="sent").count() == 1


# --- templates -------------------------------------------------------------------------
def test_template_rendering_and_safety():
    ctx = {"asset_name": "<script>x</script>", "asset_tag": "AST-1", "days_left": 3}
    assert render("{{ asset_tag }} / {{unknown}} / {{asset_tag}}", ctx) == "AST-1 /  / AST-1"
    assert render_subject("Line1\nInjected: header {{asset_tag}}", ctx) == "Line1 Injected: header AST-1"
    assert "&lt;script&gt;" in render_html("Name: {{asset_name}}", ctx) and "<script>" not in render_html("{{asset_name}}", ctx)
    link = "https://x.io/api/reminders/download/abc/"
    msg = sms_text("A" * 300, {}, link)
    assert len(msg) <= 160 and msg.endswith(link)
    assert len(sms_text("{{asset_tag}} " * 50, ctx)) == 160


def test_template_preview_and_variables(manager_client):
    res = manager_client.post(
        "/api/reminders/templates/preview/",
        {"subject": "Due {{due_date}}", "body": "Hi {{recipient_name}}", "sms_text": "{{asset_tag}}"},
        format="json",
    )
    assert res.data["subject"].startswith("Due ") and "Max Manager" in res.data["body"] and res.data["sms"] == "AST-000042"
    assert any(v["key"] == "asset_tag" for v in manager_client.get("/api/reminders/templates/variables/").data["variables"])
    assert (
        manager_client.post(
            "/api/reminders/templates/", {"name": "x", "subject": "s", "body": "b", "sms_text": "x" * 161}, format="json"
        ).status_code
        == 400
    )


# --- delivery, dedupe, opt-out ------------------------------------------------------------
def test_email_sent_once_per_occurrence(assets_page, template, due_asset, employee):
    rule = make_rule(assets_page, template)
    assert tasks.run_rule.apply(args=[rule.pk]).get() == 1
    assert len(mail.outbox) == 1
    m = mail.outbox[0]
    assert m.to == [employee.email] and due_asset.asset_tag in m.subject
    assert "&lt;b&gt;ends" in m.alternatives[0][0]  # body HTML is escaped
    log = ReminderLog.objects.get(rule=rule)
    assert log.status == "sent" and log.provider_message_id and log.sent_at
    assert tasks.run_rule.apply(args=[rule.pk]).get() == 0  # dedupe: same rule + object + date
    assert len(mail.outbox) == 1


def test_recipients_holder_department_head_managers_custom(assets_page, template, due_asset, employee, manager):
    head = UserFactory()
    employee.department.head = head
    employee.department.save()
    due_asset.department = employee.department
    due_asset.save()
    rule = make_rule(
        assets_page,
        template,
        recipients={"types": ["holder", "department_head", "managers", "custom"], "emails": ["ops@example.org"], "phones": []},
    )
    tasks.run_rule.apply(args=[rule.pk])
    assert {m.to[0] for m in mail.outbox} == {employee.email, head.email, manager.email, "ops@example.org"}


def test_opt_out_per_section_and_global(assets_page, template, due_asset, employee):
    NotificationPreference.objects.create(user=employee, section=assets_page, email_enabled=False)
    rule = make_rule(assets_page, template)
    tasks.run_rule.apply(args=[rule.pk])
    log = ReminderLog.objects.get(rule=rule)
    assert log.status == "skipped" and "turned off" in log.error and not mail.outbox
    # A global opt-out applies when no section preference exists.
    NotificationPreference.objects.all().delete()
    NotificationPreference.objects.create(user=employee, section=None, email_enabled=False)
    rule2 = make_rule(assets_page, template, name="Again")
    tasks.run_rule.apply(args=[rule2.pk])
    assert ReminderLog.objects.get(rule=rule2).status == "skipped"


def test_sms_requires_verified_phone_and_gets_link(assets_page, template, due_asset, employee, fake_sms):
    employee.phone = "+15550001111"
    employee.save()
    rule = make_rule(assets_page, template, channels=["sms"], attachments=["export_csv"], created_by=UserFactory(role="admin"))
    tasks.run_rule.apply(args=[rule.pk])
    assert ReminderLog.objects.get(rule=rule).error == "phone number not verified" and not fake_sms.sent
    ContactSettings.objects.update_or_create(user=employee, defaults={"verified_phone": "+15550001111"})
    rule2 = make_rule(
        assets_page, template, name="sms2", channels=["sms"], attachments=["export_csv"], created_by=rule.created_by
    )
    tasks.run_rule.apply(args=[rule2.pk])
    to, text = fake_sms.sent[0]
    assert to == "+15550001111" and len(text) <= 160 and "/api/reminders/download/" in text


def test_quiet_hours_defer_delivery(assets_page, template, due_asset, employee, monkeypatch):
    now = timezone.now()
    start = (now - datetime.timedelta(hours=1)).time().replace(second=0, microsecond=0)
    end = (now + datetime.timedelta(hours=2)).time().replace(second=0, microsecond=0)
    ContactSettings.objects.create(user=employee, quiet_start=start, quiet_end=end, timezone="UTC")
    calls = []
    monkeypatch.setattr(tasks.deliver_log, "apply_async", lambda args, eta: calls.append(eta))
    rule = make_rule(assets_page, template)
    tasks.run_rule.apply(args=[rule.pk])
    log = ReminderLog.objects.get(rule=rule)
    assert log.status == "queued" and log.deliver_after and calls and calls[0] > now


# --- attachments -------------------------------------------------------------------------
def test_export_attachment_uses_column_names_bom_and_injection_guard(assets_page, template, category, employee, admin_user):
    a = AssetFactory(
        category=category,
        name="=HYPERLINK(1)",
        assigned_to=employee,
        status="assigned",
        warranty_expiry=timezone.localdate() + datetime.timedelta(days=7),
        custom_data={"ram_gb": 1},
    )
    from apps.navigation.tables import ensure_columns

    ensure_columns(assets_page)
    TableColumn.objects.filter(sidebar_item=assets_page, key="name").update(name="Equipment")
    rule = make_rule(assets_page, template, attachments=["export_csv", "export_pdf"], created_by=admin_user)
    tasks.run_rule.apply(args=[rule.pk])
    names = {n: c for n, c, _ in mail.outbox[0].attachments}
    csv_name = next(n for n in names if n.endswith(".csv"))
    content = names[csv_name]
    content = content.encode() if isinstance(content, str) else content
    assert content.startswith("﻿".encode())
    text = content.decode("utf-8-sig")
    assert text.splitlines()[0].split(",")[1] == "Equipment" and "'=HYPERLINK(1)" in text
    assert any(n.endswith(".pdf") for n in names)
    assert a.asset_tag in mail.outbox[0].subject


def test_bill_attachment_from_uploaded_invoice(manager_client, assets_page, template, due_asset, admin_user):
    pdf = SimpleUploadedFile("bill.pdf", b"%PDF-1.4 test bill", content_type="application/pdf")
    assert manager_client.post(f"/api/assets/{due_asset.id}/invoice/", {"file": pdf}, format="multipart").status_code == 200
    bad = SimpleUploadedFile("bill.pdf", b"not a pdf", content_type="application/pdf")
    assert manager_client.post(f"/api/assets/{due_asset.id}/invoice/", {"file": bad}, format="multipart").status_code == 400
    rule = make_rule(assets_page, template, attachments=["bill"], created_by=admin_user)
    tasks.run_rule.apply(args=[rule.pk])
    ((name, content, mimetype),) = mail.outbox[0].attachments
    assert name.endswith(".pdf") and content.startswith(b"%PDF") and mimetype == "application/pdf"


def test_large_attachments_become_signed_links(settings, assets_page, template, due_asset, admin_user, anon_client):
    settings.REMINDER_ATTACHMENT_MAX_MB = 0
    rule = make_rule(assets_page, template, attachments=["export_csv"], created_by=admin_user)
    tasks.run_rule.apply(args=[rule.pk])
    m = mail.outbox[0]
    assert not m.attachments and "/api/reminders/download/" in m.body
    token = m.body.split("/api/reminders/download/")[1].split("/")[0]
    assert ":" in token
    res = anon_client.get(f"/api/reminders/download/{token}/")
    assert res.status_code == 200 and b"".join(res.streaming_content).startswith("﻿".encode())
    assert anon_client.get(f"/api/reminders/download/{token}x/").status_code == 403
    settings.REMINDER_LINK_HOURS = 0
    import time

    time.sleep(1)
    assert anon_client.get(f"/api/reminders/download/{token}/").status_code == 404
    assert anon_client.get(
        signed_link("../../etc/passwd").split("/api")[1].replace("/reminders", "/api/reminders")
    ).status_code in (403, 404)


# --- retries, rate limits, cap ----------------------------------------------------------------
def test_retry_with_backoff_then_success(real_retries, assets_page, template, due_asset, employee, fake_sms):
    employee.phone = "+15550002222"
    employee.save()
    ContactSettings.objects.create(user=employee, verified_phone="+15550002222")
    fake_sms.fail_times = 2
    rule = make_rule(assets_page, template, channels=["sms"])
    tasks.run_rule.apply(args=[rule.pk])
    log = ReminderLog.objects.get(rule=rule)
    assert log.status == "sent" and log.attempts == 3 and len(fake_sms.sent) == 1


def test_exhausted_retries_fail_and_alert_admins(real_retries, assets_page, template, due_asset, employee, admin_user, fake_sms):
    employee.phone = "+15550003333"
    employee.save()
    ContactSettings.objects.create(user=employee, verified_phone="+15550003333")
    fake_sms.fail_times = 99
    rule = make_rule(assets_page, template, channels=["sms"])
    tasks.run_rule.apply(args=[rule.pk])
    log = ReminderLog.objects.get(rule=rule)
    assert log.status == "failed" and log.attempts == tasks.MAX_RETRIES + 1 and "provider down" in log.error
    assert Notification.objects.filter(recipient=admin_user, title__startswith="Reminder delivery failing").exists()


def test_daily_cap(assets_page, template, due_asset, employee):
    config = ChannelConfig.load()
    config.daily_cap = 0
    config.save()
    rule = make_rule(assets_page, template)
    tasks.run_rule.apply(args=[rule.pk])
    log = ReminderLog.objects.get(rule=rule)
    assert log.status == "failed" and "cap" in log.error and not mail.outbox


def test_in_app_channel(assets_page, template, due_asset, employee):
    rule = make_rule(assets_page, template, channels=["in_app"])
    tasks.run_rule.apply(args=[rule.pk])
    assert Notification.objects.filter(recipient=employee, title__contains=due_asset.asset_tag).exists()


# --- other triggers ---------------------------------------------------------------------------
def test_low_stock_and_manual_triggers(assets_page, template, category, manager, admin_user):
    AssetFactory(category=category, custom_data={"ram_gb": 1})
    low = make_rule(
        assets_page,
        template,
        name="Low",
        trigger="low_stock",
        trigger_config={"threshold": 5},
        recipients={"types": ["managers"]},
    )
    assert tasks.run_rule.apply(args=[low.pk]).get() >= 1
    manual = make_rule(
        assets_page,
        template,
        name="Report",
        trigger="manual",
        recipients={"types": ["managers"]},
        attachments=["export_xlsx"],
        created_by=admin_user,
        schedule={"kind": "manual"},
    )
    assert len(queue_rule(manual, run_tag="now:1")) == 2  # admin + manager


# --- API & permissions -----------------------------------------------------------------------
def rule_payload(section, template, **kw):
    data = {
        "name": "API rule",
        "section": section.id,
        "trigger": "warranty_expiry",
        "trigger_config": {"days": [30, 7]},
        "channels": ["email", "in_app"],
        "recipients": {"types": ["holder", "managers"]},
        "schedule": {"kind": "weekly", "weekday": 1, "time": "08:30", "timezone": "Europe/Berlin"},
        "template": template.id,
        "attachments": ["export_csv"],
        "is_active": True,
    }
    data.update(kw)
    return data


def test_rule_crud_permissions_and_audit(admin_client, manager_client, employee_client, assets_page, template):
    assert employee_client.get("/api/reminders/rules/").status_code == 403
    res = manager_client.post("/api/reminders/rules/", rule_payload(assets_page, template), format="json")
    assert res.status_code == 201, res.data
    assert res.data["next_run_at"] and res.data["trigger_config"]["days"] == [30, 7]
    assert AuditLog.objects.filter(model="reminders.reminderrule", action="create").exists()
    admin_only = SidebarItem.objects.get(route="/settings/backups")
    admin_only.table = "assets"
    admin_only.save()
    assert manager_client.post("/api/reminders/rules/", rule_payload(admin_only, template), format="json").status_code == 400
    assert (
        admin_client.post("/api/reminders/rules/", rule_payload(admin_only, template, name="adm"), format="json").status_code
        == 201
    )


@pytest.mark.parametrize(
    "override,field",
    [
        ({"channels": ["fax"]}, "channels"),
        ({"recipients": {"types": ["custom"], "emails": []}}, "recipients"),
        ({"recipients": {"types": ["custom"], "emails": ["nope"]}}, "recipients"),
        ({"schedule": {"kind": "daily", "time": "25:00"}}, "schedule"),
        ({"schedule": {"kind": "daily", "time": "09:00", "timezone": "Mars/Base"}}, "schedule"),
        ({"attachments": ["virus"]}, "attachments"),
        ({"trigger": "custom_date", "trigger_config": {"column": "nope"}}, "trigger_config"),
    ],
)
def test_rule_validation(manager_client, assets_page, template, override, field):
    res = manager_client.post("/api/reminders/rules/", rule_payload(assets_page, template, **override), format="json")
    assert res.status_code == 400 and field in res.data, res.data


def test_test_send_without_matches_uses_sample_values(manager_client, manager, assets_page, template):
    rule = make_rule(assets_page, template)
    assert manager_client.post(f"/api/reminders/rules/{rule.id}/test/").data["queued"] == 1
    assert "AST-000042" in mail.outbox[0].subject


def test_test_send_goes_only_to_me(manager_client, manager, assets_page, template, due_asset):
    rule = make_rule(assets_page, template, recipients={"types": ["managers", "holder"]})
    res = manager_client.post(f"/api/reminders/rules/{rule.id}/test/")
    assert res.status_code == 200 and res.data["queued"] == 1
    assert [m.to for m in mail.outbox] == [[manager.email]]


def test_send_now_and_logs(manager_client, assets_page, template, due_asset, employee):
    rule = make_rule(assets_page, template)
    assert manager_client.post(f"/api/reminders/rules/{rule.id}/send-now/").status_code == 202
    assert manager_client.post(f"/api/reminders/rules/{rule.id}/send-now/").status_code == 202
    assert len(mail.outbox) == 2  # send-now is deliberately not deduplicated across runs
    logs = manager_client.get("/api/reminders/logs/", {"status": "sent", "channel": "email"})
    assert logs.data["count"] == 2
    csv_res = manager_client.get("/api/reminders/logs/export/")
    assert csv_res.content.startswith("﻿".encode()) and b"Recipient" in csv_res.content
    failed = ReminderLog.objects.first()
    ReminderLog.objects.filter(pk=failed.pk).update(status="failed")
    assert manager_client.post(f"/api/reminders/logs/{failed.id}/retry/").data["status"] == "sent"


def test_channel_settings_admin_only_and_secrets_hidden(settings, admin_client, manager_client):
    settings.SMTP_PASSWORD = settings.EMAIL_HOST_PASSWORD = "super-secret"
    settings.SMS_API_KEY = "sid:token-secret"
    assert manager_client.get("/api/reminders/channels/").status_code == 403
    res = admin_client.get("/api/reminders/channels/")
    assert res.status_code == 200 and "secret" not in str(res.data)
    assert set(res.data) >= {"smtp_configured", "sms_configured", "sms_provider"}
    assert (
        admin_client.put("/api/reminders/channels/", {"sms_provider": "twilio", "daily_cap": 50}, format="json").data["daily_cap"]
        == 50
    )


def test_preferences_and_phone_verification(employee_client, employee, assets_page, fake_sms):
    data = employee_client.get("/api/reminders/preferences/").data
    assert any(s["id"] == assets_page.id for s in data["sections"])
    res = employee_client.put(
        "/api/reminders/preferences/",
        {
            "phone": "+15551234567",
            "quiet_start": "22:00",
            "quiet_end": "07:00",
            "timezone": "Asia/Kolkata",
            "default": {"email": True, "sms": False},
            "sections": [{"id": assets_page.id, "email": False, "sms": True}],
        },
        format="json",
    )
    assert res.status_code == 200, res.data
    s = next(x for x in res.data["sections"] if x["id"] == assets_page.id)
    assert (s["email"], s["sms"], res.data["default"]["sms"]) == (False, True, False)
    assert employee_client.put("/api/reminders/preferences/", {"quiet_start": "7pm"}, format="json").status_code == 400
    assert employee_client.post("/api/reminders/preferences/verify-phone/", {}, format="json").data == {"sent": True}
    code = fake_sms.sent[-1][1].split("code is ")[1][:6]
    assert (
        employee_client.post(
            "/api/reminders/preferences/verify-phone/", {"code": "000000" if code != "000000" else "111111"}, format="json"
        ).status_code
        == 400
    )
    assert employee_client.post("/api/reminders/preferences/verify-phone/", {"code": code}, format="json").data == {
        "phone_verified": True
    }
    assert employee_client.get("/api/reminders/preferences/").data["phone_verified"] is True


def test_download_of_receipt_invoice(manager_client, employee_client):
    from apps.workflows.models import GoodsReceipt

    r = GoodsReceipt.objects.create()
    pdf = SimpleUploadedFile("inv.pdf", b"%PDF-1.4 x", content_type="application/pdf")
    assert manager_client.post(f"/api/receipts/{r.id}/invoice/", {"file": pdf}, format="multipart").status_code == 200
    res = manager_client.get(f"/api/receipts/{r.id}/invoice/")
    assert res.status_code == 200 and b"".join(res.streaming_content).startswith(b"%PDF")
    assert employee_client.get(f"/api/receipts/{r.id}/invoice/").status_code == 403
