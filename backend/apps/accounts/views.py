from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import update_last_login
from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.audit.models import AuditLog
from apps.audit.services import AuditedViewSetMixin, record
from apps.core.exceptions import DomainError
from apps.core.permissions import ReadAnyWriteAdmin, ReadManagerWriteAdmin
from apps.navigation.table_api import ConfigurableTableMixin

from .models import Department, User
from .serializers import (
    ChangePasswordSerializer,
    DepartmentSerializer,
    LoginSerializer,
    MeSerializer,
    UserSerializer,
)


def _set_refresh_cookie(response, refresh: str):
    cfg = settings.JWT_REFRESH_COOKIE
    response.set_cookie(
        cfg["name"],
        refresh,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        path=cfg["path"],
        secure=cfg["secure"],
        httponly=cfg["httponly"],
        samesite=cfg["samesite"],
    )


def _clear_refresh_cookie(response):
    cfg = settings.JWT_REFRESH_COOKIE
    response.delete_cookie(cfg["name"], path=cfg["path"], samesite=cfg["samesite"])


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "login"

    def get_throttles(self):
        from rest_framework.throttling import ScopedRateThrottle

        return [ScopedRateThrottle(), *super().get_throttles()]

    @extend_schema(request=LoginSerializer, responses={200: MeSerializer})
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()
        user = authenticate(request, email=email, password=serializer.validated_data["password"])
        if user is None or not user.is_active:
            record(AuditLog.Action.LOGIN_FAILED, None, model="accounts.user", object_repr=email)
            return Response({"detail": "Invalid email or password."}, status=status.HTTP_401_UNAUTHORIZED)
        refresh = RefreshToken.for_user(user)
        update_last_login(None, user)
        record(AuditLog.Action.LOGIN, user, user)
        response = Response({"access": str(refresh.access_token), "user": MeSerializer(user, context={"request": request}).data})
        _set_refresh_cookie(response, str(refresh))
        return response


class RefreshView(APIView):
    """Exchanges the HttpOnly refresh cookie for a new access token (and rotates the cookie)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=None, responses={200: MeSerializer})
    def post(self, request):
        token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE["name"])
        if not token:
            return Response({"detail": "No refresh session."}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = TokenRefreshSerializer(data={"refresh": token})
        try:
            serializer.is_valid(raise_exception=True)
        except (InvalidToken, TokenError):
            response = Response({"detail": "Session expired."}, status=status.HTTP_401_UNAUTHORIZED)
            _clear_refresh_cookie(response)
            return response
        data = serializer.validated_data
        user_id = AccessToken(data["access"]).get(settings.SIMPLE_JWT.get("USER_ID_CLAIM", "user_id"))
        user = User.objects.filter(pk=user_id, is_active=True).select_related("department").first()
        if user is None:
            response = Response({"detail": "Session expired."}, status=status.HTTP_401_UNAUTHORIZED)
            _clear_refresh_cookie(response)
            return response
        response = Response({"access": data["access"], "user": MeSerializer(user, context={"request": request}).data})
        _set_refresh_cookie(response, data.get("refresh", token))
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE["name"])
        if token:
            try:
                refresh = RefreshToken(token)
                user = User.objects.filter(pk=refresh.get("user_id")).first()
                refresh.blacklist()
                if user:
                    record(AuditLog.Action.LOGOUT, user, user)
            except TokenError:
                pass
        response = Response(status=status.HTTP_204_NO_CONTENT)
        _clear_refresh_cookie(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        return Response(MeSerializer(request.user, context={"request": request}).data)

    @extend_schema(request=MeSerializer, responses=MeSerializer)
    def patch(self, request):
        serializer = MeSerializer(request.user, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record(AuditLog.Action.UPDATE, request.user, request.user, {"fields": sorted(serializer.validated_data)})
        return Response(serializer.data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer, responses={204: None})
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password", "must_change_password"])
        record(AuditLog.Action.PASSWORD_CHANGE, request.user, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(ConfigurableTableMixin, AuditedViewSetMixin, viewsets.ModelViewSet):
    table_key = "users"
    bulk_permission_classes = [ReadManagerWriteAdmin]
    bulk_delete_verb = "deactivated"

    def bulk_delete_reason(self, obj):
        if obj.pk == self.request.user.pk:
            return "You can't deactivate your own account."
        if not obj.is_active:
            return "Already inactive."
        return None

    def bulk_delete_one(self, obj):
        obj.is_active = False
        obj.save(update_fields=["is_active"])

    serializer_class = UserSerializer
    permission_classes = [ReadManagerWriteAdmin]
    filterset_fields = ["role", "department", "is_active"]
    search_fields = ["email", "first_name", "last_name", "employee_id", "job_title"]
    ordering_fields = ["first_name", "last_name", "email", "date_joined", "last_login", "role"]

    def get_queryset(self):
        return (
            User.objects.select_related("department")
            .annotate(assigned_asset_count=Count("assigned_assets", filter=Q(assigned_assets__status="assigned"), distinct=True))
            .order_by("first_name", "last_name", "email")
        )

    def perform_destroy(self, instance):
        """Users are deactivated, never deleted, so history and audit trails stay intact."""
        if instance.pk == self.request.user.pk:
            raise DomainError("You cannot deactivate your own account.")
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        record(AuditLog.Action.UPDATE, self.request.user, instance, {"is_active": {"from": True, "to": False}})

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        record(AuditLog.Action.UPDATE, request.user, user, {"is_active": {"from": False, "to": True}})
        return Response(self.get_serializer(user).data)


class DepartmentViewSet(ConfigurableTableMixin, AuditedViewSetMixin, viewsets.ModelViewSet):
    table_key = "departments"
    bulk_permission_classes = [ReadAnyWriteAdmin]

    def bulk_delete_reason(self, obj):
        if obj.members.exists():
            return "Still has people."
        if obj.assets.exists():
            return "Still holds assets."
        return None

    serializer_class = DepartmentSerializer
    permission_classes = [ReadAnyWriteAdmin]
    filterset_fields = ["is_active"]
    search_fields = ["name", "code", "description"]
    ordering_fields = ["name", "code", "created_at"]

    def get_queryset(self):
        return (
            Department.objects.select_related("head")
            .annotate(
                member_count=Count("members", filter=Q(members__is_active=True), distinct=True),
                asset_count=Count("assets", distinct=True),
            )
            .order_by("name")
        )
