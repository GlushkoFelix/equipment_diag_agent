"""评测样本口径单测：标签优先级与 UDI 互斥（PRD FR-EV-01 / §3.10.1）。"""

from __future__ import annotations

import collections

import pytest

from app import evaluation
from app.config import Settings


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({"PWF": "1", "OSF": "1"}, "OSF"),
        ({"HDF": "1", "OSF": "1"}, "OSF"),
        ({"HDF": "1", "PWF": "1"}, "HDF"),
        ({"PWF": "1", "TWF": "1"}, "PWF"),
        ({"TWF": "1", "RNF": "1"}, "TWF"),
        ({"RNF": "1"}, "RNF"),
        ({}, "正常"),
    ],
)
def test_multi_label_priority_follows_osf_hdf_pwf_twf_rnf(flags, expected):
    row = {**{label: "0" for label in evaluation.LABEL_PRIORITY}, **flags}
    assert evaluation._expected_primary(row) == expected


def test_eval_edge_udi_overlap_raises():
    samples = [
        {"sample_id": "70", "dataset_split": "eval"},
        {"sample_id": "70", "dataset_split": "edge"},
    ]
    with pytest.raises(RuntimeError, match="eval/edge UDI 重叠"):
        evaluation.validate_sample_exclusivity(samples)


def test_duplicate_udi_within_split_raises():
    samples = [
        {"sample_id": "70", "dataset_split": "eval"},
        {"sample_id": "70", "dataset_split": "eval"},
    ]
    with pytest.raises(RuntimeError, match="UDI 重复"):
        evaluation.validate_sample_exclusivity(samples)


def test_tuning_eval_udi_overlap_raises():
    samples = [
        {"sample_id": "70", "dataset_split": "eval"},
        {"sample_id": "70", "dataset_split": "tuning"},
    ]
    with pytest.raises(RuntimeError, match="tuning/eval UDI 重叠"):
        evaluation.validate_sample_exclusivity(samples)


def test_load_samples_matches_prd_quota_and_is_udi_exclusive():
    samples = evaluation.load_samples(Settings())
    eval_samples = [sample for sample in samples if sample["dataset_split"] == "eval"]
    edge_samples = [sample for sample in samples if sample["dataset_split"] == "edge"]
    assert len(samples) == evaluation.SAMPLE_TOTAL + evaluation.EDGE_TOTAL
    assert len(eval_samples) == evaluation.SAMPLE_TOTAL
    assert len(edge_samples) == evaluation.EDGE_TOTAL
    quota = collections.Counter(sample["expected_primary"] for sample in eval_samples)
    assert quota == collections.Counter(dict(evaluation.EVAL_QUOTA))
    assert all(sample["sample_id"].startswith("EDGE-") for sample in edge_samples)
    assert {sample["sample_id"] for sample in eval_samples}.isdisjoint(
        {sample["sample_id"] for sample in edge_samples}
    )
