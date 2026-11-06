"""P0 补证：重试与人工复核（AC-DG-07）、复核补充修订（AC-DG-09）、报告缺项降级（AC-DG-17）。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import diagnosis as diagnosis_domain
from app import report
from tests.conftest import FORM_INPUT, wait_for_status
from tests.support import PREFIX, app_client

REVIEW_FORM = {
    "input_type": "form",
    "device_id": "2号机",
    "product_type": "M",
    "air_temp_k": 308.6,
    "process_temp_k": 298.1,
    "rotational_speed_rpm": 1250,
    "torque_nm": 30,
    "tool_wear_min": 100,
}
FIXTURE_CONFIDENCE = 0.7875


def _fake_rule_diagnose(*args, **kwargs):
    """AC-DG-07：固定 0.7875 的中置信夹具，命中 RT-07。"""
    return {
        "primary_type": "HDF",
        "secondary_types": [],
        "confidence": FIXTURE_CONFIDENCE,
        "confidence_breakdown": {
            "rule": 1.0,
            "coverage": 1.0,
            "llm_self": 0.75,
            "completeness": 1.0,
            "penalties": 0.0,
            "total": FIXTURE_CONFIDENCE,
            "llm_decided": False,
        },
        "knowledge_status": "supported",
        "rule_hits": [{"fault_type": "HDF", "reason": "夹具：温差与转速命中", "value": 7.2}],
        "reason": "夹具：温差低且转速低",
        "llm_used": False,
        "pending_llm": False,
    }


def test_ac_dg07_confidence_0_7875_retries_once_top_k8_then_review(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(diagnosis_domain, "rule_diagnose", _fake_rule_diagnose)
    with app_client(tmp_path) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
        assert created.status_code == 202, created.text
        diagnosis_id = created.json()["diagnosis_id"]

        snapshot = wait_for_status(client, diagnosis_id, {"waiting_human", "succeeded", "degraded"})
        assert snapshot["status"] == "waiting_human"
        assert snapshot["confidence"] == FIXTURE_CONFIDENCE
        assert snapshot["retry_count"] == 1, "中置信度只允许重试一次"
        assert snapshot["retrieval"]["retry_used"] is True
        assert snapshot["retrieval"]["top_k"] == 8
        assert snapshot["interrupt"]["type"] == "review"
        retrieve_nodes = [step for step in snapshot["trace_steps"] if step["node"] == "retrieve"]
        assert any(step["rule_id"] == "RT-07" and step["event"] == "retry" for step in retrieve_nodes)


def test_ac_dg09_supplement_bumps_revision_keeps_old_fields(tmp_path: Path):
    with app_client(tmp_path) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=REVIEW_FORM)
        assert created.status_code == 202, created.text
        diagnosis_id = created.json()["diagnosis_id"]
        first = wait_for_status(client, diagnosis_id, {"waiting_human"})
        assert first["interrupt"]["type"] == "review"
        assert first["diagnosis_revision"] == 1

        resumed = client.post(
            f"{PREFIX}/diagnoses/{diagnosis_id}/resume",
            json={
                "decision": "supplement",
                "supplement": {"torque_nm": 55},
                "version": first["version"],
            },
        )
        assert resumed.status_code == 200, resumed.text
        second = wait_for_status(client, diagnosis_id, {"waiting_human", "succeeded", "degraded"})

        row = client.app.state.db.connection().execute(
            "SELECT diagnosis_revision FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)
        ).fetchone()
        assert row["diagnosis_revision"] == 2
        assert second["diagnosis_revision"] == 2

        parse_steps = [
            step
            for step in second["trace_steps"]
            if step["node"] == "parse_input" and step["revision"] == 2
        ]
        assert parse_steps, "复核补充后应以 revision=2 重跑 parse_input"

        normalized = second["features"]["normalized"]
        assert normalized["torque_nm"] == 55, "补充字段必须生效"
        assert normalized["air_temp_k"] == 308.6, "旧字段不得被清空"
        assert normalized["process_temp_k"] == 298.1
        assert normalized["tool_wear_min"] == 100


def _markdown_without_differential() -> str:
    lines = [
        "# 夹具机 HDF 诊断报告",
        "",
        "## 结论",
        "主类型：HDF。夹具报告缺少鉴别诊断。",
        "",
        "## 置信度",
        "高置信度（0.94）",
        "",
        "## 关键特征",
        "- 温差：7.2 K",
        "",
        "## 判断依据",
        "引用知识条目：KB-HDF-001。",
        "",
        "## 维修建议",
        "检查冷却液流量与散热风扇。",
        "",
        "## 数据质量与假设",
        "- 数据完整，未触发质量标记或假设。",
        "",
        "## 免责声明",
        report.DISCLAIMER,
    ]
    return "\n".join(lines).strip() + "\n"


def _fake_build_report(**kwargs):
    markdown = _markdown_without_differential()
    check = report.check_report(markdown, kwargs["evidence"], kwargs["diagnosis"])
    return {
        "markdown": markdown,
        "title": "夹具机 HDF 诊断报告",
        "elements_check": check,
        "meta": {"report_retry_count": 0, "model_name": "rule-engine", "llm_used": False},
    }


def test_ac_dg17_report_twice_missing_differential_degrades_with_note(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(report, "build_report", _fake_build_report)
    with app_client(tmp_path) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
        assert created.status_code == 202, created.text
        diagnosis_id = created.json()["diagnosis_id"]

        snapshot = wait_for_status(
            client, diagnosis_id, {"succeeded", "degraded", "failed", "failed_timeout"}
        )
        assert snapshot["status"] == "degraded", "OBS-10：报告缺项不得静默 succeeded"
        assert snapshot["report_retry_count"] == 1
        assert snapshot["error"]["code"] == "REPORT_CHECK_FAILED"
        markdown = snapshot["report"]["markdown"]
        assert markdown.startswith("> 报告自检未通过，缺少要素：")
        assert "鉴别诊断" in markdown.splitlines()[0]
        assert "## 鉴别诊断" not in markdown

        retry_steps = [step for step in snapshot["trace_steps"] if step["rule_id"] == "RT-12"]
        assert len(retry_steps) == 1, "报告修复与告警只允许一次"
        assert retry_steps[0]["node"] == "report_fix"
        check = snapshot["report_elements_check"]
        assert "鉴别诊断" in check["missing"]
