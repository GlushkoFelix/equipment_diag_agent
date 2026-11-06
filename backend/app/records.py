"""诊断持久化投影、事件追加写与快照组装。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from app.db import Database, new_id, transaction, utcnow

TERMINAL_STATUSES = {
    "succeeded",
    "degraded",
    "degraded_review",
    "aborted",
    "failed",
    "failed_timeout",
    "expired",
}


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def next_seq(conn: sqlite3.Connection, diagnosis_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS seq FROM diagnosis_events WHERE diagnosis_id=?",
        (diagnosis_id,),
    ).fetchone()
    return int(row["seq"]) + 1


def append_event(
    db: Database,
    diagnosis_id: str,
    event_type: str,
    payload: dict[str, Any],
    revision: int,
) -> int:
    conn = db.connection()
    with transaction(conn):
        seq = next_seq(conn, diagnosis_id)
        conn.execute(
            "INSERT INTO diagnosis_events (event_id, diagnosis_id, seq, type, revision, payload_json, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (new_id("evt"), diagnosis_id, seq, event_type, revision, _dumps(payload), utcnow()),
        )
        if event_type == "status":
            conn.execute(
                "UPDATE diagnoses SET version=? WHERE diagnosis_id=?",
                (int(payload.get("version", revision)), diagnosis_id),
            )
    return seq


def next_batch_seq(conn: sqlite3.Connection, batch_task_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS seq FROM batch_events WHERE batch_task_id=?",
        (batch_task_id,),
    ).fetchone()
    return int(row["seq"]) + 1


def append_batch_event(db: Database, batch_task_id: str, event_type: str, payload: dict[str, Any]) -> int:
    """批量事件追加写（ARCH §4.7 / §5.5.6）：seq 独立自增，revision 恒为 null。"""
    conn = db.connection()
    with transaction(conn):
        seq = next_batch_seq(conn, batch_task_id)
        conn.execute(
            "INSERT INTO batch_events (event_id, batch_task_id, seq, type, payload_json, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (new_id("bevt"), batch_task_id, seq, event_type, _dumps(payload), utcnow()),
        )
    return seq


def append_step(
    db: Database,
    diagnosis_id: str,
    revision: int,
    node: str,
    event: str,
    rule_id: str | None = None,
    summary: str | None = None,
    duration_ms: int | None = None,
    error_code: str | None = None,
) -> None:
    # 确定性 step_id：节点在 resume/重建后会重新执行，避免重复追加
    step_id = "stp_" + hashlib.sha1(
        f"{diagnosis_id}|{revision}|{node}|{event}".encode("utf-8")
    ).hexdigest()[:24]
    conn = db.connection()
    conn.execute(
        "INSERT OR IGNORE INTO diagnosis_steps"
        " (step_id, diagnosis_id, revision, node, event, rule_id, summary, duration_ms, error_code, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            step_id,
            diagnosis_id,
            revision,
            node,
            event,
            rule_id,
            summary,
            duration_ms,
            error_code,
            utcnow(),
        ),
    )


def get_for_user(db: Database, user_id: int, diagnosis_id: str) -> sqlite3.Row:
    from app.errors import not_found

    row = db.connection().execute(
        "SELECT * FROM diagnoses WHERE diagnosis_id=? AND user_id=?",
        (diagnosis_id, user_id),
    ).fetchone()
    if row is None:
        raise not_found("DIAGNOSIS_NOT_FOUND", "诊断不存在或无权访问")
    return row


def find_active_by_fingerprint(conn: sqlite3.Connection, user_id: int, fingerprint: str) -> sqlite3.Row | None:
    key = f"{user_id}:{fingerprint}"
    return conn.execute(
        "SELECT * FROM diagnoses WHERE user_id=? AND active_fingerprint_key=? "
        "AND status IN ('running','waiting_human') LIMIT 1",
        (user_id, key),
    ).fetchone()


def expire_if_needed(db: Database, row: sqlite3.Row) -> bool:
    """RT-16 懒判定：置 expired 并清空 active 指纹（同事务）。"""
    if row["status"] != "waiting_human" or not row["interrupt_expires_at"]:
        return False
    if row["interrupt_expires_at"] > utcnow():
        return False
    conn = db.connection()
    with transaction(conn):
        new_version = int(row["version"]) + 1
        conn.execute(
            "UPDATE diagnoses SET status='expired', version=?, finished_at=?, active_fingerprint_key=NULL,"
            " duration_ms=COALESCE(duration_ms,0) WHERE diagnosis_id=? AND status='waiting_human'",
            (new_version, utcnow(), row["diagnosis_id"]),
        )
        conn.execute(
            "UPDATE chat_sessions SET status='terminal', updated_at=? WHERE diagnosis_id=? AND status='active'",
            (utcnow(), row["diagnosis_id"]),
        )
        seq = next_seq(conn, row["diagnosis_id"])
        conn.execute(
            "INSERT INTO diagnosis_events (event_id, diagnosis_id, seq, type, revision, payload_json, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                new_id("evt"),
                row["diagnosis_id"],
                seq,
                "expired",
                int(row["diagnosis_revision"]),
                _dumps(
                    {
                        "expires_at": row["interrupt_expires_at"],
                        "reason": "TTL_EXCEEDED",
                        "version": new_version,
                    }
                ),
                utcnow(),
            ),
        )
    return True


def set_running(
    db: Database,
    diagnosis_id: str,
    human_decision: str | None = None,
    *,
    expected_version: int | None = None,
) -> int | None:
    """恢复诊断：waiting_human → running，版本 +1，清空中断字段。

    传入 expected_version 时使用条件 UPDATE 保证并发 resume 只有一个赢家（AC-DG-16）；
    条件不满足返回 None，由调用方映射为 409。
    """
    conn = db.connection()
    if expected_version is not None:
        updated = conn.execute(
            "UPDATE diagnoses SET status='running', version=version+1, interrupt_type=NULL,"
            " interrupt_payload_json=NULL, interrupt_expires_at=NULL, human_decision=?"
            " WHERE diagnosis_id=? AND status='waiting_human' AND version=?",
            (human_decision, diagnosis_id, int(expected_version)),
        ).rowcount
        return int(expected_version) + 1 if updated == 1 else None
    row = conn.execute("SELECT version FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)).fetchone()
    new_version = int(row["version"]) + 1
    conn.execute(
        "UPDATE diagnoses SET status='running', version=?, interrupt_type=NULL, interrupt_payload_json=NULL,"
        " interrupt_expires_at=NULL, human_decision=? WHERE diagnosis_id=?",
        (new_version, human_decision, diagnosis_id),
    )
    return new_version


def update_projection(db: Database, diagnosis_id: str, **fields: Any) -> None:
    allowed = {
        "primary_type",
        "secondary_types_json",
        "confidence",
        "confidence_level",
        "confidence_breakdown_json",
        "knowledge_status",
        "evidence_refs_json",
        "retry_count",
        "review_round",
        "report_retry_count",
        "diagnosis_revision",
        "auto_review",
        "input_summary_json",
        "duration_ms",
        "error_code",
        "report_title",
        "report_md",
        "report_meta_json",
        "report_elements_check_json",
        "started_at",
    }
    pairs = []
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"字段不允许投影：{key}")
        if key.endswith("_json") and value is not None:
            value = _dumps(value)
        if key == "auto_review":
            value = 1 if value else 0
        pairs.append(f"{key}=?")
        values.append(value)
    if not pairs:
        return
    values.append(diagnosis_id)
    db.connection().execute(
        f"UPDATE diagnoses SET {', '.join(pairs)} WHERE diagnosis_id=?", values
    )


def finalize(
    db: Database,
    diagnosis_id: str,
    status: str,
    *,
    report_md: str | None = None,
    report_title: str | None = None,
    report_meta: dict[str, Any] | None = None,
    report_check: dict[str, Any] | None = None,
    error_code: str | None = None,
    duration_ms: int | None = None,
) -> int:
    conn = db.connection()
    with transaction(conn):
        row = conn.execute("SELECT version, started_at, created_at FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)).fetchone()
        new_version = int(row["version"]) + 1
        conn.execute(
            "UPDATE diagnoses SET status=?, version=?, finished_at=?, active_fingerprint_key=NULL,"
            " interrupt_type=NULL, interrupt_payload_json=NULL, interrupt_expires_at=NULL,"
            " report_md=?, report_title=?, report_meta_json=?, report_elements_check_json=?,"
            " error_code=?, duration_ms=? WHERE diagnosis_id=?",
            (
                status,
                new_version,
                utcnow(),
                report_md,
                report_title,
                _dumps(report_meta) if report_meta is not None else None,
                _dumps(report_check) if report_check is not None else None,
                error_code,
                duration_ms,
                diagnosis_id,
            ),
        )
        conn.execute(
            "UPDATE chat_sessions SET status='terminal', updated_at=? WHERE diagnosis_id=? AND status='active'",
            (utcnow(), diagnosis_id),
        )
        seq = next_seq(conn, diagnosis_id)
        conn.execute(
            "INSERT INTO diagnosis_events (event_id, diagnosis_id, seq, type, revision, payload_json, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                new_id("evt"),
                diagnosis_id,
                seq,
                "status",
                int(
                    conn.execute(
                        "SELECT diagnosis_revision FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)
                    ).fetchone()["diagnosis_revision"]
                ),
                _dumps({"from": "running", "to": status, "reason": "finalize", "version": new_version}),
                utcnow(),
            ),
        )
    return new_version


def mark_interrupt(
    db: Database,
    diagnosis_id: str,
    interrupt_type: str,
    payload: dict[str, Any],
    expires_at: str,
    review_round: int,
) -> int:
    conn = db.connection()
    with transaction(conn):
        row = conn.execute(
            "SELECT version, diagnosis_revision FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)
        ).fetchone()
        new_version = int(row["version"]) + 1
        conn.execute(
            "UPDATE diagnoses SET status='waiting_human', version=?, interrupt_type=?,"
            " interrupt_payload_json=?, interrupt_expires_at=?, review_round=? WHERE diagnosis_id=?",
            (
                new_version,
                interrupt_type,
                _dumps(payload),
                expires_at,
                review_round,
                diagnosis_id,
            ),
        )
        seq = next_seq(conn, diagnosis_id)
        conn.execute(
            "INSERT INTO diagnosis_events (event_id, diagnosis_id, seq, type, revision, payload_json, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                new_id("evt"),
                diagnosis_id,
                seq,
                "interrupt",
                int(row["diagnosis_revision"]),
                _dumps(
                    {
                        "interrupt_type": interrupt_type,
                        "payload": payload,
                        "expires_at": expires_at,
                        "review_round": review_round,
                        "version": new_version,
                    }
                ),
                utcnow(),
            ),
        )
        seq += 1
        conn.execute(
            "INSERT INTO diagnosis_events (event_id, diagnosis_id, seq, type, revision, payload_json, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                new_id("evt"),
                diagnosis_id,
                seq,
                "status",
                int(row["diagnosis_revision"]),
                _dumps({"from": "running", "to": "waiting_human", "reason": interrupt_type, "version": new_version}),
                utcnow(),
            ),
        )
    return new_version


def touch_runtime(
    db: Database,
    diagnosis_id: str,
    features_block: dict[str, Any] | None = None,
    retrieval: dict[str, Any] | None = None,
) -> None:
    conn = db.connection()
    row = conn.execute("SELECT input_summary_json FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)).fetchone()
    summary = _loads(row["input_summary_json"], {})
    if features_block is not None:
        summary["features"] = features_block
    if retrieval is not None:
        summary["retrieval"] = retrieval
    conn.execute(
        "UPDATE diagnoses SET input_summary_json=? WHERE diagnosis_id=?",
        (_dumps(summary), diagnosis_id),
    )


def build_snapshot(db: Database, row: sqlite3.Row) -> dict[str, Any]:
    diagnosis_id = row["diagnosis_id"]
    summary = _loads(row["input_summary_json"], {})
    features_block = summary.get("features")
    retrieval = summary.get("retrieval")
    steps = [
        {
            "step_id": step["step_id"],
            "node": step["node"],
            "event": step["event"],
            "rule_id": step["rule_id"],
            "revision": step["revision"],
            "summary": step["summary"],
            "duration_ms": step["duration_ms"],
            "created_at": step["created_at"],
        }
        for step in db.connection()
        .execute(
            # 同毫秒事件按写入顺序稳定回放：start 必先于 end（ARCH §4.5.3）
            "SELECT * FROM diagnosis_steps WHERE diagnosis_id=? ORDER BY created_at, rowid",
            (diagnosis_id,),
        )
        .fetchall()
    ]
    interrupt = None
    if row["interrupt_type"]:
        interrupt = {
            "type": row["interrupt_type"],
            "version": row["version"],
            "review_round": row["review_round"],
            "expires_at": row["interrupt_expires_at"],
            "payload": _loads(row["interrupt_payload_json"], {}),
        }
    report = None
    if row["report_md"]:
        report = {
            "markdown": row["report_md"],
            "download_url": f"/api/v1/diagnoses/{diagnosis_id}/report.md",
        }
    error = None
    if row["error_code"]:
        error = {
            "code": row["error_code"],
            "message": "诊断执行失败，请查看错误码",
            "node": None,
            "recoverable": row["error_code"] in {"TIMEOUT", "PROCESS_RESTART", "HUMAN_ABORT"},
        }
    nodes_ms = {step["node"]: step["duration_ms"] for step in steps if step["duration_ms"] is not None}
    snapshot = {
        "diagnosis_id": diagnosis_id,
        "device_id": row["device_id"],
        "input_type": row["input_type"],
        "input_summary": {
            key: summary.get(key)
            for key in ("file_name", "row_no", "text_excerpt")
            if summary.get(key) is not None
        },
        "report_title": row["report_title"],
        "status": row["status"],
        "version": row["version"],
        "diagnosis_revision": row["diagnosis_revision"],
        "primary_type": row["primary_type"],
        "secondary_types": _loads(row["secondary_types_json"], []),
        "confidence": row["confidence"],
        "confidence_level": row["confidence_level"],
        "confidence_breakdown": _loads(row["confidence_breakdown_json"], None),
        "knowledge_status": row["knowledge_status"],
        "evidence_refs": _loads(row["evidence_refs_json"], []),
        "features": features_block,
        "retrieval": retrieval,
        "retry_count": row["retry_count"],
        "review_round": row["review_round"],
        "report_retry_count": row["report_retry_count"],
        "report_elements_check": _loads(row["report_elements_check_json"], None),
        "duration_ms": row["duration_ms"] or 0,
        "interrupt": interrupt,
        "human_decision": row["human_decision"],
        "auto_review": bool(row["auto_review"]),
        "report": report,
        "report_meta": _loads(row["report_meta_json"], None),
        "trace_steps": steps,
        "timings": {"total_ms": row["duration_ms"] or 0, "nodes": nodes_ms},
        "error": error,
        "batch": None,
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
    }
    if row["batch_task_id"]:
        batch_row = db.connection().execute(
            "SELECT row_no FROM batch_rows WHERE row_id=?", (row["row_id"],)
        ).fetchone()
        snapshot["batch"] = {
            "batch_task_id": row["batch_task_id"],
            "row_id": row["row_id"],
            "row_no": batch_row["row_no"] if batch_row else None,
        }
    return snapshot


def summary_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "diagnosis_id": row["diagnosis_id"],
        "device_id": row["device_id"],
        "report_title": row["report_title"],
        "input_type": row["input_type"],
        "status": row["status"],
        "primary_type": row["primary_type"],
        "secondary_types": _loads(row["secondary_types_json"], []),
        "confidence": row["confidence"],
        "confidence_level": row["confidence_level"],
        "knowledge_status": row["knowledge_status"],
        "auto_review": bool(row["auto_review"]),
        "retry_count": row["retry_count"],
        "duration_ms": row["duration_ms"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "batch_task_id": row["batch_task_id"],
        "row_no": None,
    }
