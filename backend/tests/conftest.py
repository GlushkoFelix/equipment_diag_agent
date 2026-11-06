"""测试夹具：临时存储 + hash 向量 + fake LLM，避免外部依赖。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(
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
        sse_poll_seconds=0.1,
    )


@pytest.fixture()
def client(settings: Settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/auth/register",
            json={"username": "tester", "password": "Passw0rd!"},
        )
        assert response.status_code == 201, response.text
        yield test_client


def auth_headers() -> dict[str, str]:
    return {}


def wait_for_status(client: TestClient, diagnosis_id: str, statuses: set[str], timeout: float = 20.0) -> dict:
    deadline = time.time() + timeout
    snapshot: dict = {}
    while time.time() < deadline:
        response = client.get(f"/api/v1/diagnoses/{diagnosis_id}")
        assert response.status_code == 200, response.text
        snapshot = response.json()
        if snapshot["status"] in statuses:
            return snapshot
        time.sleep(0.1)
    raise AssertionError(f"诊断 {diagnosis_id} 未在 {timeout}s 内进入 {statuses}，实际 {snapshot.get('status')}")


FORM_INPUT = {
    "input_type": "form",
    "device_id": "3号机",
    "product_type": "M",
    "air_temp_k": 298.1,
    "process_temp_k": 305.3,
    "rotational_speed_rpm": 1250,
    "torque_nm": 30,
    "tool_wear_min": 100,
}
