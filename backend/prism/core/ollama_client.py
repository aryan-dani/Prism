"""Shared Ollama client + keep-alive helpers.

One client instance; every chat/embeddings call passes `keep_alive` so the
7B gen model (and embed model) stay resident between turns instead of
cold-loading on an 8GB card.

The client also carries an explicit request timeout. Without one, a stalled
Ollama call (GPU contention, VRAM swap, a genuinely hung model) blocks the
FastAPI request forever with nothing to catch it -- the caller (browser or
harness) eventually gives up, but the server keeps holding the request open.
Bounding it here means a stall becomes a clear, fast exception that callers
(see agent.py's _safe_generate_answer) can turn into an honest "try again"
answer instead of a silent hang.
"""

from __future__ import annotations

import ollama

from prism.core.config import (
    OLLAMA_HOST,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_REQUEST_TIMEOUT_S,
    OLLAMA_TITLE_KEEP_ALIVE,
    TITLE_MODEL,
)

_client: ollama.Client | None = None


def get_ollama_client() -> ollama.Client:
    global _client
    if _client is None:
        _client = ollama.Client(host=OLLAMA_HOST, timeout=OLLAMA_REQUEST_TIMEOUT_S)
    return _client


def _parse_keep_alive(raw: str) -> str | int:
    """Ollama accepts duration strings ('25m') or -1 (forever) / 0 (unload)."""
    raw = (raw or "25m").strip()
    if raw in {"-1", "0"}:
        return int(raw)
    return raw


def keep_alive_value() -> str | int:
    return _parse_keep_alive(OLLAMA_KEEP_ALIVE)


def title_keep_alive_value() -> str | int:
    """Short keep-alive for TITLE_MODEL -- see config.OLLAMA_TITLE_KEEP_ALIVE
    for why this model gets evicted fast instead of staying resident like
    GEN_MODEL/EMBED_MODEL."""
    return _parse_keep_alive(OLLAMA_TITLE_KEEP_ALIVE)


def keep_alive_for(model: str) -> str | int:
    """Pick the right keep-alive policy for whichever model is being called."""
    return title_keep_alive_value() if model == TITLE_MODEL else keep_alive_value()


def warm_models(models: list[str]) -> None:
    """Best-effort ping so models are loaded before the first user turn."""
    client = get_ollama_client()
    for name in models:
        ka = keep_alive_for(name)
        try:
            client.chat(
                model=name,
                messages=[{"role": "user", "content": "ok"}],
                options={"temperature": 0, "num_predict": 1},
                keep_alive=ka,
            )
        except Exception:
            # Embed-only models won't accept chat; try embeddings.
            try:
                client.embeddings(model=name, prompt="ok", keep_alive=ka)
            except Exception:
                pass
