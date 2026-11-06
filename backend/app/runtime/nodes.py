"""LangGraph 节点实现。

规则/模板全部在领域模块（features/diagnosis/report），节点只做编排与投影。
interrupt() 之前不写业务副作用（ARCH §3.7）。
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from langgraph.types import interrupt

from app import diagnosis as diagnosis_domain
from app import features as features_domain
from app import records, report
from app.config import Settings
from app.db import Database, utcnow
from app.knowledge import KnowledgeService
from app.runtime import routing
from app.runtime.state import DiagnosisState

logger = logging.getLogger("edg.nodes")


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Nodes:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        knowledge: KnowledgeService,
        reasoner: Any | None = None,
    ):
        self.settings = settings
        self.db = db
        self.knowledge = knowledge
        self.reasoner = reasoner

    # ---------- helpers ----------
    def _remaining_budget(self, state: DiagnosisState) -> float | None:
        """LLM 单次预算 = min(5s, 剩余全局预算 - 余量)（ARCH §4.6）。"""
        raw = state.get("deadline_at")
        if not raw:
            return None
        try:
            deadline = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
        budget = min(float(self.settings.llm_call_budget_seconds), remaining - 0.3)
        return budget if budget >= 0.3 else None

    def _step(
        self,
        state: DiagnosisState,
        node: str,
        event: str,
        rule_id: str | None = None,
        summary: str | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        records.append_step(
            self.db,
            state["thread_id"],
            state.get("diagnosis_revision", 1),
            node,
            event,
            rule_id=rule_id,
            summary=summary,
            duration_ms=duration_ms,
            error_code=error_code,
        )

    # ---------- nodes ----------
    async def parse_input(self, state: DiagnosisState) -> dict[str, Any]:
        started = time.perf_counter()
        self._step(state, "parse_input", "start")
        payload = dict(state.get("raw_input") or {})
        payload["_user_id"] = state.get("user_id", 0)
        result = features_domain.normalize_input(state["input_type"], payload)
        duration = int((time.perf_counter() - started) * 1000)

        if not result.ok:
            rule = "RT-14" if state["execution_mode"] == "eval" else (
                "RT-19" if state["execution_mode"] == "batch" else "RT-03"
            )
            self._step(
                state,
                "parse_input",
                "end",
                rule_id=rule,
                summary=result.error_code or "字段校验失败",
                duration_ms=duration,
                error_code=result.error_code,
            )
            return {
                "hard_error": {"code": result.error_code, "node": "parse_input"},
                "missing_fields": result.missing_fields,
                "timings": {**state.get("timings", {}), "parse_input": duration},
            }

        features_block = {
            "normalized": result.normalized,
            "derived": result.derived,
            "completeness": result.completeness,
            "missing_fields": [item["field"] for item in result.missing_fields],
            "assumptions": result.assumptions,
            "data_quality_flags": result.data_quality_flags,
        }
        records.touch_runtime(self.db, state["thread_id"], features_block=features_block)
        self._step(
            state,
            "parse_input",
            "end",
            rule_id="RT-02" if result.missing_fields else "RT-01",
            summary="字段缺失，进入澄清" if result.missing_fields else "7 项特征齐备",
            duration_ms=duration,
        )
        return {
            "device_id": result.normalized.get("device_id") or state.get("device_id"),
            "normalized_features": result.normalized,
            "derived_features": result.derived,
            "feature_completeness": result.completeness,
            "missing_fields": result.missing_fields,
            "assumptions": result.assumptions,
            "data_quality_flags": result.data_quality_flags,
            "hard_error": None,
            "timings": {**state.get("timings", {}), "parse_input": duration},
        }

    async def clarify(self, state: DiagnosisState) -> dict[str, Any]:
        expires_at = _iso(datetime.now(timezone.utc) + timedelta(minutes=self.settings.interrupt_ttl_minutes))
        payload = {
            "created_at": utcnow(),
            "missing_fields": state.get("missing_fields", []),
            "partial_features": {
                k: v for k, v in (state.get("normalized_features") or {}).items() if k != "device_id" and v is not None
            },
            "device_id": state.get("device_id"),
        }
        decision = interrupt(
            {
                "interrupt_type": "clarification",
                "payload": payload,
                "expires_at": expires_at,
                "review_round": 0,
            }
        )
        merged = dict(state.get("raw_input") or {})
        for key, value in (decision.get("supplement") or {}).items():
            if value is not None:
                merged[key] = value
        self._step(state, "clarify", "resume", rule_id="RT-10", summary="用户补充澄清字段")
        return {
            "raw_input": merged,
            "human_review": decision,
            "interrupt_type": "clarification",
            "interrupt_expires_at": expires_at,
        }

    async def retrieve(self, state: DiagnosisState) -> dict[str, Any]:
        started = time.perf_counter()
        self._step(state, "retrieve", "start")
        retry_used = bool(state.get("retry_requested"))
        top_k = 8 if retry_used else 5
        features = dict(state.get("normalized_features") or {})
        features["completeness"] = state.get("feature_completeness", 1.0)
        features.update(state.get("derived_features") or {})
        result = self.knowledge.retrieve(features, top_k=top_k, retry=retry_used)
        duration = int((time.perf_counter() - started) * 1000)
        retrieval = {
            "coverage": result.coverage,
            "max_score": result.max_score,
            "top_k": result.top_k,
            "retry_used": retry_used,
            "hits": result.hits,
        }
        records.touch_runtime(self.db, state["thread_id"], retrieval=retrieval)
        if retry_used:
            records.update_projection(self.db, state["thread_id"], retry_count=1)
            self._step(state, "retrieve", "retry", rule_id="RT-07", summary="扩展检索 Top-8", duration_ms=duration)
        self._step(
            state,
            "retrieve",
            "end",
            rule_id="RT-04",
            summary=f"命中 {len(result.hits)} 条，coverage={result.coverage}",
            duration_ms=duration,
        )
        return {
            "retrieval": retrieval,
            "retry_count": 1 if retry_used else int(state.get("retry_count", 0)),
            "retry_requested": False,
            "timings": {**state.get("timings", {}), "retrieve": duration},
        }

    async def diagnose(self, state: DiagnosisState) -> dict[str, Any]:
        started = time.perf_counter()
        self._step(state, "diagnose", "start")
        features = dict(state.get("normalized_features") or {})
        features["completeness"] = state.get("feature_completeness", 1.0)
        features.update(state.get("derived_features") or {})
        retrieval = state.get("retrieval") or {}
        base = diagnosis_domain.rule_diagnose(
            features,
            state.get("data_quality_flags", []),
            state.get("assumptions", []),
            retrieval,
        )
        result = base
        llm_used = False
        llm_attempts = 0
        # 知识未覆盖时按 PRD US-19 直接声明未覆盖，不调用 LLM 归因
        if self.reasoner is not None and base["knowledge_status"] == "supported":
            budget = self._remaining_budget(state)
            if budget is not None:
                try:
                    call = await asyncio.wait_for(
                        self.reasoner.attribute(
                            features=features,
                            derived=state.get("derived_features") or {},
                            flags=state.get("data_quality_flags", []),
                            assumptions=state.get("assumptions", []),
                            retrieval=retrieval,
                            rule_hits=base["rule_hits"],
                            user_text=(state.get("raw_input") or {}).get("text"),
                            budget=budget,
                        ),
                        timeout=budget + 0.15,
                    )
                    llm_attempts = call.attempts
                    merged, accepted = diagnosis_domain.merge_llm_attribution(
                        base, call.payload, retrieval
                    )
                    if accepted:
                        result, llm_used = merged, True
                    else:
                        result = diagnosis_domain.finalize_rule_only(base)
                except asyncio.TimeoutError:
                    logger.warning("diagnose llm timeout diagnosis=%s", state["thread_id"])
                except Exception as exc:  # LLM 失败按规则兜底，不伪造成功
                    logger.warning(
                        "diagnose llm fallback code=%s diagnosis=%s",
                        getattr(exc, "code", type(exc).__name__),
                        state["thread_id"],
                    )
        if not llm_used:
            result = diagnosis_domain.finalize_rule_only(base)
        result["confidence_breakdown"] = {
            **result["confidence_breakdown"],
            "llm_used": llm_used,
            "llm_attempts": llm_attempts,
        }
        confidence = float(result["confidence"])
        evidence = diagnosis_domain.evidence_refs(state.get("retrieval") or {})
        duration = int((time.perf_counter() - started) * 1000)
        records.update_projection(
            self.db,
            state["thread_id"],
            primary_type=result["primary_type"],
            secondary_types_json=result["secondary_types"],
            confidence=confidence,
            confidence_level=routing.confidence_level(confidence),
            confidence_breakdown_json=result["confidence_breakdown"],
            knowledge_status=result["knowledge_status"],
            evidence_refs_json=evidence,
        )
        self._step(
            state,
            "diagnose",
            "end",
            rule_id="RT-05" if result["knowledge_status"] == "missing" else "RT-06",
            summary=(
                f"主类型 {result['primary_type']}，置信度 {confidence:.4f}，"
                f"{'LLM 归因' if llm_used else '规则兜底'}"
            ),
            duration_ms=duration,
        )
        retry_requested = (
            result["knowledge_status"] == "supported"
            and 0.5 <= confidence < 0.8
            and int(state.get("retry_count", 0)) < 1
        )
        return {
            "diagnosis": result,
            "retry_requested": retry_requested,
            "timings": {**state.get("timings", {}), "diagnose": duration},
        }

    async def auto_review_report(self, state: DiagnosisState) -> dict[str, Any]:
        trace = routing.auto_review_step()
        self._step(
            state,
            "auto_review_report",
            "auto_degrade",
            rule_id="RT-18",
            summary="置 auto_review=true",
        )
        records.update_projection(self.db, state["thread_id"], auto_review=1)
        return {"auto_review": True, "trace_steps": [*state.get("trace_steps", []), trace]}

    async def auto_confirm_report(self, state: DiagnosisState) -> dict[str, Any]:
        self._step(state, "auto_confirm_report", "resume", summary="评测夹具自动确认")
        return {
            "human_review": {"decision": "confirm", "source": "eval_fixture"},
            "auto_review": False,
        }

    async def human_review(self, state: DiagnosisState) -> dict[str, Any]:
        review_round = int(state.get("review_round", 0)) + 1
        expires_at = _iso(datetime.now(timezone.utc) + timedelta(minutes=self.settings.interrupt_ttl_minutes))
        diag = state.get("diagnosis") or {}
        payload = {
            "created_at": utcnow(),
            "primary_type": diag.get("primary_type"),
            "secondary_types": diag.get("secondary_types", []),
            "confidence": diag.get("confidence"),
            "confidence_level": routing.confidence_level(float(diag.get("confidence", 0))),
            "confidence_breakdown": diag.get("confidence_breakdown"),
            "evidence_refs": diagnosis_domain.evidence_refs(state.get("retrieval") or {}),
            "reason": diag.get("reason", "证据不足，建议人工复核"),
            "missing_fields": state.get("missing_fields", []),
            "review_round": review_round,
        }
        decision = interrupt(
            {
                "interrupt_type": "review",
                "payload": payload,
                "expires_at": expires_at,
                "review_round": review_round,
            }
        )
        self._step(state, "human_review", "resume", rule_id="RT-09", summary=str(decision.get("decision")))
        revision = state.get("diagnosis_revision", 1)
        updates: dict[str, Any] = {
            "human_review": decision,
            "interrupt_type": "review",
            "interrupt_expires_at": expires_at,
            "review_round": review_round,
        }
        if decision.get("decision") == "supplement":
            revision += 1
            merged = dict(state.get("raw_input") or {})
            merged.update({k: v for k, v in (decision.get("supplement") or {}).items() if v is not None})
            updates.update(
                {
                    "raw_input": merged,
                    "diagnosis_revision": revision,
                    "diagnosis": None,
                    "retrieval": None,
                    "report_md": None,
                    "report_title": None,
                    "report_elements_check": None,
                    "report_meta": None,
                }
            )
            records.update_projection(
                self.db,
                state["thread_id"],
                diagnosis_revision=revision,
                primary_type=None,
                secondary_types_json=None,
                confidence=None,
                confidence_level=None,
                confidence_breakdown_json=None,
                knowledge_status=None,
                evidence_refs_json=None,
            )
        return updates

    async def report(self, state: DiagnosisState) -> dict[str, Any]:
        started = time.perf_counter()
        self._step(state, "report", "start")
        features = dict(state.get("normalized_features") or {})
        features["completeness"] = state.get("feature_completeness", 1.0)
        evidence = diagnosis_domain.evidence_refs(state.get("retrieval") or {})
        narrative = None
        narrative_used = False
        narrative_attempts = 0
        if self.reasoner is not None:
            budget = self._remaining_budget(state)
            if budget is not None:
                try:
                    call = await asyncio.wait_for(
                        self.reasoner.narrate(
                            diagnosis=state.get("diagnosis") or {},
                            features=features,
                            derived=state.get("derived_features") or {},
                            flags=state.get("data_quality_flags", []),
                            assumptions=state.get("assumptions", []),
                            evidence=evidence,
                            budget=budget,
                        ),
                        timeout=budget + 0.15,
                    )
                    narrative = call.payload.model_dump()
                    narrative_used = True
                    narrative_attempts = call.attempts
                except asyncio.TimeoutError:
                    logger.warning("report llm timeout diagnosis=%s", state["thread_id"])
                except Exception as exc:
                    logger.warning(
                        "report llm fallback code=%s diagnosis=%s",
                        getattr(exc, "code", type(exc).__name__),
                        state["thread_id"],
                    )
        prompt_version = (
            self.reasoner.prompt_version("reporter")
            if self.reasoner is not None
            else "reporter-v1"
        )
        result = report.build_report(
            diagnosis_id=state["thread_id"],
            device_id=state.get("device_id", ""),
            features=features,
            derived=state.get("derived_features") or {},
            flags=state.get("data_quality_flags", []),
            assumptions=state.get("assumptions", []),
            diagnosis=state.get("diagnosis") or {},
            retrieval=state.get("retrieval") or {},
            evidence=evidence,
            auto_review=bool(state.get("auto_review")),
            human_confirmed=(state.get("human_review") or {}).get("decision") == "confirm",
            kb_version=self.knowledge.kb_version,
            narrative=narrative,
            prompt_version=prompt_version,
            model_name=self.reasoner.model_name if narrative_used else "rule-engine",
            llm_used=narrative_used,
            llm_calls=narrative_attempts,
            sensitive_words_path=self.settings.sensitive_words_path,
        )
        duration = int((time.perf_counter() - started) * 1000)
        self._step(
            state,
            "report",
            "end",
            summary="报告生成完成",
            duration_ms=duration,
        )
        return {
            "report_md": result["markdown"],
            "report_title": result["title"],
            "report_elements_check": result["elements_check"],
            "report_meta": result["meta"],
            "timings": {**state.get("timings", {}), "report": duration},
        }

    async def report_fix(self, state: DiagnosisState) -> dict[str, Any]:
        check = state.get("report_elements_check") or {}
        fixed = report.fix_report(state.get("report_md") or "", check)
        new_check = report.check_report(fixed, diagnosis_domain.evidence_refs(state.get("retrieval") or {}), state.get("diagnosis") or {})
        new_check["report_retry_count"] = 1
        self._step(state, "report_fix", "degrade", rule_id="RT-12", summary="报告缺项修复一次")
        records.update_projection(self.db, state["thread_id"], report_retry_count=1)
        meta = dict(state.get("report_meta") or {})
        meta["report_retry_count"] = 1
        return {
            "report_md": fixed,
            "report_elements_check": new_check,
            "report_retry_count": 1,
            "report_meta": meta,
        }

    def _finalize_common(self, state: DiagnosisState, status: str, error_code: str | None = None) -> dict[str, Any]:
        duration = sum(int(v) for v in (state.get("timings") or {}).values())
        records.finalize(
            self.db,
            state["thread_id"],
            status,
            report_md=state.get("report_md"),
            report_title=state.get("report_title"),
            report_meta=state.get("report_meta"),
            report_check=state.get("report_elements_check"),
            error_code=error_code,
            duration_ms=duration,
        )
        self._step(state, status, "end", summary="诊断终态", duration_ms=duration)
        return {
            "status": status,
            "timings": {**(state.get("timings") or {}), "total_ms": duration},
        }

    async def finalize(self, state: DiagnosisState) -> dict[str, Any]:
        return self._finalize_common(state, "succeeded")

    async def degraded_finalize(self, state: DiagnosisState) -> dict[str, Any]:
        missing = (state.get("report_elements_check") or {}).get("missing") or []
        noted = dict(state)
        noted["report_md"] = report.prepend_missing_note(state.get("report_md") or "", missing)
        return self._finalize_common(noted, "degraded", error_code="REPORT_CHECK_FAILED")

    async def degraded_review_finalize(self, state: DiagnosisState) -> dict[str, Any]:
        return self._finalize_common(state, "degraded_review")

    async def aborted(self, state: DiagnosisState) -> dict[str, Any]:
        return self._finalize_common(state, "aborted", error_code="HUMAN_ABORT")

    async def error(self, state: DiagnosisState) -> dict[str, Any]:
        code = (state.get("hard_error") or {}).get("code", "INTERNAL_ERROR")
        return self._finalize_common(state, "failed", error_code=code)

    async def row_failed(self, state: DiagnosisState) -> dict[str, Any]:
        return {"status": "failed"}

    async def sample_failed(self, state: DiagnosisState) -> dict[str, Any]:
        return {"status": "failed"}
