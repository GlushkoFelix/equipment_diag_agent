"""诊断端点：创建、列表、快照、SSE、恢复、报告下载、删除（ARCH §5.4.6 / §5.5）。"""

from __future__ import annotations

import asyncio
import json
import math
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import PlainTextResponse, StreamingResponse

from app import features as features_domain
from app import records, security, services, uploads
from app.db import utcnow
from app.errors import ApiError
from app.runtime.routing import TERMINAL_STATUSES, is_terminal
from app.schemas.api import (
    DiagnosisCreateRequest,
    DiagnosisCreateResponse,
    DiagnosisListResponse,
    DiagnosisSnapshot,
    DiagnosisSummary,
    ResumeRequest,
)
from app.schemas.events import SseEvent, SseEventType

router = APIRouter(tags=["diagnoses"])

VALID_STATUSES = {
    "running",
    "waiting_human",
    "succeeded",
    "degraded",
    "degraded_review",
    "aborted",
    "failed",
    "failed_timeout",
    "expired",
}
VALID_PRIMARY = {"正常", "TWF", "HDF", "PWF", "OSF", "RNF", "未覆盖"}


def _row_or_404(request: Request, user_id: int, diagnosis_id: str):
    row = records.get_for_user(request.app.state.db, user_id, diagnosis_id)
    if records.expire_if_needed(request.app.state.db, row):
        row = records.get_for_user(request.app.state.db, user_id, diagnosis_id)
    return row


def _snapshot(request: Request, row) -> dict[str, Any]:
    return records.build_snapshot(request.app.state.db, row)


