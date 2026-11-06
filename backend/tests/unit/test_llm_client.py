"""LLM 客户端：超时、重试、Schema 校验与日志脱敏。"""

from __future__ import annotations

import logging

import httpx
import pytest
from pydantic import BaseModel

from app.config import Settings
from app.llm_client import (
    DeepSeekClient,
    LlmInvalidOutput,
    LlmTimeout,
    LlmUpstreamError,
)


class Demo(BaseModel):
    ok: bool
    n: int


def _settings(**overrides) -> Settings:
    return Settings(
        llm_mode="deepseek",
        deepseek_api_key="sk-test-secret-value",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        **overrides,
    )


def _reply(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 12}},
    )


def _client(handler) -> DeepSeekClient:
    return DeepSeekClient(_settings(), transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_complete_json_success_and_redacted_logs(caplog):
    caplog.set_level(logging.INFO, logger="edg.llm")
    client = _client(lambda request: _reply('{"ok": true, "n": 1}'))
    result = await client.complete_json(
        system="sys", user="user", schema=Demo, temperature=0.1, max_tokens=100, budget=3
    )
    assert result.payload.ok is True
    assert result.attempts == 1
    assert result.total_tokens == 12
    assert "sk-test-secret-value" not in caplog.text
    assert "prompt_sha256=" in caplog.text


@pytest.mark.asyncio
async def test_invalid_json_retries_once_then_succeeds():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _reply("not-json") if len(calls) == 1 else _reply('{"ok": false, "n": 2}')

    result = await _client(handler).complete_json(
        system="s", user="u", schema=Demo, temperature=0.1, max_tokens=100, budget=3
    )
    assert result.attempts == 2
    assert result.payload.n == 2
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_schema_violation_twice_raises_invalid_output():
    client = _client(lambda request: _reply('{"ok": true}'))
    with pytest.raises(LlmInvalidOutput):
        await client.complete_json(
            system="s", user="u", schema=Demo, temperature=0.1, max_tokens=100, budget=3
        )


@pytest.mark.asyncio
async def test_upstream_401_not_retried():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(LlmUpstreamError):
        await _client(handler).complete_json(
            system="s", user="u", schema=Demo, temperature=0.1, max_tokens=100, budget=3
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_connect_timeout_retries_then_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    with pytest.raises(LlmTimeout):
        await _client(handler).complete_json(
            system="s", user="u", schema=Demo, temperature=0.1, max_tokens=100, budget=2
        )


@pytest.mark.asyncio
async def test_insufficient_budget_raises_without_request():
    calls: list[int] = []
    client = _client(lambda request: calls.append(1) or _reply('{"ok": true, "n": 1}'))
    with pytest.raises(LlmTimeout):
        await client.complete_json(
            system="s", user="u", schema=Demo, temperature=0.1, max_tokens=100, budget=0.05
        )
    assert calls == []
