"""CSV 上传预检、映射解析与行读取（ARCH §5.4.3 / §5.4.6）。"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

from app import features as features_domain
from app.config import Settings
from app.db import Database, new_id, utcnow
from app.errors import ApiError

STANDARD_KEYS = (
    "device_id",
    "product_type",
    "air_temp_k",
    "process_temp_k",
    "rotational_speed_rpm",
    "torque_nm",
    "tool_wear_min",
)
# AI4I 2020 数据集列名（本地资产默认建议）
DEFAULT_MAPPING = {
    "device_id": "Product ID",
    "product_type": "Type",
    "air_temp_k": "Air temperature [K]",
    "process_temp_k": "Process temperature [K]",
    "rotational_speed_rpm": "Rotational speed [rpm]",
    "torque_nm": "Torque [Nm]",
    "tool_wear_min": "Tool wear [min]",
}

# 表头建议匹配别名（归一化后比较：小写、去空白与标点）
_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "device_id": ("deviceid", "device", "productid", "产品id", "设备id", "设备标识", "机台", "设备编号"),
    "product_type": ("producttype", "type", "产品类型", "类型"),
    "air_temp_k": ("airtemperaturek", "airtemperature", "airtemp", "空气温度", "空温"),
    "process_temp_k": ("processtemperaturek", "processtemperature", "processtemp", "工艺温度", "加工温度", "工温"),
    "rotational_speed_rpm": ("rotationalspeedrpm", "rotationalspeed", "rpm", "转速", "主轴转速"),
    "torque_nm": ("torquenm", "torque", "扭矩", "转矩"),
    "tool_wear_min": ("toolwearmin", "toolwear", "刀具磨损", "磨损"),
}


def _normalize_header(value: str) -> str:
    return re.sub(r"[\s\-_./\\()\[\]〔〕（）·:：,，]+", "", value.strip().lower())


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    """按列名相似度为 7 个标准键给出建议映射（仅建议，仍需用户确认）。"""
    normalized = {header: _normalize_header(header) for header in headers}
    suggestion: dict[str, str | None] = {}
    for key, aliases in _HEADER_ALIASES.items():
        match = None
        for alias in aliases:
            for header, norm in normalized.items():
                if norm == alias or norm.startswith(alias) or alias.startswith(norm) and norm:
                    match = header
                    break
            if match:
                break
        suggestion[key] = match
    return suggestion


def header_signature(headers: list[str]) -> str:
    """表头去空格后按原顺序 JSON 序列化并 SHA-256（ARCH §5.4.3）。"""
    canonical = json.dumps([header.strip() for header in headers], ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _decode(content: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return content.decode(encoding), "utf-8" if encoding == "utf-8-sig" else "gbk"
        except UnicodeDecodeError:
            continue
    raise ApiError(422, "FILE_ENCODING_UNSUPPORTED", "文件编码不支持，请另存为 UTF-8 或 GBK")


def _split_rows(text: str) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ApiError(422, "FILE_EMPTY", "文件没有表头")
    headers = [cell.strip() for cell in rows[0]]
    if not headers or any(not h for h in headers) or len(set(headers)) != len(headers):
        raise ApiError(422, "CSV_HEADER_INVALID", "表头为空、重复或错位")
    data_rows = [row for row in rows[1:] if any(cell.strip() for cell in row)]
    return headers, data_rows


def matched_scheme(db: Database, user_id: int, signature: str) -> dict[str, Any] | None:
    row = db.connection().execute(
        "SELECT * FROM mapping_schemes WHERE user_id=? AND header_signature=? ORDER BY updated_at DESC LIMIT 1",
        (user_id, signature),
    ).fetchone()
    if row is None:
        return None
    return {
        "mapping_id": row["mapping_id"],
        "name": row["name"],
        "header_signature": row["header_signature"],
        "mapping": json.loads(row["mapping_json"]),
        "default_device_id": row["default_device_id"],
        "updated_at": row["updated_at"],
    }


def build_upload_payload(
    db: Database,
    user_id: int,
    *,
    upload_id: str,
    file_name: str,
    size_bytes: int,
    encoding: str,
    headers: list[str],
    data_rows: list[list[str]],
    signature: str,
) -> dict[str, Any]:
    preview_rows = [
        {header: (row[i].strip() if i < len(row) else "") for i, header in enumerate(headers)}
        for row in data_rows[:5]
    ]
    scheme = matched_scheme(db, user_id, signature)
    suggestion = dict(scheme["mapping"]) if scheme else suggest_mapping(headers)
    return {
        "upload_id": upload_id,
        "file_name": file_name,
        "size_bytes": size_bytes,
        "encoding": encoding,
        "row_count": len(data_rows),
        "headers": headers,
        "preview_rows": preview_rows,
        "header_signature": signature,
        "suggested_mapping": suggestion,
        "matched_scheme": scheme,
        "issues": [],
    }


def save_upload(
    db: Database, settings: Settings, user_id: int, filename: str, content: bytes
) -> dict[str, Any]:
    if not filename.lower().endswith(".csv"):
        raise ApiError(415, "FILE_TYPE_NOT_ALLOWED", "仅支持 .csv 文件")
    if len(content) == 0:
        raise ApiError(422, "FILE_EMPTY", "文件为空")
    if len(content) > settings.upload_max_bytes:
        raise ApiError(413, "FILE_TOO_LARGE", "文件超过 5MB 上限")
    text, encoding = _decode(content)
    headers, data_rows = _split_rows(text)
    if not data_rows:
        raise ApiError(422, "FILE_EMPTY", "文件没有数据行")
    if len(data_rows) > settings.csv_max_rows:
        raise ApiError(422, "CSV_ROW_LIMIT_EXCEEDED", f"CSV 数据行最多 {settings.csv_max_rows} 行")

    upload_id = new_id("up")
    safe_name = re.sub(r"[^A-Za-z0-9_.\-\u4e00-\u9fff]", "_", Path(filename).name)[:120]
    stored = Path(settings.upload_dir) / f"{upload_id}_{safe_name}"
    stored.write_bytes(content)
    signature = header_signature(headers)
    db.connection().execute(
        "INSERT INTO uploads (upload_id, user_id, original_name, stored_path, size_bytes, encoding,"
        " row_count, headers_json, header_signature, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            upload_id,
            user_id,
            safe_name,
            str(stored),
            len(content),
            encoding,
            len(data_rows),
            json.dumps(headers, ensure_ascii=False),
            signature,
            utcnow(),
        ),
    )
    return build_upload_payload(
        db,
        user_id,
        upload_id=upload_id,
        file_name=safe_name,
        size_bytes=len(content),
        encoding=encoding,
        headers=headers,
        data_rows=data_rows,
        signature=signature,
    )


def load_upload_row(db: Database, user_id: int, upload_id: str):
    row = db.connection().execute(
        "SELECT * FROM uploads WHERE upload_id=? AND user_id=?", (upload_id, user_id)
    ).fetchone()
    if row is None:
        raise ApiError(404, "UPLOAD_NOT_FOUND", "上传不存在或无权访问")
    return row


def get_upload(db: Database, user_id: int, upload_id: str) -> dict[str, Any]:
    row = load_upload_row(db, user_id, upload_id)
    headers, data_rows = read_rows(row)
    return build_upload_payload(
        db,
        user_id,
        upload_id=row["upload_id"],
        file_name=row["original_name"],
        size_bytes=row["size_bytes"],
        encoding=row["encoding"],
        headers=headers,
        data_rows=data_rows,
        signature=row["header_signature"],
    )


def read_rows(upload_row) -> tuple[list[str], list[list[str]]]:
    headers = json.loads(upload_row["headers_json"])
    text, _ = _decode(Path(upload_row["stored_path"]).read_bytes())
    _, data_rows = _split_rows(text)
    return headers, data_rows


def resolve_mapping(
    mapping: dict[str, Any] | None, headers: list[str], default_device_id: str | None
) -> tuple[dict[str, str | None], list[str], list[dict[str, Any]]]:
    """校验映射；返回 (生效映射, 缺失必填键, 错误列表)。

    ARCH §5.4.3：device_id 列可为 null，但此时必须提供 default_device_id。
    """
    active = dict(mapping or DEFAULT_MAPPING)
    has_default_device = bool((default_device_id or "").strip())
    missing_required: list[str] = []
    for key in STANDARD_KEYS:
        if active.get(key):
            continue
        if key == "device_id" and has_default_device:
            continue
        missing_required.append(key)
    errors: list[dict[str, Any]] = []
    for key in STANDARD_KEYS:
        column = active.get(key)
        if column and column not in headers:
            errors.append(
                {
                    "code": "MAPPING_CONFLICT",
                    "message": f"映射列不存在：{column}",
                    "column": column,
                    "row_no": None,
                }
            )
    return active, missing_required, errors


def parse_data_row(
    headers: list[str],
    raw: list[str],
    active_mapping: dict[str, str | None],
    default_device_id: str | None,
    row_no: int,
) -> dict[str, Any]:
    """把一行 CSV 转成标准特征；返回含 error 的解析结果（不抛异常）。"""
    index = {header: i for i, header in enumerate(headers)}

    def cell(key: str) -> str:
        column = active_mapping.get(key)
        if not column or column not in index:
            return ""
        idx = index[column]
        return raw[idx].strip() if idx < len(raw) else ""

    # 行级设备标识优先于批次统一值（ARCH §5.4.3）
    device_id = cell("device_id") or (default_device_id or "").strip() or None
    payload: dict[str, Any] = {"device_id": device_id, "product_type": cell("product_type") or None}
    for key in STANDARD_KEYS[2:]:
        raw_value = cell(key)
        if raw_value == "":
            payload[key] = None
            continue
        try:
            payload[key] = float(raw_value)
        except ValueError:
            return {
                "row_no": row_no,
                "device_id": device_id,
                "features": {},
                "derived": {},
                "data_quality_flags": [],
                "error": {
                    "field": key,
                    "code": "FIELD_INVALID",
                    "message": f"第 {row_no} 行 {key} 不是数值：{raw_value}",
                },
            }

    result = features_domain.normalize_input("csv_single", payload)
    if not result.ok:
        first = (result.fields or result.missing_fields or [{}])[0]
        return {
            "row_no": row_no,
            "device_id": device_id,
            "features": {},
            "derived": {},
            "data_quality_flags": [],
            "error": {
                "field": first.get("field"),
                "code": result.error_code or "VALIDATION_FAILED",
                "message": first.get("message") or "字段校验失败",
            },
        }
    return {
        "row_no": row_no,
        "device_id": result.normalized.get("device_id"),
        "features": result.normalized,
        "derived": result.derived,
        "data_quality_flags": result.data_quality_flags,
        "error": None,
        "normalized": result,
        "raw_input": payload,
    }


def read_csv_row(
    db: Database,
    user_id: int,
    upload_id: str,
    row_no: int,
    mapping: dict[str, str] | None,
    default_device_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    upload = load_upload_row(db, user_id, upload_id)
    headers, data_rows = read_rows(upload)
    active_mapping, missing_required, errors = resolve_mapping(mapping, headers, default_device_id)
    if missing_required:
        raise ApiError(
            422,
            "MAPPING_MISSING_REQUIRED",
            "映射缺少必填列",
            details={"fields": [{"field": key, "reason": "MISSING"} for key in missing_required]},
        )
    if errors:
        raise ApiError(
            422,
            "MAPPING_CONFLICT",
            errors[0]["message"],
            details={"fields": [{"field": "mapping", "reason": "COLUMN_NOT_FOUND"}]},
        )
    if row_no < 1 or row_no > len(data_rows):
        raise ApiError(
            422,
            "VALIDATION_FAILED",
            "行号超出范围",
            details={"fields": [{"field": "row_no", "reason": "OUT_OF_RANGE"}]},
        )
    parsed = parse_data_row(headers, data_rows[row_no - 1], active_mapping, default_device_id, row_no)
    if parsed["error"]:
        raise ApiError(
            422,
            parsed["error"]["code"],
            parsed["error"]["message"],
            details={
                "fields": [
                    {
                        "field": parsed["error"]["field"],
                        "reason": parsed["error"]["code"],
                        "message": parsed["error"]["message"],
                    }
                ]
            },
        )
    summary = {"file_name": upload["original_name"], "row_no": row_no}
    return parsed["raw_input"], summary
