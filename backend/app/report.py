"""报告生成、8 要素自检与安全过滤（ARCH §4.5 / §5.4.6）。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.text_guard import load_sensitive_words, mask_sensitive_words

ELEMENTS = (
    "结论",
    "置信度",
    "关键特征",
    "判断依据",
    "鉴别诊断",
    "维修建议",
    "数据质量与假设",
    "免责声明",
)
DISCLAIMER = (
    "> 本报告由设备故障诊断智能体基于输入数据与知识库条目自动生成，"
    "仅用于辅助判断，不替代现场检修与设备厂商的技术结论。"
)
MAINTENANCE = {
    "HDF": "检查冷却液流量与温度、散热风扇与风道滤网，复核低转速工况设置。",
    "PWF": "检查供电电压/电流波形、驱动模块告警与使能信号，核对扭矩与转速采样同步。",
    "OSF": "降低切削负载，核对产品类型过载阈值，检查刀具与主轴应力状态。",
    "TWF": "按刀具寿命台账安排换刀，检查刃口崩刃与工件表面质量，复测振动与扭矩。",
    "正常": "保持当前工况，按计划点检温度、转速、功率与刀具磨损趋势。",
    "未覆盖": "知识库未覆盖当前工况，请按设备手册执行通用安全检查并补充特征后重新诊断。",
}
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_KB_ID = re.compile(r"KB-[A-Za-z0-9_-]+")


# AC-RP-05：中/低置信度报告须显式给出“建议人工复核”提示
CONFIDENCE_NAMES = {"high": "高", "medium": "中等", "low": "低"}
REVIEW_HINT = "，建议人工复核"


def confidence_label(level: str, confidence: float) -> str:
    name = CONFIDENCE_NAMES.get(level, "低")
    label = f"{name}置信度（{confidence:.2f}）"
    if level in ("medium", "low"):
        label += REVIEW_HINT
    return label


def build_report(
    *,
    diagnosis_id: str,
    device_id: str,
    features: dict[str, Any],
    derived: dict[str, Any],
    flags: list[str],
    assumptions: list[str],
    diagnosis: dict[str, Any],
    retrieval: dict[str, Any],
    evidence: list[dict[str, Any]],
    auto_review: bool,
    human_confirmed: bool,
    kb_version: str,
    generated_at: str | None = None,
    narrative: dict[str, Any] | None = None,
    prompt_version: str = "reporter-v1",
    model_name: str = "rule-engine",
    llm_used: bool = False,
    llm_calls: int = 0,
    sensitive_words: list[str] | None = None,
    sensitive_words_path: Path | str | None = None,
) -> dict[str, Any]:
    primary = diagnosis["primary_type"]
    confidence = float(diagnosis["confidence"])
    level = "high" if confidence >= 0.8 else ("medium" if confidence >= 0.5 else "low")
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    title = f"{device_id} {primary} 诊断报告"

    citations = "、".join(f"{e['entry_id']}《{e['title']}》" for e in evidence) or "无（知识库未覆盖）"
    secondary = diagnosis.get("secondary_types") or []
    secondary_text = "；".join(secondary) if secondary else "无"
    quality = []
    if flags:
        quality.append("数据质量标记：" + "、".join(flags))
    if assumptions:
        quality.append("假设：" + "、".join(assumptions))
    if not quality:
        quality.append("数据完整，未触发质量标记或假设。")
    if "TEMP_INVERSION" in flags:
        quality.append("工艺温度低于空气温度（温差倒挂），HDF 规则不生效并已扣减置信度。")

    confidence_text = confidence_label(level, confidence)
    if auto_review:
        confidence_text += "，待人工复核（批量模式）"
    if human_confirmed:
        confidence_text += "，已人工确认"

    allowed_ids = {entry["entry_id"] for entry in evidence}
    allowed_numbers = _collect_numbers([features, derived, diagnosis, retrieval, evidence])
    safe = _safe_narrative(narrative, allowed_numbers, allowed_ids)
    if diagnosis.get("knowledge_status") == "missing":
        # 知识未覆盖时不允许 LLM 给出确定性维修步骤
        safe.pop("maintenance", None)

    conclusion = safe.get("conclusion") or diagnosis.get("reason", "")
    evidence_explanation = safe.get("evidence_explanation")
    differential = safe.get("differential")
    maintenance = safe.get("maintenance") or MAINTENANCE.get(primary, MAINTENANCE["未覆盖"])

    lines = [
        f"# {title}",
        "",
        "## 结论",
        f"主类型：{primary}。" + conclusion,
        "",
        "## 置信度",
        confidence_text,
        "",
        "## 关键特征",
        f"- 空气温度：{features.get('air_temp_k')} K",
        f"- 工艺温度：{features.get('process_temp_k')} K",
        f"- 温差：{derived.get('temp_diff')} K",
        f"- 转速：{features.get('rotational_speed_rpm')} rpm",
        f"- 扭矩：{features.get('torque_nm')} Nm",
        f"- 功率：{derived.get('power_w')} W",
        f"- 刀具磨损：{features.get('tool_wear_min')} min",
        f"- 磨损×扭矩：{derived.get('wear_torque')} Nm·min",
        "",
        "## 判断依据",
        f"引用知识条目：{citations}。",
        f"规则命中：{'；'.join(h['reason'] for h in diagnosis.get('rule_hits', [])) or '无'}。",
        *([f"归因说明：{evidence_explanation}"] if evidence_explanation else []),
        "",
        "## 鉴别诊断",
        f"候选类型：{secondary_text}。" + (f"{differential}" if differential else ""),
        "",
        "## 维修建议",
        maintenance,
        "",
        "## 数据质量与假设",
        "\n".join(f"- {item}" for item in quality),
        "",
        "## 免责声明",
        DISCLAIMER,
    ]
    markdown = "\n".join(lines).strip() + "\n"
    markdown = sanitize_markdown(
        markdown, sensitive_words=sensitive_words, sensitive_words_path=sensitive_words_path
    )
    check = check_report(markdown, evidence, diagnosis)
    meta = {
        "template_version": "report.md.j2-v1",
        "prompt_version": prompt_version,
        "kb_version": kb_version,
        "model_name": model_name,
        "llm_used": llm_used,
        "llm_calls": llm_calls,
        "narrative_fields": sorted(safe.keys()),
        "auto_review": auto_review,
        "human_confirmed": human_confirmed,
        "generated_at": generated_at,
        "degraded_reasons": list(flags),
        "report_retry_count": 0,
    }
    return {
        "title": title,
        "markdown": markdown,
        "elements_check": check,
        "meta": meta,
    }


_NARRATIVE_LIMITS = {
    "conclusion": 400,
    "evidence_explanation": 600,
    "differential": 400,
    "maintenance": 600,
}


def _collect_numbers(bundle: list[Any]) -> set[float]:
    values: set[float] = set()

    def walk(value: Any) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            values.add(round(float(value), 6))
        elif isinstance(value, str):
            for token in _NUMBER.findall(value):
                try:
                    values.add(round(float(token), 6))
                except ValueError:
                    continue
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for node in bundle:
        walk(node)
    return values


def _safe_narrative(
    narrative: dict[str, Any] | None,
    allowed_numbers: set[float],
    allowed_ids: set[str],
) -> dict[str, str]:
    """LLM 文本守卫：超长、引用不存在的条目、出现输入外数值或 HTML 时整段丢弃。"""
    if not narrative:
        return {}
    safe: dict[str, str] = {}
    for key, limit in _NARRATIVE_LIMITS.items():
        raw = narrative.get(key)
        if not isinstance(raw, str):
            continue
        text = " ".join(raw.split()).strip()
        if not text or len(text) > limit:
            continue
        if "<" in text or "```" in text or text.startswith("#"):
            continue
        if any(entry_id not in allowed_ids for entry_id in _KB_ID.findall(text)):
            continue
        numbers_ok = True
        for token in _NUMBER.findall(text):
            try:
                if round(float(token), 6) not in allowed_numbers:
                    numbers_ok = False
                    break
            except ValueError:
                numbers_ok = False
                break
        if numbers_ok:
            safe[key] = text
    return safe


def sanitize_markdown(
    markdown: str,
    *,
    sensitive_words: list[str] | None = None,
    sensitive_words_path: Path | str | None = None,
) -> str:
    cleaned = re.sub(r"<script.*?>.*?</script>", "", markdown, flags=re.S | re.I)
    cleaned = re.sub(r"<iframe.*?>.*?</iframe>", "", cleaned, flags=re.S | re.I)
    cleaned = re.sub(r"<(?!br\b)[a-zA-Z][^>]*>", "", cleaned)
    words = sensitive_words if sensitive_words is not None else load_sensitive_words(sensitive_words_path)
    cleaned, _hits = mask_sensitive_words(cleaned, words, scene="report")
    if DISCLAIMER not in cleaned:
        cleaned = cleaned.rstrip() + "\n\n" + DISCLAIMER + "\n"
    return cleaned


def check_report(markdown: str, evidence: list[dict[str, Any]], diagnosis: dict[str, Any]) -> dict[str, Any]:
    present: list[str] = []
    missing: list[str] = []
    for name in ELEMENTS:
        match = re.search(rf"^## {re.escape(name)}\s*\n(.+?)(?=\n## |\Z)", markdown, flags=re.S | re.M)
        if match and match.group(1).strip():
            present.append(name)
        else:
            missing.append(name)
    if diagnosis.get("knowledge_status") == "supported" and not evidence:
        missing.append("引用")
    if diagnosis.get("confidence") is not None:
        level = "high" if diagnosis["confidence"] >= 0.8 else ("medium" if diagnosis["confidence"] >= 0.5 else "low")
        if f"{CONFIDENCE_NAMES[level]}置信度" not in markdown:
            missing.append("置信度一致性")
    if "<script" in markdown.lower():
        missing.append("无原始 HTML")
    return {
        "passed": len(missing) == 0,
        "present": present,
        "missing": missing,
        "report_retry_count": 0,
    }


def fix_report(markdown: str, check: dict[str, Any]) -> str:
    """仅补结构与免责声明，不臆造事实；一次修复。"""
    if not check.get("missing"):
        return markdown
    patched = markdown
    if "免责声明" in check["missing"]:
        patched = patched.rstrip() + "\n\n## 免责声明\n" + DISCLAIMER + "\n"
    return sanitize_markdown(patched)


def prepend_missing_note(markdown: str, missing: list[str]) -> str:
    """AC-DG-17：修复后仍缺项时，在报告顶部显式列出缺失要素。"""
    if not missing:
        return markdown
    note = "> 报告自检未通过，缺少要素：" + "、".join(missing) + "。以下内容按降级模板输出。"
    if markdown.startswith(note):
        return markdown
    return note + "\n\n" + markdown
