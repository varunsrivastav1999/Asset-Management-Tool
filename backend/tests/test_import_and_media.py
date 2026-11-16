import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook
from PIL import Image

from apps.audit.models import AuditLog
from apps.navigation.models import TableColumn, TableDefinition, TableMedia, TableRecord
from apps.navigation.tasks import purge_orphan_table_media

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("seeded_config")]


@pytest.fixture
def table(admin_client):
    res = admin_client.post(
        "/api/table-definitions/",
        {
            "name": "Licences",
            "singular": "Licence",
            "columns": [
                {"name": "Product"},
                {"name": "Seats", "type": "number"},
                {"name": "Renews", "type": "date"},
                {"name": "State", "type": "status"},
                {"name": "Owner", "type": "user"},
                {"name": "Proof", "type": "media"},
            ],
        },
        format="json",
    )
    assert res.status_code == 201, res.data
    return res.data


def csv_file(text, name="rows.csv"):
    return SimpleUploadedFile(name, ("﻿" + text).encode(), content_type="text/csv")


def png_bytes():
    out = io.BytesIO()
    Image.new("RGB", (4, 4), "green").save(out, "PNG")
    return out.getvalue()


# --- Import ----------------------------------------------------------------------------------
def test_template_lists_importable_columns(manager_client, table):
    res = manager_client.get(f"/api/records/import-template/?table_item={table['sidebar_item']}")
    assert res.status_code == 200 and res["Content-Disposition"].endswith('licences-import-template.csv"')
    assert res.content.decode("utf-8-sig").strip() == "Product,Seats,Renews,State,Owner"  # media isn't importable


def test_csv_import_validates_then_creates(manager_client, manager, table):
    item = table["sidebar_item"]
    text = (
        "Product,Seats,Renews,State,Owner,Ignored\n"
        f"Office,25,2027-03-01,In progress,{manager.email},x\n"
        f"IDE,5,,Done,{manager.get_full_name()},\n"
    )
    url = f"/api/records/import/?table_item={item}"
    dry = manager_client.post(url, {"file": csv_file(text), "dry_run": "true"})
    assert dry.status_code == 200 and dry.data["created"] == 2 and dry.data["ignored_columns"] == ["Ignored"]
    assert not TableRecord.objects.filter(definition_id=table["id"]).exists()  # dry run saves nothing

    res = manager_client.post(url, {"file": csv_file(text)})
    assert res.status_code == 200 and res.data["created"] == 2
    rows = {r.custom_data["product"]: r.custom_data for r in TableRecord.objects.filter(definition_id=table["id"])}
    assert rows["Office"] == {
        "product": "Office",
        "seats": 25,
        "renews": "2027-03-01",
        "state": "In progress",
        "owner": {"id": manager.pk, "name": manager.get_full_name()},
    }
    assert rows["IDE"]["owner"]["id"] == manager.pk
    assert AuditLog.objects.filter(action="import", model="navigation.tablerecord").exists()


def test_excel_import_with_real_dates_and_numbers(manager_client, table):
    wb = Workbook()
    ws = wb.active
    ws.append(["product", "seats", "renews"])  # keys work as headers too
    import datetime

    ws.append(["CAD", 3.0, datetime.datetime(2027, 1, 31)])
    out = io.BytesIO()
    wb.save(out)
    upload = SimpleUploadedFile("rows.xlsx", out.getvalue())
    res = manager_client.post(f"/api/records/import/?table_item={table['sidebar_item']}", {"file": upload})
    assert res.status_code == 200, res.data
    assert TableRecord.objects.get(definition_id=table["id"]).custom_data == {
        "product": "CAD",
        "seats": 3,
        "renews": "2027-01-31",
    }


def test_bad_rows_reject_the_whole_file(manager_client, table):
    text = "Product,Seats,State,Owner\nOK,1,Open,\n,abc,Exploded,nobody@nowhere.test\n"
    res = manager_client.post(f"/api/records/import/?table_item={table['sidebar_item']}", {"file": csv_file(text)})
    assert res.status_code == 400 and res.data["created"] == 0
    errors = res.data["errors"][0]
    assert errors["row"] == 3 and set(errors["errors"]) == {"Product", "Seats", "State", "Owner"}
    assert not TableRecord.objects.filter(definition_id=table["id"]).exists()  # all or nothing


def test_missing_required_column_and_wrong_file_type(manager_client, table):
    url = f"/api/records/import/?table_item={table['sidebar_item']}"
    res = manager_client.post(url, {"file": csv_file("Seats\n4\n")})
    assert res.status_code == 400 and "Product" in res.data["errors"][0]["errors"]["file"]
    bad = manager_client.post(url, {"file": SimpleUploadedFile("rows.pdf", b"%PDF-1.4")})
    assert bad.status_code == 400


def test_import_is_for_managers_and_admins(employee_client, admin_client, table):
    item = table["sidebar_item"]
    assert employee_client.post(f"/api/records/import/?table_item={item}", {"file": csv_file("Product\nX\n")}).status_code == 403
    assert employee_client.get(f"/api/records/import-template/?table_item={item}").status_code in (403, 404)
    assert admin_client.post(f"/api/records/import/?table_item={item}", {"file": csv_file("Product\nX\n")}).status_code == 200


# --- Media columns ---------------------------------------------------------------------------------
def upload(client, table, data, name="photo.png", column="proof"):
    return client.post(
        "/api/table-media/", {"file": SimpleUploadedFile(name, data), "table_item": table["sidebar_item"], "column": column}
    )


