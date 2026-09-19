"""Turn the synthetic HR and Finance markdown policy docs into normalized,
heading-chunked JSONL records -- the same schema shape as the real-document
pipelines, so build_index.py can treat all five domains uniformly.

Run: uv run python -m prism.ingest.build_synthetic
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from prism.core.config import PROCESSED_DIR, SYNTHETIC_DIR
from prism.core.rbac import apply_rbac_fields
from prism.ingest.chunk import chunk_markdown, split_if_too_long

DOCS = [
    {
        "path": SYNTHETIC_DIR / "hr_policy.md",
        "domain": "hr",
        "category": "hr_policy",
        "doc_title": "Meridian Fixtures Inc. HR Policy Manual",
        "output": "hr.jsonl",
        "access_roles": ["general_employee", "hr_staff", "finance_staff"],
        "source_kind": "markdown",
        "source_priority": 50,
    },
    {
        "path": SYNTHETIC_DIR / "finance_policy.md",
        "domain": "finance",
        "category": "finance_policy",
        "doc_title": "Meridian Fixtures Inc. Finance Policy Manual",
        "output": "finance.jsonl",
        "access_roles": ["general_employee", "hr_staff", "finance_staff"],
        "source_kind": "markdown",
        "source_priority": 50,
    },
    {
        "path": SYNTHETIC_DIR / "hr_employee_records.md",
        "domain": "hr",
        "category": "hr_employee_record",
        "doc_title": "Meridian Fixtures Inc. Employee Records Register",
        "output": "hr_records.jsonl",
        "access_roles": ["hr_staff"],
        "source_kind": "markdown",
        "source_priority": 50,
        "type": "employee_record",
    },
    {
        "path": SYNTHETIC_DIR / "finance_compensation.md",
        "domain": "finance",
        "category": "finance_compensation",
        "doc_title": "Meridian Fixtures Inc. Compensation Register",
        "output": "finance_compensation.jsonl",
        "access_roles": ["finance_staff"],
        "source_kind": "markdown",
        "source_priority": 50,
        "type": "compensation",
    },
]


def make_id(domain: str, key: str, idx: int) -> str:
    digest = hashlib.sha256(f"{domain}:{key}#{idx}".encode()).hexdigest()[:16]
    return f"{domain}_{digest}"


def build_doc(
    path: Path,
    *,
    domain: str,
    category: str,
    doc_title: str,
    access_roles: list[str],
    source_kind: str,
    source_priority: int,
    type_: str = "policy",
) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    md_chunks = chunk_markdown(text)

    records = []
    idx = 0
    for c in md_chunks:
        # Skip the disclosure banner blockquote as its own chunk -- it's
        # important context but not a retrievable policy fact; it's instead
        # surfaced permanently via docs/decisions.md and the prompts PDF.
        if c.text.strip().startswith("> **SYNTHETIC DOCUMENT DISCLOSURE**"):
            continue
        heading_title = c.heading_path[-1] if c.heading_path else doc_title
        for sub_text in split_if_too_long(c.text):
            rec = {
                "id": make_id(domain, path.stem, idx),
                "domain": domain,
                "also_domains": [],
                "category": category,
                "title": f"{doc_title} \u2014 {heading_title}" if c.heading_path else doc_title,
                "source_url": f"data/synthetic/{path.name}",
                "type": type_,
                "heading_path": c.heading_path,
                "text": sub_text,
                "is_synthetic": True,
                "access_roles": access_roles,
                "source_kind": source_kind,
                "source_priority": source_priority,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            records.append(apply_rbac_fields(rec))
            idx += 1
    return records


def build_all() -> dict:
    report = {}
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for doc in DOCS:
        records = build_doc(
            doc["path"],
            domain=doc["domain"],
            category=doc["category"],
            doc_title=doc["doc_title"],
            access_roles=doc["access_roles"],
            source_kind=doc["source_kind"],
            source_priority=doc["source_priority"],
            type_=doc.get("type", "policy"),
        )
        out_path = PROCESSED_DIR / doc["output"]
        with out_path.open("w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        report[doc["output"]] = len(records)
    return report


if __name__ == "__main__":
    report = build_all()
    print(json.dumps(report, indent=2))
