"""诊断创建（RT-17 原子去重）与共享服务。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from app import features as features_domain
from app import records
from app import text_guard
from app.config import Settings
from app.db import Database, new_id, transaction, utcnow
from app.errors import ApiError

FIELD_CODE_TO_HTTP = {
    "DEVICE_ID_INVALID": (422, "DEVICE_ID_INVALID"),
    "FEATURE_OUT_OF_RANGE": (422, "FEATURE_OUT_OF_RANGE"),
    "FIELD_INVALID": (422, "VALIDATION_FAILED"),
    "VALIDATION_FAILED": (422, "VALIDATION_FAILED"),
    "MACHINE_STOPPED": (422, "MACHINE_STOPPED"),
    "DATA_CONTRADICTION": (422, "DATA_CONTRADICTION"),
}


class SessionBindError(Exception):
    pass


def ensure_llm_configured(settings: Settings) -> None:
    if settings.llm_mode == "deepseek" and not settings.deepseek_api_key:
        raise ApiError(503, "LLM_NOT_CONFIGURED", "未配置 DeepSeek Key，无法发起诊断")


def normalize_or_fail(input_type: str, raw_input: dict[str, Any], user_id: int):
    payload = dict(raw_input)
    payload["_user_id"] = user_id
    result = features_domain.normalize_input(input_type, payload)
    if not result.ok:
        status, code = FIELD_CODE_TO_HTTP.get(result.error_code or "VALIDATION_FAILED", (422, "VALIDATION_FAILED"))
        raise ApiError(
            status,
            code,
            "输入字段校验失败",
            details={"fields": result.fields or result.missing_fields},
        )
    return result


def create_diagnosis(
    db: Database,
    settings: Settings,
    user_id: int,
    input_type: str,
    raw_input: dict[str, Any],
    *,
    upload_id: str | None = None,
    input_summary: dict[str, Any] | None = None,
    bind_session_id: str | None = None,
) -> dict[str, Any]:
    """创建单条诊断；命中 RT-17 返回已有记录（deduplicated=true）。"""
    ensure_llm_configured(settings)
    raw_input = dict(raw_input)
    text = raw_input.get("text")
    if isinstance(text, str) and text:
        cleaned, _hits = text_guard.sanitize_text(text, scene="diagnosis.create", user_id=user_id)
        raw_input["text"] = cleaned
    result = normalize_or_fail(input_type, raw_input, user_id)
    fingerprint = result.input_fingerprint
    active_key = f"{user_id}:{fingerprint}" if fingerprint else None

    conn = db.connection()
    # 过期懒判定：同指纹的 waiting_human 若已过期先置 expired
    if fingerprint:
        stale = conn.execute(
            "SELECT * FROM diagnoses WHERE user_id=? AND active_fingerprint_key=? AND status='waiting_human'",
            (user_id, active_key),
        ).fetchall()
        for row in stale:
            records.expire_if_needed(db, row)

    summary = dict(input_summary or {})
    if isinstance(text, str) and text:
        summary["text_excerpt"] = raw_input["text"][:120]
    summary["features"] = {
        "normalized": result.normalized,
        "derived": result.derived,
        "completeness": result.completeness,
        "missing_fields": [item["field"] for item in result.missing_fields],
        "assumptions": result.assumptions,
        "data_quality_flags": result.data_quality_flags,
    }
    diagnosis_id = new_id("dx")
    now = utcnow()
    try:
        with transaction(conn):
            conn.execute(
                "INSERT INTO diagnoses (diagnosis_id, user_id, device_id, input_type, input_summary_json,"
                " status, input_fingerprint, fingerprint_scope, active_fingerprint_key, execution_mode,"
                " upload_id, started_at, created_at, version)"
                " VALUES (?,?,?,?,?,'running',?,?,?,'single',?,?,?,1)",
                (
                    diagnosis_id,
                    user_id,
                    result.normalized["device_id"],
                    input_type,
                    json.dumps(summary, ensure_ascii=False),
                    fingerprint,
                    "dedupe" if fingerprint else None,
                    active_key,
                    upload_id,
                    now,
                    now,
                ),
            )
            if bind_session_id:
                bound = conn.execute(
                    "UPDATE chat_sessions SET diagnosis_id=?, status='active', updated_at=?"
                    " WHERE session_id=? AND user_id=? AND status='draft' AND diagnosis_id IS NULL",
                    (diagnosis_id, now, bind_session_id, user_id),
                ).rowcount
                if bound != 1:
                    raise SessionBindError("会话不可绑定诊断")
    except sqlite3.IntegrityError as exc:
        message = str(exc)
        if bind_session_id and ("chat_sessions" in message or "UNIQUE" in message and "diagnosis_id" in message):
            raise SessionBindError("会话不可绑定诊断") from exc
        existing = records.find_active_by_fingerprint(conn, user_id, fingerprint or "")
        if existing is not None:
            return {
                "diagnosis_id": existing["diagnosis_id"],
                "deduplicated": True,
                "row": existing,
                "state": None,
            }
        # 并发终态清理后重试一次（ARCH §4.1.3）
        try:
            with transaction(conn):
                conn.execute(
                    "INSERT INTO diagnoses (diagnosis_id, user_id, device_id, input_type, input_summary_json,"
                    " status, input_fingerprint, fingerprint_scope, active_fingerprint_key, execution_mode,"
                    " upload_id, started_at, created_at, version)"
                    " VALUES (?,?,?,?,?,'running',?,?,?,'single',?,?,?,1)",
                    (
                        diagnosis_id,
                        user_id,
                        result.normalized["device_id"],
                        input_type,
                        json.dumps(summary, ensure_ascii=False),
                        fingerprint,
                        "dedupe" if fingerprint else None,
                        active_key,
                        upload_id,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as retry_exc:
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "并发创建冲突，请重试或查看诊断列表") from retry_exc

    row = records.get_for_user(db, user_id, diagnosis_id)
    return {
        "diagnosis_id": diagnosis_id,
        "deduplicated": False,
        "row": row,
        "state": build_initial_state(settings, row, result, raw_input),
    }


def build_initial_state(
    settings: Settings,
    row: sqlite3.Row,
    result: features_domain.NormalizeResult,
    raw_input: dict[str, Any],
    *,
    execution_mode: str = "single",
    batch_task_id: str | None = None,
    row_id: str | None = None,
):
    from app.runtime.state import DiagnosisState

    started = utcnow()
    deadline = (datetime.now(timezone.utc) + timedelta(seconds=settings.global_timeout_seconds))
    state: DiagnosisState = {
        "request_id": new_id("req"),
        "thread_id": row["diagnosis_id"],
        "version": 1,
        "user_id": row["user_id"],
        "input_type": row["input_type"],
        "raw_input": dict(raw_input),
        "input_fingerprint": row["input_fingerprint"],
        "fingerprint_scope": row["fingerprint_scope"],
        "device_id": row["device_id"],
        "normalized_features": result.normalized,
        "derived_features": result.derived,
        "feature_completeness": result.completeness,
        "missing_fields": result.missing_fields,
        "assumptions": result.assumptions,
        "data_quality_flags": result.data_quality_flags,
        "retrieval": {},
        "diagnosis": {},
        "retry_count": 0,
        "review_round": 0,
        "report_retry_count": 0,
        "diagnosis_revision": 1,
        "auto_review": False,
        "interrupt_type": None,
        "interrupt_payload": None,
        "interrupt_expires_at": None,
        "human_review": None,
        "report_md": None,
        "report_title": None,
        "report_elements_check": None,
        "report_meta": None,
        "status": "running",
        "errors": [],
        "trace_steps": [],
        "timings": {},
        "execution_mode": execution_mode,
        "execution_started_at": started,
        "deadline_at": deadline.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "batch_task_id": batch_task_id,
        "row_id": row_id,
        "intake_draft": None,
        "hard_error": None,
        "retry_requested": False,
    }
    return state


def insert_diagnosis_from_result(
    db: Database,
    settings: Settings,
    user_id: int,
    *,
    input_type: str,
    result: features_domain.NormalizeResult,
    raw_input: dict[str, Any],
    execution_mode: str,
    input_summary: dict[str, Any] | None = None,
    batch_task_id: str | None = None,
    row_id: str | None = None,
    upload_id: str | None = None,
    fingerprint_scope: str | None = None,
) -> tuple[str, Any]:
    """批量/评测诊断创建：不参与 RT-17（不写 active_fingerprint_key）。

    批量仍计算并保存 input_fingerprint（fingerprint_scope='trace'）供追溯（ARCH §4.1.4）。
    """
    fingerprint = None
    if fingerprint_scope == "trace":
        fingerprint = features_domain.compute_fingerprint(
            user_id, input_type, result.normalized, features_domain.normalize_text(raw_input.get("text"))
        )
    summary = dict(input_summary or {})
    summary["features"] = {
        "normalized": result.normalized,
        "derived": result.derived,
        "completeness": result.completeness,
        "missing_fields": [item["field"] for item in result.missing_fields],
        "assumptions": result.assumptions,
        "data_quality_flags": result.data_quality_flags,
    }
    diagnosis_id = new_id("dx")
    now = utcnow()
    conn = db.connection()
    with transaction(conn):
        conn.execute(
            "INSERT INTO diagnoses (diagnosis_id, user_id, device_id, input_type, input_summary_json,"
            " status, input_fingerprint, fingerprint_scope, active_fingerprint_key, execution_mode,"
            " batch_task_id, row_id, upload_id, started_at, created_at, version)"
            " VALUES (?,?,?,?,?,'running',?,?,NULL,?,?,?,?,?,?,1)",
            (
                diagnosis_id,
                user_id,
                result.normalized["device_id"],
                input_type,
                json.dumps(summary, ensure_ascii=False),
                fingerprint,
                fingerprint_scope,
                execution_mode,
                batch_task_id,
                row_id,
                upload_id,
                now,
                now,
            ),
        )
    row = records.get_for_user(db, user_id, diagnosis_id)
    state = build_initial_state(
        settings,
        row,
        result,
        raw_input,
        execution_mode=execution_mode,
        batch_task_id=batch_task_id,
        row_id=row_id,
    )
    return diagnosis_id, state


# ---------- 幂等键（10 分钟） ----------
def idempotency_get(db: Database, user_id: int, endpoint: str, key: str, request_hash: str) -> dict[str, Any] | None:
    conn = db.connection()
    row = conn.execute(
        "SELECT * FROM idempotency_keys WHERE user_id=? AND endpoint=? AND key=?",
        (user_id, endpoint, key),
    ).fetchone()
    if row is None:
        return None
    if row["expires_at"] <= utcnow():
        conn.execute(
            "DELETE FROM idempotency_keys WHERE user_id=? AND endpoint=? AND key=?",
            (user_id, endpoint, key),
        )
        return None
    if row["request_hash"] != request_hash:
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "同一 Idempotency-Key 的请求体不一致")
    return {"status_code": row["status_code"], "body": json.loads(row["response_json"])}


def idempotency_put(
    db: Database,
    user_id: int,
    endpoint: str,
    key: str,
    request_hash: str,
    status_code: int,
    body: dict[str, Any],
) -> None:
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    db.connection().execute(
        "INSERT OR REPLACE INTO idempotency_keys"
        " (user_id, endpoint, key, request_hash, response_json, status_code, created_at, expires_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (
            user_id,
            endpoint,
            key,
            request_hash,
            json.dumps(body, ensure_ascii=False),
            status_code,
            utcnow(),
            expires.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        ),
    )


def request_hash(*parts: Any) -> str:
    canonical = json.dumps(parts, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
