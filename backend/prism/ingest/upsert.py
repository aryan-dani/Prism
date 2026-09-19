"""Runtime upsert into prism_kb (PDF/DOCX/MD) with the same RBAC tagging as ingest.

Bonus: add or replace documents without a full crawl. Rebuilds BM25 after add.

  uv run python -m prism.ingest.upsert --file path.pdf --domain legal \\
      --source-id fixture-k3901-warranty --replace-source
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from prism.core.config import PROCESSED_DIR, ensure_dirs
from prism.core.rbac import ROLES, apply_rbac_fields, default_access_roles
from prism.core.retriever import clear_acl_cache
from prism.core.store import get_store
from prism.ingest.chunk import chunk_markdown, split_if_too_long
from prism.ingest.extract import extract_plain_text


def _records_from_file(
    path: Path,
    *,
    domain: str,
    source_id: str,
    access_roles: list[str] | None,
    visibility_hint: str | None,
) -> list[dict]:
    suffix = path.suffix.lower()
    text = extract_plain_text(path, suffix)
    if not text.strip():
        raise SystemExit(f"No text extracted from {path}")

    source_kind = {".pdf": "pdf", ".docx": "docx", ".md": "markdown", ".markdown": "markdown"}.get(
        suffix, "html"
    )
    source_priority = 100 if source_kind in ("pdf", "docx") else 50
    roles = access_roles
    if not roles:
        hint = visibility_hint or ""
        roles = default_access_roles(
            {
                "domain": domain,
                "source_url": f"upsert://{source_id}",
                "title": hint or path.name,
                "type": hint,
            }
        )

    pieces: list[str] = []
    if suffix in {".md", ".markdown", ".txt"}:
        for c in chunk_markdown(text):
            if c.text.strip().startswith("> **SYNTHETIC"):
                continue
            pieces.extend(split_if_too_long(c.text))
    else:
        pieces = split_if_too_long(text)

    records = []
    for i, sub in enumerate(pieces):
        digest = hashlib.sha256(f"{source_id}#{i}".encode()).hexdigest()[:16]
        records.append(
            apply_rbac_fields(
                {
                    "id": f"{domain}_{digest}",
                    "domain": domain,
                    "also_domains": [],
                    "category": domain,
                    "title": path.stem.replace("_", " "),
                    "source_url": f"upsert://{source_id}",
                    "type": "upsert",
                    "heading_path": [],
                    "text": sub,
                    "is_synthetic": True,
                    "access_roles": roles,
                    "source_kind": source_kind,
                    "source_priority": source_priority,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
    return records


def upsert(
    path: Path,
    *,
    domain: str,
    source_id: str,
    replace_source: bool = True,
    access_roles: list[str] | None = None,
) -> int:
    ensure_dirs()
    store = get_store()
    records = _records_from_file(path, domain=domain, source_id=source_id, access_roles=access_roles, visibility_hint=None)

    if replace_source:
        # Delete existing chunks with this source_url / source_id prefix
        got = store._collection.get(include=["metadatas"])
        drop = []
        for id_, meta in zip(got.get("ids") or [], got.get("metadatas") or []):
            url = str((meta or {}).get("source_url") or "")
            if source_id in url or url.endswith(source_id) or url == f"upsert://{source_id}" or url == f"fixture://{source_id}.pdf":
                drop.append(id_)
        if drop:
            store._collection.delete(ids=drop)
            # rebuild BM25 from remaining — easiest: full reload via rebuild of all processed
            # For bonus path: append new then reconstruct BM25 from collection
            print(f"[upsert] removed {len(drop)} existing chunks for {source_id}")

    # Append to a sidecar JSONL for reproducibility
    out = PROCESSED_DIR / f"upsert_{source_id}.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Add to Chroma
    from prism.core.embeddings import embed_batch
    from prism.core.store import _flatten_metadata, tokenize
    from rank_bm25 import BM25Okapi

    ids = [r["id"] for r in records]
    texts = [r["text"] for r in records]
    metas = [_flatten_metadata(r) for r in records]
    embeddings = embed_batch(texts, show_progress=False)
    # upsert: delete same ids then add
    try:
        store._collection.delete(ids=ids)
    except Exception:
        pass
    store._collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metas)

    # Rebuild BM25 from full collection
    all_got = store._collection.get(include=["documents", "metadatas"])
    store._bm25_ids = list(all_got.get("ids") or [])
    store._bm25_docs = list(all_got.get("documents") or [])
    store._bm25_metas = list(all_got.get("metadatas") or [])
    store._bm25 = BM25Okapi([tokenize(t) for t in store._bm25_docs]) if store._bm25_docs else None
    store._save_bm25()
    clear_acl_cache()
    print(f"[upsert] added {len(records)} chunks; collection now {store.count()}")
    return len(records)


def main() -> None:
    p = argparse.ArgumentParser(description="Upsert a PDF/DOCX/MD into prism_kb with RBAC tags")
    p.add_argument("--file", required=True, type=Path)
    p.add_argument("--domain", required=True, choices=["hr", "finance", "customer_support", "privacy", "legal"])
    p.add_argument("--source-id", required=True)
    p.add_argument("--replace-source", action="store_true", default=True)
    p.add_argument("--roles", default="", help="Comma-separated access_roles override")
    args = p.parse_args()
    roles = [r.strip() for r in args.roles.split(",") if r.strip()] or None
    if roles:
        for r in roles:
            if r not in ROLES:
                raise SystemExit(f"Unknown role {r}; choose from {ROLES}")
    upsert(args.file, domain=args.domain, source_id=args.source_id, replace_source=args.replace_source, access_roles=roles)


if __name__ == "__main__":
    main()
