"""Per-user saved prompt library (reuse questions in the composer)."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from prism.core.config import SESSIONS_DB

MAX_BODY_CHARS = 2000
MAX_PROMPTS_PER_USER = 50
MAX_TITLE_CHARS = 120

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        return _conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_prompts (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_saved_prompts_user ON saved_prompts(user_id, created_at DESC)"
    )


def _title_from_body(body: str) -> str:
    first = (body or "").strip().splitlines()[0] if body.strip() else "Saved prompt"
    first = " ".join(first.split())
    if len(first) > MAX_TITLE_CHARS:
        return first[: MAX_TITLE_CHARS - 1].rstrip() + "…"
    return first or "Saved prompt"


def list_saved_prompts(user_id: str) -> list[dict]:
    conn = _get_conn()
    with _lock:
        rows = conn.execute(
            """
            SELECT id, title, body, created_at
            FROM saved_prompts
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def create_saved_prompt(user_id: str, body: str, title: str | None = None) -> dict:
    text = (body or "").strip()
    if not text:
        raise ValueError("Prompt body is empty")
    if len(text) > MAX_BODY_CHARS:
        raise ValueError(f"Prompt is too long (max {MAX_BODY_CHARS} characters)")

    conn = _get_conn()
    with _lock:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM saved_prompts WHERE user_id = ?",
            (user_id,),
        ).fetchone()["n"]
        if count >= MAX_PROMPTS_PER_USER:
            raise ValueError(f"Limit reached ({MAX_PROMPTS_PER_USER} saved prompts)")

        prompt_id = str(uuid.uuid4())
        created = _now_iso()
        resolved_title = (title or "").strip() or _title_from_body(text)
        if len(resolved_title) > MAX_TITLE_CHARS:
            resolved_title = resolved_title[: MAX_TITLE_CHARS - 1].rstrip() + "…"
        conn.execute(
            """
            INSERT INTO saved_prompts (id, user_id, title, body, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (prompt_id, user_id, resolved_title, text, created),
        )
    return {"id": prompt_id, "title": resolved_title, "body": text, "created_at": created}


def delete_saved_prompt(user_id: str, prompt_id: str) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "DELETE FROM saved_prompts WHERE id = ? AND user_id = ?",
            (prompt_id, user_id),
        )
        return cur.rowcount > 0
