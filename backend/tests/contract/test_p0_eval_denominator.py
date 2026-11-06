"""P0 补证：单条样本非法时隔离失败、其余继续、KPI 分母仍 120（AC-EV-03）。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from app import evaluation, services
from app.config import Settings
from app.db import Database, new_id, utcnow
from app.report import ELEMENTS
from tests.conftest import FORM_INPUT
from tests.support import build_settings

EVAL_TOTAL = 120
INVALID_SAMPLE_NO = 61


def _raw_input(index: int) -> dict:
    payload = {key: value for key, value in FORM_INPUT.items() if key != "input_type"}
    payload["device_id"] = f"EVAL-{index:03d}"
    payload["_expected"] = "HDF"
    return payload


def _samples() -> list[dict]:
    samples = []
    for index in range(1, EVAL_TOTAL + 1):
        payload = _raw_input(index)
        if index == INVALID_SAMPLE_NO:
            payload.pop("air_temp_k")  # 第 61 条置非法（缺失特征）
        samples.append(
            {
                "sample_no": index,
                "sample_id": f"S-{index:03d}",
                "dataset_split": "eval",
                "expected_primary": "HDF",
                "raw_input": payload,
            }
        )
    return samples


class _FakeRunner:
    async def run_inline(self, diagnosis_id: str, state: dict) -> None:
        return None


def test_ac_ev03_invalid_sample_failed_but_report_count_119(tmp_path: Path, monkeypatch):
    settings = build_settings(tmp_path)
    settings.ensure_dirs()
    db = Database(settings.db_path)
    db.migrate()
    user_id = evaluation.ensure_eval_user(db)

    def fake_insert(db, settings: Settings, user_id: int, *, input_type, result, raw_input, **kwargs):
        diagnosis_id = new_id("dx")
        now = utcnow()
        db.connection().execute(
            "INSERT INTO diagnoses (diagnosis_id, user_id, device_id, input_type, input_summary_json,"
            " status, primary_type, confidence, confidence_level, confidence_breakdown_json,"
            " report_elements_check_json, report_title, report_meta_json, knowledge_status,"
            " execution_mode, duration_ms, report_md, started_at, created_at, version, finished_at)"
            " VALUES (?,?,?,?,'{}','succeeded',?,?,?,?,?,'夹具报告','{}',?,'eval',?,"
            "'# 夹具报告',?,?,1,?)",
            (
                diagnosis_id,
                user_id,
                result.normalized["device_id"],
                input_type,
                raw_input.get("_expected"),
                0.9,
                "high",
                json.dumps({"llm_used": False, "llm_decided": False}),
                json.dumps({"passed": True, "present": list(ELEMENTS), "missing": []}),
                "supported",
                123,
                now,
                now,
                now,
            ),
        )
        return diagnosis_id, {}

    monkeypatch.setattr(evaluation, "load_samples", lambda _settings: _samples())
    monkeypatch.setattr(services, "insert_diagnosis_from_result", fake_insert)

    knowledge = SimpleNamespace(kb_version="kb_v1")
    batch_id = asyncio.run(evaluation.run_evaluation(db, settings, _FakeRunner(), knowledge, user_id))

    batch = db.connection().execute(
        "SELECT * FROM eval_batches WHERE eval_batch_id=?", (batch_id,)
    ).fetchone()
    assert batch["sample_total"] == EVAL_TOTAL, "KPI 分母固定 120"
    assert batch["report_count"] == 119
    assert batch["accuracy"] == 119 / EVAL_TOTAL

    invalid = db.connection().execute(
        "SELECT status, error_category, predicted_primary FROM eval_samples"
        " WHERE eval_batch_id=? AND sample_no=?",
        (batch_id, INVALID_SAMPLE_NO),
    ).fetchone()
    assert invalid["status"] == "failed"
    assert invalid["error_category"] == "feature_missing"
    assert invalid["predicted_primary"] is None

    succeeded = db.connection().execute(
        "SELECT COUNT(*) AS c FROM eval_samples WHERE eval_batch_id=? AND status IN ('succeeded','degraded')",
        (batch_id,),
    ).fetchone()["c"]
    assert succeeded == 119, "其余样本必须继续执行"

    detail = evaluation.detail(db, batch_id)
    assert detail["batch"]["sample_total"] == EVAL_TOTAL
    assert detail["batch"]["report_count"] == 119
    db.close()
