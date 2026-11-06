"""RT-01~RT-20 路由纯函数测试（先红后绿）。

测试只依赖 runtime.routing 的公开函数与 DiagnosisState 约定，
不 mock 内部实现，断言来自 ARCH §3.4 / §3.5 与 HANDOFF §5。
"""

from __future__ import annotations

import pytest

from app.runtime import routing


def state(**overrides):
    base = {
        "execution_mode": "single",
        "input_type": "form",
        "missing_fields": [],
        "input_fingerprint": "sha256:" + "a" * 64,
        "fingerprint_scope": "dedupe",
        "diagnosis": {"confidence": 0.95, "knowledge_status": "supported"},
        "retry_count": 0,
        "review_round": 0,
        "report_retry_count": 0,
        "auto_review": False,
        "report_elements_check": {"passed": True, "missing": [], "present": []},
        "human_review": None,
        "interrupt_type": None,
        "status": "running",
        "hard_error": None,
        "interrupt_expires_at": None,
    }
    base.update(overrides)
    return base


# RT-01 完整输入 → retrieve
def test_rt01_single_complete_goes_retrieve():
    assert routing.route_after_parse(state()) == "retrieve"


# RT-02 单条 NL/chat 缺字段 → clarify；批量/eval 禁止
def test_rt02_single_nl_missing_goes_clarify():
    s = state(input_type="nl", missing_fields=[{"field": "product_type"}])
    assert routing.route_after_parse(s) == "clarify"


def test_rt02_chat_single_missing_goes_clarify():
    s = state(input_type="chat", missing_fields=[{"field": "air_temp_k"}])
    assert routing.route_after_parse(s) == "clarify"


def test_rt02_batch_never_clarifies():
    s = state(
        execution_mode="batch",
        input_type="csv_batch",
        missing_fields=[{"field": "product_type"}],
    )
    assert routing.route_after_parse(s) == "row_failed"


def test_rt02_eval_never_clarifies():
    s = state(
        execution_mode="eval",
        input_type="form",
        missing_fields=[{"field": "product_type"}],
    )
    assert routing.route_after_parse(s) == "sample_failed"


# RT-03 CSV 单条/表单缺字段 → error，不进 retrieval
def test_rt03_single_csv_missing_goes_error():
    s = state(input_type="csv_single", missing_fields=[{"field": "torque_nm"}])
    assert routing.route_after_parse(s) == "error"


def test_rt03_single_form_missing_goes_error():
    s = state(input_type="form", missing_fields=[{"field": "tool_wear_min"}])
    assert routing.route_after_parse(s) == "error"


# RT-04 检索覆盖 → diagnose 固定边
def test_rt04_coverage_covered_goes_diagnose():
    s = state(retrieval={"coverage": "covered"})
    assert routing.route_after_retrieve(s) == "diagnose"


# RT-05 未覆盖优先于其他规则
def test_rt05_missing_knowledge_goes_report_even_if_low_confidence():
    s = state(diagnosis={"confidence": 0.42, "knowledge_status": "missing"})
    assert routing.route_after_diagnose(s) == "report"


# RT-06 高置信 0.8 边界归 high → report
def test_rt06_high_confidence_goes_report():
    s = state(diagnosis={"confidence": 0.8, "knowledge_status": "supported"})
    assert routing.route_after_diagnose(s) == "report"
    assert routing.confidence_level(0.8) == "high"
    assert routing.confidence_level(0.7999) == "medium"


# RT-07 中置信首次 → retrieve 重试一次，之后不再重试
def test_rt07_medium_confidence_first_retries_once():
    s = state(diagnosis={"confidence": 0.62, "knowledge_status": "supported"})
    assert routing.route_after_diagnose(s) == "retrieve"


def test_rt07_after_retry_medium_goes_human_review():
    s = state(
        diagnosis={"confidence": 0.62, "knowledge_status": "supported"},
        retry_count=1,
    )
    assert routing.route_after_diagnose(s) == "human_review"


# RT-08 低置信不重试（RT-08 优先于 RT-07）→ human_review
def test_rt08_low_confidence_first_never_retries():
    s = state(diagnosis={"confidence": 0.42, "knowledge_status": "supported"})
    assert routing.route_after_diagnose(s) == "human_review"


def test_rt08_batch_low_confidence_goes_auto_review():
    s = state(
        execution_mode="batch",
        input_type="csv_batch",
        diagnosis={"confidence": 0.42, "knowledge_status": "supported"},
    )
    assert routing.route_after_diagnose(s) == "auto_review_report"


def test_rt08_eval_low_confidence_goes_auto_confirm():
    s = state(
        execution_mode="eval",
        diagnosis={"confidence": 0.42, "knowledge_status": "supported"},
    )
    assert routing.route_after_diagnose(s) == "auto_confirm_report"


# RT-09 人工 confirm → report（不重跑上游）
def test_rt09_confirm_resumes_to_report():
    s = state(
        status="waiting_human",
        interrupt_type="review",
        human_review={"decision": "confirm"},
        review_round=1,
    )
    assert routing.route_after_resume(s) == "report"


