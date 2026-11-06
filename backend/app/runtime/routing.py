"""RT-01~RT-20 的纯路由函数。

只做判定，不做 IO；节点副作用在 runtime/nodes.py。
权威来源：ARCH V1.2.0 §3.4 / §3.5 / §4.9。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

TERMINAL_STATUSES = {
    "succeeded",
    "degraded",
    "degraded_review",
    "aborted",
    "failed",
    "failed_timeout",
    "expired",
}
DEDUPE_INPUT_TYPES = {"csv_single", "form", "nl", "chat"}
SINGLE_INPUT_TYPES = {"csv_single", "form", "nl", "chat"}
CLARIFY_INPUT_TYPES = {"nl", "chat"}


class DecisionNotAllowed(ValueError):
    """review round=2 仍提交 supplement（API 前置应返回 409 DECISION_NOT_ALLOWED）。"""


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


def confidence_level(confidence: float) -> str:
    """ARCH §4.3.1：0.8 归 high；[0.5,0.8) medium；[0,0.5) low。"""
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def has_missing(state: dict[str, Any]) -> bool:
    return bool(state.get("missing_fields"))


def route_after_parse(state: dict[str, Any]) -> str:
    """RT-01 / RT-02 / RT-03 / RT-14 / RT-19。"""
    mode = state["execution_mode"]
    missing = has_missing(state)

    if state.get("hard_error"):
        return "error"  # RT-14
    if missing:
        if mode == "eval":
            return "sample_failed"
        if mode == "batch":
            return "row_failed"  # RT-19，批量禁止 clarify
        if state["input_type"] in CLARIFY_INPUT_TYPES:
            return "clarify"  # RT-02，仅单条 nl/chat
        return "error"  # RT-03，单条 CSV/表单绝不进 retrieve
    return "retrieve"  # RT-01


def route_after_retrieve(state: dict[str, Any]) -> str:
    """RT-04：检索完成固定进入 diagnose（覆盖判定在 diagnose 中记录）。"""
    return "diagnose"


def route_after_diagnose(state: dict[str, Any]) -> str:
    """RT-05 / RT-06 / RT-07 / RT-08 / RT-18。"""
    diagnosis = state["diagnosis"]
    confidence = float(diagnosis["confidence"])

    if diagnosis.get("knowledge_status") == "missing":
        return "report"  # RT-05 优先
    if confidence >= 0.8:
        return "report"  # RT-06
    if state.get("retry_count", 0) < 1 and 0.5 <= confidence < 0.8:
        return "retrieve"  # RT-07
    if state["execution_mode"] == "batch":
        return "auto_review_report"  # RT-18
    if state["execution_mode"] == "eval":
        return "auto_confirm_report"
    return "human_review"  # RT-08（含首次 <0.5，不重试）


def route_after_report_check(state: dict[str, Any]) -> str:
    """RT-12 / RT-13；缺项优先于 degraded_review。"""
    check = state.get("report_elements_check") or {}
    if check.get("passed"):
        return "degraded_review_finalize" if state.get("auto_review") else "finalize"
    if state.get("report_retry_count", 0) < 1:
        return "report_fix"  # RT-12
    return "degraded_finalize"  # RT-13


def route_after_resume(state: dict[str, Any]) -> str:
    """RT-09 / RT-10 / RT-11。"""
    human = state.get("human_review") or {}
    decision = human.get("decision")
    if decision == "abort":
        return "aborted"  # RT-11
    if decision == "confirm":
        return "report"  # RT-09，不重跑上游
    if state.get("interrupt_type") == "clarification":
        return "parse_input"  # RT-10 澄清补充不增修订号
    if state.get("review_round", 0) >= 2:
        raise DecisionNotAllowed("review_round=2 不允许 supplement")
    return "parse_input"  # RT-10


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def should_expire(state: dict[str, Any], now_iso: str | None = None) -> bool:
    """RT-16 懒判定：仅 waiting_human 且已过 interrupt_expires_at。"""
    if state.get("status") != "waiting_human":
        return False
    expires_at = state.get("interrupt_expires_at")
    if not expires_at:
        return False
    now = _parse_iso(now_iso) if now_iso else datetime.now(timezone.utc)
    return now >= _parse_iso(expires_at)


def is_dedupe_candidate(
    input_type: str, execution_mode: str, fingerprint: str | None
) -> bool:
    """RT-17：单条完整输入才参与；csv_batch/eval 不参与。"""
    return (
        execution_mode == "single"
        and input_type in DEDUPE_INPUT_TYPES
        and bool(fingerprint)
    )


def auto_review_flag(state: dict[str, Any]) -> bool:
    """RT-18：仅批量置 auto_review。"""
    return state.get("execution_mode") == "batch"


def auto_review_step() -> dict[str, Any]:
    return {
        "node": "auto_review_report",
        "event": "auto_degrade",
        "rule_id": "RT-18",
        "summary": "批量低置信自动复核",
    }


def node_error_outcome(node: str, exc: BaseException) -> dict[str, Any]:
    """RT-14：未捕获异常映射为 failed，保留节点与错误码。"""
    code = getattr(exc, "error_code", None) or "INTERNAL_ERROR"
    return {
        "status": "failed",
        "error_code": code,
        "node": node,
        "message": str(exc) or exc.__class__.__name__,
    }


def row_failure_outcome(exc: BaseException) -> dict[str, Any]:
    """RT-15 / RT-19：批量行失败隔离，不进入图。"""
    code = getattr(exc, "error_code", None) or "FIELD_INVALID"
    return {"status": "failed", "error_code": code, "message": str(exc)}


def batch_timeout_actions(
    rows: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    """RT-20：未开始行取消，运行中行允许完成。"""
    cancelled = [r["row_id"] for r in rows if r.get("status") == "pending"]
    allowed = [r["row_id"] for r in rows if r.get("status") == "running"]
    return cancelled, allowed


def is_clarify_interrupt(status: str, interrupt_type: str | None, execution_mode: str, input_type: str) -> bool:
    """DB CHECK 同口径：clarification 只存在于 single + nl/chat。"""
    return (
        status == "waiting_human"
        and interrupt_type == "clarification"
        and execution_mode == "single"
        and input_type in CLARIFY_INPUT_TYPES
    )
