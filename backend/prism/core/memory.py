"""Multi-turn conversation state (Piece 7 / 2b), persisted to SQLite.

Each session tracks: recent turn history, the currently active domain
(for sticky-domain routing and anaphora resolution), the last retrieved
documents, the last canonical structured answer (so reformat requests don't
need to re-run retrieval or the answer LLM call, per 2d), and any pending
clarification question.

SQLite access is serialized with an RLock + WAL so concurrent chat/stream
requests (multi-tab / multi-user demo) don't corrupt the DB.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from prism.core.answer import CanonicalAnswer
from prism.core.config import SESSIONS_DB


class Turn(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    domain: str | None = None
    is_clarification: bool = False
    no_answer: bool = False
    confidence: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SourceDocRef(BaseModel):
    id: str
    title: str
    source_url: str
    domain: str
    text: str


class PendingClarification(BaseModel):
    original_query: str
    question: str
    candidate_domains: list[str]


class UploadedDocRef(BaseModel):
    id: str
    filename: str
    content_type: str = ""
    bytes_size: int = 0
    chunk_count: int = 0
    # len(session.turns) at upload time — drives the "recently attached" bias.
    turn_index: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionState(BaseModel):
    session_id: str
    user_id: str | None = None
    title: str | None = None
    turns: list[Turn] = Field(default_factory=list)
    active_domain: str | None = None
    last_docs: list[SourceDocRef] = Field(default_factory=list)
    last_answer: CanonicalAnswer | None = None
    pending_clarification: PendingClarification | None = None
    uploaded_docs: list[UploadedDocRef] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add_turn(
        self,
        role: str,
        content: str,
        domain: str | None = None,
        *,
        max_history: int = 48,
        is_clarification: bool = False,
        no_answer: bool = False,
        confidence: str | None = None,
    ) -> None:
        """Keep enough turns for long multi-domain demos (12+ user exchanges)."""
        self.turns.append(
            Turn(
                role=role,
                content=content,
                domain=domain,
                is_clarification=is_clarification,
                no_answer=no_answer,
                confidence=confidence,
            )
        )
        if len(self.turns) > max_history:
            self.turns = self.turns[-max_history:]
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def user_turns(self) -> list[Turn]:
        return [t for t in self.turns if t.role == "user"]

    def recent_context_str(self, n: int = 6) -> str:
        recent = self.turns[-n:]
        return "\n".join(f"{t.role}: {t.content}" for t in recent)


class SessionStore:
    def __init__(self, db_path: Path = SESSIONS_DB):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            timeout=30.0,
            isolation_level=None,  # autocommit; we still use explicit BEGIN for writes
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Migrate older DBs that lack user_id
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(sessions)").fetchall()}
            if "user_id" not in cols:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")

    def create(self, user_id: str | None = None) -> SessionState:
        session_id = str(uuid.uuid4())
        state = SessionState(session_id=session_id, user_id=user_id)
        self.save(state)
        return state

    def save(self, state: SessionState) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    """
                    INSERT INTO sessions (id, user_id, title, state_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        user_id=excluded.user_id,
                        title=excluded.title,
                        state_json=excluded.state_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        state.session_id,
                        state.user_id,
                        state.title,
                        state.model_dump_json(),
                        state.created_at,
                        state.updated_at,
                    ),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def load(self, session_id: str) -> SessionState | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT state_json FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if not row:
            return None
        return SessionState.model_validate_json(row[0])

    def load_for_user(self, session_id: str, user_id: str) -> SessionState | None:
        state = self.load(session_id)
        if state is None:
            return None
        if state.user_id and state.user_id != user_id:
            return None
        # Legacy sessions without user_id: claim on first authenticated access
        if not state.user_id:
            state.user_id = user_id
            self.save(state)
        return state

    def list_sessions(self, user_id: str | None = None) -> list[dict]:
        with self._lock:
            if user_id:
                rows = self._conn.execute(
                    """
                    SELECT id, title, created_at, updated_at, state_json
                    FROM sessions
                    WHERE user_id = ? OR user_id IS NULL
                    ORDER BY updated_at DESC
                    """,
                    (user_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT id, title, created_at, updated_at, state_json FROM sessions ORDER BY updated_at DESC"
                ).fetchall()
        out = []
        for r in rows:
            active_domain = None
            try:
                st = SessionState.model_validate_json(r[4])
                active_domain = st.active_domain
                # Only list legacy null-user sessions to the requesting user once claimed,
                # or if they already belong to them. Filter orphaned nulls out of other users'
                # views by requiring match when user_id is set on the row via state.
                if user_id and st.user_id and st.user_id != user_id:
                    continue
                if user_id and not st.user_id:
                    # Don't show unclaimed legacy sessions in the sidebar — avoids cross-user leak.
                    continue
            except Exception:
                pass
            out.append(
                {
                    "id": r[0],
                    "title": r[1] or "New conversation",
                    "created_at": r[2],
                    "updated_at": r[3],
                    "active_domain": active_domain,
                }
            )
        return out

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        try:
            from prism.core.uploads import get_upload_store

            get_upload_store().delete_session(session_id)
        except Exception:
            pass


_store_singleton: SessionStore | None = None
_store_lock = threading.Lock()


def get_session_store() -> SessionStore:
    global _store_singleton
    with _store_lock:
        if _store_singleton is None:
            _store_singleton = SessionStore()
        return _store_singleton
