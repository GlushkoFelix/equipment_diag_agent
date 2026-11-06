"""域诊断：故障规则、主类型优先级与四因子置信度（PRD §3.6 / ARCH §4.3）。"""

from __future__ import annotations

from typing import Any

OSF_THRESHOLDS = {"L": 11000.0, "M": 12000.0, "H": 13000.0}
PRIMARY_PRIORITY = ("OSF", "HDF", "PWF", "TWF", "RNF")


def rule_hits(features: dict[str, Any], flags: list[str]) -> list[dict[str, Any]]:
    """纯规则匹配；RNF 不作兜底。"""
    hits: list[dict[str, Any]] = []
    product_type = features.get("product_type")
    temp_diff = features.get("temp_diff")
    rpm = features.get("rotational_speed_rpm")
    power = features.get("power_w")
    wear = features.get("tool_wear_min")
    wear_torque = features.get("wear_torque")
    osf_threshold = OSF_THRESHOLDS.get(product_type or "", 12000.0)

    if (
        wear_torque is not None
        and wear_torque > osf_threshold
    ):
        hits.append(
            {
                "fault_type": "OSF",
                "reason": f"磨损×扭矩 {wear_torque:g} 超过 {product_type or 'M'} 型阈值 {osf_threshold:g}",
                "value": wear_torque,
            }
        )

    if (
        temp_diff is not None
        and rpm is not None
        # AI4I CSV 温度差保留 1 位小数，HDF 标注行会出现恰好 8.6 K；取闭区间以复现数据集标签。
        # 该工程口径已在 ARCH §10.4 C-009 登记，PRD 阈值语义不变。
        and temp_diff <= 8.6
        and rpm < 1380
        and "TEMP_INVERSION" not in flags
    ):
        hits.append(
            {
                "fault_type": "HDF",
                "reason": f"温差 {temp_diff:g} K ≤ 8.6 K 且转速 {rpm:g} rpm < 1380 rpm",
                "value": temp_diff,
            }
        )

    if power is not None and rpm is not None:
        if power < 3500 or power > 9000:
            hits.append(
                {
                    "fault_type": "PWF",
                    "reason": f"功率 {power:g} W 超出 3500–9000 W 区间",
                    "value": power,
                }
            )

    if (
        wear is not None
        and wear_torque is not None
        and 190 <= wear <= 300
        and wear_torque < osf_threshold
    ):
        hits.append(
            {
                "fault_type": "TWF",
                "reason": f"刀具磨损 {wear:g} min 位于 190–300 min，且磨损×扭矩未达 OSF 阈值",
                "value": wear,
            }
        )
    return hits


def is_normal(features: dict[str, Any], flags: list[str]) -> bool:
    temp_diff = features.get("temp_diff")
    rpm = features.get("rotational_speed_rpm")
    power = features.get("power_w")
    wear = features.get("tool_wear_min")
    if temp_diff is None or rpm is None or power is None or wear is None:
        return False
    return (
        temp_diff >= 8.6
        and rpm >= 1380
        and 3500 <= power <= 9000
        and wear < 190
        and "TEMP_INVERSION" not in flags
    )


