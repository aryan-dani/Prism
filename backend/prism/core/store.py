"""Unified Chroma vector store + BM25 sparse sidecar.

Design (see docs/decisions.md "Vector store choice"): ONE Chroma collection
for all five domains, with a `domain` metadata field (plus boolean
`domain_<x>` flags to support cross-tagged chunks like warranty pages that
are both `legal` and `customer_support`). This is what makes mid-conversation
domain-switching (Piece 7) tractable -- retrieval just changes its `where`
filter, it never has to fan out across five separate indexes.

BM25 exists alongside dense retrieval because exact tokens the embedding
model doesn't weight heavily -- model numbers ("K-3901"), section numbers,
and numeric thresholds ("₹25,000") -- are exactly the tokens Finance/Legal
questions hinge on. Chroma's dense search alone under-ranks exact-token
matches; BM25 + dense fused via reciprocal-rank fusion covers both.

The BM25 pickle stores ids, documents, AND metadatas so sparse hits do not
need a per-id Chroma `get` on every query (major latency win on hybrid search).
"""

from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi

from prism.core.config import CHROMA_COLLECTION, CHROMA_DIR, DOMAINS
from prism.core.embeddings import embed_batch, embed_one
from prism.core.rbac import ROLES, apply_rbac_fields

BM25_PATH = CHROMA_DIR / "bm25_index.pkl"

_TOKEN_RE = re.compile(r"[A-Za-z0-9\u20B9]+")


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _flatten_metadata(record: dict) -> dict:
    """Chroma metadata values must be str/int/float/bool -- flatten lists."""
    record = apply_rbac_fields(record)

    category = record.get("category", "")
    if isinstance(category, list):
        category_str = ",".join(category)
    else:
        category_str = str(category)

    also_domains = record.get("also_domains") or []
    domain = record["domain"]
    all_domains = {domain, *also_domains}

    access_roles = record.get("access_roles") or []
    if isinstance(access_roles, str):
        access_roles = [r.strip() for r in access_roles.split(",") if r.strip()]
    access_set = set(access_roles)

    meta = {
        "domain": domain,
        "also_domains": ",".join(also_domains),
        "category": category_str,
        "title": record.get("title", ""),
        "source_url": record.get("source_url", ""),
        "type": record.get("type", ""),
        "is_synthetic": bool(record.get("is_synthetic", False)),
        "heading_path": " > ".join(record.get("heading_path", []) or []),
        "models_mentioned": ",".join(record.get("models_mentioned", []) or []),
        "access_roles": ",".join(access_roles),
        "source_priority": int(record.get("source_priority") or 10),
        "source_kind": str(record.get("source_kind") or "html"),
    }
    for d in DOMAINS:
        meta[f"domain_{d}"] = d in all_domains
    for r in ROLES:
        meta[f"role_{r}"] = r in access_set
    return meta


@dataclass
class RetrievedChunk:
    id: str
    text: str
    metadata: dict
    dense_rank: int | None = None
    sparse_rank: int | None = None
    dense_distance: float | None = None
    fused_score: float = 0.0


