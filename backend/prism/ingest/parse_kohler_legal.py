"""Fetch and heading-chunk real Kohler legal/privacy pages.

Covers Pieces 5 (Privacy) and part of 6 (Legal/Compliance):
    - https://www.kohler.com/en/legal/privacy-policy
    - https://www.kohler.com/en/legal/terms-and-conditions
    - https://www.kohler.com/en/legal (hub page's own "Legal Statement" text)
    - https://www.kohler.com/en/legal/accessibility (discovered from the hub)
    - https://www.kohler.com/en/legal/cookie-policy (discovered from the hub)
    - https://assist.kohler.com/en/cookies (CCPA page; verified 404 -- flagged
      in the crawl report, not synthesized. Not a blocker: the real Privacy
      Policy page itself contains a full "UNITED STATES: STATE PRIVACY RIGHTS
      NOTICE" section with explicit CCPA / "Do Not Sell or Share" content --
      see the `sectionInformationCollection` / `howToContact` headings below.)

These pages are already section-structured (h1/h2/h3), so we chunk along
the document's own heading boundaries instead of fixed-length windows, per
the Phase 1 brief for the Privacy domain.

www.kohler.com is fronted by Akamai and returns 403 to bare requests; we use
curl_cffi's Chrome-TLS-impersonation backend (see fetch.py) which passes the
Akamai bot check -- but the pages themselves are an AEM/Contentful-style app
that hydrates content client-side into a `tmpData.htmlPageItems` JSON tree,
not plain server-rendered HTML. curl_cffi's raw response is a valid page
shell but the actual policy text isn't present as static HTML text.

Verified fix: a one-time browser render (Chrome DevTools Protocol snapshot of
`document.querySelector('main').outerHTML` after the page hydrates) captures
the real rendered DOM -- clean h1/h2/h3/p/li structure, no nav/footer, because
`main` never contained that noise to begin with. Those five snapshots are
cached at `data/raw/kohler_legal/*_rendered.html` and are the authoritative
source for these five URLs (see RENDERED_CACHE below) -- they are treated
exactly like any other cached fetch, just captured via a different backend.
This is documented in docs/decisions.md Section 7b.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from prism.core.config import KOHLER_BASE, PROCESSED_DIR
from prism.ingest.chunk import split_if_too_long
from prism.ingest.fetch import fetch

PRIVACY_URL = f"{KOHLER_BASE}/en/legal/privacy-policy"
TERMS_URL = f"{KOHLER_BASE}/en/legal/terms-and-conditions"
LEGAL_HUB_URL = f"{KOHLER_BASE}/en/legal"
ACCESSIBILITY_URL = f"{KOHLER_BASE}/en/legal/accessibility"
COOKIE_POLICY_URL = f"{KOHLER_BASE}/en/legal/cookie-policy"
CCPA_URL = "https://assist.kohler.com/en/cookies"

# These five kohler.com pages hydrate their content client-side (see module
# docstring). curl_cffi gets a valid-but-unusable JSON-shell page for them;
# a one-time browser DOM capture of `main` was cached here instead. Treated
# as the authoritative source for these URLs -- any other kohler.com legal
# sub-page discovered later falls back to the live curl_cffi fetch and, if
# that also turns out to be JS-hydrated content, is flagged in the report
# rather than silently producing an empty/garbage record.
from prism.core.config import RAW_DIR  # noqa: E402

RENDERED_CACHE: dict[str, str] = {
    PRIVACY_URL: "privacy_policy_rendered.html",
    TERMS_URL: "terms_and_conditions_rendered.html",
    LEGAL_HUB_URL: "legal_hub_rendered.html",
    ACCESSIBILITY_URL: "accessibility_rendered.html",
    COOKIE_POLICY_URL: "cookie_policy_rendered.html",
}

# Sub-pages of the /en/legal hub, confirmed by hand (the hub's live HTML is
# also client-hydrated, so automatic <a href> discovery on it finds nothing --
# see discover_legal_hub_links()'s docstring).
KNOWN_LEGAL_SUBPAGES = [ACCESSIBILITY_URL, COOKIE_POLICY_URL]


def _fetch_legal_page(url: str, *, force: bool = False):
    """fetch() that prefers the browser-rendered cache for hydrated pages."""
    if url in RENDERED_CACHE:
        cache_file = RAW_DIR / "kohler_legal" / RENDERED_CACHE[url]
        if cache_file.exists():
            from prism.ingest.fetch import FetchResult

            return FetchResult(url=url, status_code=200, text=cache_file.read_text(encoding="utf-8"), from_cache=True)
    return fetch(url, subdir="kohler_legal", use_curl_cffi=True, force=force)

# Boilerplate blocks that appear on every kohler.com page (nav/footer/cookie
# banner) -- stripped by container selector, not by text matching, so real
# policy text that happens to mention "privacy" or "terms" isn't nuked too.
NOISE_SELECTORS = [
    "nav", "footer", "header", "script", "style", "noscript",
    "[class*=cookie-banner]", "[class*=Footer]", "[class*=Header]", "[id*=footer]", "[id*=header]",
]

MAIN_CONTENT_SELECTORS = [
    "main", "article", "[class*=legal-content]", "[class*=LegalContent]",
    "[class*=rich-text]", "[class*=RichText]", "#content", "[role=main]",
]


@dataclass
class HeadingChunk:
    heading_path: list[str]
    text: str


def _find_main_container(soup: BeautifulSoup):
    for sel in MAIN_CONTENT_SELECTORS:
        node = soup.select_one(sel)
        if node and len(node.get_text(strip=True)) > 500:
            return node
    return soup.body or soup


def _strip_noise(node) -> None:
    for sel in NOISE_SELECTORS:
        for el in node.select(sel):
            el.decompose()


def chunk_by_headings(html: str, *, min_chunk_chars: int = 40) -> list[HeadingChunk]:
    soup = BeautifulSoup(html, "lxml")
    container = _find_main_container(soup)
    _strip_noise(container)

    chunks: list[HeadingChunk] = []
    heading_stack: list[tuple[int, str]] = []  # (level, text)
    current_texts: list[str] = []

    def flush():
        text = "\n".join(t for t in current_texts if t.strip())
        if text.strip() and len(text.strip()) >= min_chunk_chars:
            chunks.append(HeadingChunk(heading_path=[h for _, h in heading_stack], text=text.strip()))
        current_texts.clear()

    body_elements = container.find_all(["h1", "h2", "h3", "h4", "p", "li", "td"], recursive=True)
    for el in body_elements:
        name = el.name
        text = el.get_text(" ", strip=True)
        if not text:
            continue
        if name in ("h1", "h2", "h3", "h4"):
            flush()
            level = int(name[1])
            heading_stack = [h for h in heading_stack if h[0] < level]
            heading_stack.append((level, text))
        else:
            prefix = "- " if name == "li" else ""
            current_texts.append(prefix + text)
    flush()

    if not chunks:
        # Fall back to whole-page text as a single chunk if heading structure
        # wasn't detected (better than silently producing zero records).
        full_text = container.get_text("\n", strip=True)
        if full_text:
            chunks = [HeadingChunk(heading_path=[], text=full_text)]

    return chunks


def discover_legal_hub_links(html: str) -> list[str]:
    """Best-effort <a href> scan of the hub page's raw HTML.

    In practice this returns an empty list for kohler.com's hub page: it's a
    client-hydrated app shell (see module docstring), so its raw HTML has no
    <a> tags for sub-pages -- they're rendered from the tmpData JSON tree at
    runtime. Kept as a real (if currently no-op) discovery step rather than
    removed, so a future non-hydrated hub page would still be picked up
    automatically; KNOWN_LEGAL_SUBPAGES below covers the pages that this
    can't currently discover on its own.
    """
    soup = BeautifulSoup(html, "lxml")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/en/legal") or href.startswith(f"{KOHLER_BASE}/en/legal"):
            full = urljoin(KOHLER_BASE, href)
            if urlparse(full).path.rstrip("/") not in (
                urlparse(LEGAL_HUB_URL).path.rstrip("/"),
            ):
                links.add(full.split("#")[0])
    return sorted(links)


def make_id(url: str, idx: int) -> str:
    digest = hashlib.sha256(f"{url}#{idx}".encode()).hexdigest()[:16]
    return f"legal_{digest}"


def build_records(url: str, html: str, *, domain: str, title: str, also_domains: list[str] | None = None) -> list[dict]:
    chunks = chunk_by_headings(html)
    records = []
    idx = 0
    for c in chunks:
        heading_title = c.heading_path[-1] if c.heading_path else title
        # Avoid "Doc Title \u2014 Section" duplicating into "...\u2014 Section \u2014 Section"
        # when the page's own top-level heading text repeats the doc title we
        # were given by the caller (e.g. a page titled "Accessibility" whose
        # own <h1> is also "Accessibility").
        show_heading = bool(c.heading_path) and heading_title.strip().lower() not in title.strip().lower()
        for sub_text in split_if_too_long(c.text):
            records.append(
                {
                    "id": make_id(url, idx),
                    "domain": domain,
                    "also_domains": also_domains or [],
                    "category": "legal" if domain == "legal" else "privacy",
                    "title": f"{title} \u2014 {heading_title}" if show_heading else title,
                    "source_url": url,
                    "type": "policy",
                    "heading_path": c.heading_path,
                    "text": sub_text,
                    "is_synthetic": False,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            idx += 1
    return records


def crawl_privacy_and_legal(*, force: bool = False) -> dict:
    all_privacy: list[dict] = []
    all_legal: list[dict] = []
    failures: list[dict] = []

    # --- Privacy policy (real only) ---
    try:
        r = _fetch_legal_page(PRIVACY_URL, force=force)
        if r.status_code == 200:
            all_privacy.extend(build_records(PRIVACY_URL, r.text, domain="privacy", title="Kohler Privacy Policy"))
        else:
            failures.append({"url": PRIVACY_URL, "error": f"status={r.status_code}"})
    except Exception as e:
        failures.append({"url": PRIVACY_URL, "error": str(e)})

    # --- CCPA / Do Not Sell page ---
    try:
        r = fetch(CCPA_URL, subdir="assist", force=force)
        if r.status_code == 200:
            all_privacy.extend(
                build_records(CCPA_URL, r.text, domain="privacy", title="Do Not Sell or Share My Personal Information")
            )
        else:
            failures.append({"url": CCPA_URL, "error": f"status={r.status_code} -- flagged, not synthesized"})
    except Exception as e:
        failures.append({"url": CCPA_URL, "error": f"{e} -- flagged, not synthesized"})

    # --- Terms & Conditions ---
    try:
        r = _fetch_legal_page(TERMS_URL, force=force)
        if r.status_code == 200:
            all_legal.extend(build_records(TERMS_URL, r.text, domain="legal", title="Kohler Terms & Conditions"))
        else:
            failures.append({"url": TERMS_URL, "error": f"status={r.status_code}"})
    except Exception as e:
        failures.append({"url": TERMS_URL, "error": str(e)})

    # --- Legal hub (its own "Legal Statement" text) ---
    try:
        r = _fetch_legal_page(LEGAL_HUB_URL, force=force)
        if r.status_code == 200:
            all_legal.extend(build_records(LEGAL_HUB_URL, r.text, domain="legal", title="Kohler Legal Statement"))
        else:
            failures.append({"url": LEGAL_HUB_URL, "error": f"status={r.status_code}"})
    except Exception as e:
        failures.append({"url": LEGAL_HUB_URL, "error": str(e)})

    # --- Legal hub sub-pages (auto-discovered + KNOWN_LEGAL_SUBPAGES, since
    # the hub's raw HTML has no discoverable <a> links -- see
    # discover_legal_hub_links docstring) ---
    sub_links = sorted(set(KNOWN_LEGAL_SUBPAGES))
    for link in sub_links:
        try:
            sr = _fetch_legal_page(link, force=force)
            if sr.status_code == 200:
                title = link.rstrip("/").split("/")[-1].replace("-", " ").title()
                all_legal.extend(build_records(link, sr.text, domain="legal", title=f"Kohler Legal \u2014 {title}"))
            else:
                failures.append({"url": link, "error": f"status={sr.status_code}"})
        except Exception as e:
            failures.append({"url": link, "error": str(e)})

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with (PROCESSED_DIR / "privacy.jsonl").open("w", encoding="utf-8") as f:
        for r in all_privacy:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (PROCESSED_DIR / "legal_from_kohler.jsonl").open("w", encoding="utf-8") as f:
        for r in all_legal:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    report = {
        "privacy_records": len(all_privacy),
        "legal_records_from_kohler": len(all_legal),
        "failures": failures,
    }
    with (PROCESSED_DIR / "_crawl_legal_report.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report = crawl_privacy_and_legal(force=args.force)
    print(json.dumps(report, indent=2))
