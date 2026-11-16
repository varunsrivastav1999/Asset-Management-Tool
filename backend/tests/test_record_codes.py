import re

import pytest

from apps.navigation.models import TableDefinition, TableRecord

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("seeded_config")]


@pytest.fixture
def table(admin_client):
    return admin_client.post("/api/table-definitions/", {"name": "Licences", "singular": "Licence"}, format="json").data


def add(client, table, name):
    res = client.post(f"/api/records/?table_item={table['sidebar_item']}", {"custom_data": {"name": name}}, format="json")
    assert res.status_code == 201, res.data
    return res.data


def test_every_row_gets_a_permanent_unique_code(admin_client, manager_client, table):
    a, b = add(manager_client, table, "Office"), add(manager_client, table, "IDE")
    assert re.fullmatch(r"LIC-\d{5}", a["code"]) and a["code"] != b["code"]
    # Renaming the table or moving the row never changes the code.
    admin_client.patch(f"/api/table-definitions/{table['id']}/", {"name": "Software"}, format="json")
    other = admin_client.post("/api/table-definitions/", {"name": "Old kit", "singular": "Item"}, format="json").data
    manager_client.post(
        f"/api/records/bulk-move/?table_item={table['sidebar_item']}", {"ids": [a["id"]], "target": other["id"]}, format="json"
    )
    assert TableRecord.objects.get(pk=a["id"]).code == a["code"]
    # Imported rows get codes too.
    from django.core.files.uploadedfile import SimpleUploadedFile

    manager_client.post(
        f"/api/records/import/?table_item={table['sidebar_item']}", {"file": SimpleUploadedFile("r.csv", b"Name\nCAD\n")}
    )
    assert TableRecord.objects.filter(definition_id=table["id"], code__isnull=True).count() == 0


def test_code_column_is_shown_and_searchable(manager_client, table):
    row = add(manager_client, table, "Office")
    add(manager_client, table, "IDE")
    listing = manager_client.get(f"/api/records/?table_item={table['sidebar_item']}&with_columns=1&search={row['code']}").data
    assert listing["count"] == 1 and listing["results"][0]["code"] == row["code"]
    assert "code" in [c["key"] for c in listing["table"]["columns"]]


def test_qr_and_barcode_images(manager_client, employee_client, table):
    row = add(manager_client, table, "Office")
    base = f"/api/records/{row['id']}/%s/?table_item={table['sidebar_item']}"
    png = employee_client.get(base % "qr")
    assert png.status_code == 200 and png["Content-Type"] == "image/png" and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    svg = employee_client.get(base % "qr" + "&fmt=svg")
    assert svg["Content-Type"] == "image/svg+xml" and b"<svg" in svg.content
    bar = employee_client.get(base % "barcode")
    assert bar["Content-Type"] == "image/svg+xml" and row["code"].encode() in bar.content  # human-readable line
    assert employee_client.get(base % "barcode" + "&fmt=png").content[:4] == b"\x89PNG"


def test_label_sheet_for_selected_or_all_rows(manager_client, employee_client, table):
    ids = [add(manager_client, table, n)["id"] for n in ("A", "B", "C")]
    url = f"/api/records/labels/?table_item={table['sidebar_item']}"
    one = manager_client.post(url, {"ids": ids[:1]}, format="json")
    assert one.status_code == 200 and one.content.startswith(b"%PDF") and one["Content-Type"] == "application/pdf"
    assert manager_client.post(url, {"all": True}, format="json").content.startswith(b"%PDF")
    assert manager_client.post(url, {"ids": []}, format="json").status_code == 400
    assert employee_client.post(url, {"all": True}, format="json").status_code == 403


@pytest.mark.parametrize("form", ["code", "lower", "url"])
def test_scanner_lookup_by_code_or_qr_link(manager_client, employee_client, table, form):
    row = add(manager_client, table, "Office")
    scanned = {"code": row["code"], "lower": row["code"].lower(), "url": f"https://192.168.1.45:2025/r/{row['code']}"}[form]
    res = employee_client.get("/api/records/lookup/", {"code": scanned})
    assert res.status_code == 200, res.data
    assert res.data == {
        "id": row["id"],
        "code": row["code"],
        "title": "Office",
        "table": "Licences",
        "table_item": table["sidebar_item"],
        "route": "/t/licences",
        "archived": False,
    }


def test_lookup_respects_visibility_and_archive(admin_client, manager_client, employee_client, table):
    row = add(manager_client, table, "Office")
    assert employee_client.get("/api/records/lookup/", {"code": "NOPE-00001"}).status_code == 404
    manager_client.post(f"/api/records/bulk-archive/?table_item={table['sidebar_item']}", {"ids": [row["id"]]}, format="json")
    assert employee_client.get("/api/records/lookup/", {"code": row["code"]}).status_code == 404  # archived: managers only
    assert manager_client.get("/api/records/lookup/", {"code": row["code"]}).data["archived"] is True
    item = TableDefinition.objects.get(pk=table["id"]).sidebar_item
    item.visible_roles = ["admin", "manager"]
    item.save()
    manager_client.post(
        f"/api/records/bulk-archive/?table_item={table['sidebar_item']}", {"ids": [row["id"]], "restore": True}, format="json"
    )
    assert employee_client.get("/api/records/lookup/", {"code": row["code"]}).status_code == 404  # table hidden


def test_asset_labels_still_work(manager_client, asset):
    res = manager_client.post("/api/assets/labels/", {"ids": [asset.pk]}, format="json")
    assert res.status_code == 200 and res.content.startswith(b"%PDF")
