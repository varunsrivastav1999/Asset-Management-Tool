from django.contrib.auth import password_validation
from rest_framework import serializers

from apps.core.files import validate_image_upload

from .models import Department, User


class UserBriefSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "employee_id", "role"]


class DepartmentSerializer(serializers.ModelSerializer):
    head_detail = UserBriefSerializer(source="head", read_only=True)
    member_count = serializers.IntegerField(read_only=True, default=0)
    asset_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "code",
            "description",
            "head",
            "head_detail",
            "is_active",
            "member_count",
            "asset_count",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate_code(self, value):
        return value.strip().upper()


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False, min_length=8)
    assigned_asset_count = serializers.IntegerField(read_only=True, default=0)
    avatar = serializers.ImageField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "department",
            "department_name",
            "employee_id",
            "job_title",
            "phone",
            "avatar",
            "is_active",
            "last_login",
            "date_joined",
            "assigned_asset_count",
            "password",
        ]
        read_only_fields = ["last_login", "date_joined"]

    def validate_email(self, value):
        value = value.lower().strip()
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        password = attrs.get("password")
        if password:
            candidate = self.instance or User(**{k: v for k, v in attrs.items() if k != "password"})
            password_validation.validate_password(password, candidate)
        request = self.context.get("request")
        # Prevent an admin from locking themselves out.
        if self.instance and request and self.instance.pk == request.user.pk:
            if attrs.get("is_active") is False:
                raise serializers.ValidationError({"is_active": "You cannot deactivate your own account."})
            if "role" in attrs and attrs["role"] != User.Role.ADMIN and request.user.is_admin:
                raise serializers.ValidationError({"role": "You cannot remove your own admin role."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class MeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    avatar = serializers.ImageField(required=False, allow_null=True, validators=[validate_image_upload])

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "department",
            "department_name",
            "employee_id",
            "job_title",
            "phone",
            "avatar",
            "is_superuser",
            "last_login",
        ]
        read_only_fields = ["email", "role", "department", "employee_id", "is_superuser", "last_login"]


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        password_validation.validate_password(value, self.context["request"].user)
        return value


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
