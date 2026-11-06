"""健康检查与运行参数（ARCH §5.4.2）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app import security
from app.db import utcnow
from app.schemas.api import HealthResponse, SystemConfig

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request):
    state = request.app.state
    checks = state.self_check.components
    status = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {
        "status": status,
        "version": state.settings.version,
        "checked_at": utcnow(),
        "dependencies": checks,
    }


@router.get("/system/config", response_model=SystemConfig)
def system_config(request: Request, user: dict = Depends(security.current_user)):
    settings = request.app.state.settings
    return {
        "limits": {
            "upload_max_bytes": settings.upload_max_bytes,
            "csv_max_rows": settings.csv_max_rows,
            "page_size_default": settings.page_size_default,
            "page_size_max": settings.page_size_max,
            "device_id_max_length": settings.device_id_max_length,
        },
        "timeouts": {
            "global_timeout_seconds": int(settings.global_timeout_seconds),
            "interrupt_ttl_minutes": settings.interrupt_ttl_minutes,
            "batch_task_timeout_minutes": settings.batch_task_timeout_minutes,
            "llm_call_budget_seconds": int(settings.llm_call_budget_seconds),
            "llm_connect_timeout_seconds": int(settings.llm_connect_timeout_seconds),
        },
        "enums": {
            "input_types": ["csv_single", "csv_batch", "form", "nl", "chat"],
            "diagnosis_status": [
                "running",
                "waiting_human",
                "succeeded",
                "degraded",
                "degraded_review",
                "aborted",
                "failed",
                "failed_timeout",
                "expired",
            ],
            "batch_task_status": [
                "queued",
                "running",
                "completed",
                "partially_failed",
                "failed",
                "cancelled",
                "timed_out",
            ],
            "batch_row_status": [
                "pending",
                "running",
                "succeeded",
                "degraded",
                "degraded_review",
                "failed",
                "failed_timeout",
                "cancelled",
            ],
            "primary_types": ["正常", "TWF", "HDF", "PWF", "OSF", "RNF", "未覆盖"],
            "confidence_levels": ["high", "medium", "low"],
            "decisions": ["confirm", "supplement", "abort"],
        },
        "features": {"evaluation_web": True},
    }
