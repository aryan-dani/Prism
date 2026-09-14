"""Download and extract text from linked PDFs (warranty terms, error-code sheets).

Separate from fetch.py because PDFs are binary and cached/read differently
from the HTML text cache used for article pages.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import httpx
from pypdf import PdfReader

from prism.core.config import RAW_DIR, REQUEST_DELAY_SECONDS, REQUEST_TIMEOUT, USER_AGENT

_last_request_at = 0.0


def _throttle() -> None:
    global _last_request_at
    now = time.monotonic()
    wait = REQUEST_DELAY_SECONDS - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def download_pdf(url: str, *, force: bool = False) -> Path | None:
    """Download a PDF to data/raw/pdf/, cached by URL hash. Returns local path or None on failure."""
    digest = hashlib.sha256(url.encode()).hexdigest()[:24]
    name = Path(url).name or "document.pdf"
    dest = RAW_DIR / "pdf" / f"{digest}_{name}"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        return dest

    _throttle()
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200 or "pdf" not in resp.headers.get("content-type", "").lower() and not url.lower().endswith(".pdf"):
                if resp.status_code != 200:
                    return None
            dest.write_bytes(resp.content)
            return dest
    except Exception:
        return None


def extract_text(pdf_path: Path, *, max_pages: int | None = None) -> str:
    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return ""
    pages = reader.pages[:max_pages] if max_pages else reader.pages
    texts = []
    for page in pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(texts).strip()


def fetch_and_extract(url: str, *, force: bool = False, max_pages: int | None = None) -> str:
    path = download_pdf(url, force=force)
    if path is None:
        return ""
    return extract_text(path, max_pages=max_pages)
