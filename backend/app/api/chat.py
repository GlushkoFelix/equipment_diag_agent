"""对话入口（ARCH §5.4.5）：首条消息只抽取，confirm 后才创建诊断。"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse

from app import chat_extract, records, security, services, text_guard
from app.chat_extract import FEATURE_META
from app.db import new_id, transaction, utcnow
from app.errors import ApiError
from app.schemas.api import (
    ChatConfirmRequest,
    ChatConfirmResponse,
    ChatExtractionResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatSessionCreateResponse,
    ChatSessionDetail,
    ChatSupplementResponse,
)

router = APIRouter(tags=["chat"])


def _get_session(request: Request, user_id: int, session_id: str):
    row = request.app.state.db.connection().execute(
        "SELECT * FROM chat_sessions WHERE session_id=? AND user_id=?",
        (session_id, user_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "CHAT_SESSION_NOT_FOUND", "会话不存在或无权访问")
    return row


def _diagnosis_row(request: Request, user_id: int, diagnosis_id: str):
    return request.app.state.db.connection().execute(
        "SELECT * FROM diagnoses WHERE diagnosis_id=? AND user_id=?",
        (diagnosis_id, user_id),
    ).fetchone()


def _insert_message(request: Request, session_id: str, role: str, text: str, payload: dict | None) -> str:
    message_id = new_id("msg")
    db = request.app.state.db
    conn = db.connection()
    with transaction(conn):
        conn.execute(
            "INSERT INTO chat_messages (message_id, session_id, role, text, payload_json, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (
                message_id,
                session_id,
                role,
                text,
                json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                utcnow(),
            ),
        )
        conn.execute("UPDATE chat_sessions SET updated_at=? WHERE session_id=?", (utcnow(), session_id))
    return message_id


def _extraction_payload(features: dict[str, Any]) -> dict[str, Any]:
    missing = [
        {"field": key, "label": meta[0], "unit": meta[1], "example": meta[2], "reason": "MISSING"}
        for key, meta in chat_extract.FEATURE_META.items()
        if features.get(key) is None
    ]
    extracted = sum(1 for value in features.values() if value is not None)
    if extracted == 7:
        status, action = "ok", "confirm"
    elif extracted:
        status, action = "partial", "clarify"
    else:
        status, action = "failed", "use_form"
    return {
        "extraction_status": status,
        "features": features,
        "missing_fields": missing,
        "recommended_action": action,
    }


@router.post("/chat/sessions", response_model=ChatSessionCreateResponse, status_code=201)
def create_session(request: Request, user: dict = Depends(security.current_user)):
    session_id = new_id("cht")
    db = request.app.state.db
    created_at = utcnow()
    db.connection().execute(
        "INSERT INTO chat_sessions (session_id, user_id, status, created_at, updated_at)"
        " VALUES (?,?,'draft',?,?)",
        (session_id, user["user_id"], created_at, created_at),
    )
    return {"session_id": session_id, "status": "draft", "created_at": created_at}


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(session_id: str, request: Request, user: dict = Depends(security.current_user)):
    session = _get_session(request, user["user_id"], session_id)
    diagnosis_status = None
    if session["diagnosis_id"]:
        diagnosis = _diagnosis_row(request, user["user_id"], session["diagnosis_id"])
        if diagnosis is not None:
            records.expire_if_needed(request.app.state.db, diagnosis)
            diagnosis = _diagnosis_row(request, user["user_id"], session["diagnosis_id"])
            if diagnosis is not None:
                diagnosis_status = diagnosis["status"]
                if diagnosis_status != "waiting_human" and diagnosis_status != "running":
                    request.app.state.db.connection().execute(
                        "UPDATE chat_sessions SET status='terminal' WHERE session_id=? AND status='active'"
                        " AND EXISTS (SELECT 1 FROM diagnoses d WHERE d.diagnosis_id=chat_sessions.diagnosis_id"
                        " AND d.status IN ('succeeded','degraded','degraded_review','aborted','failed',"
                        "'failed_timeout','expired'))",
                        (session_id,),
                    )
    messages = [
        {
            "message_id": row["message_id"],
            "role": row["role"],
            "text": row["text"],
            "payload": json.loads(row["payload_json"]) if row["payload_json"] else None,
            "created_at": row["created_at"],
        }
        for row in request.app.state.db.connection()
        .execute(
            "SELECT * FROM chat_messages WHERE session_id=? ORDER BY created_at, message_id",
            (session_id,),
        )
        .fetchall()
    ]
    refreshed = _get_session(request, user["user_id"], session_id)
    return {
        "session_id": refreshed["session_id"],
        "status": refreshed["status"],
        "diagnosis_id": refreshed["diagnosis_id"],
        "diagnosis_status": diagnosis_status,
        "created_at": refreshed["created_at"],
        "updated_at": refreshed["updated_at"],
        "messages": messages,
    }


@router.post(
    "/chat/sessions/{session_id}/messages",
    response_model=ChatExtractionResponse | ChatSupplementResponse | ChatMessageResponse,
)
def post_message(
    session_id: str,
    body: ChatMessageRequest,
    request: Request,
    user: dict = Depends(security.current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    session = _get_session(request, user["user_id"], session_id)
    db = request.app.state.db
    hash_value = services.request_hash(session_id, body.text)
    text, _injection = text_guard.sanitize_text(
        body.text,
        scene="chat.message",
        user_id=user["user_id"],
        request_id=getattr(request.state, "request_id", None),
    )
    if idempotency_key:
        cached = services.idempotency_get(db, user["user_id"], "chat.messages", idempotency_key, hash_value)
        if cached:
            return JSONResponse(status_code=200, content=cached["body"])

    if session["status"] == "terminal":
        raise ApiError(409, "CHAT_SESSION_CLOSED", "会话已结束，请新建对话")
    if session["status"] == "active":
        diagnosis = _diagnosis_row(request, user["user_id"], session["diagnosis_id"])
        if diagnosis is None:
            raise ApiError(409, "CHAT_SESSION_CLOSED", "会话绑定的诊断不存在")
        if records.expire_if_needed(db, diagnosis):
            raise ApiError(409, "CHAT_SESSION_CLOSED", "会话已过期，请新建对话")
        if diagnosis["status"] == "running":
            raise ApiError(409, "DIAGNOSIS_STATE_CONFLICT", "诊断执行中，暂不接受新消息")
        if diagnosis["status"] == "waiting_human" and diagnosis["interrupt_type"] == "review":
            raise ApiError(409, "CHAT_DECISION_REQUIRED", "请使用确认面板提交决策")
        if diagnosis["status"] != "waiting_human":
            raise ApiError(409, "CHAT_SESSION_CLOSED", "会话已结束，请新建对话")
        interrupt = json.loads(diagnosis["interrupt_payload_json"] or "{}")
        parsed = chat_extract.extract(text, diagnosis["device_id"])
        merged = {key: None for key in chat_extract.FEATURE_META}
        merged.update(interrupt.get("partial_features") or {})
        merged["device_id"] = diagnosis["device_id"]
        merged.update({k: v for k, v in parsed["features"].items() if v is not None})
        extraction = _extraction_payload(merged)
        _insert_message(request, session_id, "user", text, None)
        agent_text = "已抽取补充值，请确认后继续"
        agent_message_id = _insert_message(
            request,
            session_id,
            "agent",
            agent_text,
            {"type": "supplement", "extraction": extraction},
        )
        response = {
            "session_id": session_id,
            "message_id": agent_message_id,
            "diagnosis_id": diagnosis["diagnosis_id"],
            "diagnosis_status": diagnosis["status"],
            "version": diagnosis["version"],
            "agent_text": agent_text,
            "interrupt": {
                "type": diagnosis["interrupt_type"],
                "version": diagnosis["version"],
                "review_round": diagnosis["review_round"],
                "expires_at": diagnosis["interrupt_expires_at"],
                "payload": interrupt,
            },
            "extraction": extraction,
            "stream_url": None,
        }
        if idempotency_key:
            services.idempotency_put(
                db, user["user_id"], "chat.messages", idempotency_key, hash_value, 200, response
            )
        return response

    # draft：首条消息只抽取，不创建诊断、不建流
    parsed = chat_extract.extract(text, None)
    extraction = {
        "extraction_status": parsed["extraction_status"],
        "features": parsed["features"],
        "missing_fields": parsed["missing_fields"],
        "recommended_action": parsed["recommended_action"],
    }
    _insert_message(request, session_id, "user", text, None)
    agent_text = parsed["message"]
    agent_message_id = _insert_message(
        request,
        session_id,
        "agent",
        agent_text,
        {"type": "extraction", "extraction": extraction},
    )
    response = {
        "session_id": session_id,
        "message_id": agent_message_id,
        "diagnosis_id": None,
        "diagnosis_status": None,
        "version": None,
        "agent_text": agent_text,
        "interrupt": None,
        "extraction": extraction,
        "stream_url": None,
    }
    if idempotency_key:
        services.idempotency_put(db, user["user_id"], "chat.messages", idempotency_key, hash_value, 200, response)
    return response


def _record_user_correction(
    db,
    session_id: str,
    diagnosis_id: str,
    revision: int,
    features: dict[str, Any],
) -> None:
    """AC-IN-14：确认卡字段与会话抽取结果不一致时写 user_correct，不改 diagnosis_revision。"""
    row = db.connection().execute(
        "SELECT payload_json FROM chat_messages WHERE session_id=? AND role='agent'"
        " AND payload_json IS NOT NULL ORDER BY created_at DESC, rowid DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if row is None:
        return
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, ValueError):
        return
    original = ((payload or {}).get("extraction") or {}).get("features") or {}
    changed: list[str] = []
    for field in FEATURE_META:
        after = features.get(field)
        if after is None:
            continue
        before = original.get(field)
        if before is None:
            changed.append(field)
            continue
        if field == "device_id":
            if str(before).strip() != str(after).strip():
                changed.append(field)
            continue
        try:
            if abs(float(before) - float(after)) > 1e-9:
                changed.append(field)
        except (TypeError, ValueError):
            if str(before) != str(after):
                changed.append(field)
    if not changed:
        return
    records.append_step(
        db,
        diagnosis_id,
        revision,
        "intake",
        "user_correct",
        summary="用户修正字段：" + "、".join(changed),
    )


def _bind_existing_diagnosis(request: Request, user_id: int, session_id: str, diagnosis_id: str) -> None:
    conn = request.app.state.db.connection()
    try:
        with transaction(conn):
            bound = conn.execute(
                "UPDATE chat_sessions SET diagnosis_id=?, status='active', updated_at=?"
                " WHERE session_id=? AND user_id=? AND status='draft' AND diagnosis_id IS NULL",
                (diagnosis_id, utcnow(), session_id, user_id),
            ).rowcount
            if bound != 1:
                raise ApiError(409, "CHAT_SESSION_ALREADY_ACTIVE", "会话已绑定诊断，不能再次确认")
    except Exception as exc:
        if isinstance(exc, ApiError):
            raise
        if "UNIQUE" in str(exc) or "chat_sessions" in str(exc):
            raise ApiError(409, "CHAT_SESSION_ALREADY_ACTIVE", "该诊断已被其他会话绑定") from exc
        raise


@router.post(
    "/chat/sessions/{session_id}/confirm",
    response_model=ChatConfirmResponse,
    status_code=202,
)
async def confirm(
    session_id: str,
    body: ChatConfirmRequest,
    request: Request,
    response: Response,
    user: dict = Depends(security.current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    session = _get_session(request, user["user_id"], session_id)
    features = body.features
    key = idempotency_key or (f"msg:{body.message_id}" if body.message_id else None)
    hash_value = services.request_hash(session_id, body.message_id, body.features, body.text)
    db = request.app.state.db
    # 幂等重放优先于状态校验：同一 message_id / Idempotency-Key 必须返回首次结果 200（TBD-K）
    if key:
        cached = services.idempotency_get(db, user["user_id"], "chat.confirm", key, hash_value)
        if cached:
            return JSONResponse(status_code=200, content=cached["body"])

    # P2-N1：必须同时校验 status='draft' 且 diagnosis_id IS NULL
    if session["status"] == "terminal":
        raise ApiError(409, "CHAT_SESSION_CLOSED", "会话已结束，请新建对话")
    if session["status"] == "active" or session["diagnosis_id"] is not None:
        raise ApiError(409, "CHAT_SESSION_ALREADY_ACTIVE", "会话已绑定诊断，不能再次确认")

    if not isinstance(features, dict) or not features:
        raise ApiError(422, "VALIDATION_FAILED", "features 必填")
    null_keys = [key for key, value in features.items() if value is None]
    if null_keys:
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "features 不接受 null 值，请剔除空字段",
            details={"fields": [{"field": key, "reason": "NULL_NOT_ALLOWED"} for key in null_keys]},
        )
    device_id = features.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        raise ApiError(422, "DEVICE_ID_INVALID", "设备标识必填")

    text, _injection = text_guard.sanitize_text(
        body.text or "",
        scene="chat.confirm",
        user_id=user["user_id"],
        request_id=getattr(request.state, "request_id", None),
    )
    created = services.create_diagnosis(
        db,
        request.app.state.settings,
        user["user_id"],
        "chat",
        {**features, "text": text},
        input_summary={"text_excerpt": text[:120]},
        bind_session_id=session_id,
    )
    if created["deduplicated"]:
        _bind_existing_diagnosis(request, user["user_id"], session_id, created["diagnosis_id"])
        status_code = 200
    else:
        request.app.state.runner.start(created["diagnosis_id"], created["state"])
        status_code = 202
        _record_user_correction(db, session_id, created["diagnosis_id"], int(created["row"]["diagnosis_revision"]), features)

    row = created["row"]
    payload = {
        "session_id": session_id,
        "diagnosis_id": row["diagnosis_id"],
        "diagnosis_status": row["status"],
        "version": row["version"],
        "deduplicated": created["deduplicated"],
        "stream_url": f"/api/v1/diagnoses/{row['diagnosis_id']}/events",
    }
    if key:
        services.idempotency_put(db, user["user_id"], "chat.confirm", key, hash_value, status_code, payload)
    response.status_code = status_code
    return payload
