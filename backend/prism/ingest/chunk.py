"""Shared chunking utilities: heading-aware markdown splitting + token-based
overflow splitting for the rare article/section that runs unusually long.

Used by:
    - build_synthetic.py (HR/Finance markdown policy docs)
    - parse_kohler_legal.py's HTML chunker follows the same heading-path idea
      but operates on BeautifulSoup nodes directly (see chunk_by_headings there).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from prism.core.config import MAX_CHUNK_TOKENS

try:
    import tiktoken

    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover - tiktoken should always be installed, but degrade gracefully
    _ENC = None

HEADING_RE = re.compile(r"(?m)^(#{1,4})\s+(.+?)\s*$")


def count_tokens(text: str) -> int:
    if _ENC is not None:
        return len(_ENC.encode(text))
    return max(1, len(text) // 4)  # rough fallback: ~4 chars/token


@dataclass
class MdChunk:
    heading_path: list[str]
    text: str


def chunk_markdown(md_text: str) -> list[MdChunk]:
    """Split a markdown document into chunks along its own heading boundaries."""
    matches = list(HEADING_RE.finditer(md_text))
    if not matches:
        return [MdChunk(heading_path=[], text=md_text.strip())] if md_text.strip() else []

    chunks: list[MdChunk] = []
    heading_stack: list[tuple[int, str]] = []

    preamble = md_text[: matches[0].start()].strip()
    if preamble and len(preamble) > 20:
        chunks.append(MdChunk(heading_path=[], text=preamble))

    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        body = md_text[start:end].strip()

        heading_stack = [h for h in heading_stack if h[0] < level]
        heading_stack.append((level, heading))

        if body:
            chunks.append(MdChunk(heading_path=[h for _, h in heading_stack], text=f"{heading}\n\n{body}"))

    return chunks


def _greedy_pack(units: list[str], *, max_tokens: int, joiner: str) -> list[str]:
    """Greedily pack a list of text units into sub-chunks near max_tokens."""
    packed: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for u in units:
        u_tokens = count_tokens(u)
        if current and current_tokens + u_tokens > max_tokens:
            packed.append(joiner.join(current))
            current, current_tokens = [], 0
        current.append(u)
        current_tokens += u_tokens
    if current:
        packed.append(joiner.join(current))
    return packed


def _hard_split(text: str, *, max_tokens: int) -> list[str]:
    """Last-resort split for a single unbroken blob (e.g. a table row or a
    paragraph with no internal newlines) that's still too long after
    paragraph/line splitting -- slice by an approximate chars-per-token
    ratio rather than leave an over-context chunk that would make the
    embedding call fail outright."""
    approx_chars_per_token = max(1, len(text) // max(1, count_tokens(text)))
    window = max(200, max_tokens * approx_chars_per_token)
    return [text[i : i + window] for i in range(0, len(text), window)] or [text]


def split_if_too_long(text: str, *, max_tokens: int = MAX_CHUNK_TOKENS) -> list[str]:
    """Split an overly long chunk into sub-chunks near max_tokens.

    Three-tier fallback, because real content doesn't always have the
    paragraph breaks we'd like: some scraped tables/policy blocks render as
    one unbroken blob (single "\\n"-joined lines, no "\\n\\n"). Verified
    necessary in practice -- the Terms & Conditions and CCPA-category-table
    chunks (7305 and 3196 tokens respectively) have no double-newlines and
    were still being handed to the embedding model as one oversized chunk,
    which fails outright (nomic-embed-text's Ollama context is 2048 tokens,
    NOT the 8k the model card advertises -- see docs/decisions.md Section 10
    correction) rather than degrading gracefully.
        1. split on paragraph boundaries ("\\n\\n")
        2. any still-too-long paragraph: split on single-line boundaries ("\\n")
        3. any still-too-long line: hard character-window split
    """
    if count_tokens(text) <= max_tokens:
        return [text]

    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [p for p in text.split("\n") if p.strip()] or [text]
        packed = _greedy_pack(paragraphs, max_tokens=max_tokens, joiner="\n")
    else:
        packed = _greedy_pack(paragraphs, max_tokens=max_tokens, joiner="\n\n")

    final: list[str] = []
    for chunk in packed:
        if count_tokens(chunk) <= max_tokens:
            final.append(chunk)
            continue
        lines = [ln for ln in chunk.split("\n") if ln.strip()]
        if len(lines) > 1:
            final.extend(_greedy_pack(lines, max_tokens=max_tokens, joiner="\n"))
        else:
            final.extend(_hard_split(chunk, max_tokens=max_tokens))

    # Final safety net: anything STILL over budget (e.g. one giant line with
    # no newlines at all) gets hard-split rather than shipped as-is.
    safe: list[str] = []
    for chunk in final:
        if count_tokens(chunk) <= max_tokens:
            safe.append(chunk)
        else:
            safe.extend(_hard_split(chunk, max_tokens=max_tokens))

    return safe or [text]
