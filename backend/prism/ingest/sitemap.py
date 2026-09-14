"""Parse the Kohler Assist sitemap into a deduplicated list of article URLs.

https://assist.kohler.com/en/sitemap lists every troubleshooting/support
article as a plain <a href> link, grouped implicitly by URL path:
    /en/<category-slug>/<Article-Title>          -> a real article
    /en/<category-slug>                          -> a category hub page (skip)
    /en/return-policy                            -> standalone article (no category segment)
    /en/cookies                                  -> CCPA page (belongs to Privacy domain, not Customer Support)
    /en/sitemap                                  -> the sitemap page itself (skip)

A handful of slugs are cross-listed under more than one category (verified
by hand: 5 slugs, e.g. "Extension-Deep-Roughing-In-Kits-for-Faucets" appears
under kitchen-faucets, bathroom-faucets, and valves-shower-bath). We store
each slug once and tag it with every category it was found under.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from prism.core.config import ASSIST_BASE
from prism.ingest.fetch import fetch

SITEMAP_URL = f"{ASSIST_BASE}/en/sitemap"

KNOWN_CATEGORIES = {
    "toilets-and-seats",
    "kitchen-faucets",
    "bathroom-faucets",
    "valves-shower-bath",
    "bathing",
    "other-products",
    "warranty",
    "shower-doors",
    "sinks",
    "orders-and-returns",
    "product-registration",
}

# Paths that are navigation/hub pages or out-of-scope, not articles.
SKIP_PATHS = {"/en/sitemap"} | {f"/en/{c}" for c in KNOWN_CATEGORIES}

# Standalone single-segment paths that ARE real content, just not
# category-scoped articles.
STANDALONE_PATHS = {
    "/en/return-policy": "return-policy",  # Piece 4/6 (legal, cross-tag customer_support)
    "/en/cookies": "cookies",  # Piece 5 (privacy / CCPA) -- verified 404 live; kept for
    # completeness, falls through to the privacy-domain fallback discovery if unreachable.
}


@dataclass
class SitemapEntry:
    url: str
    path: str
    slug: str
    categories: list[str] = field(default_factory=list)


def _normalize(href: str) -> str | None:
    """Return an absolute assist.kohler.com URL path, or None if out of scope."""
    if href.startswith("http"):
        parsed = urlparse(href)
        if parsed.netloc != "assist.kohler.com":
            return None
        path = parsed.path
    elif href.startswith("/en/"):
        path = href
    else:
        return None
    return path.rstrip("/")


def parse_sitemap(html: str) -> list[SitemapEntry]:
    soup = BeautifulSoup(html, "lxml")
    by_slug: dict[str, SitemapEntry] = {}
    standalone: dict[str, SitemapEntry] = {}

    for a in soup.find_all("a", href=True):
        path = _normalize(a["href"])
        if not path:
            continue
        if path in SKIP_PATHS:
            continue

        parts = [p for p in path.split("/") if p]  # ["en", "<cat>", "<slug>"] or ["en", "<standalone>"]
        if len(parts) == 3 and parts[0] == "en":
            _, category, slug = parts
            if category not in KNOWN_CATEGORIES:
                continue
            full_url = urljoin(ASSIST_BASE, path)
            if slug not in by_slug:
                by_slug[slug] = SitemapEntry(url=full_url, path=path, slug=slug, categories=[category])
            elif category not in by_slug[slug].categories:
                by_slug[slug].categories.append(category)
        elif len(parts) == 2 and parts[0] == "en" and parts[1] in {
            p.lstrip("/").split("/")[-1] for p in STANDALONE_PATHS
        }:
            slug = parts[1]
            full_url = urljoin(ASSIST_BASE, path)
            standalone.setdefault(slug, SitemapEntry(url=full_url, path=path, slug=slug, categories=[slug]))

    return list(by_slug.values()) + list(standalone.values())


def get_sitemap_entries(*, force: bool = False) -> list[SitemapEntry]:
    result = fetch(SITEMAP_URL, subdir="assist", force=force)
    return parse_sitemap(result.text)


def summarize(entries: list[SitemapEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in entries:
        for c in e.categories:
            counts[c] = counts.get(c, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    entries = get_sitemap_entries()
    print(f"Total unique articles: {len(entries)}")
    for cat, count in summarize(entries).items():
        print(f"  {cat:24s} {count}")
    cross = [e for e in entries if len(e.categories) > 1]
    print(f"Cross-listed articles: {len(cross)}")
    for e in cross:
        print(f"  {e.slug}: {e.categories}")
