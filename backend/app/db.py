"""SQLite 连接、迁移与通用工具（DB V1.1.0 §4.4 / §8.1）。"""

from __future__ import annotations

import hashlib
import random
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = 1


class MigrationError(RuntimeError):
    pass


def utcnow() -> str:
    """UTC ISO8601，毫秒精度，Z 结尾（与 DB 默认值同格式）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def utcnow_dt() -> datetime:
    return datetime.now(timezone.utc)


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_id_lock = threading.Lock()


def new_id(prefix: str) -> str:
    """ULID（时间有序）+ 业务前缀；对客户端不透明。"""
    with _id_lock:
        timestamp = int(time.time() * 1000)
        randomness = random.getrandbits(80)
    # 26 位 ULID：前 10 位时间，后 16 位随机
    time_part = ""
    value = timestamp
    for _ in range(10):
        time_part = _CROCKFORD[value & 31] + time_part
        value >>= 5
    rand_part = "".join(_CROCKFORD[(randomness >> (5 * i)) & 31] for i in range(15, -1, -1))
    return f"{prefix}_{time_part}{rand_part}"


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._local = threading.local()

    def connection(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect(self.path)
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        checksum = "sha256:" + hashlib.sha256(schema.encode("utf-8")).hexdigest()
        conn = connect(self.path)
        try:
            existing = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            if existing is None:
                conn.executescript(schema)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at, checksum, note) VALUES (?,?,?,?)",
                    (SCHEMA_VERSION, utcnow(), checksum, "DB V1.1.0 full DDL"),
                )
                return
            row = conn.execute(
                "SELECT version, checksum FROM schema_migrations ORDER BY version DESC LIMIT 1"
            ).fetchone()
            if row is None:
                raise MigrationError("schema_migrations 为空，无法确认 schema 版本；请重建数据库")
            if row["checksum"] != checksum or row["version"] != SCHEMA_VERSION:
                raise MigrationError(
                    "schema 版本/校验和不一致："
                    f"db_version={row['version']} expected={SCHEMA_VERSION}; "
                    "请备份后重建数据库或补充迁移脚本（DB V1.1.0 §8.1）"
                )
        finally:
            conn.close()


def health_check(db_path: str | Path) -> bool:
    try:
        conn = connect(db_path)
        try:
            conn.execute("SELECT 1").fetchone()
            return True
        finally:
            conn.close()
    except Exception:
        return False
