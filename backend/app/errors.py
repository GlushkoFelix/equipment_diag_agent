"""统一错误码与 API 异常（ARCH §5.2）。"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}


def not_found(code: str, message: str) -> ApiError:
    return ApiError(404, code, message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def validation_error(message: str, fields: list[dict[str, Any]] | None = None) -> ApiError:
    details = {"fields": fields} if fields else None
    return ApiError(422, "VALIDATION_FAILED", message, details)