# RT-10 补充重建 → parse_input；round=2 禁止
def test_rt10_review_supplement_rebuilds_parse():
    s = state(
        status="waiting_human",
        interrupt_type="review",
        human_review={"decision": "supplement"},
        review_round=1,
    )
    assert routing.route_after_resume(s) == "parse_input"


def test_rt10_clarification_supplement_rebuilds_parse():
    s = state(
        status="waiting_human",
        interrupt_type="clarification",
        human_review={"decision": "supplement"},
    )
    assert routing.route_after_resume(s) == "parse_input"


def test_rt10_round_two_supplement_is_rejected():
    s = state(
        status="waiting_human",
        interrupt_type="review",
        human_review={"decision": "supplement"},
        review_round=2,
    )
    with pytest.raises(routing.DecisionNotAllowed):
        routing.route_after_resume(s)


# RT-11 abort → aborted
def test_rt11_abort_goes_aborted():
    s = state(
        status="waiting_human",
        interrupt_type="review",
        human_review={"decision": "abort"},
        review_round=1,
    )
    assert routing.route_after_resume(s) == "aborted"


# RT-12 报告缺项首次 → report_fix
def test_rt12_report_missing_first_fix():
    s = state(report_elements_check={"passed": False, "missing": ["免责声明"]})
    assert routing.route_after_report_check(s) == "report_fix"


# RT-13 修复一次后仍缺 → degraded_finalize（缺项优先于 degraded_review）
def test_rt13_report_missing_after_fix_degrades():
    s = state(
        report_elements_check={"passed": False, "missing": ["免责声明"]},
        report_retry_count=1,
        auto_review=True,
    )
    assert routing.route_after_report_check(s) == "degraded_finalize"


def test_report_pass_auto_review_goes_degraded_review():
    s = state(auto_review=True)
    assert routing.route_after_report_check(s) == "degraded_review_finalize"


def test_report_pass_normal_goes_finalize():
    assert routing.route_after_report_check(state()) == "finalize"


# RT-14 未捕获异常 → error
def test_rt14_hard_error_goes_error():
    s = state(hard_error={"code": "FIELD_INVALID", "node": "parse_input"})
    assert routing.route_after_parse(s) == "error"


def test_rt14_node_error_maps_to_failed_outcome():
    outcome = routing.node_error_outcome("retrieve", RuntimeError("boom"))
    assert outcome["status"] == "failed"
    assert outcome["error_code"] == "INTERNAL_ERROR"
    assert outcome["node"] == "retrieve"


# RT-15 批量行失败隔离
def test_rt15_row_error_isolation():
    outcome = routing.row_failure_outcome(ValueError("bad row"))
    assert outcome["status"] == "failed"
    assert outcome["error_code"] == "FIELD_INVALID"


# RT-16 TTL 懒判定
def test_rt16_expired_when_past_deadline():
    s = state(
        status="waiting_human",
        interrupt_type="clarification",
        interrupt_expires_at="2026-10-23T10:00:00Z",
    )
    assert routing.should_expire(s, now_iso="2026-10-23T10:00:01Z") is True
    assert routing.should_expire(s, now_iso="2026-10-23T09:59:59Z") is False


def test_rt16_non_waiting_never_expires():
    s = state(
        status="running",
        interrupt_expires_at="2026-10-23T10:00:00Z",
    )
    assert routing.should_expire(s, now_iso="2026-11-23T10:00:01Z") is False


# RT-17 指纹去重适用性
def test_rt17_dedupe_only_for_single_complete_inputs():
    assert routing.is_dedupe_candidate("form", "single", "sha256:" + "a" * 64) is True
    assert routing.is_dedupe_candidate("nl", "single", "sha256:" + "a" * 64) is True
    assert routing.is_dedupe_candidate("chat", "single", "sha256:" + "a" * 64) is True
    assert routing.is_dedupe_candidate("csv_batch", "batch", "sha256:" + "a" * 64) is False
    assert routing.is_dedupe_candidate("form", "eval", None) is False
    assert routing.is_dedupe_candidate("form", "single", None) is False


# RT-18 批量低置信置 auto_review 并写 auto_degrade
def test_rt18_auto_review_flag():
    step = routing.auto_review_step()
    assert step["event"] == "auto_degrade"
    assert step["rule_id"] == "RT-18"
    assert routing.auto_review_flag(state(execution_mode="batch")) is True
    assert routing.auto_review_flag(state(execution_mode="single")) is False


# RT-19 批量行缺失/非法不得进入 clarify
def test_rt19_batch_row_missing_never_clarifies():
    s = state(
        execution_mode="batch",
        input_type="csv_batch",
        missing_fields=[{"field": "device_id"}],
    )
    assert routing.route_after_parse(s) == "row_failed"


# RT-20 批量任务超时：未开始取消，运行中允许完成
def test_rt20_timeout_cancels_pending_only():
    rows = [
        {"row_id": "row_1", "status": "pending"},
        {"row_id": "row_2", "status": "running"},
        {"row_id": "row_3", "status": "succeeded"},
    ]
    cancelled, allowed = routing.batch_timeout_actions(rows)
    assert cancelled == ["row_1"]
    assert allowed == ["row_2"]


# 终态集合与状态投影
def test_terminal_statuses():
    assert routing.is_terminal("degraded_review") is True
    assert routing.is_terminal("waiting_human") is False
