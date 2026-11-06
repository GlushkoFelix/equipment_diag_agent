"""LLM 归因边界、报告守卫与提示词文件契约。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import diagnosis, report
from app.config import Settings
from app.prompts import PromptLibrary
from app.reasoning import AttributionOut


def _features(**overrides):
    base = {
        "product_type": "M",
        "air_temp_k": 298.1,
        "process_temp_k": 306.6,
        "rotational_speed_rpm": 1500,
        "torque_nm": 40,
        "tool_wear_min": 100,
        "completeness": 1.0,
        "temp_diff": 8.5,
        "power_w": 6283.2,
        "wear_torque": 4000.0,
    }
    base.update(overrides)
    return base


def _retrieval(*entry_ids):
    hits = [
        {
            "entry_id": entry_id,
            "title": f"条目 {entry_id}",
            "fault_type": entry_id.split("-")[1],
            "snippet": "温度差 8.6 K，转速 1380 rpm，磨损 190 min",
            "score": 0.8,
        }
        for entry_id in (entry_ids or ("KB-HDF-001",))
    ]
    return {"coverage": "covered", "hits": hits, "max_score": 0.8, "top_k": 5}


def _attribution(**overrides):
    data = {
        "primary_type": "HDF",
        "secondary_types": ["TWF"],
        "reason": "温差接近边界且转速偏低，符合 HDF 特征",
        "llm_self": 0.82,
        "evidence_entry_ids": ["KB-HDF-001"],
        "unattributable": False,
    }
    data.update(overrides)
    return AttributionOut(**data)


def test_rule_evidence_not_overridden_by_llm():
    features = _features(tool_wear_min=210, torque_nm=65, wear_torque=13650)
    base = diagnosis.rule_diagnose(features, [], [], _retrieval("KB-OSF-001"))
    assert base["primary_type"] == "OSF"
    merged, accepted = diagnosis.merge_llm_attribution(
        base,
        _attribution(primary_type="TWF", evidence_entry_ids=["KB-OSF-001"]),
        _retrieval("KB-OSF-001"),
    )
    assert accepted is True
    assert merged["primary_type"] == "OSF"
    assert merged["llm_used"] is True


def test_rnf_requires_unattributable_flag():
    base = diagnosis.rule_diagnose(_features(), [], [], _retrieval("KB-RNF-001"))
    rejected, accepted = diagnosis.merge_llm_attribution(
        base,
        _attribution(primary_type="RNF", evidence_entry_ids=["KB-RNF-001"], unattributable=False),
        _retrieval("KB-RNF-001"),
    )
    assert accepted is False
    assert rejected["primary_type"] == "未覆盖"

    merged, accepted = diagnosis.merge_llm_attribution(
        base,
        _attribution(
            primary_type="RNF",
            evidence_entry_ids=["KB-RNF-001"],
            unattributable=True,
            reason="无规则证据，判定为随机失效",
        ),
        _retrieval("KB-RNF-001"),
    )
    assert accepted is True
    assert merged["primary_type"] == "RNF"
    assert merged["confidence"] <= 0.4
    assert merged["reason"].startswith("不可归因")


def test_llm_must_bind_existing_evidence():
    base = diagnosis.rule_diagnose(_features(), [], [], _retrieval("KB-HDF-001"))
    rejected, accepted = diagnosis.merge_llm_attribution(
        base, _attribution(evidence_entry_ids=["KB-FAKE-999"]), _retrieval("KB-HDF-001")
    )
    assert accepted is False
    assert rejected["primary_type"] == "未覆盖"
    assert rejected["llm_used"] is False


def test_llm_cannot_pick_type_outside_rule_candidates():
    features = _features(tool_wear_min=210, torque_nm=65, wear_torque=13650)
    base = diagnosis.rule_diagnose(features, [], [], _retrieval("KB-OSF-001"))
    merged, accepted = diagnosis.merge_llm_attribution(
        base, _attribution(primary_type="未覆盖"), _retrieval("KB-OSF-001")
    )
    assert accepted is True
    assert merged["primary_type"] == "OSF"


def test_build_report_guards_numbers_and_unknown_entries():
    diagnosis_data = {
        "primary_type": "HDF",
        "secondary_types": [],
        "confidence": 0.82,
        "confidence_breakdown": {"total": 0.82},
        "knowledge_status": "supported",
        "reason": "温差 8.6 K 且转速 1380 rpm 以下",
        "rule_hits": [{"fault_type": "HDF", "reason": "温差 8.6 K 且转速 1380 rpm"}],
    }
    built = report.build_report(
        diagnosis_id="diag_1",
        device_id="3号机",
        features=_features(),
        derived={"temp_diff": 8.5, "power_w": 6283.2, "wear_torque": 4000.0},
        flags=[],
        assumptions=[],
        diagnosis=diagnosis_data,
        retrieval=_retrieval("KB-HDF-001"),
        evidence=[
            {
                "entry_id": "KB-HDF-001",
                "title": "HDF 条目",
                "fault_type": "HDF",
                "feature": "temp_diff",
                "value": 8.6,
                "unit": "K",
            }
        ],
        auto_review=False,
        human_confirmed=False,
        kb_version="kb_v1",
        narrative={
            "conclusion": "温差 8.6 K 且转速偏低，符合 HDF。",
            "evidence_explanation": "引用 KB-HDF-001 与规则命中。",
            "differential": "排除 PWF。",
            "maintenance": "检查 999 号阀门。",
        },
        prompt_version="reporter-v1",
        model_name="deepseek-chat",
        llm_used=True,
        llm_calls=1,
    )
    assert built["elements_check"]["passed"] is True
    assert "温差 8.6 K" in built["markdown"]
    assert "999" not in built["markdown"]
    assert report.MAINTENANCE["HDF"] in built["markdown"]
    assert built["meta"]["llm_used"] is True
    assert built["meta"]["model_name"] == "deepseek-chat"


def test_build_report_drops_fabricated_entry_reference():
    built = report.build_report(
        diagnosis_id="diag_2",
        device_id="3号机",
        features=_features(),
        derived={"temp_diff": 8.5, "power_w": 6283.2, "wear_torque": 4000.0},
        flags=[],
        assumptions=[],
        diagnosis={
            "primary_type": "HDF",
            "secondary_types": [],
            "confidence": 0.82,
            "knowledge_status": "supported",
            "reason": "规则命中",
            "rule_hits": [],
        },
        retrieval=_retrieval("KB-HDF-001"),
        evidence=[
            {
                "entry_id": "KB-HDF-001",
                "title": "HDF 条目",
                "fault_type": "HDF",
                "feature": "temp_diff",
                "value": 8.6,
                "unit": "K",
            }
        ],
        auto_review=False,
        human_confirmed=False,
        kb_version="kb_v1",
        narrative={"evidence_explanation": "引用 KB-XXX-999 的结论。"},
    )
    assert "KB-XXX-999" not in built["markdown"]


def test_prompt_files_have_version_headers():
    settings = Settings()
    library = PromptLibrary(settings.prompts_dir)
    for name in (
        "supervisor_router",
        "data_reader_nl",
        "retriever_query",
        "diagnostician",
        "reporter",
    ):
        doc = library.get(name)
        assert Path(settings.prompts_dir, f"{name}.md").exists()
        assert doc.version != "unversioned"
        assert doc.updated_at
        assert len(doc.body) > 50
