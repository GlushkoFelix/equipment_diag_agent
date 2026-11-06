"""字段映射校验预览与映射方案（ARCH §5.4.3）。"""

from __future__ import annotations

import json
import math
from typing import Any

from app import uploads
from app.db import Database, new_id, utcnow
from app.errors import ApiError

PREVIEW_ROWS = 3
FIRST_INVALID_LIMIT = 20


def _preview_entry(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_no": parsed["row_no"],
        "device_id": parsed["device_id"],
        "features": parsed["features"],
        "derived": parsed["derived"],
        "data_quality_flags": parsed["data_quality_flags"],
    }


def preview_mapping(db: Database, user_id: int, upload_id: str, body: dict[str, Any]) -> dict[str, Any]:
    upload = uploads.load_upload_row(db, user_id, upload_id)
    headers, data_rows = uploads.read_rows(upload)
    mapping = body.get("mapping") or {}
    default_device_id = body.get("default_device_id")
    mode = body["mode"]
    row_no = body.get("row_no")

    active, missing_required, errors = uploads.resolve_mapping(mapping, headers, default_device_id)
    if missing_required or errors:
        return {
            "valid": False,
            "missing_required": missing_required,
            "errors": errors,
            "preview": [],
            "row_summary": None,
        }

    if mode == "single":
        if not row_no or row_no < 1 or row_no > len(data_rows):
            raise ApiError(
                422,
                "VALIDATION_FAILED",
                "row_no 超出范围",
                details={"fields": [{"field": "row_no", "reason": "OUT_OF_RANGE"}]},
            )
        parsed = uploads.parse_data_row(
            headers, data_rows[row_no - 1], active, default_device_id, row_no
        )
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
        # 预览固定 3 行（不足 3 行则全部），单条与批量同一口径（ARCH §5.4.3）
        preview = [
            _preview_entry(
                uploads.parse_data_row(headers, data_rows[index], active, default_device_id, index + 1)
            )
            for index in range(min(PREVIEW_ROWS, len(data_rows)))
        ]
        return {
            "valid": True,
            "missing_required": [],
            "errors": [],
            "preview": preview,
            "row_summary": None,
        }

    # batch 模式：返回全量校验汇总与固定 3 行预览
    valid = 0
    first_invalid: list[dict[str, Any]] = []
    preview: list[dict[str, Any]] = []
    for index, raw in enumerate(data_rows):
        parsed = uploads.parse_data_row(headers, raw, active, default_device_id, index + 1)
        if parsed["error"]:
            if len(first_invalid) < FIRST_INVALID_LIMIT:
                first_invalid.append(
                    {
                        "row_no": parsed["row_no"],
                        "field": parsed["error"]["field"],
                        "code": parsed["error"]["code"],
                        "message": parsed["error"]["message"],
                    }
                )
        else:
            valid += 1
        if len(preview) < PREVIEW_ROWS:
            preview.append(_preview_entry(parsed))
    total = len(data_rows)
    return {
        "valid": valid > 0,
        "missing_required": [],
        "errors": [],
        "preview": preview,
        "row_summary": {
            "total": total,
            "valid": valid,
            "invalid": total - valid,
            "first_invalid": first_invalid,
        },
    }


def _scheme_out(row) -> dict[str, Any]:
    return {
        "mapping_id": row["mapping_id"],
        "name": row["name"],
        "header_signature": row["header_signature"],
        "mapping": json.loads(row["mapping_json"]),
        "default_device_id": row["default_device_id"],
        "updated_at": row["updated_at"],
    }


def list_schemes(db: Database, user_id: int, header_signature: str | None = None) -> dict[str, Any]:
    if header_signature:
        rows = db.connection().execute(
            "SELECT * FROM mapping_schemes WHERE user_id=? AND header_signature=? ORDER BY updated_at DESC",
            (user_id, header_signature),
        ).fetchall()
    else:
        rows = db.connection().execute(
            "SELECT * FROM mapping_schemes WHERE user_id=? ORDER BY updated_at DESC", (user_id,)
        ).fetchall()
    return {"items": [_scheme_out(row) for row in rows]}


def create_scheme(db: Database, user_id: int, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    name = body["name"]
    now = utcnow()
    existing = db.connection().execute(
        "SELECT * FROM mapping_schemes WHERE user_id=? AND name=?", (user_id, name)
    ).fetchone()
    payload = json.dumps(body["mapping"], ensure_ascii=False, separators=(",", ":"))
    default_device_id = body.get("default_device_id")
    if existing is not None:
        if not body.get("overwrite"):
            raise ApiError(409, "MAPPING_SCHEME_EXISTS", "同名映射方案已存在，如需覆盖请传 overwrite=true")
        db.connection().execute(
            "UPDATE mapping_schemes SET header_signature=?, mapping_json=?, default_device_id=?, updated_at=?"
            " WHERE mapping_id=?",
            (body["header_signature"], payload, default_device_id, now, existing["mapping_id"]),
        )
        row = db.connection().execute(
            "SELECT * FROM mapping_schemes WHERE mapping_id=?", (existing["mapping_id"],)
        ).fetchone()
        return 200, _scheme_out(row)
    mapping_id = new_id("map")
    db.connection().execute(
        "INSERT INTO mapping_schemes (mapping_id, user_id, name, header_signature, mapping_json,"
        " default_device_id, updated_at) VALUES (?,?,?,?,?,?,?)",
        (mapping_id, user_id, name, body["header_signature"], payload, default_device_id, now),
    )
    row = db.connection().execute(
        "SELECT * FROM mapping_schemes WHERE mapping_id=?", (mapping_id,)
    ).fetchone()
    return 201, _scheme_out(row)


def ceil_pages(total: int, page_size: int) -> int:
    return math.ceil(total / page_size) if total else 0