def decide_primary(hits: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    types = [h["fault_type"] for h in hits]
    if not types:
        return None, []
    primary = next((t for t in PRIMARY_PRIORITY if t in types), types[0])
    secondary = [t for t in types if t != primary]
    return primary, secondary


def perimeter_confidence(
    *,
    rule_evidence: float,
    hit_count: int,
    llm_self: float,
    completeness: float,
    penalties: float,
    knowledge_missing: bool,
) -> dict[str, float]:
    coverage = 1.0 if hit_count >= 2 else (0.5 if hit_count == 1 else 0.0)
    total = (
        0.35 * rule_evidence
        + 0.20 * coverage
        + 0.25 * llm_self
        + 0.20 * completeness
        - penalties
    )
    total = max(0.0, min(1.0, total))
    if knowledge_missing:
        total = min(total, 0.4)
    return {
        "rule": round(rule_evidence, 4),
        "coverage": round(coverage, 4),
        "llm_self": round(llm_self, 4),
        "completeness": round(completeness, 4),
        "penalties": round(penalties, 4),
        "total": round(total, 4),
    }


def rule_diagnose(
    features: dict[str, Any],
    flags: list[str],
    assumptions: list[str],
    retrieval: dict[str, Any],
) -> dict[str, Any]:
    """规则先行：产出候选、证据与置信度；无规则且非正常时标记待 LLM 归因。"""
    hits = rule_hits(features, flags)
    knowledge_missing = retrieval.get("coverage") != "covered"
    hit_count = len(retrieval.get("hits", []))

    penalties = 0.10 * len(flags) + 0.05 * len(assumptions)

    pending_llm = False
    if knowledge_missing:
        primary, secondary = "未覆盖", [h["fault_type"] for h in hits]
        rule_evidence = 0.5
        llm_self = 0.35
        reason = "知识库未覆盖，仅提供未验证假设与通用安全建议"
    elif hits:
        primary, secondary = decide_primary(hits)
        rule_evidence = 1.0 if len(hits) == 1 else 0.7
        llm_self = 0.75 if len(hits) == 1 else 0.6
        reason = "；".join(h["reason"] for h in hits if h["fault_type"] == primary)
    elif is_normal(features, flags):
        primary, secondary = "正常", []
        rule_evidence = 1.0
        llm_self = 0.8
        reason = "温度、转速、功率与磨损均处于正常基线区间，无故障规则命中"
    else:
        primary, secondary = None, []
        rule_evidence = 0.5
        llm_self = 0.45
        reason = "规则无命中，等待知识归因"
        pending_llm = True

    breakdown = perimeter_confidence(
        rule_evidence=rule_evidence,
        hit_count=hit_count,
        llm_self=llm_self,
        completeness=float(features.get("completeness", 1.0)),
        penalties=penalties,
        knowledge_missing=knowledge_missing,
    )
    breakdown["llm_decided"] = False
    confidence = breakdown["total"]
    if primary is None:
        confidence = min(confidence, 0.4)
        breakdown["total"] = round(confidence, 4)
    return {
        "primary_type": primary,
        "secondary_types": secondary,
        "confidence": confidence,
        "confidence_breakdown": breakdown,
        "knowledge_status": "missing" if knowledge_missing else "supported",
        "rule_hits": hits,
        "reason": reason,
        "llm_used": False,
        "pending_llm": pending_llm,
    }


def finalize_rule_only(result: dict[str, Any]) -> dict[str, Any]:
    """无 LLM（或 LLM 失败）时的规则终态：无规则候选一律“未覆盖”，不得用 RNF 兜底。"""
    out = dict(result)
    out["confidence_breakdown"] = dict(result.get("confidence_breakdown") or {})
    if out.get("primary_type") is None:
        out["primary_type"] = "未覆盖"
        out["confidence"] = min(float(out.get("confidence") or 0.0), 0.4)
        out["confidence_breakdown"]["total"] = round(out["confidence"], 4)
        out["reason"] = "无规则命中，且 LLM 未给出可引用的归因"
    out["llm_used"] = False
    out["pending_llm"] = False
    out["confidence_breakdown"]["llm_decided"] = False
    return out


def merge_llm_attribution(
    base: dict[str, Any],
    attribution: Any,
    retrieval: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """把 LLM 归因合入规则结论。

    返回 `(result, accepted)`。规则已给出主类型（含“正常”）时，LLM 只能解释，
    不得改写主类型；只有规则无候选时，LLM 才可决定主类型。
    """
    out = dict(base)
    breakdown = dict(base.get("confidence_breakdown") or {})
    out["confidence_breakdown"] = breakdown
    rule_types = {hit["fault_type"] for hit in base.get("rule_hits", [])}
    valid_ids = {hit["entry_id"] for hit in retrieval.get("hits", []) if hit.get("entry_id")}
    evidence_ids = [item for item in attribution.evidence_entry_ids if item in valid_ids]
    llm_primary = attribution.primary_type

    if not evidence_ids and llm_primary != "未覆盖":
        return finalize_rule_only(base), False
    if llm_primary == "RNF" and not attribution.unattributable:
        return finalize_rule_only(base), False

    base_primary = base.get("primary_type")
    if rule_types or base_primary == "正常":
        primary = base_primary
        secondary = list(base.get("secondary_types") or [])
    else:
        primary = llm_primary
        secondary = list(attribution.secondary_types or [])
    secondary = [item for item in _unique(secondary) if item != primary][:3]

    base_self = float(breakdown.get("llm_self") or 0.5)
    llm_self = float(attribution.llm_self)
    if rule_types or base_primary == "正常":
        llm_self = min(llm_self, base_self + 0.05)

    recomputed = perimeter_confidence(
        rule_evidence=float(breakdown.get("rule") or 0.5),
        hit_count=len(retrieval.get("hits", [])),
        llm_self=llm_self,
        completeness=float(breakdown.get("completeness") or 1.0),
        penalties=float(breakdown.get("penalties") or 0.0),
        knowledge_missing=False,
    )
    recomputed["llm_decided"] = not (rule_types or base_primary == "正常")
    confidence = recomputed["total"]
    if primary in ("未覆盖", "RNF"):
        confidence = min(confidence, 0.4)
        recomputed["total"] = round(confidence, 4)

    reason = attribution.reason.strip()
    if primary == "RNF":
        reason = "不可归因（随机失效）：" + reason
    elif primary == "未覆盖":
        reason = reason or "知识库未覆盖，仅提供未验证假设与通用安全建议"

    out.update(
        {
            "primary_type": primary,
            "secondary_types": secondary,
            "confidence": confidence,
            "confidence_breakdown": recomputed,
            "reason": reason,
            "llm_used": True,
            "pending_llm": False,
            "llm_attribution": {
                "primary_type": llm_primary,
                "evidence_entry_ids": evidence_ids,
                "unattributable": bool(attribution.unattributable),
                "llm_self": llm_self,
            },
        }
    )
    return out, True


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def diagnose(
    features: dict[str, Any],
    flags: list[str],
    assumptions: list[str],
    retrieval: dict[str, Any],
    has_llm: bool = False,
) -> dict[str, Any]:
    """兼容入口：仅规则判定（LLM 接线由节点负责）。"""
    return finalize_rule_only(rule_diagnose(features, flags, assumptions, retrieval))


def evidence_refs(retrieval: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in retrieval.get("hits", []):
        evidence = hit.get("evidence")
        if evidence and evidence["entry_id"] not in seen:
            refs.append(evidence)
            seen.add(evidence["entry_id"])
    if not refs:
        for hit in retrieval.get("hits", [])[:3]:
            refs.append(
                {
                    "entry_id": hit["entry_id"],
                    "title": hit["title"],
                    "fault_type": hit["fault_type"],
                    "feature": "retrieval",
                    "value": hit["score"],
                    "unit": "score",
                }
            )
    return refs
