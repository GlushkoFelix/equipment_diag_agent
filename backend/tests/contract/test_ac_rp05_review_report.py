"""AC-RP-05：confidence=0.62 首轮复核 → 确认后报告含 AC 指定文案。"""

from __future__ import annotations

from pathlib import Path

from app import diagnosis as diagnosis_domain
from tests.conftest import FORM_INPUT, wait_for_status
from tests.support import PREFIX, app_client, write_evidence

FIXTURE_CONFIDENCE = 0.62


def _fake_rule_diagnose(*args, **kwargs):
    return {
        "primary_type": "HDF",
        "secondary_types": [],
        "confidence": FIXTURE_CONFIDENCE,
        "confidence_breakdown": {
            "rule": 0.8,
            "coverage": 1.0,
            "llm_self": 0.6,
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


def test_ac_rp05_confidence_062_report_has_medium_and_review_hint(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(diagnosis_domain, "rule_diagnose", _fake_rule_diagnose)
    with app_client(tmp_path) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
        assert created.status_code == 202, created.text
        diagnosis_id = created.json()["diagnosis_id"]

        first = wait_for_status(client, diagnosis_id, {"waiting_human"})
        assert first["interrupt"]["type"] == "review"
        assert first["retry_count"] == 1, "0.62 中置信度必须先重试一次"
        assert first["confidence"] == FIXTURE_CONFIDENCE

        resumed = client.post(
            f"{PREFIX}/diagnoses/{diagnosis_id}/resume",
            json={"decision": "confirm", "version": first["version"]},
        )
        assert resumed.status_code == 200, resumed.text
        final = wait_for_status(client, diagnosis_id, {"succeeded", "degraded"})
        assert final["status"] == "succeeded"
        assert final["retry_count"] == 1
        markdown = final["report"]["markdown"]

        assert "0.62" in markdown
        assert "中等置信度" in markdown
        assert "建议人工复核" in markdown
        confidence_line = next(
            line for line in markdown.splitlines() if line.startswith("中等置信度")
        )
        assert confidence_line.startswith("中等置信度（0.62），建议人工复核")
        top = "\n".join(markdown.splitlines()[:16])
        assert "0.62" in top and "中等置信度" in top and "建议人工复核" in top

        write_evidence(
            "AC-RP-05-report",
            {
                "diagnosis_id": diagnosis_id,
                "confidence": final["confidence"],
                "confidence_level": final["confidence_level"],
                "retry_count": final["retry_count"],
                "confidence_line": confidence_line,
                "report_top": top,
            },
        )
