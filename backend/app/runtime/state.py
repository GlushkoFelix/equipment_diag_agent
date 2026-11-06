"""LangGraph 共享状态（ARCH §3.1）。"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class DiagnosisState(TypedDict, total=False):
    request_id: str
    thread_id: str
    version: int
    user_id: int
    input_type: Literal["csv_single", "csv_batch", "form", "nl", "chat"]
    raw_input: dict[str, Any]
    input_fingerprint: str | None
    device_id: str
    field_mapping: dict[str, Any]
    normalized_features: dict[str, Any]
    derived_features: dict[str, Any]
    feature_completeness: float
    missing_fields: list[dict[str, Any]]
    assumptions: list[str]
    data_quality_flags: list[str]
    retrieval: dict[str, Any]
    diagnosis: dict[str, Any]
    retry_count: int
    review_round: int
    report_retry_count: int
    diagnosis_revision: int
    auto_review: bool
    interrupt_type: Literal["clarification", "review"] | None
    interrupt_payload: dict[str, Any] | None
    interrupt_expires_at: str | None
    human_review: dict[str, Any] | None
    report_md: str | None
    report_title: str | None
    report_elements_check: dict[str, Any] | None
    report_meta: dict[str, Any] | None
    status: str
    errors: list[dict[str, Any]]
    trace_steps: list[dict[str, Any]]
    timings: dict[str, Any]

    execution_mode: Literal["single", "batch", "eval"]
    execution_started_at: str
    deadline_at: str
    batch_task_id: str | None
    row_id: str | None
    intake_draft: dict[str, Any] | None
    fingerprint_scope: Literal["dedupe", "trace"] | None
    hard_error: dict[str, Any] | None
    retry_requested: bool
