"""SQLite auth: bcrypt passwords, opaque session tokens, access-denial log."""

from __future__ import annotations

import secrets
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from prism.core.config import SESSIONS_DB
from prism.core.rbac import DEMO_PASSWORD, SEED_USERS, normalize_role

TOKEN_TTL_DAYS = 7

_bearer = HTTPBearer(auto_error=False)
_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


@dataclass
class AuthUser:
    id: str
    email: str
    name: str
    role: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _get_conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            SESSIONS_DB.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(
                str(SESSIONS_DB),
                check_same_thread=False,
                timeout=30.0,
                isolation_level=None,
            )
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA busy_timeout=30000")
            _init_schema(_conn)
            seed_users(_conn)
        return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS access_denials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL,
            query TEXT NOT NULL,
            attempted_domain TEXT,
            reason TEXT NOT NULL
        )
        """
    )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False


def seed_users(conn: sqlite3.Connection | None = None) -> None:
    conn = conn or _get_conn()
    with _lock:
        for u in SEED_USERS:
            row = conn.execute("SELECT id FROM users WHERE email = ?", (u["email"],)).fetchone()
            if row:
                continue
            conn.execute(
                """
                INSERT INTO users (id, email, name, role, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    u["email"],
                    u["name"],
                    normalize_role(u["role"]),
                    hash_password(DEMO_PASSWORD),
                    _iso(_now()),
                ),
            )


def ensure_auth_ready() -> None:
    _get_conn()


def login(email: str, password: str) -> dict:
    conn = _get_conn()
    email_n = (email or "").strip().lower()
    with _lock:
        row = conn.execute(
            "SELECT id, email, name, role, password_hash FROM users WHERE lower(email) = ?",
            (email_n,),
        ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = secrets.token_urlsafe(32)
    created = _now()
    expires = created + timedelta(days=TOKEN_TTL_DAYS)
    with _lock:
        conn.execute(
            "INSERT INTO auth_tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, row["id"], _iso(created), _iso(expires)),
        )
    return {
        "token": token,
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "expires_at": _iso(expires),
    }


def logout(token: str | None) -> None:
    if not token:
        return
    conn = _get_conn()
    with _lock:
        conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))


def user_from_token(token: str | None) -> AuthUser | None:
    if not token:
        return None
    conn = _get_conn()
    with _lock:
        row = conn.execute(
            """
            SELECT u.id, u.email, u.name, u.role, t.expires_at
            FROM auth_tokens t
            JOIN users u ON u.id = t.user_id
            WHERE t.token = ?
            """,
            (token,),
        ).fetchone()
    if row is None:
        return None
    try:
        expires = datetime.fromisoformat(row["expires_at"])
    except Exception:
        return None
    if expires < _now():
        with _lock:
            conn.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
        return None
    return AuthUser(id=row["id"], email=row["email"], name=row["name"], role=normalize_role(row["role"]))


def log_denial(
    *,
    email: str,
    role: str,
    query: str,
    attempted_domain: str | None,
    reason: str,
) -> None:
    conn = _get_conn()
    with _lock:
        conn.execute(
            """
            INSERT INTO access_denials (ts, email, role, query, attempted_domain, reason)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (_iso(_now()), email, normalize_role(role), query[:2000], attempted_domain, reason[:500]),
        )


def list_denials(limit: int = 50) -> list[dict]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            """
            SELECT ts, email, role, query, attempted_domain, reason
            FROM access_denials
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser:
    token = creds.credentials if creds else None
    user = user_from_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthUser | None:
    token = creds.credentials if creds else None
    return user_from_token(token)
