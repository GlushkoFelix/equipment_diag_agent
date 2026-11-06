"""对话入口契约：抽取卡、confirm 200/202/409/422、幂等重放、P2-N1 绑定校验。"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app import records
from app.db import new_id, utcnow
from tests.conftest import wait_for_status

PREFIX = "/api/v1"

FULL_FEATURES = {
    "device_id": "3号机",
    "product_type": "M",
    "air_temp_k": 298.1,
    "process_temp_k": 305.3,
    "rotational_speed_rpm": 1250,
    "torque_nm": 30,
    "tool_wear_min": 100,
}
# 温差倒挂样本：稳定进入 review，便于验证绑定与 RT-17
REVIEW_FEATURES = {
    "device_id": "2号机",
    "product_type": "M",
    "air_temp_k": 308.6,
    "process_temp_k": 298.1,
    "rotational_speed_rpm": 1250,
    "torque_nm": 30,
    "tool_wear_min": 100,
}


def new_session(client: TestClient) -> str:
    response = client.post(f"{PREFIX}/chat/sessions")
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


def test_draft_message_returns_extraction_card_without_diagnosis(client: TestClient):
    session_id = new_session(client)
    before = client.get(f"{PREFIX}/diagnoses").json()["total"]
    response = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/messages",
        json={"text": "3号机异响，扭矩 55，有点烫"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["diagnosis_id"] is None
    assert body["version"] is None
    assert body["interrupt"] is None
    assert body["stream_url"] is None
    assert body["extraction"]["extraction_status"] == "partial"
    assert body["extraction"]["features"]["device_id"] == "3号机"
    assert body["extraction"]["features"]["torque_nm"] == 55
    assert body["extraction"]["recommended_action"] == "clarify"
    assert client.get(f"{PREFIX}/diagnoses").json()["total"] == before
    detail = client.get(f"{PREFIX}/chat/sessions/{session_id}").json()
    assert detail["status"] == "draft"
    assert len(detail["messages"]) == 2


def test_confirm_creates_diagnosis_and_then_conflicts(client: TestClient):
    session_id = new_session(client)
    card = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/messages",
        json={"text": "3号机 M 型 空气温度 298.1K"},
    ).json()
    confirm = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/confirm",
        json={"message_id": card["message_id"], "text": "3号机 M 型", "features": FULL_FEATURES},
    )
    assert confirm.status_code == 202, confirm.text
    payload = confirm.json()
    assert payload["deduplicated"] is False
    assert payload["stream_url"].endswith("/events")
    assert payload["session_id"] == session_id

    detail = client.get(f"{PREFIX}/chat/sessions/{session_id}").json()
    assert detail["status"] in ("active", "terminal")
    assert detail["diagnosis_id"] == payload["diagnosis_id"]

    again = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/confirm",
        json={"text": "重复确认", "features": FULL_FEATURES},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] in ("CHAT_SESSION_ALREADY_ACTIVE", "CHAT_SESSION_CLOSED")


def test_confirm_idempotent_replay_returns_first_result(client: TestClient):
    session_id = new_session(client)
    headers = {"Idempotency-Key": "idem-confirm-0001"}
    first = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/confirm",
        json={"text": "3号机", "features": FULL_FEATURES},
        headers=headers,
    )
    assert first.status_code == 202, first.text
    first_body = first.json()
    replay = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/confirm",
        json={"text": "3号机", "features": FULL_FEATURES},
        headers=headers,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["diagnosis_id"] == first_body["diagnosis_id"]
    assert replay.json()["deduplicated"] is False


def test_confirm_rejects_null_and_missing_device_id(client: TestClient):
    session_id = new_session(client)
    null_response = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/confirm",
        json={"features": {"device_id": "3号机", "product_type": None}},
    )
    assert null_response.status_code == 422
    assert null_response.json()["error"]["code"] == "VALIDATION_FAILED"

    missing = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/confirm",
        json={"features": {"product_type": "M", "torque_nm": 40}},
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "DEVICE_ID_INVALID"


def test_terminal_session_with_null_diagnosis_cannot_rebind(client: TestClient):
    """P2-N1：terminal 且 diagnosis_id 置空的会话不可再绑定。"""
    session_id = new_id("cht")
    conn = client.app.state.db.connection()
    conn.execute(
        "INSERT INTO chat_sessions (session_id, user_id, diagnosis_id, status, created_at, updated_at)"
        " VALUES (?,?,NULL,'terminal',?,?)",
        (session_id, 1, utcnow(), utcnow()),
    )
    response = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/confirm",
        json={"features": FULL_FEATURES},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHAT_SESSION_CLOSED"


def test_active_review_rejects_free_text(client: TestClient):
    session_id = new_session(client)
    confirm = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/confirm",
        json={"features": REVIEW_FEATURES},
    )
    assert confirm.status_code == 202, confirm.text
    diagnosis_id = confirm.json()["diagnosis_id"]
    wait_for_status(client, diagnosis_id, {"waiting_human"})
    response = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/messages", json={"text": "补充扭矩 35"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CHAT_DECISION_REQUIRED"


def test_active_clarification_returns_supplement_card_without_mutation(client: TestClient):
    session_id = new_session(client)
    confirm = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/confirm",
        json={"features": {"device_id": "3号机", "torque_nm": 55}},
    )
    assert confirm.status_code == 202, confirm.text
    diagnosis_id = confirm.json()["diagnosis_id"]
    snapshot = wait_for_status(client, diagnosis_id, {"waiting_human"})
    version_before = snapshot["version"]

    response = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/messages",
        json={"text": "产品类型 M，刀具磨损 120 分钟"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["diagnosis_id"] == diagnosis_id
    assert body["version"] == version_before
    assert body["interrupt"]["type"] == "clarification"
    assert body["extraction"]["features"]["product_type"] == "M"

    after = client.get(f"{PREFIX}/diagnoses/{diagnosis_id}").json()
    assert after["status"] == "waiting_human"
    assert after["version"] == version_before


def test_running_diagnosis_rejects_messages(client: TestClient):
    session_id = new_session(client)
    confirm = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/confirm",
        json={"features": REVIEW_FEATURES},
    )
    diagnosis_id = confirm.json()["diagnosis_id"]
    wait_for_status(client, diagnosis_id, {"waiting_human"})
    records.set_running(client.app.state.db, diagnosis_id)
    response = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/messages", json={"text": "在吗"}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DIAGNOSIS_STATE_CONFLICT"


def test_confirm_rt17_reuse_binds_existing_diagnosis_or_conflicts(client: TestClient):
    first_session = new_session(client)
    first = client.post(
        f"{PREFIX}/chat/sessions/{first_session}/confirm",
        json={"features": REVIEW_FEATURES},
    )
    assert first.status_code == 202, first.text
    diagnosis_id = first.json()["diagnosis_id"]
    wait_for_status(client, diagnosis_id, {"waiting_human"})

    second_session = new_session(client)
    second = client.post(
        f"{PREFIX}/chat/sessions/{second_session}/confirm",
        json={"features": REVIEW_FEATURES},
    )
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "CHAT_SESSION_ALREADY_ACTIVE"


def test_confirm_rt17_reuse_returns_200_and_does_not_rerun(client: TestClient):
    """RT-17 命中且既有 chat 诊断未被任何会话占用 → 200 + deduplicated + 绑定，不重复执行。"""
    first_session = new_session(client)
    created = client.post(
        f"{PREFIX}/chat/sessions/{first_session}/confirm",
        json={"features": REVIEW_FEATURES},
    )
    assert created.status_code == 202, created.text
    diagnosis_id = created.json()["diagnosis_id"]
    wait_for_status(client, diagnosis_id, {"waiting_human"})

    # 模拟该诊断未被任何会话占用（原会话解绑）
    conn = client.app.state.db.connection()
    conn.execute(
        "UPDATE chat_sessions SET diagnosis_id=NULL, status='terminal' WHERE session_id=?",
        (first_session,),
    )
    before = client.get(f"{PREFIX}/diagnoses").json()["total"]

    session_id = new_session(client)
    reused = client.post(
        f"{PREFIX}/chat/sessions/{session_id}/confirm",
        json={"features": REVIEW_FEATURES},
    )
    assert reused.status_code == 200, reused.text
    body = reused.json()
    assert body["deduplicated"] is True
    assert body["diagnosis_id"] == diagnosis_id
    assert client.get(f"{PREFIX}/diagnoses").json()["total"] == before

    detail = client.get(f"{PREFIX}/chat/sessions/{session_id}").json()
    assert detail["diagnosis_id"] == diagnosis_id
    assert detail["status"] == "active"
