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

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from prism.core.agent import handle_turn
from prism.core.config import RuntimeInfo
from prism.core.memory import get_session_store
from prism.core.renderers import available_formats, render as render_format
from prism.core.store import get_store
from prism.core.titler import generate_title, maybe_retitle

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


@router.get("/health")
def health():
    store = get_store()
    info = RuntimeInfo()
    return {
        "status": "ok",
        "chunks_indexed": store.count(),
        "embed_model": info.embed_model,
        "gen_model": info.gen_model,
        "title_model": info.title_model,
        "domains": info.domains,
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
    }


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    store = get_session_store()
    store.delete(session_id)
    return {"ok": True}


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
