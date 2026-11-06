"""测试支撑：可覆盖 Settings 的应用客户端。"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PREFIX = "/api/v1"


def write_evidence(name: str, payload: dict) -> Path:
    """验收证据落盘：<repo>/storage/evidence/<name>.json。"""
    root = Path(__file__).resolve().parents[2] / "storage" / "evidence"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(
        storage_dir=tmp_path,
        db_path=tmp_path / "app.db",
        checkpoint_path=tmp_path / "checkpoints.sqlite3",
        upload_dir=tmp_path / "uploads",
        knowledge_dir=tmp_path / "knowledge",
        batch_dir=tmp_path / "batches",
        embedding_mode="hash",
        llm_mode="fake",
        deepseek_api_key="",
        csrf_enforce=False,
        global_timeout_seconds=15,
        sse_poll_seconds=0.05,
    )
    values.update(overrides)
    return Settings(**values)


@contextmanager
def app_client(tmp_path: Path, **overrides):
    app = create_app(build_settings(tmp_path, **overrides))
    with TestClient(app) as client:
        response = client.post(
            f"{PREFIX}/auth/register",
            json={"username": "tester", "password": "Passw0rd!"},
        )
        assert response.status_code == 201, response.text
        yield client
