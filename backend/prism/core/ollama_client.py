"""Shared Ollama client + keep-alive helpers.

One client instance; every chat/embeddings call passes `keep_alive` so the
7B gen model (and embed model) stay resident between turns instead of
cold-loading on an 8GB card.
"""

from __future__ import annotations

import ollama

from prism.core.config import OLLAMA_HOST, OLLAMA_KEEP_ALIVE

_client: ollama.Client | None = None


def get_ollama_client() -> ollama.Client:
    global _client
    if _client is None:
        _client = ollama.Client(host=OLLAMA_HOST)
    return _client


def keep_alive_value() -> str | int:
    """Ollama accepts duration strings ('25m') or -1 (forever) / 0 (unload)."""
    raw = (OLLAMA_KEEP_ALIVE or "25m").strip()
    if raw in {"-1", "0"}:
        return int(raw)
    return raw


def warm_models(models: list[str]) -> None:
    """Best-effort ping so models are loaded before the first user turn."""
    client = get_ollama_client()
    ka = keep_alive_value()
    for name in models:
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
