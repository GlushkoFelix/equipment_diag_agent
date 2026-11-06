"""图执行器：后台运行、中断投影、全局 15s 熔断与启动对账。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command

from app import records
from app.config import Settings
from app.db import Database, utcnow
from app.knowledge import KnowledgeService
from app.llm_client import DeepSeekClient
from app.prompts import PromptLibrary
from app.reasoning import LlmReasoner
from app.runtime.graph import build_graph
from app.runtime.nodes import Nodes
from app.runtime.state import DiagnosisState

logger = logging.getLogger("edg.runner")


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class DiagnosisRunner:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        knowledge: KnowledgeService,
        checkpointer: Any,
    ):
        self.settings = settings
        self.db = db
        self.knowledge = knowledge
        self.checkpointer = checkpointer
        self.nodes = Nodes(settings, db, knowledge, reasoner=self._build_reasoner())
        self.graph = build_graph(self.nodes, checkpointer)
        self.semaphore = asyncio.Semaphore(max(1, settings.graph_concurrency))
        self._tasks: dict[str, asyncio.Task] = {}

    def _build_reasoner(self) -> LlmReasoner | None:
        """只有 deepseek 模式且 Key 齐备时才接线；fake 模式保持纯规则离线。"""
        if self.settings.llm_mode != "deepseek" or not self.settings.deepseek_api_key:
            return None
        try:
            prompts = PromptLibrary(self.settings.prompts_dir)
            return LlmReasoner(DeepSeekClient(self.settings), prompts)
        except Exception as exc:
            logger.warning("llm reasoner disabled: %s", type(exc).__name__)
            return None

    # ---------- lifecycle ----------
    def start(self, diagnosis_id: str, state: DiagnosisState) -> None:
        task = asyncio.create_task(self._run_new(diagnosis_id, state))
        self._tasks[diagnosis_id] = task

    async def resume(self, diagnosis_id: str, decision: dict[str, Any]) -> None:
        config = {"configurable": {"thread_id": diagnosis_id}}
        try:
            async with self.semaphore:
                # 每次 resume 重置执行窗口（ARCH §4.4）
                timeout = self.settings.global_timeout_seconds + 1.0
                result = await asyncio.wait_for(
                    self.graph.ainvoke(Command(resume=decision), config), timeout=timeout
                )
            self._handle_result(diagnosis_id, result)
        except asyncio.TimeoutError:
            self._timeout(diagnosis_id)
        except Exception as exc:  # RT-14
            logger.exception("resume failed for %s", diagnosis_id)
            self._fail(diagnosis_id, exc)

    async def wait(self, diagnosis_id: str, timeout: float = 30.0) -> None:
        task = self._tasks.get(diagnosis_id)
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except Exception:
                pass

    async def wait_all(self) -> None:
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _run_new(self, diagnosis_id: str, state: DiagnosisState) -> None:
        config = {"configurable": {"thread_id": diagnosis_id}}
        try:
            async with self.semaphore:
                deadline = _parse_iso(state["deadline_at"])
                timeout = max(0.05, (deadline - datetime.now(timezone.utc)).total_seconds()) + 1.0
                result = await asyncio.wait_for(self.graph.ainvoke(state, config), timeout=timeout)
            self._handle_result(diagnosis_id, result)
        except asyncio.TimeoutError:
            self._timeout(diagnosis_id)
        except Exception as exc:  # RT-14
            logger.exception("diagnosis failed for %s", diagnosis_id)
            self._fail(diagnosis_id, exc)

    async def run_inline(self, diagnosis_id: str, state: DiagnosisState) -> None:
        """批量/评测就地执行到终态；节点自带 finalize，超时/异常按 RT-14 投影。"""
        config = {"configurable": {"thread_id": diagnosis_id}}
        try:
            async with self.semaphore:
                deadline = _parse_iso(state["deadline_at"])
                timeout = max(0.05, (deadline - datetime.now(timezone.utc)).total_seconds()) + 1.0
                await asyncio.wait_for(self.graph.ainvoke(state, config), timeout=timeout)
        except asyncio.TimeoutError:
            self._timeout(diagnosis_id)
        except Exception as exc:  # RT-14
            logger.exception("inline diagnosis failed for %s", diagnosis_id)
            self._fail(diagnosis_id, exc)

    def _handle_result(self, diagnosis_id: str, result: dict[str, Any]) -> None:
        interrupts = result.get("__interrupt__") or ()
        if not interrupts:
            return
        payload = interrupts[0].value
        interrupt_type = payload["interrupt_type"]
        expires_at = payload["expires_at"]
        review_round = int(payload.get("review_round", 0))
        row = self.db.connection().execute(
            "SELECT status, version, diagnosis_revision FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)
        ).fetchone()
        if row is None or row["status"] != "running":
            return  # 幂等：已投影的中断不重复写
        records.mark_interrupt(
            self.db,
            diagnosis_id,
            interrupt_type,
            payload["payload"],
            expires_at,
            review_round,
        )
        records.append_step(
            self.db,
            diagnosis_id,
            int(row["diagnosis_revision"]),
            "clarify" if interrupt_type == "clarification" else "human_review",
            "interrupt",
            summary=f"{interrupt_type} 中断",
        )

    def _timeout(self, diagnosis_id: str) -> None:
        row = self.db.connection().execute(
            "SELECT status, started_at FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)
        ).fetchone()
        if row is None or row["status"] not in ("running", "waiting_human"):
            return
        duration = int(
            (datetime.now(timezone.utc) - _parse_iso(row["started_at"])).total_seconds() * 1000
        )
        if row["status"] == "waiting_human":
            records.set_running(self.db, diagnosis_id)
        records.finalize(
            self.db, diagnosis_id, "failed_timeout", error_code="TIMEOUT", duration_ms=duration
        )
        records.append_step(
            self.db, diagnosis_id, 1, "timeout_finalize", "timeout", summary="全局 15s 熔断"
        )

    def _fail(self, diagnosis_id: str, exc: BaseException) -> None:
        from app.runtime import routing

        outcome = routing.node_error_outcome("graph", exc)
        row = self.db.connection().execute(
            "SELECT status FROM diagnoses WHERE diagnosis_id=?", (diagnosis_id,)
        ).fetchone()
        if row is None or row["status"] not in ("running", "waiting_human"):
            return
        if row["status"] == "waiting_human":
            records.set_running(self.db, diagnosis_id)
        records.finalize(
            self.db, diagnosis_id, "failed", error_code=outcome["error_code"], duration_ms=0
        )

    # ---------- startup reconciliation ----------
    async def reconcile_on_startup(self) -> None:
        """ARCH §4.9：进程重启时 running 诊断置 failed(PROCESS_RESTART)，不自动重跑。"""
        conn = self.db.connection()
        rows = conn.execute("SELECT diagnosis_id FROM diagnoses WHERE status='running'").fetchall()
        for row in rows:
            records.finalize(
                self.db, row["diagnosis_id"], "failed", error_code="PROCESS_RESTART", duration_ms=0
            )
        await self.run_once()

    async def run_once(self) -> int:
        """扫描 waiting_human 并过期超时中断（AC-DG-22）；无请求也会被后台任务驱动。"""
        conn = self.db.connection()
        rows = conn.execute(
            "SELECT * FROM diagnoses WHERE status='waiting_human' AND interrupt_expires_at IS NOT NULL"
        ).fetchall()
        expired = 0
        for row in rows:
            if records.expire_if_needed(self.db, row):
                expired += 1
        if expired:
            logger.info("interrupt ttl scan expired=%s", expired)
        return expired

    async def ttl_loop(self, interval_seconds: float) -> None:
        """应用 lifespan 注册的后台任务：每 interval 秒执行一次 run_once。"""
        interval = max(0.05, float(interval_seconds))
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.run_once()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("interrupt ttl scan failed")
        except asyncio.CancelledError:
            raise
