"""Hybrid (dense + BM25) retrieval with reciprocal-rank fusion, domain
scoping, and a relevance floor that powers the "no confident answer" honesty
path (Piece 7 / 2b).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from prism.core.config import (
    RELEVANCE_FLOOR_DEFAULT,
    RELEVANCE_FLOOR_STRICT,
    RETRIEVAL_CANDIDATE_K,
    RETRIEVAL_TOP_K,
    RRF_K,
    STRICT_DOMAINS,
)
from prism.core.embeddings import embed_one
from prism.core.store import RetrievedChunk, get_store


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    query: str
    domain_filter: str | None
    best_dense_distance: float | None
    is_confident: bool
    relevance_floor_used: float = field(default=RELEVANCE_FLOOR_DEFAULT)


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
        scores[c.id] = scores.get(c.id, 0.0) + 1.0 / (k + rank + 1)

    ranked_ids = sorted(scores.keys(), key=lambda i: -scores[i])
    fused = []
    for i in ranked_ids:
        chunk = by_id[i]
        chunk.fused_score = scores[i]
        fused.append(chunk)
    return fused


def retrieve(
    query: str,
    *,
    domain: str | None = None,
    top_k: int = RETRIEVAL_TOP_K,
    candidate_k: int = RETRIEVAL_CANDIDATE_K,
) -> RetrievalResult:
    store = get_store()
    query_embedding = embed_one(query)

    where = {f"domain_{domain}": True} if domain else None
    dense_hits = store.dense_search(query_embedding, top_k=candidate_k, where=where)

    allowed_ids = None
    if domain:
        allowed_ids = {c.id for c in dense_hits}  # sparse search scoped to the same domain-filtered set
        # widen the allowed set slightly so BM25 can surface exact-token matches
        # dense search alone might rank low -- fetch a broader domain id set.
        allowed_ids |= _domain_ids(store, domain)

    sparse_hits = store.sparse_search(query, top_k=candidate_k, allowed_ids=allowed_ids)

    fused = _rrf_fuse(dense_hits, sparse_hits)[:top_k]

    best_distance = None
    if dense_hits:
        distances = [c.dense_distance for c in dense_hits if c.dense_distance is not None]
        if distances:
            best_distance = min(distances)

    floor = RELEVANCE_FLOOR_STRICT if domain in STRICT_DOMAINS else RELEVANCE_FLOOR_DEFAULT
    is_confident = best_distance is not None and best_distance <= floor

    return RetrievalResult(
        chunks=fused,
        query=query,
        domain_filter=domain,
        best_dense_distance=best_distance,
        is_confident=is_confident,
        relevance_floor_used=floor,
    )


_domain_id_cache: dict[str, set[str]] = {}


def _domain_ids(store, domain: str) -> set[str]:
    if domain in _domain_id_cache:
        return _domain_id_cache[domain]
    got = store._collection.get(where={f"domain_{domain}": True}, include=[])
    ids = set(got.get("ids", []))
    _domain_id_cache[domain] = ids
    return ids
