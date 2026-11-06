"""NL/chat 轻量抽取（规则优先；LLM 未配置时的可用路径）。"""

from __future__ import annotations

import re
from typing import Any

FEATURE_META = {
    "device_id": ("设备标识", None, "3号机"),
    "product_type": ("产品类型", None, "M"),
    "air_temp_k": ("空气温度", "K", 298.1),
    "process_temp_k": ("工艺温度", "K", 308.6),
    "rotational_speed_rpm": ("转速", "rpm", 1500),
    "torque_nm": ("扭矩", "Nm", 40),
    "tool_wear_min": ("刀具磨损", "min", 100),
}
NUMERIC_KEYS = ("air_temp_k", "process_temp_k", "rotational_speed_rpm", "torque_nm", "tool_wear_min")
QUALITATIVE = ("异响", "烫", "抖动", "振动", "噪声", "过热", "异味", "冒烟")

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def parse_number(token: str) -> float | None:
    token = token.strip().replace(",", "")
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        pass
    total = 0
    section = 0
    number = 0
    for char in token:
        if char in _CN_DIGITS:
            number = _CN_DIGITS[char]
        elif char in _CN_UNITS:
            unit = _CN_UNITS[char]
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = 0
            else:
                section += (number or 1) * unit
            number = 0
        else:
            return None
    return float(total + section + number)


def _match_number(text: str, pattern: str) -> tuple[float | None, dict[str, Any] | None]:
    match = re.search(pattern, text)
    if not match:
        return None, None
    value = parse_number(match.group(1))
    if value is None:
        return None, None
    return value, {
        "start": match.start(1),
        "end": match.end(1),
        "text": match.group(1),
    }


def _device_id(text: str, hint: str | None) -> tuple[str | None, dict[str, Any] | None]:
    if hint and hint.strip():
        start = text.find(hint.strip())
        return hint.strip(), ({"start": start, "end": start + len(hint.strip()), "text": hint.strip()} if start >= 0 else None)
    match = re.search(r"([0-9A-Za-z_\-\u4e00-\u9fff]{1,20}号机)", text)
    if not match:
        match = re.search(r"(?:设备|机台)\s*[:：]?\s*([A-Za-z0-9_\-\u4e00-\u9fff]{1,20})", text)
    if not match:
        return None, None
    return match.group(1), {"start": match.start(1), "end": match.end(1), "text": match.group(1)}


def _product_type(text: str) -> tuple[str | None, dict[str, Any] | None]:
    match = re.search(r"([LMH])\s*型", text) or re.search(r"产品类型\s*[:：]?\s*([LMH])", text)
    if not match:
        return None, None
    return match.group(1), {"start": match.start(1), "end": match.end(1), "text": match.group(1)}


def extract(text: str, device_id_hint: str | None = None) -> dict[str, Any]:
    features: dict[str, Any] = {key: None for key in FEATURE_META}
    field_confidence: dict[str, float] = {}
    spans: list[dict[str, Any]] = []

    device_id, span = _device_id(text, device_id_hint)
    features["device_id"] = device_id
    if device_id:
        field_confidence["device_id"] = 0.95
        if span:
            spans.append({"field": "device_id", **span})

    product_type, span = _product_type(text)
    features["product_type"] = product_type
    if product_type:
        field_confidence["product_type"] = 0.95
        if span:
            spans.append({"field": "product_type", **span})

    patterns = {
        "air_temp_k": r"(?:空气温度|空气)\s*[:：]?\s*(?:大概|约)?\s*([0-9]+(?:\.[0-9]+)?|[\u4e00-\u9fff]{1,6}?)\s*(?:K|k|开|度)",
        "process_temp_k": r"(?:工艺温度|加工温度|工艺)\s*[:：]?\s*(?:大概|约)?\s*([0-9]+(?:\.[0-9]+)?|[\u4e00-\u9fff]{1,6}?)\s*(?:K|k|开|度)",
        "rotational_speed_rpm": r"(?:主轴转速|转速)\s*[:：]?\s*(?:大概|约)?\s*([0-9]+(?:\.[0-9]+)?|[\u4e00-\u9fff]{1,6}?)\s*(?:rpm|转/分|转)?",
        "torque_nm": r"(?:扭矩|转矩)\s*[:：]?\s*(?:大概|约)?\s*([0-9]+(?:\.[0-9]+)?|[\u4e00-\u9fff]{1,6}?)\s*(?:Nm|N·m|牛米|牛·米|牛)?",
        "tool_wear_min": r"(?:刀具磨损|磨损)\s*[:：]?\s*(?:大概|约)?\s*([0-9]+(?:\.[0-9]+)?|[\u4e00-\u9fff]{1,6}?)\s*(?:min|分钟|分)?",
    }
    for key, pattern in patterns.items():
        value, span = _match_number(text, pattern)
        if value is not None:
            features[key] = value
            field_confidence[key] = 0.9
            spans.append({"field": key, **span})

    missing = [
        {"field": key, "label": meta[0], "unit": meta[1], "example": meta[2], "reason": "MISSING"}
        for key, meta in FEATURE_META.items()
        if features[key] is None
    ]
    extracted_count = sum(1 for value in features.values() if value is not None)
    if extracted_count == len(FEATURE_META):
        status, action = "ok", "confirm"
        message = "已抽取 7 项，请确认后开始诊断"
    elif extracted_count > 0:
        status, action = "partial", "clarify"
        message = f"已抽取 {extracted_count} 项，请确认后开始诊断"
    else:
        status, action = "failed", "use_form"
        message = "未能抽取有效特征，请改用手工表单"

    return {
        "extraction_status": status,
        "features": features,
        "missing_fields": missing,
        "recommended_action": action,
        "field_confidence": field_confidence,
        "source_spans": spans,
        "qualitative_cues": [cue for cue in QUALITATIVE if cue in text],
        "message": message,
    }
