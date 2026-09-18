"""API route handlers.

Note on streaming: the plan originally proposed SSE for chat responses, but
Prism's answer generation produces one validated structured JSON object per
turn (Piece 8) -- partially streaming a JSON object that must be fully valid
before any renderer can run doesn't buy anything here, and risks shipping an
invalid partial object to the UI. Chat is a plain request/response endpoint;
latency is dominated by one local LLM call (~2-6s on this hardware), which is
an acceptable synchronous wait for a hackathon-scale demo. This trade-off is
documented in docs/decisions.md.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

import json
from queue import Empty, SimpleQueue
from threading import Thread

from prism.core.agent import handle_turn
from prism.core.config import (
    EMBED_MODEL,
    GEN_MODEL,
    OLLAMA_HOST,
    TITLE_MODEL,
    UPLOAD_ALLOWED_SUFFIXES,
    UPLOAD_MAX_BYTES,
    UPLOAD_TTL_HOURS,
    RuntimeInfo,
)
from prism.core.memory import UploadedDocRef, get_session_store
from prism.core.renderers import available_formats, render as render_format
from prism.core.store import get_store
from prism.core.titler import generate_title, maybe_retitle
from prism.core.uploads import get_upload_store

router = APIRouter()


class CreateSessionResponse(BaseModel):
    id: str
    title: str | None


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    domain: str | None
    is_clarification: bool
    is_reformat: bool
    confidence: str | None
    no_answer: bool
    sources: list[dict]
    available_formats: list[str]
    title: str | None


class RenderRequest(BaseModel):
    format: str


class UploadResponse(BaseModel):
    doc_id: str
    filename: str
    status: str
    chunk_count: int
    uploaded_docs: list[dict]


def _ollama_status() -> dict:
    """Ping Ollama and check that required models are present."""
    import httpx

    required = [EMBED_MODEL, GEN_MODEL, TITLE_MODEL]
    try:
        with httpx.Client(base_url=OLLAMA_HOST, timeout=3.0) as client:
            resp = client.get("/api/tags")
            resp.raise_for_status()
            names = {m.get("name") for m in (resp.json().get("models") or []) if m.get("name")}
        # Ollama tags may be "model:tag" — also accept bare name prefix matches.
        def present(need: str) -> bool:
            if need in names:
                return True
            return any(n == need or n.startswith(need + ":") or need.startswith(n.split(":")[0]) for n in names)

        missing = [m for m in required if not present(m)]
        return {
            "reachable": True,
            "host": OLLAMA_HOST,
            "models_required": required,
            "models_missing": missing,
            "ok": not missing,
        }
    except Exception as e:
        return {
            "reachable": False,
            "host": OLLAMA_HOST,
            "models_required": required,
            "models_missing": required,
            "ok": False,
            "error": str(e)[:300],
        }


@router.get("/health")
def health():
    store = get_store()
    info = RuntimeInfo()
    ollama = _ollama_status()
    chunks = store.count()
    status = "ok" if ollama.get("ok") and chunks > 0 else "degraded"
    if not ollama.get("reachable"):
        status = "degraded"
    try:
        upload_chunks = get_upload_store().count()
    except Exception:
        upload_chunks = 0
    return {
        "status": status,
        "chunks_indexed": chunks,
        "embed_model": info.embed_model,
        "gen_model": info.gen_model,
        "title_model": info.title_model,
        "domains": info.domains,
        "ollama": ollama,
        "uploads": {
            "chunks_indexed": upload_chunks,
            "ttl_hours": UPLOAD_TTL_HOURS,
            "max_bytes": UPLOAD_MAX_BYTES,
            "allowed_suffixes": sorted(UPLOAD_ALLOWED_SUFFIXES),
        },
    }


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session():
    store = get_session_store()
    state = store.create()
    return CreateSessionResponse(id=state.session_id, title=state.title)


@router.get("/sessions")
def list_sessions():
    store = get_session_store()
    return store.list_sessions()


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    store = get_session_store()
    state = store.load(session_id)
    if state is None:
        raise HTTPException(404, "session not found")
    return {
        "id": state.session_id,
        "title": state.title,
        "active_domain": state.active_domain,
        "turns": [t.model_dump() for t in state.turns],
        "last_answer": state.last_answer.model_dump() if state.last_answer else None,
        "available_formats": available_formats(state.last_answer) if state.last_answer else ["prose"],
        "pending_clarification": state.pending_clarification.model_dump() if state.pending_clarification else None,
        "uploaded_docs": [d.model_dump() for d in state.uploaded_docs],
    }


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    store = get_session_store()
    store.delete(session_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Session-scoped document uploads (ephemeral "uploaded" domain)
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/upload", response_model=UploadResponse)
async def upload_document(session_id: str, file: UploadFile = File(...)):
    """Attach a file to this chat. Parsed, chunked, embedded locally and kept
    in a session-filtered collection — never merged into the five KBs, purged
    on session delete or after UPLOAD_TTL_HOURS."""
    store = get_session_store()
    state = store.load(session_id)
    if state is None:
        raise HTTPException(404, "session not found")

    data = await file.read()
    if not data:
        raise HTTPException(400, "empty file")
    try:
        doc = get_upload_store().ingest_bytes(
            session_id=session_id,
            filename=file.filename or "document",
            data=data,
            content_type=file.content_type or "",
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # parser / embedding failure
        raise HTTPException(500, f"could not ingest file: {str(e)[:200]}")

    # Re-load right before saving so a concurrent chat turn is not clobbered.
    state = store.load(session_id) or state
    state.uploaded_docs.append(
        UploadedDocRef(
            id=doc.id,
            filename=doc.filename,
            content_type=doc.content_type,
            bytes_size=doc.bytes_size,
            chunk_count=doc.chunk_count,
            turn_index=len(state.turns),
            created_at=doc.created_at,
        )
    )
    store.save(state)
    return UploadResponse(
        doc_id=doc.id,
        filename=doc.filename,
        status="indexed",
        chunk_count=doc.chunk_count,
        uploaded_docs=[d.model_dump() for d in state.uploaded_docs],
    )


@router.get("/sessions/{session_id}/uploads")
def list_uploads(session_id: str):
    store = get_session_store()
    state = store.load(session_id)
    if state is None:
        raise HTTPException(404, "session not found")
    return {"uploaded_docs": [d.model_dump() for d in state.uploaded_docs]}


@router.delete("/sessions/{session_id}/uploads/{doc_id}")
def delete_upload(session_id: str, doc_id: str):
    store = get_session_store()
    state = store.load(session_id)
    if state is None:
        raise HTTPException(404, "session not found")
    get_upload_store().delete_document(session_id, doc_id)
    state.uploaded_docs = [d for d in state.uploaded_docs if d.id != doc_id]
    if state.active_domain == "uploaded" and not state.uploaded_docs:
        state.active_domain = None
    store.save(state)
    return {"ok": True, "uploaded_docs": [d.model_dump() for d in state.uploaded_docs]}


@router.post("/sessions/{session_id}/chat", response_model=ChatResponse)
def chat(session_id: str, req: ChatRequest):
    store = get_session_store()
    state = store.load(session_id)
    if state is None:
        raise HTTPException(404, "session not found")

    was_first_exchange = len(state.turns) == 0
    prev_domain = state.active_domain

    result = handle_turn(state, req.message)

    # Session titling (Piece 2c): one cheap call on the first exchange only,
    # plus an optional re-title if the topic clearly moved to a new domain.
    if was_first_exchange and not result.is_clarification:
        try:
            state.title = generate_title(req.message)
        except Exception:
            state.title = req.message[:40]
    elif result.domain and prev_domain and result.domain != prev_domain and not result.is_reformat:
        try:
            new_title = maybe_retitle(
                current_title=state.title, new_domain=result.domain, first_message_of_new_domain=req.message
            )
            if new_title:
                state.title = new_title
        except Exception:
            pass

    store.save(state)

    return _chat_response(session_id, state, result)


def _chat_response(session_id: str, state, result) -> ChatResponse:
    sources = [
        {"id": d.id, "title": d.title, "source_url": d.source_url, "domain": d.domain} for d in state.last_docs
    ]
    formats = available_formats(state.last_answer) if state.last_answer else ["prose"]

    is_clar = result.is_clarification or (
        state.last_answer is not None and bool(state.last_answer.clarification_question) and state.last_answer.no_answer
    )

    return ChatResponse(
        session_id=session_id,
        reply=result.reply_text,
        domain=result.domain,
        is_clarification=is_clar,
        is_reformat=result.is_reformat,
        confidence=state.last_answer.confidence if state.last_answer else None,
        no_answer=state.last_answer.no_answer if state.last_answer else False,
        sources=sources,
        available_formats=formats,
        title=state.title,
    )


def _sse(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/sessions/{session_id}/chat/stream")
def chat_stream(session_id: str, req: ChatRequest):
    """SSE status tokens, then a final `result` event with the same ChatResponse JSON.

    Does not stream partial answer tokens — CanonicalAnswer must validate fully first.
    """
    store = get_session_store()
    state = store.load(session_id)
    if state is None:
        raise HTTPException(404, "session not found")

    was_first_exchange = len(state.turns) == 0
    prev_domain = state.active_domain
    q: SimpleQueue = SimpleQueue()

    def on_status(stage: str) -> None:
        q.put(("status", {"stage": stage}))

    def worker() -> None:
        try:
            result = handle_turn(state, req.message, on_status=on_status)
            q.put(("status", {"stage": "titling"}))
            if was_first_exchange and not result.is_clarification:
                try:
                    state.title = generate_title(req.message)
                except Exception:
                    state.title = req.message[:40]
            elif result.domain and prev_domain and result.domain != prev_domain and not result.is_reformat:
                try:
                    new_title = maybe_retitle(
                        current_title=state.title,
                        new_domain=result.domain,
                        first_message_of_new_domain=req.message,
                    )
                    if new_title:
                        state.title = new_title
                except Exception:
                    pass
            store.save(state)
            resp = _chat_response(session_id, state, result)
            q.put(("result", resp.model_dump()))
        except Exception as e:
            q.put(("error", {"message": str(e)[:500]}))
        finally:
            q.put(None)

    Thread(target=worker, daemon=True).start()

    def event_gen():
        yield _sse("status", {"stage": "received"})
        while True:
            try:
                item = q.get(timeout=180)
            except Empty:
                yield _sse("error", {"message": "timeout waiting for agent"})
                break
            if item is None:
                break
            event, data = item
            yield _sse(event, data)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.post("/sessions/{session_id}/render")
def render_last_answer(session_id: str, req: RenderRequest):
    store = get_session_store()
    state = store.load(session_id)
    if state is None:
        raise HTTPException(404, "session not found")
    if state.last_answer is None:
        raise HTTPException(400, "no answer yet in this session to render")

    try:
        rr = render_format(state.last_answer, req.format)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(400, str(e))

    if rr.is_binary:
        return Response(
            content=rr.content,
            media_type=rr.mime_type,
            headers={"Content-Disposition": f'attachment; filename="{rr.filename}"'},
        )
    return {"format": rr.format, "content": rr.content, "mime_type": rr.mime_type}


@router.get("/sessions/{session_id}/download/{fmt}")
def download(session_id: str, fmt: str):
    store = get_session_store()
    state = store.load(session_id)
    if state is None:
        raise HTTPException(404, "session not found")
    if state.last_answer is None:
        raise HTTPException(400, "no answer yet in this session to render")
    try:
        rr = render_format(state.last_answer, fmt)  # type: ignore[arg-type]
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not rr.is_binary:
        raise HTTPException(400, f"format {fmt} is not a downloadable binary format")
    return Response(
        content=rr.content,
        media_type=rr.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{rr.filename}"'},
    )
