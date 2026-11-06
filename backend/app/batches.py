"""批量任务：创建、调度、计数守恒、取消、导出与 SSE（ARCH §4.8 / §5.4.7）。"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app import features as features_domain
from app import records, services, uploads
from app.config import Settings
from app.db import Database, new_id, transaction, utcnow
from app.errors import ApiError

logger = logging.getLogger("edg.batch")

COUNT_COLUMNS = {
    "pending": "pending_rows",
    "running": "running_rows",
    "succeeded": "succeeded_rows",
    "degraded": "degraded_rows",
    "degraded_review": "degraded_review_rows",
    "failed": "failed_rows",
    "failed_timeout": "failed_timeout_rows",
    "cancelled": "cancelled_rows",
}
# 诊断终态 → 批量行状态（ARCH §4.3.3 / §4.8.1）
DIAGNOSIS_TO_ROW = {
    "succeeded": "succeeded",
    "degraded": "degraded",
    "degraded_review": "degraded_review",
    "aborted": "failed",
    "failed": "failed",
    "failed_timeout": "failed_timeout",
    "expired": "failed",
}
DEGRADED_REVIEW_PREFIX = "待人工复核（批量模式）"


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def counts_of(row) -> dict[str, int]:
    return {key: int(row[column]) for key, column in COUNT_COLUMNS.items()}


def summary_of(row) -> dict[str, Any]:
    total = int(row["total_rows"])
    counts = counts_of(row)
    completed = total - counts["pending"] - counts["running"]
    return {
        "batch_task_id": row["batch_task_id"],
        "file_name": row["file_name"],
        "total_rows": total,
        "status": row["status"],
        "default_device_id": row["default_device_id"],
        "counts": counts,
        "completed_rows": completed,
        "progress": round(completed / total, 6) if total else 0.0,
        "cancel_requested": row["cancel_requested_at"] is not None,
        "timeout_deadline": row["timeout_deadline"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "error_code": row["error_code"],
    }


def row_summary_of(row) -> dict[str, Any]:
    return {
        "row_id": row["row_id"],
        "row_no": row["row_no"],
        "device_id": row["device_id"],
        "status": row["status"],
        "diagnosis_id": row["diagnosis_id"],
        "report_summary": row["report_summary"],
        "auto_review": bool(row["auto_review"]),
        "duration_ms": row["duration_ms"],
        "error_field": row["error_field"],
        "error_code": row["error_code"],
    }


def get_batch_row(db: Database, user_id: int, batch_task_id: str):
    row = db.connection().execute(
        "SELECT * FROM batch_tasks WHERE batch_task_id=? AND user_id=?", (batch_task_id, user_id)
    ).fetchone()
    if row is None:
        raise ApiError(404, "BATCH_NOT_FOUND", "批量任务不存在或无权访问")
    return row


def get_batch(db: Database, user_id: int, batch_task_id: str) -> dict[str, Any]:
    return summary_of(get_batch_row(db, user_id, batch_task_id))


def list_batches(
    db: Database,
    user_id: int,
    *,
    status: str | None,
    date_from: str | None,
    date_to: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    clauses = ["user_id = ?"]
    values: list[Any] = [user_id]
    if status:
        statuses = [value.strip() for value in status.split(",") if value.strip()]
        clauses.append(f"status IN ({','.join('?' for _ in statuses)})")
        values.extend(statuses)
    if date_from:
        clauses.append("created_at >= ?")
        values.append(date_from)
    if date_to:
        clauses.append("created_at <= ?")
        values.append(date_to)
    where = " AND ".join(clauses)
    conn = db.connection()
    total = conn.execute(f"SELECT COUNT(*) AS c FROM batch_tasks WHERE {where}", values).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM batch_tasks WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        [*values, page_size, (page - 1) * page_size],
    ).fetchall()
    return {
        "items": [summary_of(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def count_batch_rows(db: Database, batch_task_id: str, statuses: list[str] | None = None) -> int:
    conn = db.connection()
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        return conn.execute(
            f"SELECT COUNT(*) AS c FROM batch_rows WHERE batch_task_id=? AND status IN ({placeholders})",
            (batch_task_id, *statuses),
        ).fetchone()["c"]
    return conn.execute(
        "SELECT COUNT(*) AS c FROM batch_rows WHERE batch_task_id=?", (batch_task_id,)
    ).fetchone()["c"]


def list_batch_rows(
    db: Database,
    user_id: int,
    batch_task_id: str,
    *,
    status: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    get_batch_row(db, user_id, batch_task_id)
    clauses = ["batch_task_id = ?"]
    values: list[Any] = [batch_task_id]
    if status:
        statuses = [value.strip() for value in status.split(",") if value.strip()]
        clauses.append(f"status IN ({','.join('?' for _ in statuses)})")
        values.extend(statuses)
    where = " AND ".join(clauses)
    conn = db.connection()
    total = conn.execute(f"SELECT COUNT(*) AS c FROM batch_rows WHERE {where}", values).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM batch_rows WHERE {where} ORDER BY row_no LIMIT ? OFFSET ?",
        [*values, page_size, (page - 1) * page_size],
    ).fetchall()
    return {
        "items": [row_summary_of(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


def batch_row_detail(db: Database, user_id: int, batch_task_id: str, row_id: str) -> dict[str, Any]:
    get_batch_row(db, user_id, batch_task_id)
    row = db.connection().execute(
        "SELECT * FROM batch_rows WHERE batch_task_id=? AND row_id=?", (batch_task_id, row_id)
    ).fetchone()
    if row is None:
        raise ApiError(404, "BATCH_ROW_NOT_FOUND", "批量行不存在")
    summary = row_summary_of(row)
    report_url = None
    diagnosis_status = None
    if row["diagnosis_id"]:
        diagnosis = db.connection().execute(
            "SELECT status, report_md FROM diagnoses WHERE diagnosis_id=?", (row["diagnosis_id"],)
        ).fetchone()
        if diagnosis is not None:
            diagnosis_status = diagnosis["status"]
            if diagnosis["report_md"]:
                report_url = f"/api/v1/diagnoses/{row['diagnosis_id']}/report.md"
    return {"row": summary, "report_url": report_url, "diagnosis_status": diagnosis_status}


def _sidecar_path(settings: Settings, batch_task_id: str):
    return Path(settings.batch_dir) / f"{batch_task_id}.json"


def write_sidecar(settings: Settings, batch_task_id: str, mapping: dict[str, Any], default_device_id: str | None) -> None:
    """冻结 DB 的 batch_tasks 无映射列：映射旁路持久化，供重启后 pending 行继续执行。"""
    Path(settings.batch_dir).mkdir(parents=True, exist_ok=True)
    _sidecar_path(settings, batch_task_id).write_text(
        json.dumps({"mapping": mapping, "default_device_id": default_device_id}, ensure_ascii=False),
        encoding="utf-8",
    )


def read_sidecar(settings: Settings, batch_task_id: str) -> dict[str, Any]:
    path = _sidecar_path(settings, batch_task_id)
    if not path.exists():
        return {"mapping": None, "default_device_id": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"mapping": None, "default_device_id": None}


def create_batch(
    db: Database, settings: Settings, user_id: int, body: dict[str, Any]
) -> dict[str, Any]:
    upload = uploads.load_upload_row(db, user_id, body["upload_id"])
    headers, data_rows = uploads.read_rows(upload)
    default_device_id = body.get("default_device_id")
    active, missing_required, errors = uploads.resolve_mapping(
        body.get("mapping"), headers, default_device_id
    )
    if missing_required:
        raise ApiError(
            422,
            "MAPPING_MISSING_REQUIRED",
            "映射缺少必填列",
            details={"fields": [{"field": key, "reason": "MISSING"} for key in missing_required]},
        )
    if errors:
        raise ApiError(
            422,
            "MAPPING_CONFLICT",
            errors[0]["message"],
            details={"fields": [{"field": "mapping", "reason": "COLUMN_NOT_FOUND"}]},
        )
    total_rows = len(data_rows)
    if total_rows < 1:
        raise ApiError(422, "FILE_EMPTY", "文件没有数据行")
    if total_rows > settings.csv_max_rows:
        raise ApiError(422, "CSV_ROW_LIMIT_EXCEEDED", f"CSV 数据行最多 {settings.csv_max_rows} 行")

    batch_task_id = new_id("bch")
    now = utcnow()
    deadline = _iso(datetime.now(timezone.utc) + timedelta(minutes=settings.batch_task_timeout_minutes))
    conn = db.connection()
    with transaction(conn):
        conn.execute(
            "INSERT INTO batch_tasks (batch_task_id, user_id, file_name, upload_id, total_rows, status,"
            " default_device_id, pending_rows, timeout_deadline, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                batch_task_id,
                user_id,
                upload["original_name"],
                upload["upload_id"],
                total_rows,
                "queued",
                default_device_id,
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
    records.append_batch_event(db, batch_task_id, "batch_snapshot", summary_of(
        get_batch_row(db, user_id, batch_task_id)
    ))
    write_sidecar(settings, batch_task_id, active, default_device_id)
    return {
        "batch_task_id": batch_task_id,
        "status": "queued",
        "total_rows": total_rows,
        "created_at": now,
        "stream_url": f"/api/v1/batches/{batch_task_id}/events",
        "snapshot_url": f"/api/v1/batches/{batch_task_id}",
    }


# ---------- 计数与行状态 ----------
def _transition_row(db: Database, row_id: str, from_status: str, to_status: str, **fields: Any) -> bool:
    """条件更新行状态并同步计数；返回是否赢得该次状态迁移。"""
    conn = db.connection()
    with transaction(conn):
        row = conn.execute(
            "SELECT batch_task_id, status FROM batch_rows WHERE row_id=?", (row_id,)
        ).fetchone()
        if row is None or row["status"] != from_status:
            return False
        assignments = ["status=?", "updated_at=?"]
        values: list[Any] = [to_status, utcnow()]
        for key, value in fields.items():
            assignments.append(f"{key}=?")
            values.append(value)
        values.append(row_id)
        conn.execute(f"UPDATE batch_rows SET {', '.join(assignments)} WHERE row_id=?", values)
        conn.execute(
            "UPDATE batch_tasks SET {from_col}={from_col}-1, {to_col}={to_col}+1 WHERE batch_task_id=?".format(
                from_col=COUNT_COLUMNS[from_status], to_col=COUNT_COLUMNS[to_status]
            ),
            (row["batch_task_id"],),
        )
    return True


def cancel_batch(db: Database, user_id: int, batch_task_id: str) -> tuple[int, dict[str, Any]]:
    task = get_batch_row(db, user_id, batch_task_id)
    if task["status"] in ("completed", "partially_failed", "failed", "cancelled", "timed_out"):
        if task["status"] == "cancelled":
            return 200, {
                "batch_task_id": batch_task_id,
                "status": task["status"],
                "cancel_requested": task["cancel_requested_at"] is not None,
            }
        raise ApiError(409, "BATCH_ALREADY_FINISHED", "批量任务已结束，无法取消")
    conn = db.connection()
    with transaction(conn):
        conn.execute(
            "UPDATE batch_tasks SET cancel_requested_at=COALESCE(cancel_requested_at, ?)"
            " WHERE batch_task_id=?",
            (utcnow(), batch_task_id),
        )
        pending = conn.execute(
            "SELECT row_id FROM batch_rows WHERE batch_task_id=? AND status='pending'", (batch_task_id,)
        ).fetchall()
    for row in pending:
        _transition_row(db, row["row_id"], "pending", "cancelled")
    _finalize_if_done(db, batch_task_id)
    refreshed = get_batch_row(db, user_id, batch_task_id)
    return 202, summary_of(refreshed) | {
        "batch_task_id": refreshed["batch_task_id"],
        "cancel_requested": refreshed["cancel_requested_at"] is not None,
    }


def _finalize_if_done(db: Database, batch_task_id: str) -> None:
    """全部行进入终态后裁决任务状态（ARCH §4.3.3）。"""
    conn = db.connection()
    task = conn.execute("SELECT * FROM batch_tasks WHERE batch_task_id=?", (batch_task_id,)).fetchone()
    if task is None or task["status"] in ("completed", "partially_failed", "failed", "cancelled", "timed_out"):
        return
    counts = counts_of(task)
    if counts["pending"] or counts["running"]:
        return
    if task["cancel_requested_at"]:
        final = "cancelled"
    elif task["timeout_deadline"] <= utcnow():
        final = "timed_out"
    elif counts["failed"] or counts["failed_timeout"]:
        final = "partially_failed"
    else:
        final = "completed"
    with transaction(conn):
        updated = conn.execute(
            "UPDATE batch_tasks SET status=?, finished_at=? WHERE batch_task_id=? AND status IN ('queued','running')",
            (final, utcnow(), batch_task_id),
        ).rowcount
    if updated == 1:
        refreshed = conn.execute(
            "SELECT * FROM batch_tasks WHERE batch_task_id=?", (batch_task_id,)
        ).fetchone()
        records.append_batch_event(
            db,
            batch_task_id,
            "batch_status",
            {
                "status": final,
                "counts": counts_of(refreshed),
                "finished_at": refreshed["finished_at"],
                "cancel_requested": refreshed["cancel_requested_at"] is not None,
                "error_code": refreshed["error_code"],
            },
        )


def _emit_progress(db: Database, batch_task_id: str) -> None:
    task = db.connection().execute(
        "SELECT * FROM batch_tasks WHERE batch_task_id=?", (batch_task_id,)
    ).fetchone()
    if task is None:
        return
    summary = summary_of(task)
    records.append_batch_event(
        db,
        batch_task_id,
        "batch_progress",
        {
            "completed_rows": summary["completed_rows"],
            "total_rows": summary["total_rows"],
            "progress": summary["progress"],
            "counts": summary["counts"],
        },
    )


def export_csv(db: Database, user_id: int, batch_task_id: str) -> tuple[str, str]:
    task = get_batch_row(db, user_id, batch_task_id)
    rows = db.connection().execute(
        "SELECT r.*, d.primary_type, d.confidence FROM batch_rows r"
        " LEFT JOIN diagnoses d ON d.diagnosis_id = r.diagnosis_id"
        " WHERE r.batch_task_id=? ORDER BY r.row_no",
        (batch_task_id,),
    ).fetchall()
    if not any(row["status"] in ("succeeded", "degraded", "degraded_review") for row in rows):
        raise ApiError(409, "REPORT_NOT_AVAILABLE", "批量任务尚无已完成行，暂不可导出")

    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(
        [
            "row_no",
            "device_id",
            "primary_type",
            "confidence",
            "status",
            "report_summary",
            "duration_ms",
            "error_field",
            "error_code",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["row_no"],
                _csv_safe(row["device_id"]),
                _csv_safe(row["primary_type"]),
                "" if row["confidence"] is None else row["confidence"],
                row["status"],
                _csv_safe(row["report_summary"]),
                "" if row["duration_ms"] is None else row["duration_ms"],
                _csv_safe(row["error_field"]),
                _csv_safe(row["error_code"]),
            ]
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    filename = f"批量汇总_{batch_task_id}_{stamp}.csv"
    return buffer.getvalue(), quote(filename)


def _csv_safe(value: Any) -> Any:
    """CSV 公式注入转义：以 = + - @ \\t \\r 开头前置单引号（ARCH §5.4.7）。"""
    if value is None:
        return ""
    text = str(value)
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


# ---------- 执行器 ----------
class BatchRunner:
    """批量调度：进程内 asyncio 并发 2；行失败隔离；取消/超时只停调度。"""

    def __init__(self, settings: Settings, db: Database, diagnosis_runner):
        self.settings = settings
        self.db = db
        self.runner = diagnosis_runner
        self._tasks: dict[str, asyncio.Task] = {}

    def start(self, batch_task_id: str) -> None:
        task = asyncio.create_task(self._run(batch_task_id))
        self._tasks[batch_task_id] = task

    async def wait_all(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def resume_queued(self) -> None:
        """启动对账：queued 任务继续调度（ARCH §4.9）。"""
        rows = self.db.connection().execute(
            "SELECT batch_task_id FROM batch_tasks WHERE status IN ('queued','running')"
        ).fetchall()
        for row in rows:
            self.start(row["batch_task_id"])

    async def _run(self, batch_task_id: str) -> None:
        try:
            task = self.db.connection().execute(
                "SELECT * FROM batch_tasks WHERE batch_task_id=?", (batch_task_id,)
            ).fetchone()
            if task is None:
                return
            if task["status"] == "queued":
                self.db.connection().execute(
                    "UPDATE batch_tasks SET status='running', started_at=? WHERE batch_task_id=?"
                    " AND status='queued'",
                    (utcnow(), batch_task_id),
                )
            await asyncio.gather(*[self._worker(batch_task_id, index) for index in range(2)])
            _finalize_if_done(self.db, batch_task_id)
            _emit_progress(self.db, batch_task_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("batch run failed: %s", batch_task_id)
            self._fail_task(batch_task_id)

    def _fail_task(self, batch_task_id: str) -> None:
        conn = self.db.connection()
        with transaction(conn):
            conn.execute(
                "UPDATE batch_tasks SET status='failed', error_code='INTERNAL_ERROR', finished_at=?"
                " WHERE batch_task_id=? AND status IN ('queued','running')",
                (utcnow(), batch_task_id),
            )

    def _next_pending_row(self, batch_task_id: str):
        conn = self.db.connection()
        task = conn.execute(
            "SELECT status, cancel_requested_at, timeout_deadline FROM batch_tasks WHERE batch_task_id=?",
            (batch_task_id,),
        ).fetchone()
        if task is None:
            return None
        if task["cancel_requested_at"] or task["status"] not in ("queued", "running"):
            return None
        if task["timeout_deadline"] <= utcnow():
            # RT-20：超时后未开始行 cancelled(TASK_TIMEOUT)，运行中行允许完成
            pending = conn.execute(
                "SELECT row_id FROM batch_rows WHERE batch_task_id=? AND status='pending'",
                (batch_task_id,),
            ).fetchall()
            for row in pending:
                _transition_row(
                    self.db, row["row_id"], "pending", "cancelled", error_code="TASK_TIMEOUT"
                )
            return None
        return conn.execute(
            "SELECT * FROM batch_rows WHERE batch_task_id=? AND status='pending' ORDER BY row_no LIMIT 1",
            (batch_task_id,),
        ).fetchone()

    async def _worker(self, batch_task_id: str, worker_index: int) -> None:
        while True:
            row = self._next_pending_row(batch_task_id)
            if row is None:
                return
            if not _transition_row(self.db, row["row_id"], "pending", "running"):
                continue
            records.append_batch_event(
                self.db,
                batch_task_id,
                "row_status",
                row_summary_of(
                    self.db.connection()
                    .execute("SELECT * FROM batch_rows WHERE row_id=?", (row["row_id"],))
                    .fetchone()
                ),
            )
            try:
                await self._execute_row(batch_task_id, row["row_id"], row["row_no"])
            except asyncio.CancelledError:
                raise
            except Exception:
                # RT-15：行失败隔离，不拖垮整个任务
                logger.exception("batch row failed: %s", row["row_id"])
                _transition_row(
                    self.db,
                    row["row_id"],
                    "running",
                    "failed",
                    error_code="INTERNAL_ERROR",
                    duration_ms=0,
                )
                self._publish_row(batch_task_id, row["row_id"], row["row_no"], None)

    async def _execute_row(self, batch_task_id: str, row_id: str, row_no: int) -> None:
        conn = self.db.connection()
        task = conn.execute(
            "SELECT * FROM batch_tasks WHERE batch_task_id=?", (batch_task_id,)
        ).fetchone()
        upload = conn.execute("SELECT * FROM uploads WHERE upload_id=?", (task["upload_id"],)).fetchone()
        headers, data_rows = uploads.read_rows(upload)
        sidecar = read_sidecar(self.settings, batch_task_id)
        mapping = sidecar.get("mapping")
        default_device_id = sidecar.get("default_device_id") or task["default_device_id"]
        active, _, _ = uploads.resolve_mapping(mapping, headers, default_device_id)
        parsed = uploads.parse_data_row(
            headers, data_rows[row_no - 1], active, default_device_id, row_no
        )
        if parsed["error"]:
            _transition_row(
                self.db,
                row_id,
                "running",
                "failed",
                device_id=parsed["device_id"],
                error_field=parsed["error"]["field"],
                error_code=parsed["error"]["code"],
                duration_ms=0,
            )
            self._publish_row(batch_task_id, row_id, row_no, None)
            return

        normalized = parsed["normalized"]
        diagnosis_id, state = services.insert_diagnosis_from_result(
            self.db,
            self.settings,
            task["user_id"],
            input_type="csv_batch",
            result=normalized,
            raw_input=parsed["raw_input"],
            execution_mode="batch",
            input_summary={"file_name": task["file_name"], "row_no": row_no},
            batch_task_id=batch_task_id,
            row_id=row_id,
            upload_id=task["upload_id"],
            fingerprint_scope="trace",
        )
        conn.execute(
            "UPDATE batch_rows SET diagnosis_id=?, device_id=?, updated_at=? WHERE row_id=?",
            (diagnosis_id, parsed["device_id"], utcnow(), row_id),
        )
        await self.runner.run_inline(diagnosis_id, state)
        diagnosis = conn.execute(
            "SELECT * FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)
        ).fetchone()
        row_status = DIAGNOSIS_TO_ROW.get(diagnosis["status"], "failed")
        report_summary = _row_report_summary(diagnosis, row_status)
        _transition_row(
            self.db,
            row_id,
            "running",
            row_status,
            report_summary=report_summary,
            auto_review=1 if diagnosis["auto_review"] else 0,
            duration_ms=diagnosis["duration_ms"] or 0,
            error_code=diagnosis["error_code"] if row_status in ("failed", "failed_timeout") else None,
        )
        self._publish_row(batch_task_id, row_id, row_no, diagnosis_id)

    def _publish_row(self, batch_task_id: str, row_id: str, row_no: int, diagnosis_id: str | None) -> None:
        row = self.db.connection().execute(
            "SELECT * FROM batch_rows WHERE row_id=?", (row_id,)
        ).fetchone()
        records.append_batch_event(self.db, batch_task_id, "row_status", row_summary_of(row))
        _emit_progress(self.db, batch_task_id)
        _finalize_if_done(self.db, batch_task_id)


def _row_report_summary(diagnosis, row_status: str) -> str | None:
    if row_status in ("failed", "failed_timeout", "cancelled"):
        return None
    title = diagnosis["report_title"] or diagnosis["primary_type"] or "诊断完成"
    if row_status == "degraded_review":
        return f"{DEGRADED_REVIEW_PREFIX}：{title}"
    return title
