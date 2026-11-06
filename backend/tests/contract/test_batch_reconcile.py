"""进程重启对账：queued 批量任务从旁路映射继续调度 pending 行（ARCH §4.9 / §10.4 C-008）。"""

from __future__ import annotations

import io
import time
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.batches import write_sidecar
from app.config import Settings
from app.db import Database, new_id, transaction, utcnow
from app.main import create_app

PREFIX = "/api/v1"
TERMINAL = {"completed", "partially_failed", "failed", "cancelled", "timed_out"}

CSV_TEXT = (
    "Product ID,Type,Air temperature [K],Process temperature [K],"
    "Rotational speed [rpm],Torque [Nm],Tool wear [min]\n"
    "1,M,298.1,305.3,1250,30,100\n"
    "2,L,300.0,310.0,1400,45,120\n"
    "3,H,299.0,309.0,1500,60,200\n"
)


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _wait_batch(client: TestClient, batch_task_id: str, timeout: float = 40.0) -> dict:
    deadline = time.time() + timeout
    snapshot: dict = {}
    while time.time() < deadline:
        snapshot = client.get(f"{PREFIX}/batches/{batch_task_id}").json()
        if snapshot["status"] in TERMINAL:
            return snapshot
        time.sleep(0.1)
    raise AssertionError(f"批量任务未在 {timeout}s 内结束：{snapshot}")


def test_startup_reconcile_resumes_queued_pending_rows(settings: Settings):
    """构造 queued 任务 + 旁路 JSON + pending 行，重启进程后 pending 行继续调度且计数守恒。"""
    credentials = {"username": "restart_user", "password": "Passw0rd!"}

    # 第一个进程：注册并上传 CSV（上传文件落在 storage/uploads，供重启后读取）
    first_app = create_app(settings)
    with TestClient(first_app) as first_client:
        assert first_client.post(f"{PREFIX}/auth/register", json=credentials).status_code == 201
        upload = first_client.post(
            f"{PREFIX}/uploads",
            files={"file": ("restart.csv", io.BytesIO(CSV_TEXT.encode("utf-8")), "text/csv")},
        ).json()

    # 进程退出后：模拟“任务已入库为 queued、行仍 pending、映射只在旁路文件”
    db = Database(settings.db_path)
    conn = db.connection()
    user_id = conn.execute(
        "SELECT user_id FROM users WHERE username=?", (credentials["username"],)
    ).fetchone()["user_id"]
    batch_task_id = new_id("bch")
    now = utcnow()
    deadline = _iso(datetime.now(timezone.utc) + timedelta(minutes=5))
    total_rows = upload["row_count"]
    with transaction(conn):
        conn.execute(
            "INSERT INTO batch_tasks (batch_task_id, user_id, file_name, upload_id, total_rows,"
            " status, default_device_id, pending_rows, timeout_deadline, created_at)"
            " VALUES (?,?,?,?,?,'queued',NULL,?,?,?)",
            (
                batch_task_id,
                user_id,
                "restart.csv",
                upload["upload_id"],
                total_rows,
                total_rows,
                deadline,
                now,
            ),
        )
        for row_no in range(1, total_rows + 1):
            conn.execute(
                "INSERT INTO batch_rows (row_id, batch_task_id, row_no, status, created_at, updated_at)"
                " VALUES (?,?,?,'pending',?,?)",
                (new_id("row"), batch_task_id, row_no, now, now),
            )
    # batch_tasks 不新增映射列：映射仅存在于旁路文件（C-008）
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(batch_tasks)").fetchall()}
    assert "mapping_json" not in columns and "mapping" not in columns
    write_sidecar(settings, batch_task_id, upload["suggested_mapping"], None)
    db.close()

    sidecar = settings.batch_dir / f"{batch_task_id}.json"
    assert sidecar.exists()

    # 第二个进程：启动对账读取旁路文件，继续调度 pending 行
    restarted_app = create_app(settings)
    with TestClient(restarted_app) as client:
        assert client.post(f"{PREFIX}/auth/login", json=credentials).status_code == 200
        snapshot = _wait_batch(client, batch_task_id)

    counts = snapshot["counts"]
    assert sum(counts.values()) == snapshot["total_rows"] == total_rows
    assert counts["pending"] == 0 and counts["running"] == 0
    assert counts["succeeded"] + counts["degraded"] + counts["degraded_review"] == total_rows
    assert snapshot["completed_rows"] == total_rows
    assert snapshot["status"] == "completed"

    # 重启前已存在的行均被真正调度执行（各行绑定诊断且均无重复）
    db = Database(settings.db_path)
    conn = db.connection()
    rows = conn.execute(
        "SELECT status, diagnosis_id FROM batch_rows WHERE batch_task_id=? ORDER BY row_no",
        (batch_task_id,),
    ).fetchall()
    assert len(rows) == total_rows
    assert all(row["status"] in ("succeeded", "degraded", "degraded_review") for row in rows)
    assert all(row["diagnosis_id"] for row in rows)
    diagnosis_count = conn.execute(
        "SELECT COUNT(*) AS c FROM diagnoses WHERE batch_task_id=? AND execution_mode='batch'",
        (batch_task_id,),
    ).fetchone()["c"]
    assert diagnosis_count == total_rows
    db.close()
