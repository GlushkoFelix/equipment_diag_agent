"""核心端点契约：健康检查、认证、单条诊断主链路、RT-17、报告、SSE。"""

from __future__ import annotations

import io
import json

from fastapi.testclient import TestClient

from tests.conftest import FORM_INPUT, wait_for_status

PREFIX = "/api/v1"


def test_health_contract(client: TestClient):
    response = client.get(f"{PREFIX}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("ok", "degraded")
    for key in ("database", "checkpoint_store", "vector_index", "embedding_model", "llm_config"):
        assert key in body["dependencies"]
    assert response.headers["X-Request-Id"].startswith("req_")


def test_auth_flow(client: TestClient):
    me = client.get(f"{PREFIX}/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "tester"
    client.post(f"{PREFIX}/auth/logout")
    assert client.get(f"{PREFIX}/auth/me").status_code == 401
    login = client.post(
        f"{PREFIX}/auth/login", json={"username": "tester", "password": "Passw0rd!"}
    )
    assert login.status_code == 200
    assert login.json()["user"]["username"] == "tester"
    assert client.get(f"{PREFIX}/auth/me").status_code == 200


def test_form_diagnosis_end_to_end(client: TestClient):
    create = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
    assert create.status_code == 202, create.text
    created = create.json()
    assert created["deduplicated"] is False
    assert created["stream_url"].endswith("/events")

    snapshot = wait_for_status(client, created["diagnosis_id"], {"succeeded", "degraded", "waiting_human"})
    assert snapshot["primary_type"] in ("正常", "HDF", "PWF", "OSF", "TWF", "未覆盖")
    assert snapshot["confidence_level"] in ("high", "medium", "low")
    assert snapshot["input_type"] == "form"
    assert snapshot["features"]["completeness"] == 1.0

    if snapshot["status"] in ("succeeded", "degraded"):
        assert snapshot["report"] is not None
        markdown = snapshot["report"]["markdown"]
        for element in (
            "## 结论",
            "## 置信度",
            "## 关键特征",
            "## 判断依据",
            "## 鉴别诊断",
            "## 维修建议",
            "## 数据质量与假设",
            "## 免责声明",
        ):
            assert element in markdown
        download = client.get(f"{PREFIX}/diagnoses/{created['diagnosis_id']}/report.md")
        assert download.status_code == 200
        assert "filename*=UTF-8''" in download.headers["content-disposition"]
        assert download.text == markdown


def test_snapshot_trace_steps_same_millisecond_keeps_start_before_end(client: TestClient):
    """历史快照同一毫秒内按写入顺序稳定回放：start 必先于 end（ARCH §4.5.3）。"""
    create = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
    assert create.status_code == 202, create.text
    diagnosis_id = create.json()["diagnosis_id"]
    wait_for_status(client, diagnosis_id, {"succeeded", "degraded"})

    conn = client.app.state.db.connection()
    conn.execute("DELETE FROM diagnosis_steps WHERE diagnosis_id=?", (diagnosis_id,))
    same_ts = "2026-10-24T11:08:30.669Z"
    # step_id 字典序故意与写入顺序相反，验证不再以 step_id 作为同毫秒排序键
    rows = [
        ("stp_88_diagnose_start", "diagnose", "start"),
        ("stp_09_diagnose_end", "diagnose", "end"),
        ("stp_77_report_start", "report", "start"),
        ("stp_07_report_end", "report", "end"),
    ]
    for step_id, node, event in rows:
        conn.execute(
            "INSERT INTO diagnosis_steps (step_id, diagnosis_id, revision, node, event, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (step_id, diagnosis_id, 1, node, event, same_ts),
        )

    trace = client.get(f"{PREFIX}/diagnoses/{diagnosis_id}").json()["trace_steps"]
    assert [(step["node"], step["event"]) for step in trace] == [
        ("diagnose", "start"),
        ("diagnose", "end"),
        ("report", "start"),
        ("report", "end"),
    ]


def test_missing_device_id_is_422_without_creating(client: TestClient):
    body = dict(FORM_INPUT)
    body.pop("device_id")
    response = client.post(f"{PREFIX}/diagnoses", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "DEVICE_ID_INVALID"
    listing = client.get(f"{PREFIX}/diagnoses").json()
    assert listing["total"] == 0


def test_out_of_range_feature_is_422(client: TestClient):
    body = dict(FORM_INPUT, torque_nm=500)
    response = client.post(f"{PREFIX}/diagnoses", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "FEATURE_OUT_OF_RANGE"


def test_nl_partial_clarification_and_resume(client: TestClient):
    response = client.post(
        f"{PREFIX}/diagnoses",
        json={
            "input_type": "nl",
            "text": "3号机异响，扭矩 55，有点烫",
            "device_id": "3号机",
            "torque_nm": 55,
        },
    )
    assert response.status_code == 202, response.text
    diagnosis_id = response.json()["diagnosis_id"]
    snapshot = wait_for_status(client, diagnosis_id, {"waiting_human"})
    interrupt = snapshot["interrupt"]
    assert interrupt["type"] == "clarification"
    fields = [item["field"] for item in interrupt["payload"]["missing_fields"]]
    assert fields == [
        "product_type",
        "air_temp_k",
        "process_temp_k",
        "rotational_speed_rpm",
        "tool_wear_min",
    ]

    resumed = client.post(
        f"{PREFIX}/diagnoses/{diagnosis_id}/resume",
        json={"decision": "supplement", "supplement": {"tool_wear_min": 120}, "version": snapshot["version"]},
    )
    assert resumed.status_code == 200, resumed.text
    after = resumed.json()
    assert after["status"] == "waiting_human"
    remaining = [item["field"] for item in after["interrupt"]["payload"]["missing_fields"]]
    assert remaining == ["product_type", "air_temp_k", "process_temp_k", "rotational_speed_rpm"]


def test_rt17_deduplicates_active_diagnosis(client: TestClient):
    # 温差倒挂样本：HDF 不生效且扣分，稳定进入 waiting_human，便于 RT-17 命中
    body = {
        "input_type": "form",
        "device_id": "2号机",
        "product_type": "M",
        "air_temp_k": 308.6,
        "process_temp_k": 298.1,
        "rotational_speed_rpm": 1250,
        "torque_nm": 30,
        "tool_wear_min": 100,
    }
    first = client.post(f"{PREFIX}/diagnoses", json=body)
    assert first.status_code == 202, first.text
    diagnosis_id = first.json()["diagnosis_id"]
    wait_for_status(client, diagnosis_id, {"waiting_human"})

    second = client.post(f"{PREFIX}/diagnoses", json=body)
    assert second.status_code == 200, second.text
    payload = second.json()
    assert payload["deduplicated"] is True
    assert payload["diagnosis_id"] == diagnosis_id


def test_csv_upload_and_single_diagnosis(client: TestClient):
    csv_text = (
        "Product ID,Type,Air temperature [K],Process temperature [K],"
        "Rotational speed [rpm],Torque [Nm],Tool wear [min]\n"
        "1,M,298.1,305.3,1250,30,100\n"
    )
    upload = client.post(
        f"{PREFIX}/uploads",
        files={"file": ("sample.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")},
    )
    assert upload.status_code == 201, upload.text
    upload_id = upload.json()["upload_id"]

    response = client.post(
        f"{PREFIX}/diagnoses",
        json={
            "input_type": "csv_single",
            "upload_id": upload_id,
            "row_no": 1,
            "default_device_id": "3号机",
            "mapping": {
                "device_id": "Product ID",
                "product_type": "Type",
                "air_temp_k": "Air temperature [K]",
                "process_temp_k": "Process temperature [K]",
                "rotational_speed_rpm": "Rotational speed [rpm]",
                "torque_nm": "Torque [Nm]",
                "tool_wear_min": "Tool wear [min]",
            },
        },
    )
    assert response.status_code == 202, response.text
    snapshot = wait_for_status(
        client, response.json()["diagnosis_id"], {"succeeded", "degraded", "waiting_human"}
    )
    assert snapshot["input_type"] == "csv_single"
    assert snapshot["input_summary"]["row_no"] == 1


def test_review_confirm_generates_report(client: TestClient):
    body = {
        "input_type": "form",
        "device_id": "2号机",
        "product_type": "M",
        "air_temp_k": 308.6,
        "process_temp_k": 298.1,
        "rotational_speed_rpm": 1250,
        "torque_nm": 30,
        "tool_wear_min": 100,
    }
    create = client.post(f"{PREFIX}/diagnoses", json=body)
    assert create.status_code == 202, create.text
    diagnosis_id = create.json()["diagnosis_id"]
    snapshot = wait_for_status(client, diagnosis_id, {"waiting_human"})
    assert snapshot["interrupt"]["type"] == "review"
    assert snapshot["report_retry_count"] == 0

    confirmed = client.post(
        f"{PREFIX}/diagnoses/{diagnosis_id}/resume",
        json={"decision": "confirm", "version": snapshot["version"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    assert result["status"] in ("succeeded", "degraded")
    assert result["human_decision"] == "confirm"
    assert "已人工确认" in result["report"]["markdown"]


def test_sse_replay_with_last_event_id(client: TestClient):
    create = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
    diagnosis_id = create.json()["diagnosis_id"]
    wait_for_status(client, diagnosis_id, {"succeeded", "degraded", "waiting_human"})
    stream = client.get(
        f"{PREFIX}/diagnoses/{diagnosis_id}/events", headers={"Last-Event-ID": "1"}
    )
    assert stream.status_code == 200
    assert "event: snapshot" not in stream.text


def test_sse_snapshot_event(client: TestClient):
    create = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
    diagnosis_id = create.json()["diagnosis_id"]
    wait_for_status(client, diagnosis_id, {"succeeded", "degraded", "waiting_human"})
    stream = client.get(f"{PREFIX}/diagnoses/{diagnosis_id}/events")
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    text = stream.text
    assert "retry: 3000" in text
    assert "event: snapshot" in text
    data_line = next(line for line in text.splitlines() if line.startswith("data: ") and '"type":"snapshot"' in line)
    payload = json.loads(data_line[len("data: "):])
    assert payload["stream_kind"] == "diagnosis"
    assert payload["payload"]["diagnosis_id"] == diagnosis_id
