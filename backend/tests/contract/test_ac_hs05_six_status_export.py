"""AC-HS-05：一份导出覆盖六状态 + 待复核摘要 + 公式字符转义。"""

from __future__ import annotations

import csv
import io
import time
from pathlib import Path

from app.batches import DEGRADED_REVIEW_PREFIX
from tests.support import PREFIX, app_client, write_evidence

TERMINAL = {"completed", "partially_failed", "failed", "cancelled", "timed_out"}
HEADER = (
    "Device ID,Type,Air temperature [K],Process temperature [K],"
    "Rotational speed [rpm],Torque [Nm],Tool wear [min]\n"
)
SIX_ROWS = HEADER + "".join(
    f"HS05-{index},M,298.1,305.3,1250,30,100\n" for index in range(1, 7)
)
SIX_STATUSES = (
    "succeeded",
    "degraded",
    "degraded_review",
    "failed",
    "failed_timeout",
    "cancelled",
)


def _upload(client, csv_text: str) -> dict:
    response = client.post(
        f"{PREFIX}/uploads",
        files={"file": ("hs05.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _wait_batch(client, batch_task_id: str, timeout: float = 40.0) -> dict:
    deadline = time.time() + timeout
    snapshot: dict = {}
    while time.time() < deadline:
        snapshot = client.get(f"{PREFIX}/batches/{batch_task_id}").json()
        if snapshot["status"] in TERMINAL:
            return snapshot
        time.sleep(0.05)
    raise AssertionError(f"批量任务未结束：{snapshot}")


def test_ac_hs05_export_covers_six_statuses_and_escapes_formula(tmp_path: Path):
    with app_client(tmp_path) as client:
        upload = _upload(client, SIX_ROWS)
        created = client.post(
            f"{PREFIX}/batches",
            json={"upload_id": upload["upload_id"], "mapping": upload["suggested_mapping"]},
        )
        assert created.status_code == 202, created.text
        batch_id = created.json()["batch_task_id"]
        _wait_batch(client, batch_id)

        conn = client.app.state.db.connection()
        for row_no, status in enumerate(SIX_STATUSES, start=1):
            summary = (
                f"{DEGRADED_REVIEW_PREFIX}：HDF 诊断报告" if status == "degraded_review" else (
                    None if status in ("failed", "failed_timeout", "cancelled") else f"HS05 报告 {row_no}"
                )
            )
            device_id = "=2+2" if status == "cancelled" else f"HS05-{row_no}"
            conn.execute(
                "UPDATE batch_rows SET status=?, report_summary=?, device_id=?, error_code=?"
                " WHERE batch_task_id=? AND row_no=?",
                (
                    status,
                    summary,
                    device_id,
                    "TASK_TIMEOUT" if status == "failed_timeout" else None,
                    batch_id,
                    row_no,
                ),
            )
        conn.execute(
            "UPDATE batch_tasks SET pending_rows=0, running_rows=0, succeeded_rows=1,"
            " degraded_rows=1, degraded_review_rows=1, failed_rows=1, failed_timeout_rows=1,"
            " cancelled_rows=1 WHERE batch_task_id=?",
            (batch_id,),
        )

        response = client.get(f"{PREFIX}/batches/{batch_id}/export.csv")
        assert response.status_code == 200, response.text
        content = response.text
        rows = list(csv.DictReader(io.StringIO(content)))

        assert [row["status"] for row in rows] == list(SIX_STATUSES)
        assert "degraded" in {row["status"] for row in rows}
        assert "failed_timeout" in {row["status"] for row in rows}
        review_rows = [row for row in rows if row["status"] == "degraded_review"]
        assert len(review_rows) == 1
        assert "待人工复核" in review_rows[0]["report_summary"]
        cancelled = [row for row in rows if row["status"] == "cancelled"][0]
        assert cancelled["device_id"].startswith("'")
        assert cancelled["device_id"] == "'=2+2"

        evidence_dir = Path(__file__).resolve().parents[3] / "storage" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "AC-HS-05-six-status-export.csv").write_text(content, encoding="utf-8")
        write_evidence(
            "AC-HS-05-export-summary",
            {
                "batch_task_id": batch_id,
                "statuses": [row["status"] for row in rows],
                "degraded_review_summary": review_rows[0]["report_summary"],
                "escaped_device_id": cancelled["device_id"],
            },
        )
