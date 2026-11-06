"""批量任务端点（ARCH §5.4.7 / §5.5.6）。"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import PlainTextResponse, StreamingResponse

from app import batches, security
from app.db import utcnow
from app.errors import ApiError
from app.runtime.routing import TERMINAL_STATUSES
from app.schemas.api import (
    BatchCreateRequest,
    BatchCreateResponse,
    BatchPage,
    BatchRowDetail,
    BatchRowsPage,
    BatchTaskSummary,
    CancelResponse,
)
from app.schemas.events import SseEvent, SseEventType

router = APIRouter(tags=["batches"])


@router.post("/batches", response_model=BatchCreateResponse, status_code=202)
async def create_batch(
    body: BatchCreateRequest,
    request: Request,
    user: dict = Depends(security.current_user),
):
    state = request.app.state
    payload = batches.create_batch(state.db, state.settings, user["user_id"], body.model_dump())
    state.batch_runner.start(payload["batch_task_id"])
    return payload


@router.get("/batches", response_model=BatchPage)
def list_batches(
    request: Request,
    user: dict = Depends(security.current_user),
    status: str | None = None,
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    page: int = 1,
    page_size: int = 20,
):
    return batches.list_batches(
        request.app.state.db,
        user["user_id"],
        status=status,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


@router.get("/batches/{batch_task_id}", response_model=BatchTaskSummary)
def get_batch(batch_task_id: str, request: Request, user: dict = Depends(security.current_user)):
    return batches.get_batch(request.app.state.db, user["user_id"], batch_task_id)


@router.get("/batches/{batch_task_id}/rows", response_model=BatchRowsPage)
def list_rows(
    batch_task_id: str,
    request: Request,
    user: dict = Depends(security.current_user),
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    return batches.list_batch_rows(
        request.app.state.db,
        user["user_id"],
        batch_task_id,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/batches/{batch_task_id}/rows/{row_id}", response_model=BatchRowDetail)
def row_detail(
    batch_task_id: str, row_id: str, request: Request, user: dict = Depends(security.current_user)
):
    return batches.batch_row_detail(request.app.state.db, user["user_id"], batch_task_id, row_id)


@router.post("/batches/{batch_task_id}/cancel", response_model=CancelResponse)
def cancel_batch(
    batch_task_id: str,
    request: Request,
    response: Response,
    user: dict = Depends(security.current_user),
):
    status_code, payload = batches.cancel_batch(
        request.app.state.db, user["user_id"], batch_task_id
    )
    response.status_code = status_code
    return payload


@router.get("/batches/{batch_task_id}/export.csv")
def export_batch(batch_task_id: str, request: Request, user: dict = Depends(security.current_user)):
    content, filename = batches.export_csv(
        request.app.state.db, user["user_id"], batch_task_id
    )
    return PlainTextResponse(
        "\ufeff" + content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Cache-Control": "no-store",
        },
    )


@router.get("/batches/{batch_task_id}/events")
async def batch_events(
    batch_task_id: str,
    request: Request,
    user: dict = Depends(security.current_user),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    batches.get_batch_row(request.app.state.db, user["user_id"], batch_task_id)
    db = request.app.state.db
    settings = request.app.state.settings

    async def event_stream():
        yield "retry: 3000\n\n"
        conn = db.connection()
        max_seq = conn.execute(
            "SELECT COALESCE(MAX(seq),0) AS s FROM batch_events WHERE batch_task_id=?",
            (batch_task_id,),
        ).fetchone()["s"]
        cursor = 0
        if last_event_id:
            try:
                cursor = max(0, int(last_event_id))
            except ValueError:
                cursor = 0
        if cursor <= 0:
            snapshot = batches.summary_of(
                batches.get_batch_row(db, user["user_id"], batch_task_id)
            )
            yield SseEvent(
                seq=int(max_seq),
                stream_kind="batch",
                stream_id=batch_task_id,
                type=SseEventType.batch_snapshot,
                revision=None,
                occurred_at=utcnow(),
                payload=snapshot,
            ).render()
            cursor = int(max_seq)

        terminal = {"completed", "partially_failed", "failed", "cancelled", "timed_out"}
        current = conn.execute(
            "SELECT status FROM batch_tasks WHERE batch_task_id=?", (batch_task_id,)
        ).fetchone()
        if current is not None and current["status"] in terminal:
            # 终态重连：snapshot 后补发 batch_status 再关闭（ARCH §5.5.5 / §5.5.6）
            snapshot = batches.summary_of(
                batches.get_batch_row(db, user["user_id"], batch_task_id)
            )
            yield SseEvent(
                seq=cursor + 1,
                stream_kind="batch",
                stream_id=batch_task_id,
                type=SseEventType.batch_status,
                revision=None,
                occurred_at=utcnow(),
                payload={
                    "status": snapshot["status"],
                    "counts": snapshot["counts"],
                    "finished_at": snapshot["finished_at"],
                    "cancel_requested": snapshot["cancel_requested"],
                    "error_code": snapshot["error_code"],
                },
            ).render()
            return

        last_beat = time.monotonic()
        while True:
            rows = conn.execute(
                "SELECT * FROM batch_events WHERE batch_task_id=? AND seq>? ORDER BY seq",
                (batch_task_id, cursor),
            ).fetchall()
            for event_row in rows:
                cursor = int(event_row["seq"])
                yield SseEvent(
                    seq=cursor,
                    stream_kind="batch",
                    stream_id=batch_task_id,
                    type=SseEventType(event_row["type"]),
                    revision=None,
                    occurred_at=event_row["created_at"],
                    payload=json.loads(event_row["payload_json"]),
                ).render()
            task = conn.execute(
                "SELECT status FROM batch_tasks WHERE batch_task_id=?", (batch_task_id,)
            ).fetchone()
            if task is None:
                break
            if task["status"] in {"completed", "partially_failed", "failed", "cancelled", "timed_out"} and not rows:
                break
            if time.monotonic() - last_beat >= settings.heartbeat_seconds:
                last_beat = time.monotonic()
                yield SseEvent(
                    seq=None,
                    stream_kind="batch",
                    stream_id=batch_task_id,
                    type=SseEventType.heartbeat,
                    revision=None,
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
