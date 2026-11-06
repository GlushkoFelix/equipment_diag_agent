"""离线评测执行入口：跑 120 条 AI4I 样本并落库 eval_batches/eval_samples。

用法（backend 目录下）：
    python scripts/run_evaluation.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: E402

from app import evaluation  # noqa: E402
from app.config import Settings  # noqa: E402
from app.db import Database  # noqa: E402
from app.knowledge import KnowledgeService  # noqa: E402
from app.runtime.runner import DiagnosisRunner  # noqa: E402


async def main() -> None:
    settings = Settings()
    settings.ensure_dirs()
    db = Database(settings.db_path)
    db.migrate()
    async with AsyncSqliteSaver.from_conn_string(str(settings.checkpoint_path)) as saver:
        knowledge = KnowledgeService(settings, db)
        knowledge.ensure_built()
        runner = DiagnosisRunner(settings, db, knowledge, saver)
        user_id = evaluation.ensure_eval_user(db)
        eval_batch_id = await evaluation.run_evaluation(
            db, settings, runner, knowledge, user_id
        )
        row = db.connection().execute(
            "SELECT * FROM eval_batches WHERE eval_batch_id=?", (eval_batch_id,)
        ).fetchone()
        print(f"eval_batch_id={eval_batch_id}")
        print(
            f"accuracy={row['accuracy']} completeness_rate={row['completeness_rate']} "
            f"timeout_rate={row['timeout_rate']} report_count={row['report_count']} "
            f"latency_p95_ms={row['latency_p95_ms']}"
        )
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
