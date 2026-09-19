"""Build processed JSONL for the K-3901 warranty PDF fixture (conflict demo).

Run: uv run python -m prism.ingest.build_warranty_fixture
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from prism.core.config import EVAL_DIR, PROCESSED_DIR
from prism.core.rbac import ROLES, apply_rbac_fields
from prism.ingest.chunk import split_if_too_long
from prism.ingest.extract import extract_plain_text

FIXTURE_PDF = EVAL_DIR / "fixtures" / "k_3901_warranty.pdf"
FIXTURE_MD = EVAL_DIR / "fixtures" / "k_3901_warranty.md"
OUT = PROCESSED_DIR / "legal_warranty_fixture.jsonl"
SOURCE_ID = "fixture-k3901-warranty"


def build() -> int:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    if FIXTURE_PDF.exists():
        try:
            text = extract_plain_text(FIXTURE_PDF, ".pdf")
        except Exception:
            text = ""
    else:
        text = ""
    if not text.strip() and FIXTURE_MD.exists():
        text = FIXTURE_MD.read_text(encoding="utf-8")
    if not text.strip():
        raise SystemExit("No warranty fixture text found")

    records = []
    for i, sub in enumerate(split_if_too_long(text)):
        digest = hashlib.sha256(f"{SOURCE_ID}#{i}".encode()).hexdigest()[:16]
        rec = apply_rbac_fields(
            {
                "id": f"legal_{digest}",
                "domain": "legal",
                "also_domains": ["customer_support"],
                "category": "warranty",
                "title": "K-3901 Limited Warranty (Official PDF Fixture)",
                "source_url": f"fixture://{SOURCE_ID}.pdf",
                "type": "warranty",
                "heading_path": ["K-3901 Warranty"],
                "text": sub,
                "is_synthetic": True,
                "access_roles": list(ROLES),
                "source_kind": "pdf",
                "source_priority": 100,
                "models_mentioned": ["K-3901"],
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        records.append(rec)

    with OUT.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(records)


if __name__ == "__main__":
    n = build()
    print(f"wrote {n} chunks -> {OUT}")
