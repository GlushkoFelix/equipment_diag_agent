"""节点级接线：真实调用 reasoner 才置 llm_used，失败按规则兜底。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config import Settings
from app.llm_client import LlmCallResult, LlmTimeout
from app.reasoning import AttributionOut, ReportNarrativeOut
from app.runtime import nodes as nodes_module
from app.runtime.nodes import Nodes


def _deadline(seconds: int = 15) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _state() -> dict:
    return {
        "thread_id": "diag_unit_llm",
        "device_id": "3号机",
        "normalized_features": {
            "product_type": "M",
            "air_temp_k": 298.1,
            "process_temp_k": 306.5,
            "rotational_speed_rpm": 1500,
            "torque_nm": 40,
            "tool_wear_min": 100,
        },
        "feature_completeness": 1.0,
        "derived_features": {"temp_diff": 8.5, "power_w": 6283.2, "wear_torque": 4000.0},
        "data_quality_flags": [],
        "assumptions": [],
        "retrieval": {
            "coverage": "covered",
            "max_score": 0.8,
            "top_k": 5,
            "hits": [
                {
                    "entry_id": "KB-HDF-001",
                    "title": "HDF 条目",
                    "fault_type": "HDF",
                    "snippet": "温差 8.6 K，转速 1380 rpm",
                    "score": 0.8,
                }
            ],
        },
        "deadline_at": _deadline(),
        "retry_count": 0,
        "timings": {},
    }


class StubReasoner:
    model_name = "stub-llm"

    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.attribute_calls = 0
        self.narrate_calls = 0

    def prompt_version(self, name: str) -> str:
        return "reporter-v1"

    async def attribute(self, **kwargs):
        self.attribute_calls += 1
        if self.fail:
            raise LlmTimeout("boom")
        return LlmCallResult(
            payload=AttributionOut(
                primary_type="HDF",
                secondary_types=[],
                reason="温差 8.6 K 边界且转速偏高，按知识条目归因",
                llm_self=0.82,
                evidence_entry_ids=["KB-HDF-001"],
            ),
            model=self.model_name,
            latency_ms=5,
            attempts=1,
            total_tokens=10,
            prompt_sha256="abc",
        )

    async def narrate(self, **kwargs):
        self.narrate_calls += 1
        return LlmCallResult(
            payload=ReportNarrativeOut(
                conclusion="温差接近边界，按 HDF 处理。",
                evidence_explanation="引用 KB-HDF-001。",
                differential="无",
                maintenance="检查冷却系统。",
            ),
            model=self.model_name,
            latency_ms=5,
            attempts=1,
            total_tokens=10,
            prompt_sha256="abc",
        )


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setattr(nodes_module.records, "append_step", lambda *a, **k: None)
    monkeypatch.setattr(nodes_module.records, "update_projection", lambda *a, **k: None)


@pytest.mark.asyncio
async def test_diagnose_sets_llm_used_only_after_real_call():
    settings = Settings(llm_mode="deepseek", deepseek_api_key="sk-test")
    reasoner = StubReasoner()
    result = await Nodes(settings, None, None, reasoner=reasoner).diagnose(_state())
    diagnosed = result["diagnosis"]
    assert reasoner.attribute_calls == 1
    assert diagnosed["llm_used"] is True
    assert diagnosed["primary_type"] == "HDF"
    assert diagnosed["confidence_breakdown"]["llm_used"] is True
    assert diagnosed["llm_attribution"]["evidence_entry_ids"] == ["KB-HDF-001"]
    assert diagnosed["reason"].startswith("温差")


@pytest.mark.asyncio
async def test_diagnose_falls_back_when_llm_fails():
    settings = Settings(llm_mode="deepseek", deepseek_api_key="sk-test")
    reasoner = StubReasoner(fail=True)
    result = await Nodes(settings, None, None, reasoner=reasoner).diagnose(_state())
    diagnosed = result["diagnosis"]
    assert diagnosed["llm_used"] is False
    assert diagnosed["primary_type"] == "未覆盖"
    assert diagnosed["confidence_breakdown"]["llm_used"] is False


@pytest.mark.asyncio
async def test_report_uses_narrative_and_records_meta():
    settings = Settings(llm_mode="deepseek", deepseek_api_key="sk-test")

    class Knowledge:
        kb_version = "kb_v1"

    state = _state()
    state["diagnosis"] = {
        "primary_type": "HDF",
        "secondary_types": [],
        "confidence": 0.82,
        "confidence_breakdown": {"total": 0.82, "llm_used": True},
        "knowledge_status": "supported",
        "reason": "规则命中",
        "rule_hits": [],
        "llm_used": True,
    }
    reasoner = StubReasoner()
    result = await Nodes(settings, None, Knowledge(), reasoner=reasoner).report(state)
    assert reasoner.narrate_calls == 1
    assert result["report_meta"]["llm_used"] is True
    assert result["report_meta"]["model_name"] == "stub-llm"
    assert result["report_elements_check"]["passed"] is True
    assert "检查冷却系统" in result["report_md"]
