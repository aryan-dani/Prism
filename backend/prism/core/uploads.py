"""Session-scoped document uploads: parse, chunk, embed, retrieve.

Kept in a separate Chroma collection (`prism_uploads`) so ad-hoc files never
mix into the five Kohler/Meridian knowledge bases. Retrieval is filtered by
`session_id`.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from rank_bm25 import BM25Okapi

from prism.core.config import (
    CHROMA_DIR,
    CHROMA_UPLOADS_COLLECTION,
    UPLOAD_ALLOWED_SUFFIXES,
    UPLOAD_CHUNK_TOKENS,
    UPLOAD_DIR,
    UPLOAD_KB_MARGIN,
    UPLOAD_MAX_BYTES,
    UPLOAD_MAX_CHUNKS,
    UPLOAD_RELEVANCE_FLOOR,
    UPLOAD_TTL_HOURS,
)
from prism.core.embeddings import embed_batch, embed_one
from prism.core.retriever import RetrievalResult, _rrf_fuse
from prism.core.store import RetrievedChunk, get_store, tokenize
from prism.ingest.chunk import HEADING_RE, chunk_markdown, split_if_too_long
from prism.ingest.extract import extract_plain_text

_lock = threading.RLock()


@dataclass
class IngestedDocument:
    id: str
    filename: str
    content_type: str
    bytes_size: int
    chunk_count: int
    created_at: str


def _safe_filename(name: str) -> str:
    base = Path(name or "document").name
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in base).strip()
    return (cleaned or "document")[:180]


def extract_plain_text(path: Path, suffix: str) -> str:
    """Backward-compatible wrapper — prefer prism.ingest.extract."""
    from prism.ingest.extract import extract_plain_text as _extract

    return _extract(path, suffix)


@dataclass
class DocChunk:
    text: str
    heading_path: str = ""


def chunk_document_text(text: str, *, filename: str) -> list[DocChunk]:
    """Same chunking philosophy as the KB ingest (heading boundaries first,
    then token-budget packing) but with a tighter budget for ad-hoc docs.

    Markdown-style headings (or PDFs whose text extractor preserved them) go
    through `chunk_markdown`; everything else is paragraph-packed via
    `split_if_too_long`. Every chunk is prefixed with the filename so BM25
    can match "what does <file> say" phrasing.
    """
    body = (text or "").strip()
    if not body:
        return []

    units: list[DocChunk] = []
    if HEADING_RE.search(body):
        for md in chunk_markdown(body):
            path = " > ".join(md.heading_path)
            for part in split_if_too_long(md.text, max_tokens=UPLOAD_CHUNK_TOKENS):
                if part.strip():
                    units.append(DocChunk(text=part.strip(), heading_path=path))
    else:
        for part in split_if_too_long(body, max_tokens=UPLOAD_CHUNK_TOKENS):
            if part.strip():
                units.append(DocChunk(text=part.strip()))

    out: list[DocChunk] = []
    for u in units:
        out.append(DocChunk(text=f"[{filename}]\n{u.text}", heading_path=u.heading_path))
        if len(out) >= UPLOAD_MAX_CHUNKS:
            break
    return out


class UploadStore:
    def __init__(self) -> None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        self._collection = self._client.get_or_create_collection(
            name=CHROMA_UPLOADS_COLLECTION, metadata={"hnsw:space": "cosine"}
        )
        self._bm25: dict[str, tuple[BM25Okapi, list[str], list[str], list[dict]]] = {}

    def ingest_bytes(
        self,
        *,
        session_id: str,
        filename: str,
        data: bytes,
        content_type: str = "",
    ) -> IngestedDocument:
        if len(data) > UPLOAD_MAX_BYTES:
            raise ValueError(f"File exceeds {UPLOAD_MAX_BYTES // (1024 * 1024)} MB limit")
        suffix = Path(filename).suffix.lower()
        if suffix not in UPLOAD_ALLOWED_SUFFIXES:
            allowed = ", ".join(sorted(UPLOAD_ALLOWED_SUFFIXES))
            raise ValueError(f"Unsupported type {suffix or '(none)'}. Allowed: {allowed}")

        doc_id = str(uuid.uuid4())
        dest_dir = UPLOAD_DIR / session_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = _safe_filename(filename)
        dest = dest_dir / f"{doc_id[:8]}_{safe}"
        dest.write_bytes(data)

        text = extract_plain_text(dest, suffix)
        chunks = chunk_document_text(text, filename=safe)
        if not chunks:
            dest.unlink(missing_ok=True)
            raise ValueError("Could not extract any text from that file")

        source_url = f"upload://{safe}"
        created_ts = datetime.now(timezone.utc).timestamp()
        ids, texts, metas = [], [], []
        for i, chunk in enumerate(chunks):
            cid = f"up_{session_id[:8]}_{doc_id[:8]}_{i:04d}"
            ids.append(cid)
            texts.append(chunk.text)
            metas.append(
                {
                    "session_id": session_id,
                    "doc_id": doc_id,
                    "domain": "uploaded",
                    "title": safe,
                    "source_url": source_url,
                    "type": "upload",
                    "heading_path": chunk.heading_path,
                    "created_ts": created_ts,
                }
            )

        embeddings = embed_batch(texts, show_progress=False)
        with _lock:
            self._collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metas)
            self._bm25.pop(session_id, None)

        return IngestedDocument(
            id=doc_id,
            filename=safe,
            content_type=content_type or suffix,
            bytes_size=len(data),
            chunk_count=len(chunks),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def delete_document(self, session_id: str, doc_id: str) -> None:
        """Delete upload chunks for this session only (session_id + doc_id)."""
        with _lock:
            got = self._collection.get(
                where={"$and": [{"doc_id": doc_id}, {"session_id": session_id}]},
                include=[],
            )
            ids = list(got.get("ids") or [])
            if ids:
                self._collection.delete(ids=ids)
            self._bm25.pop(session_id, None)
        dest_dir = UPLOAD_DIR / session_id
        if dest_dir.exists():
            for p in dest_dir.glob(f"{doc_id[:8]}_*"):
                p.unlink(missing_ok=True)

    def delete_session(self, session_id: str) -> None:
        with _lock:
            got = self._collection.get(where={"session_id": session_id}, include=[])
            ids = list(got.get("ids") or [])
            if ids:
                self._collection.delete(ids=ids)
            self._bm25.pop(session_id, None)
        dest_dir = UPLOAD_DIR / session_id
        if dest_dir.exists():
            for p in dest_dir.iterdir():
                if p.is_file():
                    p.unlink(missing_ok=True)
            try:
                dest_dir.rmdir()
            except OSError:
                pass

    def count(self) -> int:
        with _lock:
            return self._collection.count()

    def purge_expired(self, ttl_hours: float = UPLOAD_TTL_HOURS) -> dict[str, set[str]]:
        """Delete upload chunks (and files) older than `ttl_hours`.

        Returns {session_id: {doc_id, ...}} so callers can strip stale refs
        from persisted session state. Ephemeral by design — see decisions.md.
        """
        if ttl_hours <= 0:
            return {}
        cutoff = datetime.now(timezone.utc).timestamp() - ttl_hours * 3600
        with _lock:
            got = self._collection.get(where={"created_ts": {"$lt": cutoff}}, include=["metadatas"])
            ids = list(got.get("ids") or [])
            metas = list(got.get("metadatas") or [])
            if ids:
                self._collection.delete(ids=ids)
            self._bm25.clear()
        purged: dict[str, set[str]] = {}
        for m in metas:
            sid = str((m or {}).get("session_id") or "")
            did = str((m or {}).get("doc_id") or "")
            if sid and did:
                purged.setdefault(sid, set()).add(did)
        for sid, doc_ids in purged.items():
            dest_dir = UPLOAD_DIR / sid
            if not dest_dir.exists():
                continue
            for did in doc_ids:
                for p in dest_dir.glob(f"{did[:8]}_*"):
                    p.unlink(missing_ok=True)
            try:
                dest_dir.rmdir()
            except OSError:
                pass
        return purged

    def retrieve(
        self,
        session_id: str,
        query: str,
        *,
        top_k: int = 8,
        floor: float = UPLOAD_RELEVANCE_FLOOR,
    ) -> RetrievalResult:
        query_embedding = embed_one(query)
        where = {"session_id": session_id}
        dense: list[RetrievedChunk] = []
        with _lock:
            result = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k * 3, 24),
                where=where,
            )
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        for rank, (id_, doc, meta, dist) in enumerate(zip(ids, docs, metas, dists)):
            dense.append(
                RetrievedChunk(
                    id=id_,
                    text=doc or "",
                    metadata=meta or {},
                    dense_rank=rank,
                    dense_distance=dist,
                )
            )

        sparse = self._sparse_search(session_id, query, top_k=top_k * 3)
        fused = _rrf_fuse(dense, sparse)[:top_k]
        best_distance = None
        distances = [c.dense_distance for c in dense if c.dense_distance is not None]
        if distances:
            best_distance = min(distances)
        # Confidence = dense floor AND comparative check against the KBs.
        #  - Dense-only: the KB's lexical / dual-signal shortcuts assume a
        #    ~500-chunk corpus where a BM25 top-3 hit is meaningful; on a
        #    4-chunk upload *every* query has one.
        #  - Comparative: an absolute floor cannot separate "casual leave"
        #    (unrelated, 0.38 vs a travel policy) from "is alcohol reimbursable"
        #    (related, 0.39). But the KB's own best distance can — unrelated
        #    questions score far better against the permanent KBs.
        # Explicit pointers ("this document", the filename) bypass this gate in
        # the agent, so recall for the user's own file is preserved.
        kb_best: float | None = None
        if fused and best_distance is not None:
            try:
                kb_hits = get_store().dense_search(query_embedding, top_k=3)
                kb_d = [c.dense_distance for c in kb_hits if c.dense_distance is not None]
                kb_best = min(kb_d) if kb_d else None
            except Exception:
                kb_best = None
        is_confident = (
            bool(fused)
            and best_distance is not None
            and best_distance <= floor
            and (kb_best is None or best_distance <= kb_best + UPLOAD_KB_MARGIN)
        )
        return RetrievalResult(
            chunks=fused,
            query=query,
            domain_filter="uploaded",
            best_dense_distance=best_distance,
            is_confident=is_confident,
            relevance_floor_used=floor,
            best_fused_score=fused[0].fused_score if fused else None,
        )

    def _sparse_search(self, session_id: str, query: str, *, top_k: int) -> list[RetrievedChunk]:
        bm25, ids, docs, metas = self._session_bm25(session_id)
        if bm25 is None:
            return []
        scores = bm25.get_scores(tokenize(query))
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
        out: list[RetrievedChunk] = []
        rank = 0
        for i in ranked:
            if scores[i] <= 0:
                continue
            out.append(
                RetrievedChunk(
                    id=ids[i],
                    text=docs[i],
                    metadata=metas[i],
                    sparse_rank=rank,
                )
            )
            rank += 1
            if rank >= top_k:
                break
        return out

    def _session_bm25(
        self, session_id: str
    ) -> tuple[BM25Okapi | None, list[str], list[str], list[dict]]:
        cached = self._bm25.get(session_id)
        if cached is not None:
            return cached
        with _lock:
            got = self._collection.get(where={"session_id": session_id}, include=["documents", "metadatas"])
        ids = list(got.get("ids") or [])
        docs = list(got.get("documents") or [])
        metas = list(got.get("metadatas") or [])
        if not ids:
            return None, [], [], []
        tokenized = [tokenize(t or "") for t in docs]
        bm25 = BM25Okapi(tokenized) if any(tokenized) else None
        if bm25 is None:
            return None, ids, docs, metas
        packed = (bm25, ids, docs, metas)
        self._bm25[session_id] = packed
        return packed


_upload_store: UploadStore | None = None
_upload_store_lock = threading.Lock()


def get_upload_store() -> UploadStore:
    global _upload_store
    with _upload_store_lock:
        if _upload_store is None:
            _upload_store = UploadStore()
        return _upload_store
