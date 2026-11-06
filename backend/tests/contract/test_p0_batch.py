"""P0 验收补测：批量重复行追溯与批量超时（AC-IN-20 / AC-IN-21）。"""

from __future__ import annotations

import io
import time
from pathlib import Path

from fastapi.testclient import TestClient

from tests.support import PREFIX, app_client

TERMINAL = {"completed", "partially_failed", "failed", "cancelled", "timed_out"}
HEADER = (
    "Product ID,Type,Air temperature [K],Process temperature [K],"
    "Rotational speed [rpm],Torque [Nm],Tool wear [min]\n"
)
DUPLICATE_CSV = HEADER + (
    "1,M,298.1,305.3,1250,30,100\n"
    "1,M,298.1,305.3,1250,30,100\n"
)
TIMEOUT_CSV = HEADER + (
    "1,M,298.1,305.3,1250,30,100\n"
    "2,L,300.0,310.0,1400,45,120\n"
    "3,H,299.0,309.0,1500,60,200\n"
)


def _upload(client: TestClient, csv_text: str) -> dict:
    response = client.post(
        f"{PREFIX}/uploads",
        files={"file": ("batch.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
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
        time.sleep(0.05)
    raise AssertionError(f"批量任务未在 {timeout}s 内结束：{snapshot}")


def test_ac_in20_duplicate_rows_are_processed_and_traceable(client: TestClient):
    upload = _upload(client, DUPLICATE_CSV)
    created = client.post(
        f"{PREFIX}/batches",
        json={"upload_id": upload["upload_id"], "mapping": upload["suggested_mapping"]},
    )
    assert created.status_code == 202, created.text
    snapshot = _wait_batch(client, created.json()["batch_task_id"])
    assert snapshot["total_rows"] == 2
    assert snapshot["counts"]["succeeded"] + snapshot["counts"]["degraded"] == 2

    rows = client.app.state.db.connection().execute(
        "SELECT diagnosis_id FROM batch_rows WHERE batch_task_id=? ORDER BY row_no",
        (snapshot["batch_task_id"],),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["diagnosis_id"] != rows[1]["diagnosis_id"]
    diagnoses = [
        client.app.state.db.connection().execute(
            "SELECT input_fingerprint, fingerprint_scope, active_fingerprint_key"
            " FROM diagnoses WHERE diagnosis_id=?",
            (row["diagnosis_id"],),
        ).fetchone()
        for row in rows
    ]
    assert diagnoses[0]["input_fingerprint"] == diagnoses[1]["input_fingerprint"]
    assert all(item["fingerprint_scope"] == "trace" for item in diagnoses)
    assert all(item["active_fingerprint_key"] is None for item in diagnoses)


def test_ac_in21_batch_timeout_cancels_pending_rows(tmp_path: Path):
    with app_client(tmp_path, batch_task_timeout_minutes=0) as client:
        upload = _upload(client, TIMEOUT_CSV)
        created = client.post(
            f"{PREFIX}/batches",
            json={"upload_id": upload["upload_id"], "mapping": upload["suggested_mapping"]},
        )
        assert created.status_code == 202, created.text
        snapshot = _wait_batch(client, created.json()["batch_task_id"])
        assert snapshot["status"] == "timed_out"
        assert snapshot["counts"]["cancelled"] == snapshot["total_rows"]
        assert snapshot["counts"]["succeeded"] == 0
        assert snapshot["counts"]["degraded"] == 0
        # ARCH §8.7：completed_rows 为终态行数（含 cancelled）
        assert snapshot["completed_rows"] == snapshot["total_rows"]

        rows = client.get(f"{PREFIX}/batches/{snapshot['batch_task_id']}/rows").json()["items"]
        assert all(item["status"] == "cancelled" for item in rows)
        assert all(item["error_code"] == "TASK_TIMEOUT" for item in rows)
