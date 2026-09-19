"""Hybrid (dense + BM25) retrieval with reciprocal-rank fusion, domain
scoping, role ACL, and a relevance floor that powers the "no confident
answer" honesty path (Piece 7 / 2b).

Confidence uses dense distance **or** strong BM25 / dual-signal fused
scores so exact-token hits (₹ bands, model numbers) are not false-negatived
when embeddings alone are weak.

RBAC: every retrieve requires `role`. Chroma `where` ANDs `role_{role}=True`
so forbidden chunks never reach the LLM (UI filtering is not the control).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from prism.core.config import (
    FUSED_SCORE_DUAL_MIN,
    RELEVANCE_FLOOR_DEFAULT,
    RELEVANCE_FLOOR_STRICT,
    RETRIEVAL_CANDIDATE_K,
    RETRIEVAL_TOP_K,
    RRF_K,
    SPARSE_RANK_CONFIDENCE_MAX,
    STRICT_DOMAINS,
)
from prism.core.embeddings import embed_one
from prism.core.rbac import chroma_where, normalize_role
from prism.core.store import RetrievedChunk, get_store


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    query: str
    domain_filter: str | None
    best_dense_distance: float | None
    is_confident: bool
    relevance_floor_used: float = field(default=RELEVANCE_FLOOR_DEFAULT)
    best_fused_score: float | None = None


def _rrf_fuse(dense: list[RetrievedChunk], sparse: list[RetrievedChunk], *, k: int = RRF_K) -> list[RetrievedChunk]:
    by_id: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}

    for rank, c in enumerate(dense):
        by_id[c.id] = c
        scores[c.id] = scores.get(c.id, 0.0) + 1.0 / (k + rank + 1)

    for rank, c in enumerate(sparse):
        if c.id in by_id:
            # merge sparse_rank info onto the existing (dense) record
            by_id[c.id].sparse_rank = rank
        else:
            by_id[c.id] = c
            by_id[c.id].sparse_rank = rank
        scores[c.id] = scores.get(c.id, 0.0) + 1.0 / (k + rank + 1)

    for id_, chunk in by_id.items():
        chunk.fused_score = scores[id_]

    return sorted(by_id.values(), key=lambda c: -(c.fused_score or 0.0))


def confidence_from_hits(
    chunks: list[RetrievedChunk],
    *,
    best_dense_distance: float | None,
    floor: float,
) -> bool:
    """True when dense similarity OR strong BM25 / dual-signal RRF supports answering."""
    if not chunks:
        return False
    dense_ok = best_dense_distance is not None and best_dense_distance <= floor
    top = chunks[0]
    lexical_ok = top.sparse_rank is not None and top.sparse_rank <= SPARSE_RANK_CONFIDENCE_MAX
    dual_ok = (top.fused_score or 0.0) >= FUSED_SCORE_DUAL_MIN
    return dense_ok or lexical_ok or dual_ok


def _sort_by_source_priority(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Official PDF/DOCX (priority 100) before scraped HTML (10) for the LLM."""
    return sorted(
        chunks,
        key=lambda c: (
            -(int(c.metadata.get("source_priority") or 10)),
            -(c.fused_score or 0.0),
        ),
    )


def retrieve(
    query: str,
    *,
    role: str,
    domain: str | None = None,
    top_k: int = RETRIEVAL_TOP_K,
    candidate_k: int = RETRIEVAL_CANDIDATE_K,
) -> RetrievalResult:
    role = normalize_role(role)
    store = get_store()
    query_embedding = embed_one(query)

    where = chroma_where(role=role, domain=domain)
    dense_hits = store.dense_search(query_embedding, top_k=candidate_k, where=where)

    allowed_ids: set[str] | None = set(c.id for c in dense_hits)
    allowed_ids |= _acl_ids(store, role=role, domain=domain)

    sparse_hits = store.sparse_search(query, top_k=candidate_k, allowed_ids=allowed_ids)
    # Defense in depth: drop any sparse hit missing the role flag (legacy index).
    role_key = f"role_{role}"
    sparse_hits = [c for c in sparse_hits if c.metadata.get(role_key) is True or c.metadata.get(role_key) == True]

    fused = _sort_by_source_priority(_rrf_fuse(dense_hits, sparse_hits)[:top_k])

    best_distance = None
    if dense_hits:
        distances = [c.dense_distance for c in dense_hits if c.dense_distance is not None]
        if distances:
            best_distance = min(distances)

    floor = RELEVANCE_FLOOR_STRICT if domain in STRICT_DOMAINS else RELEVANCE_FLOOR_DEFAULT
    is_confident = confidence_from_hits(fused, best_dense_distance=best_distance, floor=floor)
    best_fused = fused[0].fused_score if fused else None

    return RetrievalResult(
        chunks=fused,
        query=query,
        domain_filter=domain,
        best_dense_distance=best_distance,
        is_confident=is_confident,
        relevance_floor_used=floor,
        best_fused_score=best_fused,
    )


_acl_id_cache: dict[tuple[str, str | None], set[str]] = {}


def _acl_ids(store, *, role: str, domain: str | None) -> set[str]:
    key = (role, domain)
    if key in _acl_id_cache:
        return _acl_id_cache[key]
    where = chroma_where(role=role, domain=domain)
    got = store._collection.get(where=where, include=[])
    ids = set(got.get("ids") or [])
    _acl_id_cache[key] = ids
    return ids


def clear_acl_cache() -> None:
    _acl_id_cache.clear()
