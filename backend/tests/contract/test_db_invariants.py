"""M0 数据库不变量与启动自检测试（DB V1.1.0 §6 / ARCH §4.1）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_full_schema_applied(client: TestClient):
    conn = client.app.state.db.connection()
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    expected = {
        "schema_migrations",
        "users",
        "sessions",
        "uploads",
        "mapping_schemes",
        "batch_tasks",
        "batch_rows",
        "diagnoses",
        "diagnosis_steps",
        "diagnosis_events",
        "batch_events",
        "chat_sessions",
        "chat_messages",
        "knowledge_versions",
        "eval_batches",
        "eval_samples",
        "idempotency_keys",
    }
    assert expected <= tables
    migration = conn.execute("SELECT version, checksum FROM schema_migrations").fetchone()
    assert migration["version"] == 1
    assert migration["checksum"].startswith("sha256:")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_partial_unique_index_on_active_fingerprint(client: TestClient):
    conn = client.app.state.db.connection()
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='ux_diagnoses_active_fp'"
    ).fetchone()
    assert "WHERE active_fingerprint_key IS NOT NULL" in row["sql"]
    assert conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name='ix_diagnoses_ttl'"
    ).fetchone()["sql"].count("WHERE") == 1

    now = "2026-10-23T10:00:00.000Z"
    fingerprint = "sha256:" + "b" * 64
    base = (
        "INSERT INTO diagnoses (diagnosis_id, user_id, device_id, input_type, input_summary_json,"
        " status, input_fingerprint, fingerprint_scope, active_fingerprint_key, started_at, created_at)"
        " VALUES (?,1,'3号机','nl','{}','running',?,'dedupe',?,?,?)"
    )
    conn.execute(base, ("dx_" + "A" * 26, fingerprint, "1:" + fingerprint, now, now))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base, ("dx_" + "B" * 26, fingerprint, "1:" + fingerprint, now, now))


def test_version_must_increase_on_status_change(client: TestClient):
    conn = client.app.state.db.connection()
    now = "2026-10-23T10:00:00.000Z"
    conn.execute(
        "INSERT INTO diagnoses (diagnosis_id, user_id, device_id, input_type, input_summary_json,"
        " status, started_at, created_at, version) VALUES (?,1,'3号机','nl','{}','running',?,?,1)",
        ("dx_" + "C" * 26, now, now),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE diagnoses SET status='failed', error_code='X' WHERE diagnosis_id=?",
            ("dx_" + "C" * 26,),
        )


def test_checkpoint_store_created(client: TestClient, settings):
    assert Path(settings.checkpoint_path).exists()
    assert client.app.state.checkpointer is not None


def test_assets_paths_configured(settings):
    assert (settings.bge_m3_path / "config.json").exists()
    assert settings.dataset_path.exists()
    assert settings.knowledge_seed_path.exists()


def test_knowledge_version_activation(client: TestClient):
    conn = client.app.state.db.connection()
    rows = conn.execute("SELECT kb_version, status, entry_count FROM knowledge_versions").fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "active"
    assert rows[0]["entry_count"] >= 14
