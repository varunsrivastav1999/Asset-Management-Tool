import datetime
import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Department
from apps.assets.models import Asset, AssetEvent, Category, CustomField, Location, Vendor
from apps.assets.services import log_event
from apps.maintenance.models import MaintenanceRecord

User = get_user_model()

CATEGORIES = [
    # name, icon, color, custom fields
    ("IT Equipment", "monitor", "#10b981", []),
    (
        "Laptops",
        "laptop",
        "#84cc16",
        [("ram_gb", "RAM (GB)", "number"), ("cpu", "CPU", "text"), ("os", "Operating system", "select")],
    ),
    ("Monitors", "monitor", "#22c55e", [("size_in", "Size (inches)", "number")]),
    ("Phones", "smartphone", "#65a30d", [("imei", "IMEI", "text")]),
    ("Furniture", "armchair", "#f59e0b", [("material", "Material", "text")]),
    ("Office Tools", "printer", "#a78bfa", []),
    (
        "Vehicles",
        "car",
        "#f472b6",
        [("plate", "License plate", "text"), ("mileage_km", "Mileage (km)", "number"), ("fuel", "Fuel", "select")],
    ),
]
OPTIONS = {"os": ["Windows 11", "macOS", "Ubuntu"], "fuel": ["Petrol", "Diesel", "Electric", "Hybrid"]}

ITEMS = {
    "Laptops": [("MacBook Pro 14", "Apple", 2399), ("ThinkPad X1 Carbon", "Lenovo", 1899), ("Latitude 7440", "Dell", 1499)],
    "Monitors": [("UltraSharp 27", "Dell", 549), ("ProArt 32", "ASUS", 899)],
    "Phones": [("iPhone 16", "Apple", 999), ("Pixel 9", "Google", 799)],
    "Furniture": [("Ergonomic Chair", "Herman Miller", 1295), ("Standing Desk", "Uplift", 749)],
    "Office Tools": [("LaserJet Pro", "HP", 429), ("Projector X5", "Epson", 1099)],
    "Vehicles": [("Model Y", "Tesla", 47990), ("Transit Van", "Ford", 42500)],
}


