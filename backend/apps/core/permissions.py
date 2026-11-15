from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_admin(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_superuser or user.role == "admin"))


def is_manager(user) -> bool:
    """Managers and admins."""
    return bool(user and user.is_authenticated and (is_admin(user) or user.role == "manager"))


class IsAdmin(BasePermission):
    message = "Administrator role required."

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsManager(BasePermission):
    message = "Manager or administrator role required."

    def has_permission(self, request, view):
        return is_manager(request.user)


class ReadAnyWriteManager(BasePermission):
    """Any authenticated user may read; managers/admins may write."""

    message = "Manager or administrator role required."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or is_manager(request.user)


class ReadManagerWriteAdmin(BasePermission):
    message = "Administrator role required."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return is_manager(request.user)
        return is_admin(request.user)


class ReadAnyWriteAdmin(BasePermission):
    message = "Administrator role required."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or is_admin(request.user)
