"""知识检索：BGE-M3 + FAISS IndexFlatIP，离线开发回退到字符 n-gram 哈希向量。

生产路径严格使用 models/bge-m3；hash 回退仅用于无 torch 依赖的本地测试，
启动自检会在 health.dependencies.embedding_backend 暴露实际后端。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from app.config import Settings
from app.db import Database, transaction, utcnow

logger = logging.getLogger("edg.knowledge")

DIM = 512
KB_VERSION = "kb_v1"
COVERED_SCORE = 0.35
VERSION_PATTERN = re.compile(r"^kb_v[0-9]+$")
FAULT_TYPES = ("正常基线", "HDF", "PWF", "OSF", "TWF", "RNF", "通用")
ADVICE_MARKERS = ("建议", "检查", "维护", "更换", "复测", "处置", "清理")
REQUIRED_FIELDS = ("entry_id", "title", "fault_type", "content")


class KnowledgeImportError(ValueError):
    """AC-KB-04：导入校验失败，details 为逐条修复项，调用方不得激活索引。"""

    def __init__(self, details: list[dict[str, Any]]):
        self.details = details
        super().__init__("知识导入校验失败：" + "；".join(str(item) for item in details))


def load_entries_file(path: Path | str) -> list[Any]:
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    try:
        if raw.startswith("["):
            return json.loads(raw)
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    except (TypeError, ValueError) as exc:
        raise KnowledgeImportError(
            [{"entry_index": None, "entry_id": None, "field": "file", "reason": f"JSON_INVALID: {exc}"}]
        ) from exc


def validate_entries(entries: Any) -> list[dict[str, Any]]:
    """校验必填字段、分类与类型；返回规范化条目，失败抛出 RepairItem 列表。"""
    details: list[dict[str, Any]] = []
    if not isinstance(entries, list):
        raise KnowledgeImportError(
            [{"entry_index": None, "entry_id": None, "field": "file", "reason": "ENTRIES_NOT_LIST"}]
        )
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            details.append(
                {"entry_index": index, "entry_id": None, "field": "entry", "reason": "NOT_OBJECT"}
            )
            continue
        entry_id = entry.get("entry_id")
        for field in REQUIRED_FIELDS:
            value = entry.get(field)
            if not isinstance(value, str) or not value.strip():
                details.append(
                    {
                        "entry_index": index,
                        "entry_id": entry_id if isinstance(entry_id, str) else None,
                        "field": field,
                        "reason": "REQUIRED_NON_EMPTY_STRING",
                    }
                )
        keywords = entry.get("keywords")
        if not isinstance(keywords, list) or not keywords or not all(
            isinstance(item, str) and item.strip() for item in keywords
        ):
            details.append(
                {
                    "entry_index": index,
                    "entry_id": entry_id if isinstance(entry_id, str) else None,
                    "field": "keywords",
                    "reason": "REQUIRED_NON_EMPTY_STRING_LIST",
                }
            )
        fault_type = entry.get("fault_type")
        if isinstance(fault_type, str) and fault_type.strip() and fault_type not in FAULT_TYPES:
            details.append(
                {
                    "entry_index": index,
                    "entry_id": entry_id if isinstance(entry_id, str) else None,
                    "field": "fault_type",
                    "reason": "UNKNOWN_CATEGORY",
                }
            )
        if isinstance(entry_id, str) and entry_id.strip():
            if entry_id in seen:
                details.append(
                    {"entry_index": index, "entry_id": entry_id, "field": "entry_id", "reason": "DUPLICATE"}
                )
            seen.add(entry_id)
        if details:
            continue
        normalized.append(
            {
                **entry,
                "entry_id": entry["entry_id"].strip(),
                "title": entry["title"].strip(),
                "fault_type": entry["fault_type"].strip(),
                "keywords": [item.strip() for item in entry["keywords"]],
                "content": entry["content"].strip(),
            }
        )

    if not any(entry.get("fault_type") == "正常基线" for entry in normalized):
        details.append(
            {
                "entry_index": None,
                "entry_id": None,
                "field": "fault_type",
                "reason": "MISSING_NORMAL_BASELINE",
            }
        )
    if normalized and not any(
        any(marker in entry["content"] for marker in ADVICE_MARKERS) for entry in normalized
    ):
        details.append(
            {"entry_index": None, "entry_id": None, "field": "content", "reason": "MISSING_ADVICE"}
        )
    if details:
        raise KnowledgeImportError(details)
    return normalized


def _tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).lower()
    tokens: list[str] = []
    tokens.extend(re.findall(r"[a-z0-9_.]+", text))
    for chunk in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(chunk[i : i + 2] for i in range(max(0, len(chunk) - 1)))
        tokens.append(chunk)
    return tokens


class HashEmbedder:
    """确定性字符 n-gram 哈希向量（仅开发/测试回退）。"""

    name = "hash-ngram-512"
    is_fallback = True

    def encode(self, texts: Iterable[str]) -> np.ndarray:
        items = list(texts)
        vectors = np.zeros((len(items), DIM), dtype="float32")
        for row, text in enumerate(items):
            for token in _tokenize(text):
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "little") % DIM
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vectors[row, index] += sign
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (vectors / norms).astype("float32")


class BgeM3Embedder:
    name = "BAAI/bge-m3"
    is_fallback = False

    def __init__(self, model_path: Path):
        from sentence_transformers import SentenceTransformer  # 延迟导入，避免测试加载

        self._model = SentenceTransformer(str(model_path))

    def encode(self, texts: Iterable[str]) -> np.ndarray:
        items = list(texts)
        vectors = self._model.encode(items, normalize_embeddings=True, convert_to_numpy=True)
        return np.asarray(vectors, dtype="float32")


def build_embedder(settings: Settings) -> tuple[Any, str]:
    mode = settings.embedding_mode
    model_path = Path(settings.bge_m3_path)
    model_ready = (model_path / "config.json").exists() and (model_path / "pytorch_model.bin").exists()
    if mode in ("auto", "bge-m3") and model_ready:
        try:
            return BgeM3Embedder(model_path), "ok"
        except Exception:
            if mode == "bge-m3":
                raise
    if mode == "bge-m3":
        raise RuntimeError(f"BGE-M3 模型不可用：{model_path}")
    return HashEmbedder(), "fallback"


@dataclass
class RetrievalResult:
    coverage: str
    max_score: float
    top_k: int
    retry_used: bool
    hits: list[dict[str, Any]]
    query: str


class KnowledgeService:
    def __init__(self, settings: Settings, db: Database):
        self.settings = settings
        self.db = db
        self.index = None
        self.entries: list[dict[str, Any]] = []
        self.kb_version = KB_VERSION
        self.embedder, self.embedding_status = build_embedder(settings)
        self.index_status = "missing"

    @property
    def version_dir(self) -> Path:
        return Path(self.settings.knowledge_dir) / self.kb_version

    def _version_dir_for(self, kb_version: str) -> Path:
        return Path(self.settings.knowledge_dir) / kb_version

    def _active_version(self) -> str | None:
        row = self.db.connection().execute(
            "SELECT kb_version FROM knowledge_versions WHERE status='active' LIMIT 1"
        ).fetchone()
        return row["kb_version"] if row else None

    @staticmethod
    def _has_files(directory: Path) -> bool:
        return (directory / "index.faiss").exists() and (directory / "entries.jsonl").exists()

    def _mark_missing(self, reason: str) -> None:
        """索引缺失时保持服务可用：不重建、不伪造检索结果。"""
        self.index = None
        self.entries = []
        self.index_status = "missing"
        logger.warning("knowledge index missing: %s (kb_version=%s)", reason, self.kb_version)

    def ensure_built(self) -> None:
        """只加载已存在的 active 版本；索引文件缺失时标记 missing，不自动 rebuild。"""
        active = self._active_version()
        if active:
            self.kb_version = active
            directory = self._version_dir_for(active)
            if not self._has_files(directory):
                self._mark_missing(f"active files not found: {directory}")
                return
            self._load()
            return
        directory = self._version_dir_for(KB_VERSION)
        if self._has_files(directory):
            self.kb_version = KB_VERSION
            self._load()
            if self.entries:
                self._write_record(KB_VERSION, len(self.entries), "active")
            return
        seed_path = Path(self.settings.knowledge_seed_path)
        if not seed_path.exists():
            self._mark_missing(f"seed not found: {seed_path}")
            return
        entries = load_entries_file(seed_path)
        if not entries:
            self._mark_missing(f"seed has no entries: {seed_path}")
            return
        self.build(seed_path, kb_version=KB_VERSION, activate=True)

    def build(
        self,
        seed_path: Path,
        *,
        kb_version: str | None = None,
        activate: bool | None = None,
        chunk_size: int = 400,
        overlap: int = 50,
    ) -> str:
        entries = load_entries_file(seed_path)
        target = kb_version or self.kb_version
        if not entries:
            # 空知识库不得写 knowledge_versions（entry_count >= 1），保持 missing 继续启动。
            self.kb_version = target
            self._mark_missing(f"entries empty: {seed_path}")
            return target
        self._write_version(target, entries, chunk_size=chunk_size, overlap=overlap)
        if activate is None:
            activate = self._active_version() is None
        if activate:
            self.activate(target)
        elif target == self.kb_version:
            self.kb_version = target
            self._load()
        return target

    def import_entries(
        self,
        entries: list[dict[str, Any]],
        *,
        kb_version: str,
        activate: bool = False,
    ) -> str:
        """AC-KB-03 / AC-KB-04：增量导入新版本；默认只构建不激活，失败不落盘。"""
        if not VERSION_PATTERN.match(kb_version):
            raise KnowledgeImportError(
                [
                    {
                        "entry_index": None,
                        "entry_id": None,
                        "field": "kb_version",
                        "reason": "VERSION_FORMAT_INVALID",
                    }
                ]
            )
        validated = validate_entries(entries)
        self._write_version(kb_version, validated)
        if activate:
            self.activate(kb_version)
        else:
            self._write_record(kb_version, len(validated), "archived")
            logger.info("knowledge version imported inactive: %s entries=%s", kb_version, len(validated))
        return kb_version

    def activate(self, kb_version: str) -> None:
        """手动激活指定版本；旧 active 在激活事务内归档（AC-KB-03 / OBS-02）。"""
        directory = self._version_dir_for(kb_version)
        if not self._has_files(directory):
            raise KnowledgeImportError(
                [
                    {
                        "entry_index": None,
                        "entry_id": None,
                        "field": "kb_version",
                        "reason": "VERSION_NOT_BUILT",
                    }
                ]
            )
        entries = [
            json.loads(line)
            for line in (directory / "entries.jsonl").read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        if not entries:
            raise KnowledgeImportError(
                [
                    {
                        "entry_index": None,
                        "entry_id": None,
                        "field": "kb_version",
                        "reason": "VERSION_EMPTY",
                    }
                ]
            )
        conn = self.db.connection()
        with transaction(conn):
            conn.execute("UPDATE knowledge_versions SET status='archived' WHERE status='active'")
            self._upsert_record(conn, kb_version, len(entries), "active", directory)
        self.kb_version = kb_version
        self._load()
        logger.info("knowledge version activated: %s entries=%s", kb_version, len(entries))

    def rollback(self, kb_version: str) -> None:
        """手动回滚到历史版本（AC-KB-03）。"""
        logger.warning("knowledge rollback requested: %s", kb_version)
        self.activate(kb_version)

    def list_versions(self) -> list[dict[str, Any]]:
        rows = self.db.connection().execute(
            "SELECT kb_version, entry_count, status, built_at, manifest_path"
            " FROM knowledge_versions ORDER BY built_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def _write_version(
        self,
        kb_version: str,
        entries: list[dict[str, Any]],
        *,
        chunk_size: int = 400,
        overlap: int = 50,
    ) -> Path:
        import faiss

        directory = self._version_dir_for(kb_version)
        texts = [self._embed_text(entry) for entry in entries]
        vectors = self.embedder.encode(texts)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(directory / "index.faiss"))
        with (directory / "entries.jsonl").open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        (directory / "manifest.json").write_text(
            json.dumps(
                {
                    "kb_version": kb_version,
                    "entry_count": len(entries),
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                    "model_name": self.embedder.name,
                    "model_version": "local",
                    "built_at": utcnow(),
                    "backend": "hash" if self.embedder.is_fallback else "bge-m3",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return directory

    def _load(self) -> None:
        import faiss

        directory = self._version_dir_for(self.kb_version)
        entries = [
            json.loads(line)
            for line in (directory / "entries.jsonl").read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        if not entries:
            self._mark_missing(f"entries empty: {directory}")
            return
        self.index = faiss.read_index(str(directory / "index.faiss"))
        self.entries = entries
        self.index_status = "ok"

    def _write_record(self, kb_version: str, entry_count: int, status: str) -> None:
        conn = self.db.connection()
        self._upsert_record(conn, kb_version, entry_count, status, self._version_dir_for(kb_version))

    def _upsert_record(
        self, conn, kb_version: str, entry_count: int, status: str, directory: Path
    ) -> None:
        manifest_path = directory / "manifest.json"
        manifest = str(manifest_path.resolve())
        recorded = json.loads(manifest_path.read_text(encoding="utf-8-sig")) if manifest_path.exists() else {}
        conn.execute(
            "INSERT INTO knowledge_versions (kb_version, entry_count, chunk_size, overlap, model_name,"
            " model_version, built_at, status, manifest_path) VALUES (?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(kb_version) DO UPDATE SET entry_count=excluded.entry_count,"
            " status=excluded.status, built_at=excluded.built_at, manifest_path=excluded.manifest_path",
            (
                kb_version,
                entry_count,
                recorded.get("chunk_size", 400),
                recorded.get("overlap", 50),
                self.embedder.name,
                "local",
                utcnow(),
                status,
                manifest,
            ),
        )

    @staticmethod
    def _entry_text(entry: dict[str, Any]) -> str:
        return " ".join(
            [
                entry.get("entry_id", ""),
                entry.get("title", ""),
                entry.get("fault_type", ""),
                " ".join(entry.get("keywords", [])),
                entry.get("content", ""),
            ]
        )

    def _embed_text(self, entry: dict[str, Any]) -> str:
        # 哈希回退使用“类型+标题+关键词”短文本，使字面重合度落在可解释区间；
        # BGE-M3 使用完整条目文本。
        if getattr(self.embedder, "is_fallback", False):
            return " ".join(
                [
                    entry.get("fault_type", ""),
                    entry.get("title", ""),
                    " ".join(entry.get("keywords", [])),
                ]
            )
        return self._entry_text(entry)

    def build_query(self, features: dict[str, Any], cues: list[str] | None = None) -> str:
        parts = ["设备 温度 温差 转速 扭矩 功率 刀具 磨损 数据质量"]
        temp_diff = features.get("temp_diff")
        rpm = features.get("rotational_speed_rpm")
        power = features.get("power_w")
        wear = features.get("tool_wear_min")
        if temp_diff is not None and temp_diff < 8.6:
            parts.append("温差低 散热")
        if rpm is not None and rpm < 1380:
            parts.append("转速低")
        if power is not None and (power < 3500 or power > 9000):
            parts.append("功率异常 电源")
        if wear is not None and wear >= 190:
            parts.append("刀具磨损 磨损高")
        if not any("温差低" in p or "转速低" in p or "功率异常" in p or "刀具磨损" in p for p in parts):
            parts.append("正常 健康 基线")
        if cues:
            parts.append(" ".join(cues))
        return " ".join(parts)

    def retrieve(
        self,
        features: dict[str, Any],
        top_k: int = 5,
        retry: bool = False,
        cues: list[str] | None = None,
    ) -> RetrievalResult:
        query = self.build_query(features, cues)
        if self.index_status == "missing" or self.index is None or not self.entries:
            return RetrievalResult("none", 0.0, top_k, retry, [], query)

        vector = self.embedder.encode([query])
        scores, indices = self.index.search(vector, min(len(self.entries), top_k * 2))
        hits: list[dict[str, Any]] = []
        per_type: dict[str, int] = {}
        max_score = 0.0
        for score, idx in zip(scores[0].tolist(), indices[0].tolist()):
            if idx < 0:
                continue
            entry = self.entries[idx]
            if score <= 0.05:
                continue
            fault_type = entry.get("fault_type", "通用")
            if per_type.get(fault_type, 0) >= 2:
                continue
            per_type[fault_type] = per_type.get(fault_type, 0) + 1
            evidence = self._evidence(entry, features)
            hit = {
                "entry_id": entry["entry_id"],
                "fault_type": fault_type,
                "title": entry["title"],
                "snippet": entry["content"][:120],
                "score": round(float(score), 4),
                "evidence": evidence,
            }
            hits.append(hit)
            max_score = max(max_score, float(score))
            if len(hits) >= top_k:
                break

        if not hits:
            coverage = "none"
        elif max_score >= COVERED_SCORE:
            coverage = "covered"
        else:
            coverage = "insufficient"
        if retry:
            top_k = max(top_k, 8)
        return RetrievalResult(coverage, round(max_score, 4), top_k, retry, hits, query)

    @staticmethod
    def _evidence(entry: dict[str, Any], features: dict[str, Any]) -> dict[str, Any] | None:
        candidates = {
            "HDF": ("temp_diff", features.get("temp_diff"), "K"),
            "PWF": ("power_w", features.get("power_w"), "W"),
            "OSF": ("wear_torque", features.get("wear_torque"), "Nm·min"),
            "TWF": ("tool_wear_min", features.get("tool_wear_min"), "min"),
        }
        fault_type = entry.get("fault_type")
        if fault_type in candidates:
            feature, value, unit = candidates[fault_type]
            if value is not None:
                e = {
                    "entry_id": entry["entry_id"],
                    "title": entry["title"],
                    "fault_type": fault_type,
                    "feature": feature,
                    "value": value,
                    "unit": unit,
                }
                return e
        if fault_type == "正常基线" and features.get("temp_diff") is not None:
            return {
                "entry_id": entry["entry_id"],
                "title": entry["title"],
                "fault_type": fault_type,
                "feature": "temp_diff",
                "value": features.get("temp_diff"),
                "unit": "K",
            }
        return None
