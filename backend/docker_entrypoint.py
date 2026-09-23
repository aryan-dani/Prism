"""Container startup: reuse a Chroma index if one is mounted, otherwise build it, then serve."""

from __future__ import annotations

import os
import time
import urllib.request


def wait_ollama() -> bool:
    host = os.environ.get("OLLAMA_HOST", "http://host.docker.internal:11434").rstrip("/")
    url = f"{host}/api/tags"
    for _ in range(20):
        try:
            urllib.request.urlopen(url, timeout=2)
            print(f"[prism] Ollama reachable at {host}", flush=True)
            return True
        except Exception:
            time.sleep(1)
    print(
        f"[prism] Ollama not reachable at {host}. "
        "On the Windows host set OLLAMA_HOST=0.0.0.0:11434 and restart Ollama "
        "so the container can reach the GPU models.",
        flush=True,
    )
    return False


def ensure_index() -> None:
    from prism.core.store import BM25_PATH, get_store

    try:
        n = get_store().count()
    except Exception as exc:
        print(f"[prism] Could not read Chroma index: {exc}", flush=True)
        n = 0
    if n > 0 and BM25_PATH.exists():
        print(f"[prism] Index present ({n} chunks). Skipping build.", flush=True)
        return
    print("[prism] Index missing. Building from processed JSONL (needs Ollama)...", flush=True)
    from prism.ingest.build_index import main

    main()


def main() -> None:
    wait_ollama()
    try:
        ensure_index()
    except Exception as exc:
        print(f"[prism] build_index failed: {exc}", flush=True)
        print("[prism] Starting API anyway. /api/health will report degraded until the index exists.", flush=True)
    os.execvp(
        "uvicorn",
        ["uvicorn", "prism.api.main:app", "--host", "0.0.0.0", "--port", "8000"],
    )


if __name__ == "__main__":
    main()
