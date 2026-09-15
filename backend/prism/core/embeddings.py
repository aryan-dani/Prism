"""Embedding generation via Ollama's local nomic-embed-text model.

Why nomic-embed-text (see docs/decisions.md "Embedding model choice" for the
full writeup): it's ~274MB, runs comfortably alongside a Q4 7-8B generation
model inside the 8GB VRAM budget, supports an 8k context window (more than
enough for our one-chunk-per-article/section design), and is directly
available through Ollama (no separate Python ML stack needed for embeddings).

A simple content-hash cache avoids re-embedding unchanged chunks across
repeated `build_index.py` runs during development.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from prism.core.config import CHROMA_DIR, EMBED_MODEL
from prism.core.ollama_client import get_ollama_client, keep_alive_value

_CACHE_PATH = CHROMA_DIR / "_embed_cache.jsonl"
_cache: dict[str, list[float]] | None = None


def _load_cache() -> dict[str, list[float]]:
    global _cache
    if _cache is not None:
        return _cache
    _cache = {}
    if _CACHE_PATH.exists():
        with _CACHE_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    _cache[rec["hash"]] = rec["embedding"]
                except (json.JSONDecodeError, KeyError):
                    continue
    return _cache


def _content_hash(text: str) -> str:
    return hashlib.sha256((EMBED_MODEL + "::" + text).encode("utf-8")).hexdigest()


def _append_cache(h: str, embedding: list[float]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _CACHE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"hash": h, "embedding": embedding}) + "\n")


def embed_one(text: str) -> list[float]:
    cache = _load_cache()
    h = _content_hash(text)
    if h in cache:
        return cache[h]
    client = get_ollama_client()
    resp = client.embeddings(model=EMBED_MODEL, prompt=text, keep_alive=keep_alive_value())
    embedding = resp["embedding"]
    cache[h] = embedding
    _append_cache(h, embedding)
    return embedding


def embed_batch(texts: list[str], *, show_progress: bool = False) -> list[list[float]]:
    """Embed a list of texts, using the cache where possible.

    Ollama's embeddings endpoint is called per-text (nomic-embed-text is fast
    enough on GPU that batching overhead isn't worth the added complexity at
    our corpus size of ~1-2k chunks).
    """
    iterator = texts
    if show_progress:
        from tqdm import tqdm

        iterator = tqdm(texts, desc="Embedding")
    return [embed_one(t) for t in iterator]
