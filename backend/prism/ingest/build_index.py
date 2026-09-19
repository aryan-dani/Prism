"""Build the single combined Chroma + BM25 knowledge base from every
data/processed/*.jsonl file.

Run: uv run python -m prism.ingest.build_index

Each processed JSONL file already carries its own `domain` field (the
filename is just organizational -- e.g. legal content appears in both
legal_from_kohler.jsonl and legal_from_assist.jsonl). This script merges
all of them into the one tagged `prism_kb` collection required by the
Phase 1 brief ("one combined vector store... not five separate siloed
stores").
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from prism.core.config import PROCESSED_DIR, ensure_dirs
from prism.core.store import get_store

REQUIRED_FIELDS = {"id", "domain", "title", "source_url", "type", "text"}

# Must be present under data/processed/ before a rebuild is allowed.
REQUIRED_PROCESSED_FILES = (
    "customer_support.jsonl",
    "privacy.jsonl",
    "legal_from_assist.jsonl",
    "legal_from_kohler.jsonl",
    "hr.jsonl",
    "finance.jsonl",
    "hr_records.jsonl",
    "finance_compensation.jsonl",
    "legal_warranty_fixture.jsonl",
)


def assert_required_processed_files() -> None:
    ensure_dirs()
    missing = [name for name in REQUIRED_PROCESSED_FILES if not (PROCESSED_DIR / name).exists()]
    if missing:
        raise SystemExit(
            "[build_index] ERROR: missing required processed JSONL file(s):\n  - "
            + "\n  - ".join(missing)
            + f"\nExpected under {PROCESSED_DIR}. Run crawl/parse/synthetic ingest first."
        )
    empty = []
    for name in REQUIRED_PROCESSED_FILES:
        path = PROCESSED_DIR / name
        n = sum(1 for line in path.open("r", encoding="utf-8") if line.strip())
        if n == 0:
            empty.append(name)
        else:
            print(f"[build_index] {name}: {n} lines")
    if empty:
        raise SystemExit(
            "[build_index] ERROR: required JSONL file(s) are empty:\n  - " + "\n  - ".join(empty)
        )


def load_all_records() -> list[dict]:
    assert_required_processed_files()
    ensure_dirs()
    records: list[dict] = []
    seen_ids: set[str] = set()
    dupes = 0

    jsonl_files = sorted(PROCESSED_DIR.glob("*.jsonl"))
    # Prefer required files first, then any extras (skip underscore reports).
    ordered = [PROCESSED_DIR / n for n in REQUIRED_PROCESSED_FILES]
    extras = [p for p in jsonl_files if p.name not in REQUIRED_PROCESSED_FILES and not p.name.startswith("_")]
    for path in ordered + extras:
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                missing = REQUIRED_FIELDS - rec.keys()
                if missing:
                    raise ValueError(f"{path.name}:{line_no} missing fields {missing}")
                if not rec["text"].strip():
                    continue  # skip empty chunks (e.g. a heading with no body)
                if rec["id"] in seen_ids:
                    dupes += 1
                    continue
                seen_ids.add(rec["id"])
                records.append(rec)

    if dupes:
        print(f"[build_index] skipped {dupes} duplicate chunk ids across processed files")

    return records


def summarize(records: list[dict]) -> None:
    by_domain = Counter(r["domain"] for r in records)
    by_type = Counter(r["type"] for r in records)
    synthetic = sum(1 for r in records if r.get("is_synthetic"))
    print(f"[build_index] total chunks: {len(records)}")
    print(f"[build_index] by domain: {dict(by_domain)}")
    print(f"[build_index] by type: {dict(by_type)}")
    print(f"[build_index] synthetic chunks: {synthetic} / real chunks: {len(records) - synthetic}")


def main() -> None:
    records = load_all_records()
    if not records:
        print("[build_index] No processed records found. Run the ingest scripts first:")
        print("  uv run python -m prism.ingest.crawl_assist")
        print("  uv run python -m prism.ingest.parse_kohler_legal")
        print("  uv run python -m prism.ingest.build_synthetic")
        return

    summarize(records)
    store = get_store()
    n = store.rebuild(records)
    print(f"[build_index] Indexed {n} chunks into Chroma collection at {store._collection.name!r}.")


if __name__ == "__main__":
    main()
