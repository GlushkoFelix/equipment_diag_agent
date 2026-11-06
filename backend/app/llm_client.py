"""LLM 适配器（ARCH §7.6 / §3.8）。

- OpenAI 兼容 HTTPS，默认 `https://api.deepseek.com` + `deepseek-chat`；
- 连接超时 2s，单次总预算 `min(5s, remaining)`，失败重试 1 次（指数退避）；
- `response_format=json_object` + Pydantic 校验；非法输出仍失败则抛错，由调用方规则兜底；
- Key 只从 `.env` 读取；日志只记录 hash、模型、耗时、token，不记录 prompt 与 Key。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings

logger = logging.getLogger("edg.llm")

MAX_ATTEMPTS = 2  # 首次 + 1 次重试
_BACKOFF_BASE = 0.3


class LlmError(Exception):
    """LLM 调用失败基类；`code` 与 ARCH 错误码对齐。"""

    code = "LLM_UPSTREAM_ERROR"

    def __init__(self, message: str = "", *, attempts: int = 0):
        super().__init__(message)
        self.message = message
        self.attempts = attempts


class LlmNotConfigured(LlmError):
    code = "LLM_NOT_CONFIGURED"


class LlmTimeout(LlmError):
    code = "LLM_TIMEOUT"


class LlmUpstreamError(LlmError):
    code = "LLM_UPSTREAM_ERROR"


class LlmInvalidOutput(LlmError):
    code = "LLM_INVALID_OUTPUT"


@dataclass
class LlmCallResult:
    payload: BaseModel
    model: str
    latency_ms: int
    attempts: int
    total_tokens: int | None
    prompt_sha256: str


class LlmClient(Protocol):
    model_name: str

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        temperature: float,
        max_tokens: int,
        budget: float,
    ) -> LlmCallResult: ...


def _prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()[:16]


class DeepSeekClient:
    """DeepSeek OpenAI 兼容客户端；不缓存、不落库、不记录 prompt 全文。"""

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.model_name = settings.deepseek_model
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        temperature: float,
        max_tokens: int,
        budget: float,
    ) -> LlmCallResult:
        if not self.settings.deepseek_api_key:
            raise LlmNotConfigured("未配置 DEEPSEEK_API_KEY")

        total_budget = min(float(budget), float(self.settings.llm_call_budget_seconds))
        if total_budget <= 0.1:
            raise LlmTimeout("LLM 预算不足")
        deadline = time.monotonic() + total_budget
        digest = _prompt_hash(system, user)
        last_error: LlmError = LlmTimeout("LLM 预算耗尽")

        for attempt in range(1, MAX_ATTEMPTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0.05:
                break
            started = time.monotonic()
            try:
                timeout = httpx.Timeout(
                    remaining,
                    connect=min(float(self.settings.llm_connect_timeout_seconds), remaining),
                )
                async with httpx.AsyncClient(
                    base_url=self.settings.deepseek_base_url.rstrip("/"),
                    timeout=timeout,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        "/chat/completions",
                        headers=self._headers(),
                        json={
                            "model": self.settings.deepseek_model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                            ],
                            "response_format": {"type": "json_object"},
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        },
                    )
                latency = int((time.monotonic() - started) * 1000)

                if response.status_code == 429 or response.status_code >= 500:
                    last_error = LlmUpstreamError(
                        f"上游返回 {response.status_code}", attempts=attempt
                    )
                elif response.status_code >= 400:
                    last_error = LlmUpstreamError(
                        f"上游拒绝请求 {response.status_code}", attempts=attempt
                    )
                    break  # 认证/参数错误重试无意义
                else:
                    body = response.json()
                    content = body["choices"][0]["message"]["content"]
                    data = json.loads(content)
                    if not isinstance(data, dict):
                        raise ValueError("LLM 输出不是 JSON 对象")
                    payload = schema.model_validate(data)
                    usage = body.get("usage") or {}
                    logger.info(
                        "llm_call status=ok model=%s prompt_sha256=%s latency_ms=%s attempts=%s tokens=%s",
                        self.settings.deepseek_model,
                        digest,
                        latency,
                        attempt,
                        usage.get("total_tokens"),
                    )
                    return LlmCallResult(
                        payload=payload,
                        model=self.settings.deepseek_model,
                        latency_ms=latency,
                        attempts=attempt,
                        total_tokens=usage.get("total_tokens"),
                        prompt_sha256=digest,
                    )
            except (httpx.TimeoutException, asyncio.TimeoutError):
                last_error = LlmTimeout("LLM 调用超时", attempts=attempt)
            except httpx.TransportError as exc:
                last_error = LlmUpstreamError(
                    f"LLM 连接失败：{type(exc).__name__}", attempts=attempt
                )
            except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
                last_error = LlmInvalidOutput(
                    f"LLM 输出校验失败：{type(exc).__name__}", attempts=attempt
                )
            except LlmError:
                raise

            logger.warning(
                "llm_call status=error code=%s model=%s prompt_sha256=%s attempt=%s",
                last_error.code,
                self.settings.deepseek_model,
                digest,
                attempt,
            )
            if attempt < MAX_ATTEMPTS:
                sleep_for = min(_BACKOFF_BASE * (2 ** (attempt - 1)), max(0.0, deadline - time.monotonic() - 0.05))
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)

        raise last_error


class FakeLlm:
    """测试用假实现：按序返回预设 payload 或抛出预设异常。"""

    model_name = "fake-llm"

    def __init__(self, responses: list[Any] | None = None):
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[BaseModel],
        temperature: float,
        max_tokens: int,
        budget: float,
    ) -> LlmCallResult:
        self.calls.append({"system": system, "user": user, "schema": schema})
        if not self.responses:
            raise LlmInvalidOutput("FakeLlm 无预设响应", attempts=1)
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        payload = schema.model_validate(item)
        return LlmCallResult(
            payload=payload,
            model=self.model_name,
            latency_ms=1,
            attempts=1,
            total_tokens=0,
            prompt_sha256=_prompt_hash(system, user),
        )