class Command(BaseCommand):
    help = "Seed demo data (users, catalog, ~60 assets). Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="Demo@12345", help="Password for the demo accounts")
        parser.add_argument("--assets", type=int, default=60)

    @transaction.atomic
    def handle(self, *args, password, assets, **options):
        rnd = random.Random(42)
        depts = {}
        for name, code in [("Engineering", "ENG"), ("Finance", "FIN"), ("Operations", "OPS"), ("Sales", "SAL"), ("People", "HR")]:
            depts[code], _ = Department.objects.get_or_create(code=code, defaults={"name": name})

        def user(email, first, last, role, dept, emp_id):
            u, created = User.objects.get_or_create(
                email=email,
                defaults={"first_name": first, "last_name": last, "role": role, "department": dept, "employee_id": emp_id},
            )
            if created:
                u.set_password(password)
                if role == User.Role.ADMIN:
                    u.is_staff = u.is_superuser = True
                u.save()
            return u

        admin = user("admin@example.com", "Ada", "Admin", User.Role.ADMIN, depts["OPS"], "E0001")
        user("manager@example.com", "Max", "Manager", User.Role.MANAGER, depts["OPS"], "E0002")
        employees = [
            user("employee@example.com", "Eve", "Employee", User.Role.EMPLOYEE, depts["ENG"], "E0003"),
            user("sam@example.com", "Sam", "Rivera", User.Role.EMPLOYEE, depts["SAL"], "E0004"),
            user("lee@example.com", "Lee", "Chen", User.Role.EMPLOYEE, depts["FIN"], "E0005"),
            user("noor@example.com", "Noor", "Haddad", User.Role.EMPLOYEE, depts["ENG"], "E0006"),
        ]

        it = None
        cats = {}
        for name, icon, color, fields in CATEGORIES:
            parent = it if name in ("Laptops", "Monitors", "Phones") else None
            cat, _ = Category.objects.get_or_create(name=name, parent=parent, defaults={"icon": icon, "color": color})
            for order, (key, label, ftype) in enumerate(fields):
                CustomField.objects.get_or_create(
                    category=cat,
                    key=key,
                    defaults={"label": label, "field_type": ftype, "options": OPTIONS.get(key, []), "order": order},
                )
            cats[name] = cat
            if name == "IT Equipment":
                it = cat

        hq, _ = Location.objects.get_or_create(code="HQ", defaults={"name": "Headquarters", "address": "1 Main St"})
        store, _ = Location.objects.get_or_create(code="HQ-STORE", defaults={"name": "IT Store Room", "parent": hq})
        garage, _ = Location.objects.get_or_create(code="GARAGE", defaults={"name": "Fleet Garage"})
        vendors = [Vendor.objects.get_or_create(name=n)[0] for n in ("TechSource Ltd", "OfficeHub", "Fleet Partners")]

        if Asset.objects.count() >= assets:
            self.stdout.write(self.style.WARNING("Assets already seeded; skipping asset creation."))
            return

        today = timezone.localdate()
        for i in range(assets):
            cat_name = rnd.choice(list(ITEMS))
            model, maker, price = rnd.choice(ITEMS[cat_name])
            purchase = today - datetime.timedelta(days=rnd.randint(10, 900))
            warranty = purchase + datetime.timedelta(days=rnd.choice([365, 730, 1095]))
            custom = {}
            if cat_name == "Laptops":
                custom = {
                    "ram_gb": rnd.choice([16, 32, 64]),
                    "cpu": rnd.choice(["M4 Pro", "Core Ultra 7"]),
                    "os": rnd.choice(OPTIONS["os"]),
                }
            elif cat_name == "Vehicles":
                custom = {
                    "plate": f"AMS-{rnd.randint(100, 999)}",
                    "mileage_km": rnd.randint(1000, 90000),
                    "fuel": rnd.choice(OPTIONS["fuel"]),
                }
            asset = Asset.objects.create(
                name=f"{maker} {model}",
                category=cats[cat_name],
                model=model,
                manufacturer=maker,
                serial_number=f"SN{rnd.randint(10**7, 10**8 - 1)}{i}",
                vendor=rnd.choice(vendors),
                purchase_date=purchase,
                purchase_cost=Decimal(price) * Decimal(rnd.choice(["0.9", "1", "1.05"])),
                warranty_expiry=warranty,
                maintenance_interval_days=180 if cat_name in ("Vehicles", "Office Tools") else None,
                next_maintenance_date=today + datetime.timedelta(days=rnd.randint(-5, 40))
                if cat_name in ("Vehicles", "Office Tools")
                else None,
                location=garage if cat_name == "Vehicles" else store,
                condition=rnd.choice(["new", "good", "good", "fair"]),
                custom_data=custom,
                created_by=admin,
            )
            log_event(asset, AssetEvent.Type.CREATED, admin, to_status=asset.status)
            roll = rnd.random()
            if roll < 0.45:
                emp = rnd.choice(employees)
                asset.status, asset.assigned_to, asset.department = Asset.Status.ASSIGNED, emp, emp.department
                asset.save()
                log_event(asset, AssetEvent.Type.ISSUED, admin, from_status="in_stock", to_status="assigned", to_user=emp)
            elif roll < 0.52:
                asset.status = Asset.Status.IN_REPAIR
                asset.save()
                MaintenanceRecord.objects.create(
                    asset=asset,
                    kind="corrective",
                    title="Diagnostics & repair",
                    status="in_progress",
                    scheduled_date=today,
                    previous_asset_status="in_stock",
                    created_by=admin,
                )
            elif roll < 0.56:
                asset.status = Asset.Status.RETIRED
                asset.save()
            elif roll < 0.58:
                asset.status = Asset.Status.LOST
                asset.save()
        self.stdout.write(self.style.SUCCESS(f"Seeded demo data. Log in as admin@example.com / {password}"))
