"""映射预览与映射方案契约（ARCH §5.4.3）。"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

PREFIX = "/api/v1"

CSV_TEXT = (
    "Product ID,Type,Air temperature [K],Process temperature [K],"
    "Rotational speed [rpm],Torque [Nm],Tool wear [min]\n"
    "1,M,298.1,305.3,1250,30,100\n"
    "2,L,300.0,310.0,1400,45,120\n"
    "3,H,not-a-number,309.0,1500,60,200\n"
)


def _upload(client: TestClient) -> dict:
    response = client.post(
        f"{PREFIX}/uploads",
        files={"file": ("sample.csv", io.BytesIO(CSV_TEXT.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_precheck_shape(client: TestClient):
    body = _upload(client)
    for key in (
        "upload_id",
        "file_name",
        "size_bytes",
        "encoding",
        "row_count",
        "headers",
        "preview_rows",
        "header_signature",
        "suggested_mapping",
        "matched_scheme",
        "issues",
    ):
        assert key in body, key
    assert body["row_count"] == 3
    assert len(body["preview_rows"]) == 3
    assert body["header_signature"].startswith("sha256:")
    assert body["suggested_mapping"]["product_type"] == "Type"
    assert body["matched_scheme"] is None


def test_mapping_preview_batch_reports_row_summary(client: TestClient):
    upload = _upload(client)
    response = client.post(
        f"{PREFIX}/uploads/{upload['upload_id']}/mapping/preview",
        json={"mapping": upload["suggested_mapping"], "mode": "batch", "row_no": None},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert body["row_summary"]["total"] == 3
    assert body["row_summary"]["valid"] == 2
    assert body["row_summary"]["invalid"] == 1
    assert body["row_summary"]["first_invalid"][0]["row_no"] == 3
    assert len(body["preview"]) == 3


def test_mapping_preview_single_invalid_row_422(client: TestClient):
    upload = _upload(client)
    response = client.post(
        f"{PREFIX}/uploads/{upload['upload_id']}/mapping/preview",
        json={"mapping": upload["suggested_mapping"], "mode": "single", "row_no": 3},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "FIELD_INVALID"


def test_mapping_preview_single_returns_three_rows(client: TestClient):
    """单条与批量同一预览口径：固定 3 行（ARCH §5.4.3）。"""
    upload = _upload(client)
    response = client.post(
        f"{PREFIX}/uploads/{upload['upload_id']}/mapping/preview",
        json={"mapping": upload["suggested_mapping"], "mode": "single", "row_no": 2},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert len(body["preview"]) == min(3, upload["row_count"]) == 3
    assert [item["row_no"] for item in body["preview"]] == [1, 2, 3]


def test_mapping_preview_single_short_file_returns_all_rows(client: TestClient):
    csv_text = "\n".join(CSV_TEXT.splitlines()[:3]) + "\n"
    upload = client.post(
        f"{PREFIX}/uploads",
        files={"file": ("short.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
    ).json()
    assert upload["row_count"] == 2
    response = client.post(
        f"{PREFIX}/uploads/{upload['upload_id']}/mapping/preview",
        json={"mapping": upload["suggested_mapping"], "mode": "single", "row_no": 1},
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["preview"]) == min(3, upload["row_count"]) == 2


def test_mapping_preview_missing_required_is_not_valid(client: TestClient):
    upload = _upload(client)
    mapping = dict(upload["suggested_mapping"])
    mapping["torque_nm"] = None
    response = client.post(
        f"{PREFIX}/uploads/{upload['upload_id']}/mapping/preview",
        json={"mapping": mapping, "mode": "batch", "row_no": None},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is False
    assert "torque_nm" in body["missing_required"]


def test_mapping_preview_unknown_column(client: TestClient):
    upload = _upload(client)
    mapping = dict(upload["suggested_mapping"])
    mapping["torque_nm"] = "No Such Column"
    response = client.post(
        f"{PREFIX}/uploads/{upload['upload_id']}/mapping/preview",
        json={"mapping": mapping, "mode": "batch", "row_no": None},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is False
    assert body["errors"][0]["code"] == "MAPPING_CONFLICT"


def test_device_id_null_requires_default(client: TestClient):
    upload = _upload(client)
    mapping = dict(upload["suggested_mapping"])
    mapping["device_id"] = None
    without_default = client.post(
        f"{PREFIX}/uploads/{upload['upload_id']}/mapping/preview",
        json={"mapping": mapping, "mode": "batch", "row_no": None, "default_device_id": None},
    )
    assert "device_id" in without_default.json()["missing_required"]
    with_default = client.post(
        f"{PREFIX}/uploads/{upload['upload_id']}/mapping/preview",
        json={"mapping": mapping, "mode": "batch", "row_no": None, "default_device_id": "3号机"},
    )
    assert with_default.json()["valid"] is True


def test_mapping_scheme_crud(client: TestClient):
    upload = _upload(client)
    body = {
        "name": "台账A",
        "header_signature": upload["header_signature"],
        "mapping": upload["suggested_mapping"],
        "default_device_id": "7号机",
        "overwrite": False,
    }
    created = client.post(f"{PREFIX}/mapping-schemes", json=body)
    assert created.status_code == 201, created.text
    assert created.json()["mapping_id"].startswith("map_")

    duplicate = client.post(f"{PREFIX}/mapping-schemes", json=body)
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["error"]["code"] == "MAPPING_SCHEME_EXISTS"

    overwritten = client.post(f"{PREFIX}/mapping-schemes", json={**body, "overwrite": True})
    assert overwritten.status_code == 200, overwritten.text

    listed = client.get(
        f"{PREFIX}/mapping-schemes", params={"header_signature": upload["header_signature"]}
    )
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    # 再次上传同结构文件应自动套用方案
    again = _upload(client)
    assert again["matched_scheme"] is not None
    assert again["matched_scheme"]["name"] == "台账A"
