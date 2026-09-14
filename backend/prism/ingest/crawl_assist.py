"""Full polite crawl of assist.kohler.com -> normalized JSONL records.

Run: uv run python -m prism.ingest.crawl_assist

Output:
    data/processed/customer_support.jsonl  -- troubleshooting/install/video/policy articles
    data/processed/legal.jsonl (appended)  -- warranty pages + Prop 65 / SDS / green-building
                                               pages, cross-tagged also_domains=["customer_support"]

Domain classification rule (see docs/decisions.md "Domain assignment for
assist.kohler.com content" and the Piece 4/6 brief):
    - category == "warranty"                       -> domain=legal, also_domains=[customer_support]
    - category == "other-products" AND slug in {Prop65, SDS, Green-building}
                                                     -> domain=legal, also_domains=[customer_support]
    - everything else                               -> domain=customer_support
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

from tqdm import tqdm

from prism.core.config import PROCESSED_DIR
from prism.ingest.chunk import split_if_too_long
from prism.ingest.fetch import fetch
from prism.ingest.parse_assist import parse_article
from prism.ingest.sitemap import STANDALONE_PATHS, SitemapEntry, get_sitemap_entries

LEGAL_SLUGS_UNDER_OTHER_PRODUCTS = {
    "California-Proposition-65",
    "Safety-Data-Sheets-SDS-for-Kohler-Products",
    "Does-Kohler-Offer-Product-Transparency-Documents-for-Green-Building-Certifications",
}

INSTALL_RE = re.compile(r"\b(install|installation|remove|removing|replace|replacement|replacing)\b", re.IGNORECASE)


def classify_type(category_list: list[str], title: str, is_video: bool) -> str:
    if is_video:
        return "video"
    if "warranty" in category_list:
        return "warranty"
    if any(c in category_list for c in ("orders-and-returns", "product-registration", "return-policy")):
        return "policy"
    if INSTALL_RE.search(title):
        return "install-guide"
    return "troubleshooting"


def classify_domain(slug: str, category_list: list[str]) -> tuple[str, list[str]]:
    if "warranty" in category_list:
        return "legal", ["customer_support"]
    if "other-products" in category_list and slug in LEGAL_SLUGS_UNDER_OTHER_PRODUCTS:
        return "legal", ["customer_support"]
    return "customer_support", []


def make_id(url: str) -> str:
    import hashlib

    return "assist_" + hashlib.sha256(url.encode()).hexdigest()[:16]


def crawl(*, limit: int | None = None, force: bool = False) -> dict:
    entries: list[SitemapEntry] = get_sitemap_entries(force=force)
    # Add standalone return-policy article (cookies is handled by parse_kohler_legal.py's
    # privacy pipeline since /en/cookies returns 404 live -- see docs/decisions.md).
    for path, slug in STANDALONE_PATHS.items():
        if slug == "return-policy":
            from prism.ingest.sitemap import ASSIST_BASE

            entries.append(SitemapEntry(url=f"{ASSIST_BASE}{path}", path=path, slug=slug, categories=["return-policy"]))

    if limit:
        entries = entries[:limit]

    cs_records: list[dict] = []
    legal_records: list[dict] = []
    failures: list[dict] = []

    title_index: dict[str, str] = {}  # normalized title -> url, built as we go for related-article resolution

    fetched_cards: list[tuple[SitemapEntry, object]] = []

    for entry in tqdm(entries, desc="Fetching assist.kohler.com articles"):
        try:
            result = fetch(entry.url, subdir="assist", force=force)
        except PermissionError as e:
            failures.append({"url": entry.url, "error": str(e)})
            continue
        if result.status_code != 200:
            failures.append({"url": entry.url, "error": f"status={result.status_code}"})
            continue

        parsed = parse_article(result.text, fallback_title=entry.slug.replace("-", " "))
        if parsed is None:
            failures.append({"url": entry.url, "error": "no __NEXT_DATA__ / displayCard found"})
            continue

        title_index[parsed.title.strip().lower()] = entry.url
        fetched_cards.append((entry, parsed))

    for entry, parsed in tqdm(fetched_cards, desc="Normalizing records"):
        record_id = make_id(entry.url)
        article_type = classify_type(entry.categories, parsed.title, parsed.video_url is not None and parsed.article_type == "video")
        domain, also_domains = classify_domain(entry.slug, entry.categories)

        related_urls = [title_index.get(t.strip().lower()) for t in parsed.related_articles]

        base_record = {
            "domain": domain,
            "also_domains": also_domains,
            "category": entry.categories,
            "title": parsed.title,
            "source_url": entry.url,
            "type": article_type,
            "issue_description": parsed.issue_description,
            "causes": parsed.causes,
            "corrective_actions": parsed.corrective_actions,
            "related_articles": parsed.related_articles,
            "related_article_urls": related_urls,
            "video_url": parsed.video_url,
            "models_mentioned": parsed.models_mentioned,
            "attachments": parsed.attachments,
            "is_synthetic": False,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        # Per the brief: "one article = one chunk. Only split if an article
        # is unusually long." Almost every article fits comfortably under
        # MAX_CHUNK_TOKENS as a single chunk; the rare exception (e.g. the
        # SDS article at ~1860 tokens) is split so it stays safely under
        # nomic-embed-text's real 2048-token Ollama context (see
        # docs/decisions.md Section 10).
        text_parts = split_if_too_long(parsed.full_text)
        records_for_article = [
            {**base_record, "id": record_id if len(text_parts) == 1 else f"{record_id}_p{i}", "text": part}
            for i, part in enumerate(text_parts)
        ]

        if domain == "legal":
            legal_records.extend(records_for_article)
        else:
            cs_records.extend(records_for_article)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    cs_path = PROCESSED_DIR / "customer_support.jsonl"
    legal_path = PROCESSED_DIR / "legal.jsonl"

    with cs_path.open("w", encoding="utf-8") as f:
        for r in cs_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Append (don't overwrite) -- parse_kohler_legal.py writes T&C/privacy-adjacent
    # legal content into this same file first or after; both scripts open in a mode
    # that's explicit about append vs overwrite. Here we overwrite a dedicated
    # "_from_assist" partial file to keep this script idempotent and side-effect-clear,
    # and a later merge step (build_index.py) reads all legal*.jsonl files.
    legal_from_assist_path = PROCESSED_DIR / "legal_from_assist.jsonl"
    with legal_from_assist_path.open("w", encoding="utf-8") as f:
        for r in legal_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    report = {
        "total_entries": len(entries),
        "customer_support_records": len(cs_records),
        "legal_records_from_assist": len(legal_records),
        "failures": failures,
        "cross_listed": [e.slug for e in entries if len(e.categories) > 1],
    }
    with (PROCESSED_DIR / "_crawl_assist_report.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only crawl the first N entries (smoke test)")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if cached")
    args = parser.parse_args()

    report = crawl(limit=args.limit, force=args.force)
    print(json.dumps(report, indent=2)[:4000])
