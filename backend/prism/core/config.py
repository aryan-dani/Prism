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

# Relevance floor for the "no confident answer" honesty path. Distances are
# cosine distances from Chroma (0 = identical). Legal/Privacy get a stricter
# (lower distance = higher required similarity) floor than other domains.
RELEVANCE_FLOOR_DEFAULT = 0.55
RELEVANCE_FLOOR_STRICT = 0.45
STRICT_DOMAINS = {"legal", "privacy"}

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


@dataclass
class RuntimeInfo:
    """Snapshot of what's currently configured, surfaced by /api/health."""

    embed_model: str = EMBED_MODEL
    gen_model: str = GEN_MODEL
    title_model: str = TITLE_MODEL
    collection: str = CHROMA_COLLECTION
    domains: list[str] = field(default_factory=lambda: list(DOMAINS))


def ensure_dirs() -> None:
    for d in (RAW_DIR, PROCESSED_DIR, SYNTHETIC_DIR, CHROMA_DIR, EVAL_DIR / "results"):
        d.mkdir(parents=True, exist_ok=True)
