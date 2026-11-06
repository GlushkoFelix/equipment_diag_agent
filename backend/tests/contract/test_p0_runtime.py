"""P0 验收补测：运行时生命周期、并发、TTL、超时与降级（AC-DG-13/16/21/22/23）。"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import records
from app.main import create_app
from app.runtime.nodes import Nodes
from tests.conftest import FORM_INPUT, wait_for_status
from tests.support import PREFIX, app_client, build_settings
REVIEW_FORM = {
    "input_type": "form",
    "device_id": "2号机",
    "product_type": "M",
    "air_temp_k": 308.6,
    "process_temp_k": 298.1,
    "rotational_speed_rpm": 1250,
    "torque_nm": 30,
    "tool_wear_min": 100,
}
PARTIAL_NL = {
    "input_type": "nl",
    "text": "3号机异响，扭矩 55，有点烫",
    "device_id": "3号机",
    "torque_nm": 55,
}


def _db_row(client: TestClient, diagnosis_id: str):
    return client.app.state.db.connection().execute(
        "SELECT * FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)
    ).fetchone()


def test_ac_dg22_lifespan_ttl_scan_expires_without_requests(tmp_path: Path):
    """AC-DG-22：后台任务每 60s（测试压缩为 50ms）扫描，2 分钟 TTL 压缩为 0。"""
    with app_client(tmp_path, interrupt_ttl_minutes=0, interrupt_scan_seconds=0.05) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=PARTIAL_NL)
        assert created.status_code == 202, created.text
        diagnosis_id = created.json()["diagnosis_id"]

        deadline = time.time() + 10
        status = None
        while time.time() < deadline:
            row = _db_row(client, diagnosis_id)
            status = row["status"]
            if status in ("expired", "succeeded", "failed"):
                break
            time.sleep(0.05)

        assert status == "expired", f"无请求时后台任务应自动过期，实际 {status}"
        row = _db_row(client, diagnosis_id)
        assert row["report_md"] is None
        assert row["interrupt_expires_at"] is not None  # 保留中断三字段供只读展示
        events = client.app.state.db.connection().execute(
            "SELECT type FROM diagnosis_events WHERE diagnosis_id=? ORDER BY seq", (diagnosis_id,)
        ).fetchall()
        assert "expired" in {event["type"] for event in events}


def test_ac_dg23_ttl_expired_rejects_resume_without_report(tmp_path: Path):
    """AC-DG-23：TTL 过期后 resume 返回 409，且不产出报告。"""
    with app_client(tmp_path, interrupt_ttl_minutes=30, interrupt_scan_seconds=3600) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=PARTIAL_NL)
        diagnosis_id = created.json()["diagnosis_id"]
        snapshot = wait_for_status(client, diagnosis_id, {"waiting_human"})
        client.app.state.db.connection().execute(
            "UPDATE diagnoses SET interrupt_expires_at=? WHERE diagnosis_id=?",
            ("2000-01-01T00:00:00.000Z", diagnosis_id),
        )
        expired = client.post(
            f"{PREFIX}/diagnoses/{diagnosis_id}/resume",
            json={"decision": "supplement", "supplement": {"tool_wear_min": 120}, "version": snapshot["version"]},
        )
        assert expired.status_code == 409, expired.text
        assert expired.json()["error"]["code"] == "DIAGNOSIS_EXPIRED"
        row = _db_row(client, diagnosis_id)
        assert row["status"] == "expired"
        assert row["report_md"] is None


def test_ac_dg16_concurrent_resume_only_one_wins(tmp_path: Path):
    """AC-DG-16：条件 UPDATE 保证同一 version 并发 resume 只有一个 200。"""
    with app_client(tmp_path) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=REVIEW_FORM)
        assert created.status_code == 202, created.text
        diagnosis_id = created.json()["diagnosis_id"]
        snapshot = wait_for_status(client, diagnosis_id, {"waiting_human"})
        version = snapshot["version"]

        def resume():
            return client.post(
                f"{PREFIX}/diagnoses/{diagnosis_id}/resume",
                json={"decision": "confirm", "version": version},
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = [future.result() for future in [pool.submit(resume), pool.submit(resume)]]

        codes = sorted(response.status_code for response in responses)
        assert codes == [200, 409], [response.text for response in responses]
        conflict = next(response for response in responses if response.status_code == 409)
        assert conflict.json()["error"]["code"] == "VERSION_CONFLICT"


def test_ac_dg16_stale_resume_version_returns_version_conflict(tmp_path: Path):
    """AC-DG-16：胜出方递增版本后，旧版本 resume 必须返回 VERSION_CONFLICT。"""
    with app_client(tmp_path) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=REVIEW_FORM)
        diagnosis_id = created.json()["diagnosis_id"]
        snapshot = wait_for_status(client, diagnosis_id, {"waiting_human"})
        stale_version = snapshot["version"]
        first = client.post(
            f"{PREFIX}/diagnoses/{diagnosis_id}/resume",
            json={"decision": "confirm", "version": stale_version},
        )
        assert first.status_code == 200, first.text
        stale = client.post(
            f"{PREFIX}/diagnoses/{diagnosis_id}/resume",
            json={"decision": "confirm", "version": stale_version},
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


def test_ac_dg16_conditional_update_is_atomic(tmp_path: Path):
    with app_client(tmp_path) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=REVIEW_FORM)
        diagnosis_id = created.json()["diagnosis_id"]
        snapshot = wait_for_status(client, diagnosis_id, {"waiting_human"})
        db = client.app.state.db
        first = records.set_running(db, diagnosis_id, "confirm", expected_version=snapshot["version"])
        second = records.set_running(db, diagnosis_id, "confirm", expected_version=snapshot["version"])
        assert first == snapshot["version"] + 1
        assert second is None


@pytest.mark.parametrize("node_name", ["parse_input", "retrieve", "diagnose", "report"])
def test_ac_dg21_node_overrun_finalizes_failed_timeout(tmp_path: Path, monkeypatch, node_name: str):
    """AC-DG-21：任一节点耗时超过全局时间窗 → failed_timeout，不产出报告。

    测试按 15s 口径等比压缩：global_timeout=0.5s，节点注入 1.6s（> deadline+1s）。
    """
    original = getattr(Nodes, node_name)

    async def slow(self, *args, **kwargs):
        await asyncio.sleep(1.6)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(Nodes, node_name, slow)
    with app_client(tmp_path, global_timeout_seconds=0.5) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
        assert created.status_code == 202, created.text
        diagnosis_id = created.json()["diagnosis_id"]
        snapshot = wait_for_status(client, diagnosis_id, {"failed_timeout", "succeeded", "degraded"})
        assert snapshot["status"] == "failed_timeout"
        assert snapshot["error"]["code"] == "TIMEOUT"
        assert snapshot["report"] is None


def test_ac_dg13_missing_index_degrades_to_unknown(tmp_path: Path):
    """AC-DG-13：索引缺失时不伪造结论，按知识未覆盖降级。"""
    with app_client(tmp_path) as client:
        knowledge = client.app.state.knowledge
        knowledge.index = None
        knowledge.entries = []
        knowledge.index_status = "missing"
        created = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
        diagnosis_id = created.json()["diagnosis_id"]
        snapshot = wait_for_status(client, diagnosis_id, {"succeeded", "degraded", "failed"})
        assert snapshot["status"] in ("succeeded", "degraded")
        assert snapshot["primary_type"] == "未覆盖"
        assert snapshot["confidence"] <= 0.4
        assert "知识库未覆盖" in snapshot["report"]["markdown"]


def test_ac_dg13_deleted_index_on_restart_marks_missing(tmp_path: Path):
    """AC-DG-13：删除 index.faiss 后重启，不得自动 rebuild，应降级为 missing。"""
    with app_client(tmp_path) as client:
        created = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
        wait_for_status(client, created.json()["diagnosis_id"], {"succeeded", "degraded"})

    index_file = tmp_path / "knowledge" / "kb_v1" / "index.faiss"
    assert index_file.exists()
    index_file.unlink()

    with TestClient(create_app(build_settings(tmp_path))) as client:
        login = client.post(
            f"{PREFIX}/auth/login", json={"username": "tester", "password": "Passw0rd!"}
        )
        assert login.status_code == 200, login.text
        health = client.get(f"{PREFIX}/health").json()
        assert health["dependencies"]["vector_index"] == "missing"
        assert health["status"] == "degraded"
        assert client.app.state.knowledge.index_status == "missing"

        created = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
        assert created.status_code == 202, created.text
        snapshot = wait_for_status(client, created.json()["diagnosis_id"], {"succeeded", "degraded"})
        assert snapshot["knowledge_status"] == "missing"
        assert snapshot["primary_type"] == "未覆盖"
        assert snapshot["confidence"] <= 0.4
        assert "知识库未覆盖" in snapshot["report"]["markdown"]

    assert not index_file.exists(), "索引缺失时不得自动 rebuild"


def test_ac_dg13_empty_seed_starts_as_missing(tmp_path: Path):
    """AC-DG-13：空知识库（种子为 []）应继续启动并标记 missing，不得触发 entry_count 约束崩溃。"""
    seed = tmp_path / "empty_seed.json"
    seed.write_text("[]", encoding="utf-8")
    with app_client(tmp_path, knowledge_seed_path=seed) as client:
        health = client.get(f"{PREFIX}/health").json()
        assert health["dependencies"]["vector_index"] == "missing"
        assert health["status"] == "degraded"
        assert client.app.state.knowledge.index_status == "missing"
        created = client.post(f"{PREFIX}/diagnoses", json=FORM_INPUT)
        assert created.status_code == 202, created.text
        snapshot = wait_for_status(client, created.json()["diagnosis_id"], {"succeeded", "degraded"})
        assert snapshot["knowledge_status"] == "missing"
        assert snapshot["primary_type"] == "未覆盖"
        assert "知识库未覆盖" in snapshot["report"]["markdown"]
