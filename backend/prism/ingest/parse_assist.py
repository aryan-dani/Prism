"""Parse a single Kohler Assist (Mavenoid) article into a normalized record.

Every assist.kohler.com article page embeds a Next.js `__NEXT_DATA__` JSON
blob containing the exact same content the widget renders, already free of
nav/footer/boilerplate. We parse that JSON directly instead of scraping
rendered HTML text -- it's more reliable and trivially avoids the "strip
nav/footer noise" requirement, since the JSON never contained that noise to
begin with.

Relevant shape (`props.pageProps.modelSession.history[0].displayCard`):
    title:   str                      -- the article title
    details: str (markdown)           -- the article body
    choices: [{label, type, ...}]     -- feedback buttons + related-article links
    formFields: [{type:"link", url, label}]  -- linked PDFs/spreadsheets (warranty
                                                 terms, error-code sheets, etc.)

Three article shapes observed and handled:
    1. Troubleshooting/install articles: `details` has markdown headings
       ("## Description of issue:", "# Corrective Actions:", etc.).
    2. VIDEO-* articles: `details` is a one-line description + a bare
       youtube/youtu.be URL. Little extractable text -- lighter record.
    3. Warranty articles: short marketing-style blurb + a `formFields` link
       to the full warranty PDF.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

MODEL_RE = re.compile(r"\bK-\d{3,6}[A-Z0-9]*(?:-[A-Z0-9]+)*\b")
# Many articles render numbered steps as a bolded numeral alone on its own
# line, then the instruction text on the following line(s) -- e.g.
# "**1**\nUnscrew the screw...\n\n**2**\nPull off the handle..." -- rather
# than inline "1. Unscrew...". Normalize this to standard "1. Unscrew..."
# markdown before any other processing so the same list-splitting logic
# (item_start / _LIST_MARKER_RE) picks it up.
STANDALONE_NUM_BADGE_RE = re.compile(r"(?m)^\*\*(\d+)\*\*\s*\n\s*")
VIDEO_URL_RE = re.compile(r"https?://(?:www\.)?(?:youtu\.be/|youtube\.com/\S*)\S*")
DOC_LINK_RE = re.compile(r"https?://\S+?\.(?:pdf|xlsx|xls|csv)\b", re.IGNORECASE)
HEADING_RE = re.compile(r"(?m)^#{1,3}\s*(.+?)\s*$")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

GENERIC_CHOICE_LABELS = {
    "problem solved",
    "problem is still there",
    "i found what i was looking for",
    "no, i need more help with warranty",
    "this was helpful",
    "this was not helpful",
    "i have another question",
    "ask a different question",
    "select a different product",
    "yes",
    "no",
}

CAUSE_KEYWORDS = ("cause",)
DESCRIPTION_KEYWORDS = ("description", "symptom", "issue", "overview", "purpose")
# Broadened beyond the original "correct/solution/action/..." set: a large
# fraction of install-guide/troubleshooting articles use gerund/imperative
# section headings ("Removing the Jet", "Install the Retainer", "Adjusting
# the Trip Lever") with NO literal "correct"/"step"/"action" keyword at all.
# Verified against the hand-review sample in eval/results/validation_customer_support.md
# (corrective_actions fill-rate for troubleshooting records was only ~7%
# before this fix -- see docs/decisions.md Section 10).
ACTION_KEYWORDS = (
    "correct",
    "solution",
    "action",
    "step",
    "resolution",
    "fix",
    "replac",
    "install",
    "remov",
    "adjust",
    "clean",
    "reset",
    "disassembl",
    "assembl",
    "connect",
    "repair",
    "how to",
    "instruction",
    "procedure",
    "checking",
    "testing",
)


@dataclass
class ParsedArticle:
    title: str
    full_text: str  # cleaned markdown, images stripped -- this is what gets embedded
    issue_description: str
    causes: list[str] = field(default_factory=list)
    corrective_actions: list[str] = field(default_factory=list)
    related_articles: list[str] = field(default_factory=list)
    video_url: str | None = None
    models_mentioned: list[str] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)
    article_type: str = "troubleshooting"


def extract_next_data(html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return None
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        return None


def _split_into_items(text: str) -> list[str]:
    """Split a body of markdown text into discrete list items.

    Handles numbered ("1.)", "1.", "1)") and bulleted ("-", "*") lists; falls
    back to treating the whole block as a single item if no list markers are
    found.
    """
    text = text.strip()
    if not text:
        return []

    lines = text.split("\n")
    item_start = re.compile(r"^\s*(?:\d+[.)]\s*|\d+\.\)\s*|[-*]\s+)")
    items: list[str] = []
    current: list[str] = []
    for line in lines:
        if item_start.match(line):
            if current:
                items.append(" ".join(current).strip())
            current = [item_start.sub("", line).strip()]
        elif line.strip():
            current.append(line.strip())
    if current:
        items.append(" ".join(current).strip())

    if not items:
        return [text.replace("\n", " ").strip()]
    return [i for i in items if i]


def _classify_heading(heading: str) -> str:
    h = heading.lower().strip(": ")
    if any(k in h for k in CAUSE_KEYWORDS):
        return "causes"
    if any(k in h for k in ACTION_KEYWORDS):
        return "corrective_actions"
    if any(k in h for k in DESCRIPTION_KEYWORDS):
        return "issue_description"
    return "other"


_LIST_MARKER_RE = re.compile(r"(?m)^\s*(?:\d+[.)]\s+|\d+\.\)\s+|[-*]\s+)")


def _split_sections(details_md: str) -> dict[str, list[str]]:
    """Split markdown body into buckets keyed by heading intent."""
    buckets: dict[str, list[str]] = {"issue_description": [], "causes": [], "corrective_actions": [], "other": []}

    matches = list(HEADING_RE.finditer(details_md))
    if not matches:
        # Many install-guide/troubleshooting articles have NO markdown headings
        # at all -- just a lede sentence followed directly by a numbered/bulleted
        # step list (e.g. "Follow these steps: 1. Turn off water. 2. Remove cap.").
        # Detect that shape so corrective_actions isn't silently left empty for
        # a large fraction of the corpus.
        list_matches = list(_LIST_MARKER_RE.finditer(details_md))
        if len(list_matches) >= 2:
            preamble = details_md[: list_matches[0].start()].strip()
            steps_block = details_md[list_matches[0].start() :].strip()
            if preamble:
                buckets["issue_description"].append(preamble)
            buckets["corrective_actions"].append(steps_block)
        else:
            buckets["issue_description"].append(details_md.strip())
        return buckets

    # Text before the first heading is the article's lede -- always description.
    preamble = details_md[: matches[0].start()].strip()
    if preamble:
        buckets["issue_description"].append(preamble)

    for i, m in enumerate(matches):
        heading = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(details_md)
        body = details_md[start:end].strip()
        bucket = _classify_heading(heading)
        # Fallback for headings that don't match any known keyword (e.g. a
        # plain product/part name used as a section title): if the body is a
        # numbered/bulleted list, it's almost certainly a procedure, not
        # generic "other" prose -- classify as corrective_actions instead.
        if bucket == "other" and len(list(_LIST_MARKER_RE.finditer(body))) >= 2:
            bucket = "corrective_actions"
        if body:
            buckets[bucket].append(body)

    return buckets


def parse_article(html: str, *, fallback_title: str = "") -> ParsedArticle | None:
    data = extract_next_data(html)
    if not data:
        return None

    try:
        card = data["props"]["pageProps"]["modelSession"]["history"][0]["displayCard"]
    except (KeyError, IndexError, TypeError):
        return None

    title = card.get("title") or fallback_title
    details_raw = card.get("details") or ""
    details_raw = STANDALONE_NUM_BADGE_RE.sub(lambda m: f"{m.group(1)}. ", details_raw)

    video_match = VIDEO_URL_RE.search(details_raw)
    video_url = video_match.group(0) if video_match else None

    cleaned = IMAGE_RE.sub("", details_raw)
    # Strip markdown emphasis markers for a plain-text-friendly chunk while
    # keeping the words (e.g. "**Lifetime Limited Warranty.**" -> "Lifetime...").
    cleaned = re.sub(r"[*_]{1,2}", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    is_video = title.strip().upper().startswith("VIDEO")

    attachments: list[dict] = []
    for ff in card.get("formFields") or []:
        if ff.get("type") == "link" and ff.get("url"):
            attachments.append({"label": ff.get("label", ""), "url": ff["url"]})
    for m in DOC_LINK_RE.finditer(details_raw):
        url = m.group(0)
        if not any(a["url"] == url for a in attachments):
            attachments.append({"label": "", "url": url})

    related_articles = [
        c["label"]
        for c in (card.get("choices") or [])
        if c.get("label") and c["label"].strip().lower() not in GENERIC_CHOICE_LABELS
    ]

    all_text_for_models = f"{title} {cleaned}"
    models_mentioned = sorted(set(MODEL_RE.findall(all_text_for_models)))

    if is_video:
        parsed = ParsedArticle(
            title=title,
            full_text=f"{title}\n\n{cleaned}".strip(),
            issue_description=cleaned,
            video_url=video_url,
            related_articles=related_articles,
            models_mentioned=models_mentioned,
            attachments=attachments,
            article_type="video",
        )
        return parsed

    buckets = _split_sections(cleaned)
    issue_description = "\n\n".join(buckets["issue_description"]).strip()
    causes: list[str] = []
    for block in buckets["causes"]:
        causes.extend(_split_into_items(block))
    corrective_actions: list[str] = []
    for block in buckets["corrective_actions"]:
        corrective_actions.extend(_split_into_items(block))
    # "other" sections (e.g. non-standard headings) are folded back into the
    # description so no information is silently dropped from full_text/issue text.
    if buckets["other"]:
        issue_description = (issue_description + "\n\n" + "\n\n".join(buckets["other"])).strip()

    return ParsedArticle(
        title=title,
        full_text=f"{title}\n\n{cleaned}".strip(),
        issue_description=issue_description,
        causes=causes,
        corrective_actions=corrective_actions,
        related_articles=related_articles,
        video_url=video_url,
        models_mentioned=models_mentioned,
        attachments=attachments,
        article_type="troubleshooting",  # refined by caller (install-guide/warranty/policy) using category+title
    )
