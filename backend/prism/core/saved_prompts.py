"""Per-user saved prompt library (reuse questions in the composer)."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone

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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_prompt_seeds (
            user_id TEXT NOT NULL,
            body_key TEXT NOT NULL,
            PRIMARY KEY (user_id, body_key)
        )
        """
    )


def _title_from_body(body: str) -> str:
    first = (body or "").strip().splitlines()[0] if body.strip() else "Saved prompt"
    first = " ".join(first.split())
    if len(first) > MAX_TITLE_CHARS:
        return first[: MAX_TITLE_CHARS - 1].rstrip() + "…"
    return first or "Saved prompt"


def _normalize_body(body: str) -> str:
    return " ".join((body or "").split()).casefold()


def _row_dict(row: sqlite3.Row, *, duplicate: bool = False) -> dict:
    data = dict(row)
    data["duplicate"] = duplicate
    return data


# Short titles, questions that the indexed policies and Kohler pages actually answer.
# Customers only receive the public set. Named HR/Finance records stay staff-only.
_STARTER_PROMPTS: list[dict[str, str]] = [
    {"roles": "all", "title": "Fix a running toilet", "body": "My toilet is occasionally leaking or running. What should I check?"},
    {"roles": "all", "title": "Remove a faucet aerator", "body": "How do I remove an aerator from my faucet?"},
    {"roles": "all", "title": "Faucet warranty", "body": "What warranty do Kohler faucets come with?"},
    {"roles": "all", "title": "Return a product", "body": "What is Kohler's return policy?"},
    {"roles": "all", "title": "Register a product", "body": "How do I register my new Kohler product?"},
    {"roles": "all", "title": "Shower door sticks", "body": "My shower door isn't sliding smoothly. How do I fix it?"},
    {"roles": "all", "title": "What Kohler collects", "body": "What personal information does Kohler collect?"},
    {"roles": "all", "title": "How long data is kept", "body": "How long does Kohler retain personal information?"},
    {"roles": "all", "title": "Opt out of data sale", "body": "How do I opt out of having my personal information sold or shared?"},
    {"roles": "all", "title": "California privacy rights", "body": "What rights do California residents have regarding their personal data?"},
    {"roles": "all", "title": "Proposition 65", "body": "Are Kohler products compliant with California Proposition 65?"},
    {"roles": "all", "title": "Safety data sheets", "body": "Does Kohler provide Safety Data Sheets for its products?"},
    {"roles": "all", "title": "Website terms", "body": "What are Kohler's terms and conditions for using kohler.com?"},
    {"roles": "employee", "title": "Casual leave", "body": "How many casual leave days do I get per year, and how many can I carry forward?"},
    {"roles": "employee", "title": "Probation period", "body": "How long is the probation period for a new hire?"},
    {"roles": "employee", "title": "Work from home", "body": "How many days can I work from home per week?"},
    {"roles": "employee", "title": "Sick leave", "body": "How many sick leave days do I get, and is a medical certificate required?"},
    {"roles": "employee", "title": "Expense approval", "body": "An employee submits an expense claim for ₹15,000. Who needs to approve it?"},
    {"roles": "employee", "title": "Mumbai per diem", "body": "What is the per diem rate for a business trip to Mumbai?"},
    {"roles": "employee", "title": "When a PO is required", "body": "When is a purchase order mandatory before ordering goods or services?"},
    {"roles": "hr_staff", "title": "Alex Rao leave balance", "body": "What is the CL leave balance for Alex Rao (EMP-1001)?"},
    {"roles": "finance_staff", "title": "Alex Rao annual CTC", "body": "What is the annual CTC for Alex Rao?"},
]


def _starters_for_role(role: str) -> list[dict[str, str]]:
    role = (role or "customer").strip()
    out: list[dict[str, str]] = []
    for item in _STARTER_PROMPTS:
        audience = item["roles"]
        if audience == "all":
            out.append(item)
        elif audience == "employee" and role != "customer":
            out.append(item)
        elif audience == role:
            out.append(item)
    return out


def ensure_starter_prompts(user_id: str, role: str) -> None:
    """Insert the useful default library once per user. Deletes stay deleted."""
    conn = _get_conn()
    starters = _starters_for_role(role)
    with _lock:
        seeded = {
            row["body_key"]
            for row in conn.execute(
                "SELECT body_key FROM saved_prompt_seeds WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        }
        existing = conn.execute(
            "SELECT body FROM saved_prompts WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        have = {_normalize_body(row["body"]) for row in existing}
        count = len(existing)
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        for index, item in enumerate(starters):
            key = _normalize_body(item["body"])
            if key in seeded:
                continue
            # Already in the library. Remember it so a later delete stays deleted.
            # A full library must not be marked seeded, or the missing starters never return.
            if key not in have and count >= MAX_PROMPTS_PER_USER:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO saved_prompt_seeds (user_id, body_key) VALUES (?, ?)",
                (user_id, key),
            )
            seeded.add(key)
            if key in have:
                continue
            created = (base + timedelta(seconds=index)).isoformat()
            conn.execute(
                """
                INSERT INTO saved_prompts (id, user_id, title, body, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), user_id, item["title"], item["body"], created),
            )
            have.add(key)
            count += 1


def list_saved_prompts(user_id: str, role: str = "customer") -> list[dict]:
    ensure_starter_prompts(user_id, role)
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
    return [_row_dict(r) for r in rows]


def create_saved_prompt(user_id: str, body: str, title: str | None = None) -> dict:
    text = (body or "").strip()
    if not text:
        raise ValueError("Prompt body is empty")
    if len(text) > MAX_BODY_CHARS:
        raise ValueError(f"Prompt is too long (max {MAX_BODY_CHARS} characters)")

    conn = _get_conn()
    needle = _normalize_body(text)
    with _lock:
        existing = conn.execute(
            """
            SELECT id, title, body, created_at
            FROM saved_prompts
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchall()
        for row in existing:
            if _normalize_body(row["body"]) == needle:
                return _row_dict(row, duplicate=True)

        count = len(existing)
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
    return {
        "id": prompt_id,
        "title": resolved_title,
        "body": text,
        "created_at": created,
        "duplicate": False,
    }


def update_saved_prompt_title(user_id: str, prompt_id: str, title: str) -> dict | None:
    resolved = " ".join((title or "").split())
    if not resolved:
        raise ValueError("Title is empty")
    if len(resolved) > MAX_TITLE_CHARS:
        resolved = resolved[: MAX_TITLE_CHARS - 1].rstrip() + "…"

    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            """
            UPDATE saved_prompts
            SET title = ?
            WHERE id = ? AND user_id = ?
            """,
            (resolved, prompt_id, user_id),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            """
            SELECT id, title, body, created_at
            FROM saved_prompts
            WHERE id = ? AND user_id = ?
            """,
            (prompt_id, user_id),
        ).fetchone()
    return _row_dict(row) if row else None


def delete_saved_prompt(user_id: str, prompt_id: str) -> bool:
    conn = _get_conn()
    with _lock:
        cur = conn.execute(
            "DELETE FROM saved_prompts WHERE id = ? AND user_id = ?",
            (prompt_id, user_id),
        )
        return cur.rowcount > 0
