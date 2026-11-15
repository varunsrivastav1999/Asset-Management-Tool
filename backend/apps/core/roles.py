"""Role helpers shared by role-scoped configuration (sidebar items, dashboard widgets)."""

ROLES = ("admin", "manager", "employee")


def default_roles():
    return list(ROLES)


def effective_role(user) -> str:
    if user.is_superuser:
        return "admin"
    return user.role


def validate_roles(value) -> list[str]:
    from rest_framework import serializers

    if not isinstance(value, list) or not value:
        raise serializers.ValidationError("Choose at least one role.")
    unknown = [r for r in value if r not in ROLES]
    if unknown:
        raise serializers.ValidationError(f"Unknown role(s): {', '.join(map(str, unknown))}.")
    # Admins always see everything they configure; keep canonical order and no duplicates.
    return [r for r in ROLES if r in value]
