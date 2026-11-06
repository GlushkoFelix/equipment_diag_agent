"""特征校验、标准化、派生特征与 input_fingerprint（ARCH §4.1、§5.4.6）。"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fff]+$")
PRODUCT_TYPES = ("L", "M", "H")
NUMERIC_FIELDS = (
    ("air_temp_k", "空气温度", "K", 250.0, 350.0, 298.1),
    ("process_temp_k", "工艺温度", "K", 250.0, 350.0, 308.6),
    ("rotational_speed_rpm", "转速", "rpm", 0.0, 3000.0, 1500),
    ("torque_nm", "扭矩", "Nm", 0.0, 100.0, 40),
    ("tool_wear_min", "刀具磨损", "min", 0.0, 300.0, 100),
)
ALL_FEATURE_FIELDS = ("product_type",) + tuple(f[0] for f in NUMERIC_FIELDS)
# 可缺失字段：device_id 之外的全部字段（ARCH §5.4.6）
OPTIONAL_FIELDS = ALL_FEATURE_FIELDS
PARTIAL_ALLOWED_INPUT_TYPES = {"nl", "chat"}


@dataclass
class FieldError:
    field: str
    reason: str
    message: str
    label: str = ""
    unit: str | None = None
    example: Any = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "label": self.label,
            "unit": self.unit,
            "reason": self.reason,
            "example": self.example,
            "message": self.message,
        }


@dataclass
class NormalizeResult:
    ok: bool
    normalized: dict[str, Any] = field(default_factory=dict)
    derived: dict[str, float] = field(default_factory=dict)
    missing_fields: list[dict[str, Any]] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    data_quality_flags: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    completeness: float = 0.0
    input_fingerprint: str | None = None
    error_code: str | None = None
    normalized_text: str = ""

    @property
    def fingerprint(self) -> str | None:
        return self.input_fingerprint


def device_id_error(value: Any) -> FieldError | None:
    if not isinstance(value, str):
        return FieldError("device_id", "MISSING", "设备标识必填", "设备标识")
    text = value.strip()
    if not (1 <= len(text) <= 64) or not DEVICE_ID_PATTERN.match(text):
        return FieldError(
            "device_id", "INVALID", "设备标识需为 1–64 位字母、数字、下划线、连字符或中文", "设备标识"
        )
    return None


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    value = unicodedata.normalize("NFC", text)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def q3(value: float) -> str:
    return format(Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP), "f")


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalize_input(input_type: str, payload: dict[str, Any]) -> NormalizeResult:
    """按入口校验并标准化；不填默认值（禁止把缺失当 M 型）。"""
    result = NormalizeResult(ok=False)
    raw_device_id = payload.get("device_id")
    dev_error = device_id_error(raw_device_id)
    if dev_error is not None:
        result.error_code = "DEVICE_ID_INVALID"
        result.fields = [dev_error.as_dict()]
        return result

    normalized: dict[str, Any] = {"device_id": raw_device_id.strip()}
    missing: list[FieldError] = []
    field_errors: list[FieldError] = []
    quality_flags: list[str] = []

    product_type = payload.get("product_type")
    if product_type is None:
        missing.append(FieldError("product_type", "MISSING", "产品类型缺失", "产品类型", None, "M"))
    elif product_type not in PRODUCT_TYPES:
        field_errors.append(
            FieldError("product_type", "INVALID", "产品类型仅允许 L/M/H", "产品类型", None, "M")
        )
    else:
        normalized["product_type"] = product_type

    provided = 0
    for name, label, unit, low, high, example in NUMERIC_FIELDS:
        value = payload.get(name)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            missing.append(FieldError(name, "MISSING", f"{label}缺失", label, unit, example))
            continue
        if not _is_finite_number(value):
            field_errors.append(
                FieldError(name, "INVALID", f"{label}必须为有限数值", label, unit, example)
            )
            continue
        if not (low <= float(value) <= high):
            field_errors.append(
                FieldError(
                    name,
                    "OUT_OF_RANGE",
                    f"{label}允许范围 {low:g}–{high:g} {unit}，实际 {value}",
                    label,
                    unit,
                    example,
                )
            )
            continue
        normalized[name] = float(value) if name in ("air_temp_k", "process_temp_k") else float(value)
        provided += 1

    result.missing_fields = [m.as_dict() for m in missing]
    result.completeness = provided / len(NUMERIC_FIELDS) if "product_type" not in normalized else (
        (provided + 1) / (len(NUMERIC_FIELDS) + 1)
    )
    if missing or field_errors:
        complete = not missing and not field_errors
    else:
        complete = True

    # 数值型字段错误优先返回字段错误，不把非法值当缺失
    if field_errors:
        result.fields = [f.as_dict() for f in field_errors]
        if any(f.reason == "OUT_OF_RANGE" for f in field_errors):
            result.error_code = "FEATURE_OUT_OF_RANGE"
        else:
            result.error_code = "FIELD_INVALID"
        return result

    # 跨字段矛盾（仅在两值均给出时判定）
    rpm = normalized.get("rotational_speed_rpm")
    torque = normalized.get("torque_nm")
    if rpm is not None and torque is not None:
        if rpm == 0 and torque == 0:
            result.error_code = "MACHINE_STOPPED"
            result.fields = [
                FieldError(
                    "rotational_speed_rpm", "CONTRADICTION", "转速与扭矩同时为 0，设备处于停机状态", "转速", "rpm", 1500
                ).as_dict()
            ]
            return result
        if rpm == 0 and torque > 0:
            result.error_code = "DATA_CONTRADICTION"
            result.fields = [
                FieldError(
                    "rotational_speed_rpm", "CONTRADICTION", "转速为 0 但扭矩大于 0，数据矛盾", "转速", "rpm", 1500
                ).as_dict()
            ]
            return result
        if torque == 0 and rpm > 0:
            quality_flags.append("ZERO_LOAD")

    air = normalized.get("air_temp_k")
    process = normalized.get("process_temp_k")
    if air is not None and process is not None and process < air:
        quality_flags.append("TEMP_INVERSION")

    result.normalized = normalized
    result.derived = derive_features(normalized)
    result.data_quality_flags = quality_flags

    if not complete:
        # 单条 CSV/表单在 API 前置必须阻断；nl/chat 允许部分创建并进入 clarify
        if input_type in PARTIAL_ALLOWED_INPUT_TYPES:
            result.ok = True
        else:
            result.ok = False
            result.error_code = "VALIDATION_FAILED"
        result.fields = result.missing_fields
        return result

    result.ok = True
    result.normalized_text = normalize_text(payload.get("text"))
    result.input_fingerprint = compute_fingerprint(
        payload.get("_user_id", 0), input_type, normalized, result.normalized_text
    )
    return result


def derive_features(normalized: dict[str, Any]) -> dict[str, float]:
    derived: dict[str, float] = {}
    air = normalized.get("air_temp_k")
    process = normalized.get("process_temp_k")
    rpm = normalized.get("rotational_speed_rpm")
    torque = normalized.get("torque_nm")
    wear = normalized.get("tool_wear_min")
    if air is not None and process is not None:
        derived["temp_diff"] = round(float(process) - float(air), 3)
    if rpm is not None and torque is not None:
        derived["power_w"] = round(float(torque) * float(rpm) * 2 * math.pi / 60, 3)
    if wear is not None and torque is not None:
        derived["wear_torque"] = round(float(wear) * float(torque), 3)
    return derived


def compute_fingerprint(
    user_id: int, input_type: str, normalized: dict[str, Any], normalized_text: str = ""
) -> str | None:
    """RT-17 指纹；输入不完整返回 None（ARCH §4.1.1）。"""
    required = ("product_type",) + tuple(f[0] for f in NUMERIC_FIELDS)
    if any(normalized.get(name) is None for name in required):
        return None
    payload = {
        "fp_version": 1,
        "user_id": int(user_id),
        "input_type": input_type,
        "device_id": normalize_text(normalized.get("device_id")),
        "product_type": normalized.get("product_type"),
        "air_temp_k": q3(normalized["air_temp_k"]),
        "process_temp_k": q3(normalized["process_temp_k"]),
        "rotational_speed_rpm": q3(normalized["rotational_speed_rpm"]),
        "torque_nm": q3(normalized["torque_nm"]),
        "tool_wear_min": q3(normalized["tool_wear_min"]),
        "normalized_text": normalize_text(normalized_text),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
