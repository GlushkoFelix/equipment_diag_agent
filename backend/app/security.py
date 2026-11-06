"""密码、Cookie 会话与鉴权依赖（ARCH §5.1.2 / §5.1.4）。"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Request

from app.config import Settings
from app.db import Database, new_id, transaction, utcnow
from app.errors import ApiError

COOKIE_NAME = "edg_session"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def user_id_to_public(user_id: int) -> str:
    return f"usr_{user_id:010d}"


def public_user(row: Any) -> dict[str, Any]:
    return {
        "user_id": user_id_to_public(row["user_id"]),
        "username": row["username"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


def register_user(db: Database, username: str, password: str) -> tuple[dict[str, Any], str]:
    username = username.strip()
    if not (3 <= len(username) <= 64):
        raise ApiError(422, "VALIDATION_FAILED", "用户名长度需为 3–64 位")
    if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ApiError(422, "WEAK_PASSWORD", "密码至少 8 位且包含字母与数字")
    conn = db.connection()
    try:
        with transaction(conn):
            cur = conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?,?)",
                (username, hash_password(password)),
            )
            user_id = int(cur.lastrowid)
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise ApiError(409, "USERNAME_TAKEN", "用户名已存在") from exc
        raise
    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    token = create_session(db, user_id)
    return public_user(row), token


def create_session(db: Database, user_id: int) -> str:
    token = new_token()
    expires_at = _iso_in(hours=24)
    db.connection().execute(
        "INSERT INTO sessions (session_id, user_id, token_hash, expires_at) VALUES (?,?,?,?)",
        (new_id("ses"), user_id, token_hash(token), expires_at),
    )
    return token


def _iso_in(hours: int = 0, minutes: int = 0) -> str:
    value = datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def login_user(db: Database, username: str, password: str, settings: Settings) -> tuple[dict[str, Any], str]:
    conn = db.connection()
    row = conn.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username.strip(),)).fetchone()
    if row is None:
        raise ApiError(401, "AUTH_INVALID_CREDENTIALS", "用户名或密码错误")

    locked_until = row["locked_until"]
    if locked_until and locked_until > utcnow():
        remaining = _seconds_until(locked_until)
        raise ApiError(
            423,
            "AUTH_LOCKED",
            f"账号已锁定，请 {remaining} 秒后重试",
            headers={"Retry-After": str(remaining)},
        )

    if not verify_password(password, row["password_hash"]):
        failed = int(row["failed_attempts"]) + 1
        locked = None
        if failed >= settings.login_max_failures:
            failed = 0
            locked = _iso_in(minutes=settings.login_lock_minutes)
        conn.execute(
            "UPDATE users SET failed_attempts=?, locked_until=? WHERE user_id=?",
            (failed, locked, row["user_id"]),
        )
        if locked:
            raise ApiError(
                423,
                "AUTH_LOCKED",
                f"连续失败 {settings.login_max_failures} 次，账号锁定 {settings.login_lock_minutes} 分钟",
                headers={"Retry-After": str(settings.login_lock_minutes * 60)},
            )
        raise ApiError(401, "AUTH_INVALID_CREDENTIALS", "用户名或密码错误")

    conn.execute(
        "UPDATE users SET failed_attempts=0, locked_until=NULL, last_login_at=? WHERE user_id=?",
        (utcnow(), row["user_id"]),
    )
    refreshed = conn.execute("SELECT * FROM users WHERE user_id=?", (row["user_id"],)).fetchone()
    return public_user(refreshed), create_session(db, row["user_id"])


def _seconds_until(value: str) -> int:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    expires = datetime.fromisoformat(value)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return max(0, int((expires - datetime.now(timezone.utc)).total_seconds()))


def logout(db: Database, token: str) -> None:
    db.connection().execute(
        "UPDATE sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
        (utcnow(), token_hash(token)),
    )


def resolve_session(db: Database, token: str | None) -> dict[str, Any]:
    if not token:
        raise ApiError(401, "AUTH_REQUIRED", "请先登录")
    conn = db.connection()
    row = conn.execute(
        "SELECT s.*, u.username, u.created_at AS user_created_at, u.last_login_at "
        "FROM sessions s JOIN users u ON u.user_id=s.user_id WHERE s.token_hash=?",
        (token_hash(token),),
    ).fetchone()
    if row is None:
        raise ApiError(401, "AUTH_SESSION_EXPIRED", "会话不存在，请重新登录")
    if row["revoked_at"] is not None:
        raise ApiError(401, "AUTH_SESSION_EXPIRED", "会话已退出，请重新登录")
    if row["expires_at"] <= utcnow():
        raise ApiError(401, "AUTH_SESSION_EXPIRED", "会话已过期，请重新登录")
    return {
        "user_id": int(row["user_id"]),
        "username": row["username"],
        "session_id": row["session_id"],
    }


def current_user(request: Request) -> dict[str, Any]:
    return resolve_session(request.app.state.db, request.cookies.get(COOKIE_NAME))
