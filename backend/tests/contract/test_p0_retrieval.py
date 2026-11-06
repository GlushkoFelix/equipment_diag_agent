"""P0/P1 补证：检索覆盖（AC-KB-01）、同类型配额与 RETRY（AC-KB-02）、Top-5 实测（AC-KB-06）。"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from app import evaluation
from app import knowledge as knowledge_module
from app.db import new_id, utcnow
from tests.support import PREFIX, app_client

HDF_QUERIES = (
    "HDF 散热 温差 冷却",
    "HDF 温差低 转速低",
    "HDF 散热风扇 滤网 冷却液",
    "HDF 冷却液 流量 不足",
    "HDF 温度 异常 低转速",
)
FIXED_QUERY = ["HDF", "散热", "温差", "冷却"]


def test_ac_kb01_fixed_query_top5_hdf_hit_and_covered(tmp_path: Path):
    with app_client(tmp_path) as client:
        knowledge = client.app.state.knowledge
        assert knowledge.index_status == "ok"
        result = knowledge.retrieve({}, cues=FIXED_QUERY, top_k=5)

        assert result.coverage == "covered"
        assert result.max_score >= knowledge_module.COVERED_SCORE
        assert len(result.hits) <= 5
        assert any(hit["fault_type"] == "HDF" for hit in result.hits)
        scores = [hit["score"] for hit in result.hits]
        assert scores == sorted(scores, reverse=True)


def test_ac_kb02_same_type_cap_and_retry_keeps_threshold(tmp_path: Path):
    with app_client(tmp_path) as client:
        knowledge = client.app.state.knowledge
        baseline = knowledge.retrieve({}, cues=[HDF_QUERIES[0]], top_k=5)

        for query in HDF_QUERIES:
            result = knowledge.retrieve({}, cues=[query], top_k=5)
            per_type = Counter(hit["fault_type"] for hit in result.hits)
            assert all(count <= 2 for count in per_type.values()), per_type
            assert per_type["HDF"] <= 2
            scores = [hit["score"] for hit in result.hits]
            assert scores == sorted(scores, reverse=True)

        retry = knowledge.retrieve({}, cues=[HDF_QUERIES[0]], top_k=5, retry=True)
        assert retry.retry_used is True
        assert retry.top_k == 8, "RETRY 只扩 top_k 到 8"
        assert knowledge_module.COVERED_SCORE == 0.35, "RETRY 不得降低覆盖阈值"
        assert retry.coverage == baseline.coverage, "同 query 下 RETRY 不得改变覆盖判定"
        assert len(retry.hits) <= 8


def _insert_eval_batch(client: TestClient, kb_version: str) -> str:
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


def test_ac_kb06_top5_hit_rate_is_measured_not_null(tmp_path: Path):
    with app_client(tmp_path) as client:
        knowledge = client.app.state.knowledge
        batch_id = _insert_eval_batch(client, knowledge.kb_version)

        detail = client.get(f"{PREFIX}/evaluations/{batch_id}")
        assert detail.status_code == 200, detail.text
        tuning = detail.json()["retrieval_tuning"]
        assert len(tuning) == 1
        rate = tuning[0]["top5_hit_rate"]
        assert isinstance(rate, float), "artifact 落值不得为 null"
        assert 0.0 < rate <= 1.0
        assert rate == evaluation.measure_top5_hit_rate(knowledge)

        fixed_set = Path(knowledge.settings.storage_dir) / "retrieval_queries.json"
        assert fixed_set.exists(), "固定检索集必须落盘"
        queries = json.loads(fixed_set.read_text(encoding="utf-8"))
        assert len(queries) == 50
        assert all(item["query"] and item["expected_fault_type"] for item in queries)
