"""P1 修复：提示词回归对照与失败自动回滚（AC-EV-05）。"""

from __future__ import annotations

import json
from pathlib import Path

from app.prompt_regression import run_regression
from app.prompts import PromptLibrary

BASELINE_BODY = "alpha beta gamma"
CANDIDATE_BAD = "alpha only"


def _write(path: Path, version: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nversion: {version}\nupdated_at: 2026-10-25\n---\n{body}\n",
        encoding="utf-8",
    )


def _library(tmp_path: Path) -> tuple[PromptLibrary, Path]:
    root = tmp_path / "prompts"
    _write(root / "baseline" / "reporter.md", "baseline-v1", BASELINE_BODY)
    _write(root / "reporter.md", "candidate-v2", CANDIDATE_BAD)
    return PromptLibrary(root), root


def test_ac_ev05_rollback_restores_baseline_prompts_and_records_reason(tmp_path: Path):
    library, root = _library(tmp_path)
    audit = tmp_path / "audit" / "regression.jsonl"

    outcome = run_regression(
        library,
        "reporter",
        ["alpha", "beta"],
        lambda body, case: case in body,
        baseline_dir=root / "baseline",
        audit_path=audit,
    )

    assert outcome.rolled_back is True
    assert outcome.baseline_version == "baseline-v1"
    assert outcome.candidate_version == "candidate-v2"
    assert outcome.baseline_passed == 2
    assert outcome.candidate_passed == 1
    assert outcome.active_version == "baseline-v1"
    assert "已回滚到 baseline-v1" in outcome.reason

    assert (root / "reporter.md").read_bytes() == (root / "baseline" / "reporter.md").read_bytes()
    assert library.get("reporter").version == "baseline-v1"
    assert library.get("reporter").body == BASELINE_BODY

    records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines() if line]
    assert len(records) == 1
    record = records[0]
    assert record["rolled_back"] is True
    assert record["candidate_version"] == "candidate-v2"
    assert record["baseline_version"] == "baseline-v1"
    assert "candidate-v2" in record["reason"]
    assert record["created_at"]


def test_ac_ev05_regression_detection_threshold(tmp_path: Path):
    """候选不低于基线时不得回滚，活动版本保持候选。"""
    library, root = _library(tmp_path)
    _write(root / "reporter.md", "candidate-v2", "alpha beta gamma delta")

    outcome = run_regression(
        library,
        "reporter",
        ["alpha", "beta"],
        lambda body, case: case in body,
        baseline_dir=root / "baseline",
        audit_path=tmp_path / "audit.jsonl",
    )
    assert outcome.rolled_back is False
    assert outcome.baseline_passed == outcome.candidate_passed == 2
    assert outcome.active_version == "candidate-v2"
    assert library.get("reporter").body == "alpha beta gamma delta"
