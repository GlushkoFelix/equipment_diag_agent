"""AC-SE-02：CSV 公式注入字段在导出中带单引号前缀；伪造扩展名仍 415。"""

from __future__ import annotations

import csv
import io
import time
from pathlib import Path

from tests.support import PREFIX, app_client, write_evidence

TERMINAL = {"completed", "partially_failed", "failed", "cancelled", "timed_out"}
HEADER = (
    "Device ID,Type,Air temperature [K],Process temperature [K],"
    "Rotational speed [rpm],Torque [Nm],Tool wear [min]\n"
)
FORMULA_VALUES = ("=cmd", "+SUM(1)", "-1+1", "@SUM(1)")
INJECTION_CSV = HEADER + "".join(
    f"{value},M,298.1,305.3,1250,30,100\n" for value in FORMULA_VALUES
) + "SAFE-1,M,298.1,305.3,1250,30,100\n"


def _upload(client, filename: str, content: bytes):
    return client.post(
        f"{PREFIX}/uploads",
        files={"file": (filename, io.BytesIO(content), "text/csv")},
    )


def test_ac_se02_formula_fields_escaped_in_export(tmp_path: Path):
    with app_client(tmp_path) as client:
        upload = _upload(client, "se02.csv", INJECTION_CSV.encode("utf-8"))
        assert upload.status_code == 201, upload.text
        upload_body = upload.json()

        created = client.post(
            f"{PREFIX}/batches",
            json={"upload_id": upload_body["upload_id"], "mapping": upload_body["suggested_mapping"]},
        )
        assert created.status_code == 202, created.text
        batch_id = created.json()["batch_task_id"]

        deadline = time.time() + 40
        while time.time() < deadline:
            snapshot = client.get(f"{PREFIX}/batches/{batch_id}").json()
            if snapshot["status"] in TERMINAL:
                break
            time.sleep(0.05)
        assert snapshot["status"] in TERMINAL

        response = client.get(f"{PREFIX}/batches/{batch_id}/export.csv")
        assert response.status_code == 200, response.text
        rows = list(csv.DictReader(io.StringIO(response.text)))
        exported = [row["device_id"] for row in rows]
        for value in FORMULA_VALUES:
            assert f"'{value}" in exported, exported
        assert "SAFE-1" in exported

        forged = _upload(client, "报表.csv.exe", b"Device ID\n=cmd\n")
        assert forged.status_code == 415, forged.text
        assert forged.json()["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"
        assert "仅支持 .csv" in forged.json()["error"]["message"]

        evidence_dir = Path(__file__).resolve().parents[3] / "storage" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "AC-SE-02-formula-export.csv").write_text(response.text, encoding="utf-8")
        write_evidence(
            "AC-SE-02-formula-escape",
            {
                "batch_task_id": batch_id,
                "exported_device_ids": exported,
                "forged_extension_status": forged.status_code,
                "forged_extension_error": forged.json()["error"],
            },
        )
