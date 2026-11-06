"""运行配置（ARCH §9.6）。"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="EDG_",
        extra="ignore",
    )

    app_name: str = "设备故障诊断智能体"
    version: str = "1.0.0"
    api_prefix: str = "/api/v1"
    app_origin: str = "http://127.0.0.1:8000"
    csrf_enforce: bool = False

    base_dir: Path = REPO_ROOT
    storage_dir: Path = REPO_ROOT / "storage"
    db_path: Path = REPO_ROOT / "storage" / "app.db"
    checkpoint_path: Path = REPO_ROOT / "storage" / "checkpoints.sqlite3"
    upload_dir: Path = REPO_ROOT / "storage" / "uploads"
    knowledge_dir: Path = REPO_ROOT / "storage" / "knowledge"
    batch_dir: Path = REPO_ROOT / "storage" / "batches"
    knowledge_seed_path: Path = Path(__file__).resolve().parent / "knowledge_seed.json"
    prompts_dir: Path = Path(__file__).resolve().parents[1] / "prompts"
    sensitive_words_path: Path = REPO_ROOT / "config" / "sensitive_words.txt"
    bge_m3_path: Path = REPO_ROOT / "models" / "bge-m3"
    dataset_path: Path = REPO_ROOT / "data" / "ai4i2020.csv"

    embedding_mode: str = "auto"  # auto | bge-m3 | hash
    llm_mode: str = "deepseek"  # deepseek | fake | disabled
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    session_ttl_hours: int = 24
    app_env: str = "development"
    https_enabled: bool = False
    db_encryption_key: str = ""
    login_max_failures: int = 5
    login_lock_minutes: int = 5
    global_timeout_seconds: float = 15.0
    interrupt_ttl_minutes: int = 30
    interrupt_scan_seconds: float = 60.0
    batch_task_timeout_minutes: int = 60
    llm_call_budget_seconds: float = 5.0
    llm_connect_timeout_seconds: float = 2.0
    heartbeat_seconds: float = 15.0
    sse_poll_seconds: float = 0.3

    upload_max_bytes: int = 5 * 1024 * 1024
    csv_max_rows: int = 500
    device_id_max_length: int = 64
    page_size_default: int = 20
    page_size_max: int = 100
    graph_concurrency: int = 2

    @property
    def database_url(self) -> str:
        return str(self.db_path)

    def ensure_dirs(self) -> None:
        for path in (self.db_path, self.checkpoint_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.batch_dir.mkdir(parents=True, exist_ok=True)

    def production_startup_gaps(self) -> list[str]:
        """AC-SE-05：生产环境启动自检缺失项（非生产环境返回空）。"""
        if self.app_env.strip().lower() != "production":
            return []
        gaps: list[str] = []
        if not self.https_enabled:
            gaps.append("HTTPS 未启用（EDG_HTTPS_ENABLED=false）")
        if not self.db_encryption_key.strip():
            gaps.append("数据库加密密钥缺失（EDG_DB_ENCRYPTION_KEY）")
        if self.llm_mode == "deepseek" and not self.deepseek_api_key.strip():
            gaps.append("DeepSeek API Key 缺失（EDG_DEEPSEEK_API_KEY）")
        return gaps
