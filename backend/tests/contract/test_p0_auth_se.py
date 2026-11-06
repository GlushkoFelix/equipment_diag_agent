"""P0 补证：会话过期不续期（AC-US-08）与导出鉴权（AC-SE-04）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app import security
from tests.conftest import FORM_INPUT, wait_for_status
from tests.support import PREFIX, app_client


def _iso_hours_ago(hours: int) -> str:
    value = datetime.now(timezone.utc) - timedelta(hours=hours)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _session_row(db, token: str):
    return db.connection().execute(
        "SELECT * FROM sessions WHERE token_hash=?", (security.token_hash(token),)
    ).fetchone()


def test_ac_us08_expired_session_rejected_without_renewal(tmp_path: Path):
    """AC-US-08：签发 25h 前的会话 → /auth/me 401；不续期、不影响他人会话。"""
    with app_client(tmp_path) as client:
        db = client.app.state.db
        token = client.cookies.get(security.COOKIE_NAME)
        assert token, "注册后必须写入会话 Cookie"

        expired_at = _iso_hours_ago(25)
        db.connection().execute(
            "UPDATE sessions SET created_at=?, expires_at=? WHERE token_hash=?",
            (_iso_hours_ago(26), expired_at, security.token_hash(token)),
        )
        # 另一个用户的会话（不应被清空）
        _other_user, other_token = security.register_user(db, "other_user", "Passw0rd!")
        other_before = _session_row(db, other_token)

        me = client.get(f"{PREFIX}/auth/me", cookies={security.COOKIE_NAME: token})
        assert me.status_code == 401, me.text
        assert me.json()["error"]["code"] == "AUTH_SESSION_EXPIRED"

        expired_row = _session_row(db, token)
        assert expired_row["expires_at"] == expired_at, "401 不得续期过期会话"
        assert expired_row["revoked_at"] is None

        other_after = _session_row(db, other_token)
        assert other_after["revoked_at"] is None, "不得清空他人会话"
        assert other_after["expires_at"] == other_before["expires_at"]
        assert security.resolve_session(db, other_token)["username"] == "other_user"


def test_ac_se04_unauthorized_export_and_report_have_no_report_body(tmp_path: Path):
    """AC-SE-04：无 Cookie 访问导出/报告 → 401 AUTH_REQUIRED，响应体不含报告内容。"""
    with app_client(tmp_path) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
        assert created.status_code == 202, created.text
        diagnosis_id = created.json()["diagnosis_id"]
        snapshot = wait_for_status(client, diagnosis_id, {"succeeded", "degraded"})
        assert snapshot["report"] is not None, "需先存在真实报告以验证不泄露"
        assert "## 结论" in snapshot["report"]["markdown"]

        client.cookies.clear()

        report = client.get(f"{PREFIX}/diagnoses/{diagnosis_id}/report.md")
        assert report.status_code == 401, report.text
        assert report.json()["error"]["code"] == "AUTH_REQUIRED"
        assert "## 结论" not in report.text
        assert snapshot["report"]["markdown"][:40] not in report.text

        export = client.get(f"{PREFIX}/batches/bat_p0_se04/export.csv")
        assert export.status_code == 401, export.text
        assert export.json()["error"]["code"] == "AUTH_REQUIRED"
        assert "设备标识" not in export.text
        assert "诊断报告" not in export.text
