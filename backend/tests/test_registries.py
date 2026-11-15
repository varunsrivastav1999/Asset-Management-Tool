"""Registries must cover every choice, so a new trigger or data source can't silently do nothing."""


def test_every_dashboard_source_has_a_resolver():
    from apps.dashboard.sources import RESOLVERS, SOURCES

    assert set(SOURCES) == set(RESOLVERS)


def test_every_reminder_trigger_has_a_handler():
    from apps.reminders.engine import TRIGGER_HANDLERS
    from apps.reminders.models import ReminderRule

    assert set(ReminderRule.Trigger.values) == set(TRIGGER_HANDLERS)
