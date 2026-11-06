"""AC-KB-06：跨参数（chunk_size/overlap/Top-K）前后对比 + 同参数重复一致性。"""

from __future__ import annotations

import json
from pathlib import Path

from app import evaluation
from app.db import new_id, utcnow
from tests.support import PREFIX, app_client, write_evidence

SPEC_1 = {"chunk_size": 400, "overlap": 50, "top_k": 5}
SPEC_2 = {"chunk_size": 200, "overlap": 20, "top_k": 8}
SAMPLE_TOTAL = 50


def _insert_eval_batch(client, kb_version: str) -> str:
    db = client.app.state.db
    batch_id = new_id("evb")
    db.connection().execute(
        "INSERT INTO eval_batches (eval_batch_id, dataset_version, prompt_version, kb_version,"
        " model_name, sample_total, edge_sample_total, report_count, failed_timeout_count,"
        " latency_sample_count, accuracy, completeness_rate, timeout_rate, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (batch_id, "AI4I-2020", "v1", kb_version, "fake", 120, 20, 118, 0, 118, 0.9, 0.98, 0.0, utcnow()),
    )
    return batch_id


def _tuning(client, batch_id: str) -> dict:
    response = client.get(f"{PREFIX}/evaluations/{batch_id}")
    assert response.status_code == 200, response.text
    tuning = response.json()["retrieval_tuning"]
    assert len(tuning) == 1
    return tuning[0]


def test_ac_kb06_two_runs_use_different_params_and_report_delta(tmp_path: Path):
    with app_client(tmp_path) as client:
        knowledge = client.app.state.knowledge
        batch_id = _insert_eval_batch(client, knowledge.kb_version)
        entry = _tuning(client, batch_id)

        runs = entry["runs"]
        assert [run["run"] for run in runs] == [1, 2]
        first, second = runs[0]["params"], runs[1]["params"]
        assert first != second, "两次运行必须使用不同参数"
        assert first["chunk_size"] != second["chunk_size"]
        assert first["overlap"] != second["overlap"]
        assert first["top_k"] != second["top_k"]
        assert first == SPEC_1
        assert second == SPEC_2
        assert entry["params"] == SPEC_1

        for run in runs:
            assert run["sample_total"] == SAMPLE_TOTAL
            assert run["created_at"]
            assert run["kb_version"]
            assert isinstance(run["top5_hit_rate"], float)
            assert 0.0 <= run["top5_hit_rate"] <= 1.0

        delta = entry["delta"]
        assert abs(delta - (runs[1]["top5_hit_rate"] - runs[0]["top5_hit_rate"])) <= 1e-4
        assert abs(entry["top5_hit_rate"] - runs[0]["top5_hit_rate"]) <= 1e-4

        fixed_set = Path(knowledge.settings.storage_dir) / "retrieval_queries.json"
        assert len(json.loads(fixed_set.read_text(encoding="utf-8"))) == SAMPLE_TOTAL

        write_evidence(
            "AC-KB-06-retrieval-comparison",
            {
                "runs": [
                    {
                        "run": run["run"],
                        "params": run["params"],
                        "top5_hit_rate": run["top5_hit_rate"],
                        "sample_total": run["sample_total"],
                        "kb_version": run["kb_version"],
                        "created_at": run["created_at"],
                        "backend": run["backend"],
                    }
                    for run in runs
                ],
                "delta": delta,
                "consistent": entry["consistent"],
                "repeat": entry["repeat"],
                "params_changed": first != second,
            },
        )


def test_ac_kb06_same_params_repeat_is_consistent(tmp_path: Path):
    with app_client(tmp_path) as client:
        knowledge = client.app.state.knowledge
        batch_id = _insert_eval_batch(client, knowledge.kb_version)
        entry = _tuning(client, batch_id)

        repeat = entry["repeat"]
        assert repeat["params"] == entry["runs"][0]["params"] == entry["params"]
        assert repeat["top5_hit_rate"] == entry["runs"][0]["top5_hit_rate"]
        assert entry["consistent"] is True
        assert repeat["sample_total"] == SAMPLE_TOTAL

        # 同参数、同检索集再次实测：命中率完全一致（确定性）
        again = evaluation.run_retrieval_tuning(knowledge)
        assert again["runs"][0]["top5_hit_rate"] == entry["runs"][0]["top5_hit_rate"]
        assert again["runs"][1]["top5_hit_rate"] == entry["runs"][1]["top5_hit_rate"]
        assert again["delta"] == entry["delta"]
        assert again["consistent"] is True


def test_ac_kb06_tuning_readable_from_detail_and_matches_cli(tmp_path: Path):
    with app_client(tmp_path) as client:
        knowledge = client.app.state.knowledge
        batch_id = _insert_eval_batch(client, knowledge.kb_version)
        detail = client.get(f"{PREFIX}/evaluations/{batch_id}").json()
        entry = detail["retrieval_tuning"][0]

        # detail 中可读回完整结构
        assert set(entry["runs"][0]) >= {
            "run",
            "params",
            "top5_hit_rate",
            "sample_total",
            "kb_version",
            "created_at",
        }
        assert entry["runs"][0]["params"]["top_k"] == 5
        assert entry["runs"][1]["params"]["top_k"] == 8

        # 离线复算与接口一致（run1 = 正式库同参数 Top-5 命中率）
        assert (
            abs(evaluation.measure_top5_hit_rate(knowledge) - entry["runs"][0]["top5_hit_rate"]) <= 1e-4
        )
