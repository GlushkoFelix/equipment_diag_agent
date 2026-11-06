"""AC-EV-05：提示词回归与失败自动回滚。

候选提示词先与 baseline 版本在同一批固定用例上对照；候选通过率低于 baseline 时，
自动用 baseline 覆盖候选文件，并把回滚原因、两侧版本与分数写入审计 JSONL。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from app.db import utcnow
from app.prompts import PromptLibrary

Evaluator = Callable[[str, Any], bool]


@dataclass(frozen=True)
class RegressionOutcome:
    prompt: str
    baseline_version: str
    candidate_version: str
    baseline_passed: int
    candidate_passed: int
    total_cases: int
    rolled_back: bool
    active_version: str
    reason: str
    audit_path: str | None


def run_regression(
    library: PromptLibrary,
    name: str,
    cases: Iterable[Any],
    evaluator: Evaluator,
    *,
    baseline_dir: Path | str | None = None,
    audit_path: Path | str | None = None,
) -> RegressionOutcome:
    """对照 baseline 执行回归；候选低于 baseline 时自动回滚并记录审计。"""
    baseline_dir = Path(baseline_dir) if baseline_dir else library.root / "baseline"
    baseline_library = PromptLibrary(baseline_dir)
    candidate = library.get(name)
    baseline = baseline_library.get(name)
    items = list(cases)
    if not items:
        raise ValueError("提示词回归至少需要 1 条用例")

    baseline_passed = sum(1 for case in items if evaluator(baseline.body, case))
    candidate_passed = sum(1 for case in items if evaluator(candidate.body, case))
    rolled_back = candidate_passed < baseline_passed
    reason = ""
    active_version = candidate.version
    if rolled_back:
        target = library.root / f"{name}.md"
        target.write_text((baseline_dir / f"{name}.md").read_text(encoding="utf-8"), encoding="utf-8")
        library.invalidate(name)
        active_version = baseline.version
        reason = (
            f"候选 {candidate.version} 通过率 {candidate_passed}/{len(items)} 低于基线 "
            f"{baseline.version} {baseline_passed}/{len(items)}，已回滚到 {baseline.version}"
        )

    audit = audit_path or (library.root / "regression_audit.jsonl")
    outcome = RegressionOutcome(
        prompt=name,
        baseline_version=baseline.version,
        candidate_version=candidate.version,
        baseline_passed=baseline_passed,
        candidate_passed=candidate_passed,
        total_cases=len(items),
        rolled_back=rolled_back,
        active_version=active_version,
        reason=reason,
        audit_path=str(audit) if audit else None,
    )
    record = {**asdict(outcome), "created_at": utcnow()}
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return outcome
