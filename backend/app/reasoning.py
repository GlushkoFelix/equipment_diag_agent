"""LLM 归因与报告撰写的领域适配（ARCH §3.8 / §4.2 / §7.6）。

只做提示词组装、Schema 约束与结果投影；规则、置信度、报告自检仍由代码负责。
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.llm_client import LlmCallResult, LlmClient
from app.prompts import PromptLibrary

PRIMARY_TYPES = ("正常", "TWF", "HDF", "PWF", "OSF", "RNF", "未覆盖")


class AttributionOut(BaseModel):
    """diagnostician 提示词的强制输出结构。"""

    model_config = ConfigDict(extra="ignore")

    primary_type: Literal["正常", "TWF", "HDF", "PWF", "OSF", "RNF", "未覆盖"]
    secondary_types: list[str] = Field(default_factory=list, max_length=3)
    reason: str = Field(min_length=1, max_length=300)
    llm_self: float = Field(ge=0.0, le=1.0)
    evidence_entry_ids: list[str] = Field(default_factory=list)
    unattributable: bool = False

    @field_validator("secondary_types")
    @classmethod
    def _secondary_allowed(cls, values: list[str]) -> list[str]:
        return [item for item in values if item in PRIMARY_TYPES and item != "未覆盖"][:3]

    @field_validator("evidence_entry_ids")
    @classmethod
    def _evidence_ids(cls, values: list[str]) -> list[str]:
        return [str(item).strip() for item in values if str(item).strip()][:8]


class ReportNarrativeOut(BaseModel):
    """reporter 提示词的强制输出结构；只允许四段文本。"""

    model_config = ConfigDict(extra="ignore")

    conclusion: str = Field(min_length=1, max_length=400)
    evidence_explanation: str = Field(min_length=1, max_length=600)
    differential: str = Field(default="无", max_length=400)
    maintenance: str = Field(min_length=1, max_length=600)


class LlmReasoner:
    def __init__(self, client: LlmClient, prompts: PromptLibrary):
        self.client = client
        self.prompts = prompts

    @property
    def model_name(self) -> str:
        return self.client.model_name

    def prompt_version(self, name: str) -> str:
        return self.prompts.version(name)

    async def attribute(
        self,
        *,
        features: dict[str, Any],
        derived: dict[str, Any],
        flags: list[str],
        assumptions: list[str],
        retrieval: dict[str, Any],
        rule_hits: list[dict[str, Any]],
        user_text: str | None,
        budget: float,
    ) -> LlmCallResult:
        doc = self.prompts.get("diagnostician")
        payload = {
            "features": _features_only(features),
            "derived": {
                key: derived.get(key)
                for key in ("temp_diff", "power_w", "wear_torque")
                if derived.get(key) is not None
            },
            "quality_flags": list(flags),
            "assumptions": list(assumptions),
            "rules": [
                {
                    "fault_type": hit["fault_type"],
                    "reason": hit["reason"],
                    "value": hit.get("value"),
                }
                for hit in rule_hits
            ],
            "knowledge": [
                {
                    "entry_id": hit["entry_id"],
                    "title": hit["title"],
                    "fault_type": hit["fault_type"],
                    "snippet": hit["snippet"],
                    "score": hit["score"],
                }
                for hit in retrieval.get("hits", [])
            ],
            "user_text": f"<user_text>{user_text[:500]}</user_text>" if user_text else "",
        }
        return await self.client.complete_json(
            system=doc.body,
            user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            schema=AttributionOut,
            temperature=0.1,
            max_tokens=700,
            budget=budget,
        )

    async def narrate(
        self,
        *,
        diagnosis: dict[str, Any],
        features: dict[str, Any],
        derived: dict[str, Any],
        flags: list[str],
        assumptions: list[str],
        evidence: list[dict[str, Any]],
        budget: float,
    ) -> LlmCallResult:
        doc = self.prompts.get("reporter")
        payload = {
            "diagnosis": {
                "primary_type": diagnosis.get("primary_type"),
                "secondary_types": diagnosis.get("secondary_types") or [],
                "confidence": diagnosis.get("confidence"),
                "confidence_breakdown": diagnosis.get("confidence_breakdown") or {},
                "knowledge_status": diagnosis.get("knowledge_status"),
                "reason": diagnosis.get("reason"),
                "rule_hits": diagnosis.get("rule_hits") or [],
            },
            "features": _features_only(features),
            "derived": {
                key: derived.get(key)
                for key in ("temp_diff", "power_w", "wear_torque")
                if derived.get(key) is not None
            },
            "quality_flags": list(flags),
            "assumptions": list(assumptions),
            "evidence": evidence,
        }
        return await self.client.complete_json(
            system=doc.body,
            user=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            schema=ReportNarrativeOut,
            temperature=0.3,
            max_tokens=900,
            budget=budget,
        )


def _features_only(features: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "product_type",
        "air_temp_k",
        "process_temp_k",
        "rotational_speed_rpm",
        "torque_nm",
        "tool_wear_min",
    )
    return {key: features.get(key) for key in keys if features.get(key) is not None}