class PrismStore:
    def __init__(self, persist_dir: Path = CHROMA_DIR, collection_name: str = CHROMA_COLLECTION):
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection = self._client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )
        self._bm25: BM25Okapi | None = None
        self._bm25_ids: list[str] = []
        self._bm25_docs: list[str] = []
        self._bm25_metas: list[dict] = []
        self._load_bm25()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    def rebuild(self, records: list[dict], *, batch_size: int = 64) -> int:
        """Full rebuild: clears the collection and BM25 index, then re-adds everything."""
        try:
            self._client.delete_collection(self._collection.name)
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(
            name=CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"}
        )

        ids, texts, metadatas = [], [], []
        for r in records:
            ids.append(r["id"])
            texts.append(r["text"])
            metadatas.append(_flatten_metadata(r))

        embeddings = embed_batch(texts, show_progress=True)

        for i in range(0, len(ids), batch_size):
            self._collection.add(
                ids=ids[i : i + batch_size],
                embeddings=embeddings[i : i + batch_size],
                documents=texts[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
            )

        self._bm25_ids = ids
        self._bm25_docs = texts
        self._bm25_metas = metadatas
        tokenized = [tokenize(t) for t in texts]
        self._bm25 = BM25Okapi(tokenized)
        self._save_bm25()

        return len(ids)

    def _save_bm25(self) -> None:
        BM25_PATH.parent.mkdir(parents=True, exist_ok=True)
        with BM25_PATH.open("wb") as f:
            pickle.dump(
                {
                    "ids": self._bm25_ids,
                    "docs": self._bm25_docs,
                    "metadatas": self._bm25_metas,
                },
                f,
            )

    def _load_bm25(self) -> None:
        if not BM25_PATH.exists():
            return
        with BM25_PATH.open("rb") as f:
            data = pickle.load(f)
        self._bm25_ids = data["ids"]
        self._bm25_docs = data["docs"]
        self._bm25_metas = data.get("metadatas") or []
        # Older sidecars lacked metadatas — hydrate once from Chroma and rewrite.
        if self._bm25_ids and (
            not self._bm25_metas or len(self._bm25_metas) != len(self._bm25_ids)
        ):
            self._hydrate_bm25_metas_from_chroma()
        tokenized = [tokenize(t) for t in self._bm25_docs]
        if tokenized:
            self._bm25 = BM25Okapi(tokenized)

    def _hydrate_bm25_metas_from_chroma(self) -> None:
        """One-shot bulk fetch so sparse_search never needs per-hit Chroma gets."""
        got = self._collection.get(ids=self._bm25_ids, include=["metadatas", "documents"])
        by_id = {
            id_: (doc, meta)
            for id_, doc, meta in zip(got.get("ids") or [], got.get("documents") or [], got.get("metadatas") or [])
        }
        metas: list[dict] = []
        docs: list[str] = []
        for id_ in self._bm25_ids:
            pair = by_id.get(id_)
            if pair is None:
                metas.append({})
                docs.append("")
            else:
                doc, meta = pair
                docs.append(doc or "")
                metas.append(meta or {})
        self._bm25_metas = metas
        # Prefer Chroma documents if sidecar docs were empty/mismatched length.
        if len(docs) == len(self._bm25_ids) and any(docs):
            self._bm25_docs = docs
        self._save_bm25()

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    def count(self) -> int:
        return self._collection.count()

    def dense_search(self, query_embedding: list[float], *, top_k: int, where: dict | None = None) -> list[RetrievedChunk]:
        result = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
        )
        chunks = []
        ids = result["ids"][0]
        docs = result["documents"][0]
        metas = result["metadatas"][0]
        dists = result["distances"][0]
        for rank, (id_, doc, meta, dist) in enumerate(zip(ids, docs, metas, dists)):
            chunks.append(RetrievedChunk(id=id_, text=doc, metadata=meta, dense_rank=rank, dense_distance=dist))
        return chunks

    def sparse_search(self, query: str, *, top_k: int, allowed_ids: set[str] | None = None) -> list[RetrievedChunk]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
        chunks = []
        rank = 0
        for i in ranked:
            id_ = self._bm25_ids[i]
            if allowed_ids is not None and id_ not in allowed_ids:
                continue
            if scores[i] <= 0:
                continue
            text = self._bm25_docs[i] if i < len(self._bm25_docs) else ""
            meta = self._bm25_metas[i] if i < len(self._bm25_metas) else {}
            if not text and not meta:
                # Extremely defensive fallback for corrupt sidecars.
                got = self._collection.get(ids=[id_], include=["metadatas", "documents"])
                if not got["ids"]:
                    continue
                text = got["documents"][0]
                meta = got["metadatas"][0]
            chunks.append(
                RetrievedChunk(
                    id=id_,
                    text=text,
                    metadata=meta or {},
                    sparse_rank=rank,
                )
            )
            rank += 1
            if rank >= top_k:
                break
        return chunks

    def get_by_id(self, chunk_id: str) -> RetrievedChunk | None:
        got = self._collection.get(ids=[chunk_id], include=["metadatas", "documents"])
        if not got["ids"]:
            return None
        return RetrievedChunk(id=chunk_id, text=got["documents"][0], metadata=got["metadatas"][0])


_store_singleton: PrismStore | None = None


def get_store() -> PrismStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = PrismStore()
    return _store_singleton
