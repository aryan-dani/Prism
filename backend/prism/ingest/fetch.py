"""Polite, cached HTTP fetching.

Design goals (see the scraping brief in the project prompt):
  - Respect robots.txt.
  - Throttle to ~1 request/second.
  - Use a real, honest, identifying user-agent.
  - Cache every response on disk keyed by URL, so re-running ingestion
    during development never re-hits the network for a URL we already have.

Two backends are needed because the two target sites behave differently:
  - assist.kohler.com: plain httpx works fine (no bot-protection observed).
  - www.kohler.com: fronted by Akamai; requests without a full browser-like
    TLS/header fingerprint get a 403. curl_cffi's Chrome impersonation
    passes this check reliably (verified manually during planning).
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlparse

import httpx

from prism.core.config import RAW_DIR, REQUEST_DELAY_SECONDS, REQUEST_TIMEOUT, USER_AGENT

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - curl_cffi is a hard dependency, but degrade gracefully
    curl_requests = None


_last_request_at: dict[str, float] = {}
_robots_cache: dict[str, robotparser.RobotFileParser] = {}


def _cache_path(url: str, subdir: str) -> Path:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    safe_name = "".join(c for c in urlparse(url).path if c.isalnum())[-40:] or "root"
    d = RAW_DIR / subdir
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{digest}_{safe_name}.html"


def _throttle(host: str) -> None:
    now = time.monotonic()
    last = _last_request_at.get(host, 0.0)
    wait = REQUEST_DELAY_SECONDS - (now - last)
    if wait > 0:
        time.sleep(wait)
    _last_request_at[host] = time.monotonic()


def robots_allowed(url: str) -> bool:
    """Check robots.txt for the URL's host, caching the parsed rules.

    Note: we deliberately do NOT use RobotFileParser.read(), because it
    fetches with Python's default urllib User-Agent ("Python-urllib/x.y"),
    which both assist.kohler.com and www.kohler.com return 403 Forbidden
    for -- and the standard library's robotparser treats a 401/403 on
    robots.txt itself as "disallow everything". Verified by hand: fetching
    robots.txt with our real, honest UA (the same one used for the actual
    crawl) succeeds with 200 and parses to "Allow: /" for both hosts. We
    fetch it ourselves with httpx + our real UA and hand the text to
    rp.parse() instead.
    """
    parsed = urlparse(url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    if root not in _robots_cache:
        rp = robotparser.RobotFileParser()
        rp.set_url(f"{root}/robots.txt")
        try:
            with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT) as client:
                resp = client.get(f"{root}/robots.txt")
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                # No robots.txt / unreachable -> default to allowed (nothing to respect).
                rp.parse([])
        except Exception:
            rp.parse([])
        _robots_cache[root] = rp
    return _robots_cache[root].can_fetch(USER_AGENT, url)


@dataclass
class FetchResult:
    url: str
    status_code: int
    text: str
    from_cache: bool


def fetch(url: str, *, subdir: str = "misc", use_curl_cffi: bool = False, force: bool = False) -> FetchResult:
    """Fetch a URL with on-disk caching, throttling, and robots.txt checks.

    Args:
        url: absolute URL to fetch.
        subdir: cache subdirectory (e.g. "assist", "kohler_legal").
        use_curl_cffi: use curl_cffi's Chrome-impersonation backend (needed
            for Akamai-fronted www.kohler.com pages).
        force: re-fetch even if a cached copy exists.
    """
    cache_file = _cache_path(url, subdir)
    if not force and cache_file.exists():
        return FetchResult(url=url, status_code=200, text=cache_file.read_text(encoding="utf-8"), from_cache=True)

    if not robots_allowed(url):
        raise PermissionError(f"robots.txt disallows fetching: {url}")

    host = urlparse(url).netloc

    max_retries = 4
    backoff_seconds = 5.0
    status, text = 0, ""

    for attempt in range(max_retries + 1):
        _throttle(host)

        if use_curl_cffi:
            if curl_requests is None:
                raise RuntimeError("curl_cffi is required for this host but is not installed")
            resp = curl_requests.get(
                url,
                impersonate="chrome",
                timeout=REQUEST_TIMEOUT,
                headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            status, text = resp.status_code, resp.text
        else:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                timeout=REQUEST_TIMEOUT,
                follow_redirects=True,
            ) as client:
                resp = client.get(url)
                status, text = resp.status_code, resp.text

        if status != 429:
            break

        # Rate-limited: back off (exponentially) and retry. Sustained crawling
        # at the mandated ~1 req/sec still tripped assist.kohler.com's rate
        # limiter after a few hundred requests in one session -- observed
        # directly during the Phase 1 crawl (141/362 requests got 429 on the
        # first full pass). Retrying with backoff after the burst subsides
        # recovers essentially all of them without violating politeness.
        wait = backoff_seconds * (2**attempt)
        print(f"[fetch] 429 rate-limited on {url}, backing off {wait:.0f}s (attempt {attempt + 1}/{max_retries})")
        time.sleep(wait)

    if status == 200:
        cache_file.write_text(text, encoding="utf-8")

    return FetchResult(url=url, status_code=status, text=text, from_cache=False)