@router.post("/diagnoses", response_model=DiagnosisCreateResponse, status_code=202)
async def create_diagnosis(
    body: DiagnosisCreateRequest,
    request: Request,
    response: Response,
    user: dict = Depends(security.current_user),
):
    input_type = body.input_type
    summary: dict[str, Any] = {}
    upload_id: str | None = None
    if input_type == "csv_single":
        payload, summary = uploads.read_csv_row(
            request.app.state.db,
            user["user_id"],
            body.upload_id,
            body.row_no,
            body.mapping,
            body.default_device_id,
        )
        upload_id = body.upload_id
        summary["text_excerpt"] = None
    elif input_type == "form":
        payload = body.model_dump(exclude={"input_type"})
        summary["text_excerpt"] = None
    else:
        payload = body.model_dump(exclude={"input_type"})
        summary["text_excerpt"] = (body.text or "")[:120]

    created = services.create_diagnosis(
        request.app.state.db,
        request.app.state.settings,
        user["user_id"],
        input_type,
        payload,
        upload_id=upload_id,
        input_summary=summary,
    )
    row = created["row"]
    if not created["deduplicated"]:
        request.app.state.runner.start(created["diagnosis_id"], created["state"])
        response.headers["Location"] = f"/api/v1/diagnoses/{created['diagnosis_id']}"
        response.status_code = 202
    else:
        response.status_code = 200
    return {
        "diagnosis_id": row["diagnosis_id"],
        "status": row["status"],
        "input_type": row["input_type"],
        "version": row["version"],
        "diagnosis_revision": row["diagnosis_revision"],
        "deduplicated": created["deduplicated"],
        "created_at": row["created_at"],
        "stream_url": f"/api/v1/diagnoses/{row['diagnosis_id']}/events",
        "snapshot_url": f"/api/v1/diagnoses/{row['diagnosis_id']}",
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/diagnoses", response_model=DiagnosisListResponse)
def list_diagnoses(
    request: Request,
    user: dict = Depends(security.current_user),
    primary_type: str | None = None,
    confidence_level: str | None = None,
    status: str | None = None,
    input_type: str | None = None,
    batch_task_id: str | None = None,
    keyword: str | None = None,
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    page: int = 1,
    page_size: int = 20,
):
    settings = request.app.state.settings
    if page < 1:
        raise ApiError(422, "VALIDATION_FAILED", "page 必须 ≥1")
    if not (1 <= page_size <= settings.page_size_max):
        raise ApiError(422, "VALIDATION_FAILED", f"page_size 必须在 1–{settings.page_size_max}")
    if date_from and date_to and date_to < date_from:
        raise ApiError(422, "VALIDATION_FAILED", "to 必须大于等于 from")
    if primary_type and primary_type not in VALID_PRIMARY:
        raise ApiError(422, "VALIDATION_FAILED", "primary_type 非法")
    if confidence_level and confidence_level not in {"high", "medium", "low"}:
        raise ApiError(422, "VALIDATION_FAILED", "confidence_level 非法")
    clauses = ["user_id = ?"]
    values: list[Any] = [user["user_id"]]
    if primary_type:
        clauses.append("primary_type = ?")
        values.append(primary_type)
    if confidence_level:
        clauses.append("confidence_level = ?")
        values.append(confidence_level)
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if any(s not in VALID_STATUSES for s in statuses):
            raise ApiError(422, "VALIDATION_FAILED", "status 含非法值")
        if statuses:
            clauses.append(f"status IN ({','.join('?' for _ in statuses)})")
            values.extend(statuses)
    if input_type:
        clauses.append("input_type = ?")
        values.append(input_type)
    if batch_task_id:
        clauses.append("batch_task_id = ?")
        values.append(batch_task_id)
    if keyword:
        escaped = _escape_like(keyword)
        clauses.append("(device_id LIKE ? ESCAPE '\\' OR report_title LIKE ? ESCAPE '\\')")
        values.extend([f"%{escaped}%", f"%{escaped}%"])
    if date_from:
        clauses.append("started_at >= ?")
        values.append(date_from)
    if date_to:
        clauses.append("started_at <= ?")
        values.append(date_to)
    where = " AND ".join(clauses)
    conn = request.app.state.db.connection()
    total = conn.execute(f"SELECT COUNT(*) AS c FROM diagnoses WHERE {where}", values).fetchone()["c"]
    rows = conn.execute(
        f"SELECT * FROM diagnoses WHERE {where} ORDER BY started_at DESC, diagnosis_id DESC LIMIT ? OFFSET ?",
        [*values, page_size, (page - 1) * page_size],
    ).fetchall()
    return {
        "items": [records.summary_row(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": math.ceil(total / page_size) if total else 0,
    }


@router.get("/diagnoses/{diagnosis_id}", response_model=DiagnosisSnapshot)
def get_diagnosis(diagnosis_id: str, request: Request, user: dict = Depends(security.current_user)):
    row = _row_or_404(request, user["user_id"], diagnosis_id)
    return _snapshot(request, row)


@router.get("/diagnoses/{diagnosis_id}/events")
async def diagnosis_events(
    diagnosis_id: str,
    request: Request,
    user: dict = Depends(security.current_user),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    row = _row_or_404(request, user["user_id"], diagnosis_id)
    db = request.app.state.db
    settings = request.app.state.settings

    async def event_stream():
        yield "retry: 3000\n\n"
        conn = db.connection()
        max_seq = conn.execute(
            "SELECT COALESCE(MAX(seq),0) AS s FROM diagnosis_events WHERE diagnosis_id=?",
            (diagnosis_id,),
        ).fetchone()["s"]
        revision = row["diagnosis_revision"]
        cursor = int(max_seq)
        replay = None
        if last_event_id:
            try:
                replay = int(last_event_id)
            except ValueError:
                replay = None
        if replay is None or replay <= 0:
            current = records.get_for_user(db, user["user_id"], diagnosis_id)
            snapshot = SseEvent(
                seq=int(max_seq),
                stream_kind="diagnosis",
                stream_id=diagnosis_id,
                type=SseEventType.snapshot,
                revision=current["diagnosis_revision"],
                occurred_at=utcnow(),
                payload=records.build_snapshot(db, current),
            )
            yield snapshot.render()
        else:
            cursor = replay
            rows = conn.execute(
                "SELECT * FROM diagnosis_events WHERE diagnosis_id=? AND seq>? ORDER BY seq",
                (diagnosis_id, cursor),
            ).fetchall()
            for event_row in rows:
                cursor = int(event_row["seq"])
                yield _render_event(diagnosis_id, event_row)

        current = conn.execute(
            "SELECT status, version, diagnosis_revision FROM diagnoses WHERE diagnosis_id=?",
            (diagnosis_id,),
        ).fetchone()
        if current is not None and is_terminal(current["status"]):
            # 终态重连：snapshot + 终态 status 后关闭（ARCH §5.5.5）
            yield SseEvent(
                seq=cursor + 1,
                stream_kind="diagnosis",
                stream_id=diagnosis_id,
                type=SseEventType.status,
                revision=current["diagnosis_revision"],
                occurred_at=utcnow(),
                payload={
                    "from": "running",
                    "to": current["status"],
                    "reason": "reconnect",
                    "version": current["version"],
                },
            ).render()
            return

        last_beat = time.monotonic()
        while True:
            rows = conn.execute(
                "SELECT * FROM diagnosis_events WHERE diagnosis_id=? AND seq>? ORDER BY seq",
                (diagnosis_id, cursor),
            ).fetchall()
            for event_row in rows:
                cursor = int(event_row["seq"])
                yield _render_event(diagnosis_id, event_row)
            current = conn.execute(
                "SELECT status, diagnosis_revision FROM diagnoses WHERE diagnosis_id=?",
                (diagnosis_id,),
            ).fetchone()
            if current is None:
                break
            if is_terminal(current["status"]) and not rows:
                break
            if time.monotonic() - last_beat >= settings.heartbeat_seconds:
                last_beat = time.monotonic()
                yield SseEvent(
                    seq=None,
                    stream_kind="diagnosis",
                    stream_id=diagnosis_id,
                    type=SseEventType.heartbeat,
                    revision=current["diagnosis_revision"],
                    occurred_at=utcnow(),
                    payload={"server_time": utcnow()},
                ).render()
            await asyncio.sleep(settings.sse_poll_seconds)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _render_event(diagnosis_id: str, event_row) -> str:
    return SseEvent(
        seq=int(event_row["seq"]),
        stream_kind="diagnosis",
        stream_id=diagnosis_id,
        type=SseEventType(event_row["type"]),
        revision=event_row["revision"],
        occurred_at=event_row["created_at"],
        payload=json.loads(event_row["payload_json"]),
    ).render()


@router.post("/diagnoses/{diagnosis_id}/resume", response_model=DiagnosisSnapshot)
async def resume(
    diagnosis_id: str,
    body: ResumeRequest,
    request: Request,
    user: dict = Depends(security.current_user),
):
    row = _row_or_404(request, user["user_id"], diagnosis_id)
    if row["status"] == "expired":
        raise ApiError(409, "DIAGNOSIS_EXPIRED", "中断已过期，请重新发起诊断")
    if int(body.version) != int(row["version"]):
        # AC-DG-16：并发 resume 的失败方（版本已被胜出方递增）必须得到 VERSION_CONFLICT。
        raise ApiError(409, "VERSION_CONFLICT", "状态已变更，请刷新")
    if row["status"] != "waiting_human":
        raise ApiError(409, "DIAGNOSIS_STATE_CONFLICT", "当前状态不允许恢复")
    if body.decision == "supplement" and not body.supplement:
        raise ApiError(422, "VALIDATION_FAILED", "补充决策至少需要一个字段")
    if body.decision == "supplement" and row["interrupt_type"] == "review" and int(row["review_round"]) >= 2:
        raise ApiError(409, "DECISION_NOT_ALLOWED", "第 2 轮复核不允许补充")
    if body.decision in ("confirm", "abort") and row["interrupt_type"] == "clarification" and body.decision == "confirm":
        raise ApiError(409, "DECISION_NOT_ALLOWED", "澄清中断只接受 supplement 或 abort")
    if body.decision == "supplement":
        interrupt = json.loads(row["interrupt_payload_json"] or "{}")
        summary = json.loads(row["input_summary_json"] or "{}")
        # review 中断不带 partial_features，回落到最近一次 parse_input 的规范化特征
        merged = dict((summary.get("features") or {}).get("normalized") or {})
        merged.update(interrupt.get("partial_features") or {})
        merged.update({k: v for k, v in body.supplement.items() if v is not None})
        merged["device_id"] = row["device_id"]
        merged["text"] = summary.get("text_excerpt") or ""
        normalized = features_domain.normalize_input(row["input_type"], merged)
        if not normalized.ok:
            raise ApiError(
                422,
                "VALIDATION_FAILED",
                "补充字段校验失败",
                details={"fields": normalized.fields or normalized.missing_fields},
            )

    new_version = records.set_running(
        request.app.state.db, diagnosis_id, body.decision, expected_version=int(body.version)
    )
    if new_version is None:
        raise ApiError(409, "VERSION_CONFLICT", "状态已变更，请刷新")
    records.append_event(
        request.app.state.db,
        diagnosis_id,
        "status",
        {"from": "waiting_human", "to": "running", "reason": "resume", "version": new_version},
        int(row["diagnosis_revision"]),
    )
    records.append_step(
        request.app.state.db,
        diagnosis_id,
        int(row["diagnosis_revision"]),
        "supervisor",
        "resume",
        summary=f"用户决策 {body.decision}",
    )
    await request.app.state.runner.resume(
        diagnosis_id, {"decision": body.decision, "supplement": body.supplement or {}}
    )
    row = records.get_for_user(request.app.state.db, user["user_id"], diagnosis_id)
    return _snapshot(request, row)


@router.get("/diagnoses/{diagnosis_id}/report.md")
def download_report(diagnosis_id: str, request: Request, user: dict = Depends(security.current_user)):
    row = _row_or_404(request, user["user_id"], diagnosis_id)
    if not row["report_md"]:
        raise ApiError(409, "REPORT_NOT_AVAILABLE", "当前诊断没有可导出的报告")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    filename = f"诊断报告_{row['device_id']}_{stamp}.md"
    return PlainTextResponse(
        row["report_md"],
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


@router.delete("/diagnoses/{diagnosis_id}", status_code=204)
def delete_diagnosis(diagnosis_id: str, request: Request, user: dict = Depends(security.current_user)):
    row = _row_or_404(request, user["user_id"], diagnosis_id)
    if row["status"] not in TERMINAL_STATUSES:
        raise ApiError(409, "DIAGNOSIS_STATE_CONFLICT", "仅终态诊断可删除")
    if row["execution_mode"] == "batch" or row["input_type"] == "csv_batch":
        raise ApiError(409, "DIAGNOSIS_STATE_CONFLICT", "批量来源诊断不允许单独删除")
    conn = request.app.state.db.connection()
    conn.execute("DELETE FROM diagnoses WHERE diagnosis_id=? AND user_id=?", (diagnosis_id, user["user_id"]))
    return Response(status_code=204)
