"""评测契约与样本集（ARCH §5.4.8）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import evaluation
from app.config import Settings
from app.db import Database, new_id, utcnow

PREFIX = "/api/v1"
PAGE_KEYS = {"items", "page", "page_size", "total", "total_pages"}


def test_load_samples_is_120_with_20_edge():
    settings = Settings()
    samples = evaluation.load_samples(settings)
    eval_samples = [sample for sample in samples if sample["dataset_split"] == "eval"]
    edge_samples = [sample for sample in samples if sample["dataset_split"] == "edge"]
    assert len(eval_samples) == evaluation.SAMPLE_TOTAL == 120
    assert len(edge_samples) == evaluation.EDGE_TOTAL == 20
    assert all(sample["expected_primary"] in evaluation.PRIMARY_LABELS for sample in eval_samples)
    assert all(sample["sample_id"].startswith("EDGE-") for sample in edge_samples)
    assert {sample["sample_id"] for sample in eval_samples}.isdisjoint(
        {sample["sample_id"] for sample in edge_samples}
    )


def _insert_eval_batch(db: Database) -> str:
    batch_id = new_id("evb")
    db.connection().execute(
        "INSERT INTO eval_batches (eval_batch_id, dataset_version, prompt_version, kb_version,"
        " model_name, sample_total, edge_sample_total, report_count, failed_timeout_count,"
        " latency_sample_count, accuracy, completeness_rate, timeout_rate, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (batch_id, "AI4I-2020", "v1", "kb_v1", "fake", 120, 20, 118, 2, 118, 0.9, 0.98, 0.0167, utcnow()),
    )
    db.connection().execute(
        "INSERT INTO eval_samples (eval_sample_id, eval_batch_id, sample_no, sample_id, dataset_split,"
        " expected_primary, predicted_primary, correct, confidence, elements_present, latency_ms,"
        " status, error_category) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (new_id("evs"), batch_id, 1, "1", "eval", "HDF", "PWF", 0, 0.72, 7, 4100, "degraded", "rule_misjudge"),
    )
    return batch_id


@pytest.fixture()
def eval_client(client: TestClient) -> tuple[TestClient, str]:
    db = client.app.state.db
    batch_id = _insert_eval_batch(db)
    return client, batch_id


def test_evaluations_latest_and_list(eval_client):
    client, batch_id = eval_client
    latest = client.get(f"{PREFIX}/evaluations/latest")
    assert latest.status_code == 200
    assert latest.json()["batch"]["eval_batch_id"] == batch_id

    listing = client.get(f"{PREFIX}/evaluations")
    assert listing.status_code == 200
    assert set(listing.json()) == PAGE_KEYS
    assert listing.json()["items"][0]["eval_batch_id"] == batch_id


def test_evaluation_detail_shape(eval_client):
    client, batch_id = eval_client
    detail = client.get(f"{PREFIX}/evaluations/{batch_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    matrix = body["confusion_matrix"]
    assert matrix["row_labels"] == list(evaluation.PRIMARY_LABELS)
    assert matrix["predicted_labels"] == list(evaluation.PREDICTED_LABELS)
    assert len(matrix["counts"]) == len(matrix["row_labels"])
    assert len(body["per_class_recall"]) == 6
    assert body["bad_cases"][0]["error_category"] == "rule_misjudge"


def test_evaluation_detail_404(eval_client):
    client, _ = eval_client
    assert client.get(f"{PREFIX}/evaluations/evb_00000000000000000000000000").status_code == 404


def test_evaluation_samples_bad_cases(eval_client):
    client, batch_id = eval_client
    page = client.get(f"{PREFIX}/evaluations/{batch_id}/samples", params={"only_bad_cases": True})
    assert page.status_code == 200
    assert set(page.json()) == PAGE_KEYS
    assert page.json()["total"] == 1
    sample = page.json()["items"][0]
    assert sample["correct"] is False
    assert sample["status"] == "degraded"
