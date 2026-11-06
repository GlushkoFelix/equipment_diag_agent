"""AC-IN-05：.xlsx 上传 → 415 FILE_TYPE_NOT_ALLOWED，message 含“仅支持 .csv”。"""

from __future__ import annotations

import io
from pathlib import Path

from tests.support import PREFIX, app_client, write_evidence


def test_ac_in05_xlsx_upload_rejected_415(tmp_path: Path):
    with app_client(tmp_path) as client:
        response = client.post(
            f"{PREFIX}/uploads",
            files={
                "file": (
                    "设备数据.xlsx",
                    io.BytesIO(b"PK\x03\x04fake-xlsx-content"),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 415, response.text
        body = response.json()
        assert body["error"]["code"] == "FILE_TYPE_NOT_ALLOWED"
        assert "仅支持 .csv" in body["error"]["message"]
        write_evidence("AC-IN-05-xlsx-upload", body)
