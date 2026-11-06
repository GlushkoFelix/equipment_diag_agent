"""P0 验收补测：知识导入校验与手动激活/回滚（AC-KB-03 / AC-KB-04 / OBS-02）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db import Database
from app.knowledge import (
    KB_VERSION,
    KnowledgeImportError,
    KnowledgeService,
    load_entries_file,
    validate_entries,
)
from tests.support import build_settings


def _service(tmp_path: Path) -> tuple[KnowledgeService, Database]:
    settings = build_settings(tmp_path)
    settings.ensure_dirs()
    db = Database(settings.db_path)
    db.migrate()
    knowledge = KnowledgeService(settings, db)
    knowledge.ensure_built()
    return knowledge, db


def _seed_entries() -> list[dict]:
    path = Path(__file__).resolve().parents[2] / "app" / "knowledge_seed.json"
    return load_entries_file(path)


def _new_entry() -> dict:
    return {
        "entry_id": "KB-CAST-001",
        "title": "压铸模裂纹处置",
        "fault_type": "通用",
        "keywords": ["压铸模", "裂纹"],
        "content": "压铸模出现裂纹时应停机检查模温与热应力，建议复测模具壁厚。",
    }


def test_ac_kb04_import_validation_reports_repairs_without_activation(tmp_path: Path):
    knowledge, db = _service(tmp_path)
    before = knowledge.kb_version
    invalid = [
        {
            "entry_id": "KB-BAD-001",
            "fault_type": "未知分类",
            "keywords": "not-a-list",
            "content": "",
        }
    ]
    with pytest.raises(KnowledgeImportError) as excinfo:
        knowledge.import_entries(invalid, kb_version="kb_v9")
    details = excinfo.value.details
    fields = {item["field"] for item in details}
    assert {"title", "keywords", "fault_type", "content", "fault_type"} <= fields
    reasons = {item["reason"] for item in details}
    assert "UNKNOWN_CATEGORY" in reasons
    assert "MISSING_NORMAL_BASELINE" in reasons

    assert knowledge.kb_version == before
    assert not (Path(knowledge.settings.knowledge_dir) / "kb_v9").exists()
    active = db.connection().execute(
        "SELECT kb_version FROM knowledge_versions WHERE status='active'"
    ).fetchone()
    assert active["kb_version"] == before
    assert knowledge.retrieve({"tool_wear_min": 220.0}, cues=["刀具磨损"]).hits
    db.close()


def test_ac_kb04_missing_advice_and_baseline_are_rejected():
    entries = [_new_entry()]
    with pytest.raises(KnowledgeImportError) as excinfo:
        validate_entries(entries)
    reasons = {item["reason"] for item in excinfo.value.details}
    assert "MISSING_NORMAL_BASELINE" in reasons

    baseline_only = [entry for entry in _seed_entries() if entry["fault_type"] == "正常基线"]
    with pytest.raises(KnowledgeImportError) as excinfo:
        validate_entries(baseline_only)
    assert "MISSING_ADVICE" in {item["reason"] for item in excinfo.value.details}


def test_ac_kb03_import_activate_rollback_is_manual(tmp_path: Path):
    knowledge, db = _service(tmp_path)
    assert knowledge.kb_version == KB_VERSION
    entries = _seed_entries() + [_new_entry()]

    knowledge.import_entries(entries, kb_version="kb_v2", activate=False)
    active = db.connection().execute(
        "SELECT kb_version FROM knowledge_versions WHERE status='active'"
    ).fetchone()
    assert active["kb_version"] == KB_VERSION, "导入不得自动归档/激活新版本"
    assert knowledge.kb_version == KB_VERSION
    assert not any(
        hit["entry_id"] == "KB-CAST-001"
        for hit in knowledge.retrieve({}, cues=["压铸模裂纹"]).hits
    )

    knowledge.activate("kb_v2")
    assert knowledge.kb_version == "kb_v2"
    statuses = {row["kb_version"]: row["status"] for row in knowledge.list_versions()}
    assert statuses["kb_v2"] == "active"
    assert statuses[KB_VERSION] == "archived"
    assert any(
        hit["entry_id"] == "KB-CAST-001"
        for hit in knowledge.retrieve({}, cues=["压铸模裂纹"]).hits
    )

    knowledge.rollback(KB_VERSION)
    assert knowledge.kb_version == KB_VERSION
    statuses = {row["kb_version"]: row["status"] for row in knowledge.list_versions()}
    assert statuses[KB_VERSION] == "active"
    assert statuses["kb_v2"] == "archived"
    assert not any(
        hit["entry_id"] == "KB-CAST-001"
        for hit in knowledge.retrieve({}, cues=["压铸模裂纹"]).hits
    )
    db.close()


def test_ac_kb03_manifest_and_entry_count_recorded(tmp_path: Path):
    knowledge, db = _service(tmp_path)
    entries = _seed_entries() + [_new_entry()]
    knowledge.import_entries(entries, kb_version="kb_v2", activate=True)
    row = db.connection().execute(
        "SELECT entry_count, manifest_path FROM knowledge_versions WHERE kb_version='kb_v2'"
    ).fetchone()
    assert row["entry_count"] == len(entries)
    manifest = json.loads(Path(row["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["kb_version"] == "kb_v2"
    assert manifest["entry_count"] == len(entries)
    db.close()
