"""批量任务契约（ARCH §4.8 / §5.4.7 / §5.5.6）。"""

from __future__ import annotations

import io
import time

from fastapi.testclient import TestClient

PREFIX = "/api/v1"
TERMINAL = {"completed", "partially_failed", "failed", "cancelled", "timed_out"}

CSV_TEXT = (
    "Product ID,Type,Air temperature [K],Process temperature [K],"
    "Rotational speed [rpm],Torque [Nm],Tool wear [min]\n"
    "1,M,298.1,305.3,1250,30,100\n"
    "2,L,300.0,310.0,1400,45,120\n"
    "3,H,299.0,309.0,1500,60,200\n"
    "4,M,bad,309.0,1500,60,200\n"
)


def _upload(client: TestClient) -> dict:
    response = client.post(
        f"{PREFIX}/uploads",
        files={"file": ("batch.csv", io.BytesIO(CSV_TEXT.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _wait_batch(client: TestClient, batch_task_id: str, timeout: float = 40.0) -> dict:
    deadline = time.time() + timeout
    snapshot: dict = {}
    while time.time() < deadline:
        snapshot = client.get(f"{PREFIX}/batches/{batch_task_id}").json()
        if snapshot["status"] in TERMINAL:
            return snapshot
        time.sleep(0.1)
    raise AssertionError(f"批量任务未在 {timeout}s 内结束：{snapshot}")


def test_batch_create_and_counts_conserved(client: TestClient):
    upload = _upload(client)
    created = client.post(
        f"{PREFIX}/batches",
        json={"upload_id": upload["upload_id"], "mapping": upload["suggested_mapping"]},
    )
    assert created.status_code == 202, created.text
    body = created.json()
    assert body["status"] == "queued"
    assert body["total_rows"] == 4
    assert body["stream_url"].endswith("/events")

    snapshot = _wait_batch(client, body["batch_task_id"])
    counts = snapshot["counts"]
    assert sum(counts.values()) == snapshot["total_rows"]
    assert counts["pending"] == 0 and counts["running"] == 0
    assert snapshot["completed_rows"] == 4
    # 第 4 行非法 → 行级失败隔离；其余成功
    assert counts["failed"] == 1
    assert counts["succeeded"] + counts["degraded"] + counts["degraded_review"] == 3
    assert snapshot["status"] == "partially_failed"


def test_batch_rows_and_detail(client: TestClient):
    upload = _upload(client)
    created = client.post(
        f"{PREFIX}/batches",
        json={"upload_id": upload["upload_id"], "mapping": upload["suggested_mapping"]},
    ).json()
    _wait_batch(client, created["batch_task_id"])

    rows = client.get(f"{PREFIX}/batches/{created['batch_task_id']}/rows").json()
    assert rows["total"] == 4
    statuses = {item["row_no"]: item["status"] for item in rows["items"]}
    assert statuses[4] == "failed"
    assert all(item["status"] != "waiting_human" for item in rows["items"])
    for item in rows["items"]:
        if item["status"] in ("failed", "failed_timeout", "cancelled"):
            assert item["report_summary"] is None
        if item["status"] == "degraded_review":
            assert item["report_summary"].startswith("待人工复核（批量模式）")

    failed_row = next(item for item in rows["items"] if item["row_no"] == 4)
    detail = client.get(
        f"{PREFIX}/batches/{created['batch_task_id']}/rows/{failed_row['row_id']}"
    ).json()
    assert detail["row"]["error_code"] == "FIELD_INVALID"

    ok_row = next(item for item in rows["items"] if item["row_no"] == 1)
    ok_detail = client.get(
        f"{PREFIX}/batches/{created['batch_task_id']}/rows/{ok_row['row_id']}"
    ).json()
    assert ok_detail["report_url"].endswith("/report.md")


def test_batch_export_csv(client: TestClient):
    upload = _upload(client)
    created = client.post(
        f"{PREFIX}/batches",
        json={"upload_id": upload["upload_id"], "mapping": upload["suggested_mapping"]},
    ).json()
    _wait_batch(client, created["batch_task_id"])
    response = client.get(f"{PREFIX}/batches/{created['batch_task_id']}/export.csv")
    assert response.status_code == 200, response.text
    assert "text/csv" in response.headers["content-type"]
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert response.text.lstrip("\ufeff").startswith('"row_no","device_id"')


def test_batch_missing_mapping_422(client: TestClient):
    upload = _upload(client)
    mapping = dict(upload["suggested_mapping"])
    mapping["torque_nm"] = None
    response = client.post(
        f"{PREFIX}/batches",
        json={"upload_id": upload["upload_id"], "mapping": mapping},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "MAPPING_MISSING_REQUIRED"


def test_batch_cancel_then_idempotent(client: TestClient):
    upload = _upload(client)
    created = client.post(
        f"{PREFIX}/batches",
        json={"upload_id": upload["upload_id"], "mapping": upload["suggested_mapping"]},
    ).json()
    _wait_batch(client, created["batch_task_id"])
    # 已终态取消 → 409（partially_failed）
    conflict = client.post(f"{PREFIX}/batches/{created['batch_task_id']}/cancel")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "BATCH_ALREADY_FINISHED"

    missing = client.post(f"{PREFIX}/batches/bch_00000000000000000000000000/cancel")
    assert missing.status_code == 404


def test_batch_events_stream_envelope(client: TestClient):
    upload = _upload(client)
    created = client.post(
        f"{PREFIX}/batches",
        json={"upload_id": upload["upload_id"], "mapping": upload["suggested_mapping"]},
    ).json()
    _wait_batch(client, created["batch_task_id"])
    with client.stream("GET", f"{PREFIX}/batches/{created['batch_task_id']}/events") as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())
    assert "retry: 3000" in text
    assert "event: batch_snapshot" in text
    assert "event: batch_status" in text
