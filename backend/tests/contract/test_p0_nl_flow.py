"""P0 补证：NL 完整抽取直达检索（AC-IN-11）与二次追问只列剩余项（AC-IN-13）。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import wait_for_status
from tests.support import PREFIX, app_client

COMPLETE_TEXT = "3号机 M 型 空气温度 298.1K 工艺温度 305.3K 转速 1250 扭矩 30 刀具磨损 100"
SPARSE_TEXT = "3号机 M 型"
FEATURE_KEYS = (
    "device_id",
    "product_type",
    "air_temp_k",
    "process_temp_k",
    "rotational_speed_rpm",
    "torque_nm",
    "tool_wear_min",
)


def test_ac_in11_full_nl_hits_retrieve_without_clarification(tmp_path: Path):
    """AC-IN-11：7 项齐全 → 无澄清 → 事件序列含 retrieve/report → 产出报告。"""
    with app_client(tmp_path) as client:
        extracted = client.post(f"{PREFIX}/nl/extract", json={"text": COMPLETE_TEXT})
        assert extracted.status_code == 200, extracted.text
        body = extracted.json()
        assert body["extraction_status"] == "ok"
        assert body["recommended_action"] == "confirm"
        assert body["missing_fields"] == []
        features = {key: body["features"][key] for key in FEATURE_KEYS}
        assert all(features[key] is not None for key in FEATURE_KEYS)

        created = client.post(
            f"{PREFIX}/diagnoses",
            json={"input_type": "nl", "text": COMPLETE_TEXT, **features},
        )
        assert created.status_code == 202, created.text
        diagnosis_id = created.json()["diagnosis_id"]

        snapshot = wait_for_status(client, diagnosis_id, {"succeeded", "degraded", "waiting_human"})
        assert snapshot["status"] in ("succeeded", "degraded"), snapshot
        assert snapshot["interrupt"] is None, "7 项齐全不得进入 clarification"
        assert snapshot["features"]["missing_fields"] == []

        nodes = [step["node"] for step in snapshot["trace_steps"]]
        assert "retrieve" in nodes
        assert "report" in nodes
        assert snapshot["report"] is not None
        assert "## 结论" in snapshot["report"]["markdown"]
        assert "# " in snapshot["report"]["markdown"]


def test_ac_in13_clarification_missing_count_and_append(tmp_path: Path):
    """AC-IN-13：首次缺 5 项 → 补 1 项后二次追问只列剩余 4 项，已补项不重现。"""
    with app_client(tmp_path) as client:
        extracted = client.post(f"{PREFIX}/nl/extract", json={"text": SPARSE_TEXT})
        assert extracted.status_code == 200, extracted.text
        body = extracted.json()
        assert body["extraction_status"] == "partial"

        created = client.post(
            f"{PREFIX}/diagnoses",
            json={
                "input_type": "nl",
                "text": SPARSE_TEXT,
                "device_id": "3号机",
                "product_type": "M",
            },
        )
        assert created.status_code == 202, created.text
        diagnosis_id = created.json()["diagnosis_id"]

        first = wait_for_status(client, diagnosis_id, {"waiting_human"})
        assert first["interrupt"]["type"] == "clarification"
        first_missing = {item["field"] for item in first["interrupt"]["payload"]["missing_fields"]}
        assert first_missing == {
            "air_temp_k",
            "process_temp_k",
            "rotational_speed_rpm",
            "torque_nm",
            "tool_wear_min",
        }

        resumed = client.post(
            f"{PREFIX}/diagnoses/{diagnosis_id}/resume",
            json={
                "decision": "supplement",
                "supplement": {"process_temp_k": 305.3},
                "version": first["version"],
            },
        )
        assert resumed.status_code == 200, resumed.text
        second = wait_for_status(client, diagnosis_id, {"waiting_human"})
        assert second["interrupt"]["type"] == "clarification"
        assert second["status"] == "waiting_human"
        assert second["diagnosis_revision"] == 1, "澄清补充不增修订号"

        second_missing = {item["field"] for item in second["interrupt"]["payload"]["missing_fields"]}
        assert len(second_missing) == 4
        assert "process_temp_k" not in second_missing, "已补项不得重现"
        assert second_missing == first_missing - {"process_temp_k"}
        assert second["features"]["normalized"]["process_temp_k"] == 305.3
