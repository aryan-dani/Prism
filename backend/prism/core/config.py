"""Central configuration for Prism.

Every tunable that affects the 8GB VRAM budget, model choice, or file
locations lives here so the rest of the codebase never hardcodes a path
or model name. See docs/decisions.md for the reasoning behind each choice.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
CHROMA_DIR = DATA_DIR / "chroma"
UPLOAD_DIR = DATA_DIR / "uploads"
SESSIONS_DB = DATA_DIR / "sessions.db"
EVAL_DIR = REPO_ROOT / "eval"
DOCS_DIR = REPO_ROOT.parent / "docs"

DOMAINS = ["hr", "finance", "customer_support", "privacy", "legal"]

# ---------------------------------------------------------------------------
# Ollama models
# ---------------------------------------------------------------------------
# Embedding model: tiny (274MB), runs happily alongside a Q4 7-8B generation
# model inside an 8GB VRAM budget. See docs/decisions.md "Embedding model".
EMBED_MODEL = os.environ.get("PRISM_EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = 768

# Generation model: chosen after benchmarking (eval/bench_models.py) across
# qwen2.5:7b-instruct, llama3.1:8b-instruct-q4_K_M, mistral:7b-instruct.
# Overridable via env var so the benchmark script can swap models without
# code changes.
GEN_MODEL = os.environ.get("PRISM_GEN_MODEL", "qwen2.5:7b-instruct")

# Small/fast model for cheap auxiliary calls (session titling). Kept
# separate from GEN_MODEL so titling never competes for the same context
# window/latency budget as real answers.
TITLE_MODEL = os.environ.get("PRISM_TITLE_MODEL", "qwen2.5:3b-instruct")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# ---------------------------------------------------------------------------
# Retrieval / routing
# ---------------------------------------------------------------------------
CHROMA_COLLECTION = "prism_kb"
RETRIEVAL_TOP_K = 8
RETRIEVAL_CANDIDATE_K = 30  # candidates fetched per method before RRF fusion
RRF_K = 60  # standard reciprocal-rank-fusion constant

# Router: cosine-similarity margin between the best and second-best domain
# score below which we treat the query as ambiguous and ask a clarifying
# question rather than guessing.
ROUTER_AMBIGUITY_MARGIN = 0.04
# Absolute floor below which even the best domain score is not trusted
# enough to route confidently -> falls back to domain-agnostic retrieval.
ROUTER_MIN_CONFIDENCE = 0.30

# Keep generation/embed models warm in Ollama between turns (reduces cold-load
# spikes on 8GB VRAM). Override with e.g. PRISM_OLLAMA_KEEP_ALIVE=10m or -1 (forever).
OLLAMA_KEEP_ALIVE = os.environ.get("PRISM_OLLAMA_KEEP_ALIVE", "25m")

# Relevance floor for the "no confident answer" honesty path. Distances are
# cosine distances from Chroma (0 = identical). Legal/Privacy get a stricter
# (lower distance = higher required similarity) floor than other domains.
RELEVANCE_FLOOR_DEFAULT = 0.55
RELEVANCE_FLOOR_STRICT = 0.45
STRICT_DOMAINS = {"legal", "privacy"}
# Lexical / dual-signal confidence: top fused hit also ranked in BM25 top-N,
# or RRF score implying it appeared reasonably in both lists. Lets exact-token
# Finance/CS hits (₹ amounts, model numbers) pass when dense alone is weak.
SPARSE_RANK_CONFIDENCE_MAX = 2
FUSED_SCORE_DUAL_MIN = (1.0 / (RRF_K + 1)) + (1.0 / (RRF_K + 10))

# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------
ASSIST_BASE = "https://assist.kohler.com"
KOHLER_BASE = "https://www.kohler.com"
REQUEST_DELAY_SECONDS = 1.0
USER_AGENT = (
    "PrismResearchBot/0.1 (+academic case study; Kohler-MITWPU AI Research Lab "
    "Track 3; contact: student project, read-only, respects robots.txt)"
)
REQUEST_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
# NOTE: nomic-embed-text's model card advertises an 8k context window, but
# Ollama actually serves it with a 2048-token context by default (verified:
# `ollama show nomic-embed-text` -> "context length  2048"). MAX_CHUNK_TOKENS
# is set safely under that, not under the model card's number -- see
# docs/decisions.md Section 10 for the correction and how it was found
# (a few large table-shaped chunks, e.g. Terms & Conditions and the CCPA
# category table, blew past 2048 and failed the embedding call outright).
MAX_CHUNK_TOKENS = 1500  # only split an article/section if it exceeds this

# Session document uploads (ad-hoc RAG, separate from the five KBs)
UPLOAD_MAX_BYTES = int(os.environ.get("PRISM_UPLOAD_MAX_BYTES", str(12 * 1024 * 1024)))
UPLOAD_MAX_CHUNKS = int(os.environ.get("PRISM_UPLOAD_MAX_CHUNKS", "80"))
UPLOAD_ALLOWED_SUFFIXES = {
    ".pdf",
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".html",
    ".htm",
    ".docx",
}
CHROMA_UPLOADS_COLLECTION = "prism_uploads"
# Smaller chunks than the KB (1500) — ad-hoc docs are read once, so tighter
# passages retrieve better and keep the prompt short on 8GB VRAM.
UPLOAD_CHUNK_TOKENS = int(os.environ.get("PRISM_UPLOAD_CHUNK_TOKENS", "450"))
# Ephemeral by design: vectors + files are purged after this many hours
# (checked at API startup) and immediately on session delete.
UPLOAD_TTL_HOURS = float(os.environ.get("PRISM_UPLOAD_TTL_HOURS", "24"))
# A user who just attached a file is usually asking about it: for the next N
# turns the upload path accepts a looser dense floor before falling back to
# the five permanent knowledge bases.
UPLOAD_RECENT_TURNS = int(os.environ.get("PRISM_UPLOAD_RECENT_TURNS", "4"))
UPLOAD_RELEVANCE_FLOOR = 0.58
UPLOAD_RELEVANCE_FLOOR_RECENT = 0.66
# Comparative gate: an implicit (non-pointed) question only goes to the upload
# when its best upload distance is within this margin of the best distance in
# the five permanent KBs. Calibrated on nomic-embed-text: related queries land
# within ~0.01 of the KB (or beat it); unrelated ones trail by >= 0.15.
UPLOAD_KB_MARGIN = float(os.environ.get("PRISM_UPLOAD_KB_MARGIN", "0.06"))


@dataclass
class RuntimeInfo:
    """Snapshot of what's currently configured, surfaced by /api/health."""

    embed_model: str = EMBED_MODEL
    gen_model: str = GEN_MODEL
    title_model: str = TITLE_MODEL
    collection: str = CHROMA_COLLECTION
    domains: list[str] = field(default_factory=lambda: list(DOMAINS))


def ensure_dirs() -> None:
    for d in (RAW_DIR, PROCESSED_DIR, SYNTHETIC_DIR, CHROMA_DIR, UPLOAD_DIR, EVAL_DIR / "results"):
        d.mkdir(parents=True, exist_ok=True)
