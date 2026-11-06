"""AC-IN-17：删除源文件后历史详情仍显示文件名/行号/入口类型且报告可查看。"""

from __future__ import annotations

import io
from pathlib import Path

from tests.conftest import wait_for_status
from tests.support import PREFIX, app_client, write_evidence

CSV_TEXT = (
    "Device ID,Type,Air temperature [K],Process temperature [K],"
    "Rotational speed [rpm],Torque [Nm],Tool wear [min]\n"
    "IN17-1,M,298.1,305.3,1250,30,100\n"
)


def test_ac_in17_history_detail_survives_source_file_deletion(tmp_path: Path):
    with app_client(tmp_path) as client:
        upload = client.post(
            f"{PREFIX}/uploads",
            files={"file": ("in17.csv", io.BytesIO(CSV_TEXT.encode("utf-8")), "text/csv")},
        )
        assert upload.status_code == 201, upload.text
        upload_body = upload.json()

        created = client.post(
            f"{PREFIX}/diagnoses",
            json={
                "input_type": "csv_single",
                "upload_id": upload_body["upload_id"],
                "row_no": 1,
                "mapping": upload_body["suggested_mapping"],
            },
        )
        assert created.status_code == 202, created.text
        diagnosis_id = created.json()["diagnosis_id"]
        wait_for_status(client, diagnosis_id, {"succeeded", "degraded"})

        stored = client.app.state.db.connection().execute(
            "SELECT stored_path FROM uploads WHERE upload_id=?", (upload_body["upload_id"],)
        ).fetchone()["stored_path"]
        Path(stored).unlink()
        assert not Path(stored).exists()

        detail = client.get(f"{PREFIX}/diagnoses/{diagnosis_id}")
        assert detail.status_code == 200, detail.text
        snapshot = detail.json()
        assert snapshot["input_type"] == "csv_single"
        assert snapshot["input_summary"]["file_name"] == "in17.csv"
        assert snapshot["input_summary"]["row_no"] == 1

        report = client.get(f"{PREFIX}/diagnoses/{diagnosis_id}/report.md")
        assert report.status_code == 200, report.text
        assert report.text.startswith("# ")
        assert "## 结论" in report.text

        history = client.get(f"{PREFIX}/diagnoses")
        assert history.status_code == 200
        assert history.json()["total"] == 1

        write_evidence(
            "AC-IN-17-history-after-delete",
            {
                "diagnosis_id": diagnosis_id,
                "deleted_path": stored,
                "input_summary": snapshot["input_summary"],
                "input_type": snapshot["input_type"],
                "report_status": report.status_code,
                "history_total": history.json()["total"],
            },
        )