def test_media_upload_attach_view_and_export(manager_client, employee_client, table):
    res = upload(manager_client, table, png_bytes())
    assert res.status_code == 201, res.data
    value = res.data
    assert value["type"] == "image/png" and value["name"] == "photo.png"
    row = manager_client.post(
        f"/api/records/?table_item={table['sidebar_item']}", {"custom_data": {"product": "Office", "proof": value}}, format="json"
    )
    assert row.status_code == 201, row.data
    assert row.data["custom_data"]["proof"]["id"] == value["id"]

    file_res = employee_client.get(f"/api/table-media/{value['id']}/")  # everyone who can see the table
    assert file_res.status_code == 200 and file_res["Content-Type"] == "image/png"
    assert b"".join(file_res.streaming_content) == png_bytes()
    assert file_res["Content-Security-Policy"] == "sandbox"

    export = manager_client.get("/api/records/export-table/", {"table_item": table["sidebar_item"], "file_format": "csv"})
    assert "photo.png" in export.content.decode("utf-8-sig")


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("evil.png", b"<script>alert(1)</script>"),  # not really an image
        ("doc.pdf", b"MZ\x90\x00 not a pdf"),
        ("page.html", b"<html></html>"),  # type not allowed
        ("image.svg", b"<svg/>"),
    ],
)
def test_media_rejects_disguised_or_unsafe_files(manager_client, table, name, data):
    assert upload(manager_client, table, data, name=name).status_code == 400
    assert not TableMedia.objects.exists()


def test_media_cells_only_accept_files_uploaded_for_that_column(manager_client, table):
    url = f"/api/records/?table_item={table['sidebar_item']}"
    for bad in ({"id": "not-a-uuid"}, {"id": "2b1e9a3c-0000-4000-8000-000000000000"}, "https://evil.example/x.png"):
        assert manager_client.post(url, {"custom_data": {"product": "X", "proof": bad}}, format="json").status_code == 400
    assert upload(manager_client, table, png_bytes(), column="product").status_code == 400  # not a media column


def test_media_permissions(employee_client, anon_client, manager_client, table):
    assert upload(employee_client, table, png_bytes()).status_code == 403
    media_id = upload(manager_client, table, png_bytes()).data["id"]
    assert anon_client.get(f"/api/table-media/{media_id}/").status_code == 401
    item = TableColumn.objects.get(key="proof").sidebar_item
    item.visible_roles = ["admin", "manager"]
    item.save()
    assert employee_client.get(f"/api/table-media/{media_id}/").status_code == 404  # table hidden from employees


def test_orphan_uploads_are_purged_with_their_files(manager_client, table, django_capture_on_commit_callbacks):
    kept = upload(manager_client, table, png_bytes()).data
    orphan = upload(manager_client, table, png_bytes(), name="unused.png").data
    manager_client.post(
        f"/api/records/?table_item={table['sidebar_item']}", {"custom_data": {"product": "A", "proof": kept}}, format="json"
    )
    orphan_path = TableMedia.objects.get(pk=orphan["id"]).file.path
    with django_capture_on_commit_callbacks(execute=True):  # files are removed once the delete commits
        assert purge_orphan_table_media(min_age_hours=0) == 1
    assert TableMedia.objects.filter(pk=kept["id"]).exists() and not TableMedia.objects.filter(pk=orphan["id"]).exists()
    import os

    assert not os.path.exists(orphan_path)


def test_deleting_the_table_removes_its_uploads(admin_client, manager_client, table):
    upload(manager_client, table, png_bytes())
    assert TableMedia.objects.count() == 1
    assert admin_client.delete(f"/api/table-definitions/{table['id']}/").status_code == 204
    assert TableMedia.objects.count() == 0 and not TableDefinition.objects.filter(pk=table["id"]).exists()


def test_media_column_on_a_builtin_table(admin_client, manager_client, asset):
    assets_item = TableDefinition.objects.get(source="assets").sidebar_item_id
    col = admin_client.post("/api/table-columns/", {"sidebar_item": assets_item, "name": "Photo", "type": "media"}, format="json")
    assert col.status_code == 201, col.data
    value = manager_client.post(
        "/api/table-media/", {"file": SimpleUploadedFile("a.png", png_bytes()), "table_item": assets_item, "column": "photo"}
    ).data
    res = manager_client.patch(f"/api/assets/{asset.pk}/custom-data/", {"photo": value}, format="json")
    assert res.status_code == 200, res.data
    assert purge_orphan_table_media(min_age_hours=0) == 0  # referenced from the asset


def test_files_of_a_deleted_media_column_are_purged(admin_client, manager_client, table, django_capture_on_commit_callbacks):
    value = upload(manager_client, table, png_bytes()).data
    manager_client.post(
        f"/api/records/?table_item={table['sidebar_item']}", {"custom_data": {"product": "A", "proof": value}}, format="json"
    )
    assert purge_orphan_table_media(min_age_hours=0) == 0  # still used
    col = TableColumn.objects.get(sidebar_item_id=table["sidebar_item"], key="proof")
    assert admin_client.delete(f"/api/table-columns/{col.pk}/").status_code == 204
    with django_capture_on_commit_callbacks(execute=True):
        assert purge_orphan_table_media(min_age_hours=0) == 1  # column gone -> file unused
