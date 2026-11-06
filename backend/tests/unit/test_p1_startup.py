"""P1 修复：BGE 降级健康语义（AC-SY-03）与生产启动自检（AC-SE-05）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.main import create_app
from tests.support import PREFIX, app_client, build_settings


def test_health_reports_degraded_with_embedding_reason_when_bge_unavailable(tmp_path: Path):
    """AC-SY-03：回退向量后端 → /health degraded，dependencies 含 embedding_reason。"""
    with app_client(tmp_path, embedding_mode="hash") as client:
        health = client.get(f"{PREFIX}/health")
        assert health.status_code == 200, health.text
        body = health.json()
        assert body["status"] == "degraded"
        dependencies = body["dependencies"]
        assert dependencies["embedding_model"] == "degraded"
        assert dependencies["embedding_reason"] == "fallback:hash-ngram-512"
        assert dependencies["vector_index"] == "ok"


def test_production_gate_blocks_missing_https_db_encryption_and_key(tmp_path: Path, caplog):
    """AC-SE-05：production 下 HTTPS/DB 加密/密钥缺失 → 拒绝启动并打印缺失项清单。"""
    settings = build_settings(
        tmp_path,
        app_env="production",
        https_enabled=False,
        db_encryption_key="",
        llm_mode="deepseek",
        deepseek_api_key="",
    )
    with pytest.raises(RuntimeError) as excinfo:
        create_app(settings)
    message = str(excinfo.value)
    assert "HTTPS 未启用" in message
    assert "数据库加密密钥缺失" in message
    assert "DeepSeek API Key 缺失" in message
    assert "EDG_HTTPS_ENABLED" in message
    assert "EDG_DB_ENCRYPTION_KEY" in message
    assert "EDG_DEEPSEEK_API_KEY" in message
    assert any("生产环境启动自检失败" in record.message for record in caplog.records)


def test_production_gate_allows_complete_configuration(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        app_env="production",
        https_enabled=True,
        db_encryption_key="0123456789abcdef0123456789abcdef",
        llm_mode="deepseek",
        deepseek_api_key="sk-test-production",
    )
    assert settings.production_startup_gaps() == []
    app = create_app(settings)
    assert app.title == settings.app_name
