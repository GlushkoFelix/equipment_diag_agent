"""启动自检（ARCH §5.4.2 / FR-KB-03）。"""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import Settings
from app.db import health_check
from app.knowledge import KnowledgeService

logger = logging.getLogger("edg.startup")


class SelfCheck:
    def __init__(self, settings: Settings, db_path: Path, knowledge: KnowledgeService, checkpointer_ready: bool):
        self.settings = settings
        self.components: dict[str, str] = {}
        self.components["database"] = "ok" if health_check(db_path) else "error"
        self.components["checkpoint_store"] = "ok" if checkpointer_ready else "error"
        self.components["vector_index"] = "ok" if knowledge.index_status == "ok" else "missing"
        # 回退向量后端仍可服务诊断；生产默认 BGE-M3（见 knowledge.build_embedder）
        if knowledge.embedding_status == "fallback":
            self.components["embedding_model"] = "degraded"
            self.components["embedding_reason"] = f"fallback:{getattr(knowledge.embedder, 'name', 'unknown')}"
            logger.warning("BGE-M3 不可用，向量后端降级：%s", self.components["embedding_reason"])
        elif knowledge.embedder is None:
            self.components["embedding_model"] = "error"
            self.components["embedding_reason"] = "embedding_backend_unavailable"
        else:
            self.components["embedding_model"] = "ok"
        if settings.llm_mode in ("fake",) or settings.deepseek_api_key:
            self.components["llm_config"] = "ok"
        else:
            # AC-SY-01：缺 Key 时不阻断启动，但须在 /health 列出缺失项
            self.components["llm_config"] = "missing"
            gaps: list[str] = []
            if settings.llm_mode == "deepseek" and not settings.deepseek_api_key.strip():
                gaps.append("EDG_DEEPSEEK_API_KEY")
            self.components["llm_config_missing"] = ",".join(gaps) if gaps else "UNKNOWN"
            logger.warning(
                "LLM 未配置（llm_mode=%s），诊断接口将返回 503：%s",
                settings.llm_mode,
                self.components["llm_config_missing"],
            )
        self._check_assets()

    def _check_assets(self) -> None:
        model_dir = Path(self.settings.bge_m3_path)
        dataset = Path(self.settings.dataset_path)
        if not model_dir.exists():
            if self.settings.embedding_mode == "bge-m3":
                raise RuntimeError(f"BGE-M3 模型目录不存在：{model_dir}")
            logger.warning("BGE-M3 模型目录不存在，使用回退向量后端：%s", model_dir)
        if not dataset.exists():
            logger.warning("AI4I 数据集不存在（评测阶段需补齐）：%s", dataset)

    @property
    def status(self) -> str:
        return "ok" if all(value == "ok" for value in self.components.values()) else "degraded"
