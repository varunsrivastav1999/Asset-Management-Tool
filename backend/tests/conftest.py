import base64
import io

import factory
import pytest
from PIL import Image, ImageDraw
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Department, User
from apps.assets.models import Asset, Category, CustomField, Location, Vendor


class DepartmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Department

    name = factory.Sequence(lambda n: f"Department {n}")
    code = factory.Sequence(lambda n: f"D{n:03d}")


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    role = User.Role.EMPLOYEE
    department = factory.SubFactory(DepartmentFactory)
    password = factory.PostGenerationMethodCall("set_password", "Str0ng!Passw0rd")

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        if create:
            instance.save()


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Category {n}")


class LocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Location

    name = factory.Sequence(lambda n: f"Location {n}")
    code = factory.Sequence(lambda n: f"LOC{n}")


class VendorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Vendor

    name = factory.Sequence(lambda n: f"Vendor {n}")


class AssetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Asset

    name = factory.Sequence(lambda n: f"Asset {n}")
    category = factory.SubFactory(CategoryFactory)
    serial_number = factory.Sequence(lambda n: f"SN-{n:06d}")


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / "media")
    settings.PRIVATE_MEDIA_ROOT = str(tmp_path / "private")


@pytest.fixture
def admin_user(db):
    return UserFactory(role=User.Role.ADMIN, email="admin@test.io", is_staff=True)


@pytest.fixture
def manager(db):
    return UserFactory(role=User.Role.MANAGER, email="manager@test.io")


@pytest.fixture
def employee(db):
    return UserFactory(role=User.Role.EMPLOYEE, email="employee@test.io")


@pytest.fixture
def other_employee(db):
    return UserFactory(role=User.Role.EMPLOYEE, email="other@test.io")


def _client_for(user):
    client = APIClient()
    if user is not None:
        token = RefreshToken.for_user(user).access_token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def client_for():
    return _client_for


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture
def admin_client(admin_user):
    return _client_for(admin_user)


@pytest.fixture
def manager_client(manager):
    return _client_for(manager)


@pytest.fixture
def employee_client(employee):
    return _client_for(employee)


@pytest.fixture
def category(db):
    cat = CategoryFactory(name="Laptops")
    CustomField.objects.create(category=cat, key="ram_gb", label="RAM", field_type="number", required=True)
    CustomField.objects.create(category=cat, key="os", label="OS", field_type="select", options=["Windows", "macOS"])
    return cat


@pytest.fixture
def location(db):
    return LocationFactory(code="HQ", name="Headquarters")


@pytest.fixture
def asset(db, category):
    return AssetFactory(category=category, custom_data={"ram_gb": 16})


def make_signature() -> str:
    img = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
    ImageDraw.Draw(img).line([(10, 80), (120, 20), (290, 70)], fill=(0, 0, 0, 255), width=4)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def signature():
    return make_signature()


@pytest.fixture
def png_file():
    from django.core.files.uploadedfile import SimpleUploadedFile

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (34, 211, 238)).save(buf, format="PNG")
    return SimpleUploadedFile("photo.png", buf.getvalue(), content_type="image/png")


@pytest.fixture
def seeded_config(db):
    """Default sidebar and dashboard (seeded by migrations, but transactional tests flush them)."""
    from apps.dashboard.defaults import seed_widgets
    from apps.dashboard.models import DashboardWidget
    from apps.navigation.defaults import seed_sidebar
    from apps.navigation.models import SidebarItem

    seed_sidebar(SidebarItem)
    seed_widgets(DashboardWidget)
