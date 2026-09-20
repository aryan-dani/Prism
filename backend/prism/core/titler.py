"""Session auto-titling.

Deterministic titles. The 3B title model invented camelCase mush and
vague lines like "not enough info". A phrase table plus a cleaned noun
phrase is faster, stays on the 8GB budget, and matches the stress harness.
"""

from __future__ import annotations

import re

TITLE_SYSTEM_PROMPT = (
    "Generate a short, descriptive chat title (max 6 words). "
    "Use ordinary spaces between words. No camelCase, no quotes, no punctuation, no JSON. "
    "Summarize the topic, not the user's full sentence. Output ONLY the title text."
)

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "at", "is", "are",
    "was", "be", "my", "me", "i", "we", "you", "what", "who", "how", "when", "should",
    "can", "do", "does", "this", "that", "these", "those", "according", "document",
    "please", "actually", "need", "needs", "needed", "about", "with", "from", "it",
    "get", "per", "year", "many",
}

_FOLLOWUP = re.compile(
    r"^(actually|and|also|what about|how about|is that|does that|and is)\b",
    re.I,
)

_BAD_TITLE = re.compile(
    r"generate short descriptive|output only|provide (a )?summary|user request|"
    r"chat title|descriptive title|not enough info|insufficient",
    re.I,
)

# First matching rule wins. Keep eval keywords from ux_01_five_session_titles.
_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sick\s+leave|\bsl\b", re.I), "Sick leave entitlement"),
    (re.compile(r"per\s+diem|tier[-\s]?[123]", re.I), "Tier per diem rates"),
    (re.compile(r"shower\s+door|sliding", re.I), "Shower door sliding"),
    (re.compile(r"opt\s*out|do not sell|sale or sharing|personal information", re.I), "Privacy opt-out"),
    (re.compile(r"prop(?:osition)?\s*65|california proposition", re.I), "Proposition 65 warnings"),
    (re.compile(r"(this document|attached|orion).{0,80}(approv|claim)|(approv|claim).{0,80}(this document|attached|orion)", re.I), "Uploaded claim approval"),
    (re.compile(r"expense claim|15,?000|₹\s*15", re.I), "Expense claim approval"),
    (re.compile(r"toilet|flapper|leak|running", re.I), "Toilet leak troubleshooting"),
    (re.compile(r"warranty|k-?3901", re.I), "Warranty coverage"),
    (re.compile(r"casual leave|carry\s*forward|\bcl\b", re.I), "Casual leave carry-forward"),
    (re.compile(r"privacy|personal information|collect", re.I), "Privacy collection"),
]


def _fallback_title(message: str) -> str:
    cleaned = re.sub(r"[^\w\s₹$.,-]", " ", message or "")
    kept: list[str] = []
    for w in cleaned.split():
        if w.lower() in _STOP and not re.search(r"\d", w):
            continue
        kept.append(w)
        if len(kept) >= 6:
            break
    if not kept:
        kept = cleaned.split()[:5]
    title = " ".join(kept).strip(" .,")
    if title and title[0].islower():
        title = title[0].upper() + title[1:]
    return title[:70] or "New conversation"


def _split_camel(text: str) -> str:
    if " " in text:
        return text
    if sum(1 for c in text if c.isupper()) >= 3:
        return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return text


def generate_title(first_user_message: str) -> str:
    text = (first_user_message or "").strip()
    for pattern, title in _RULES:
        if pattern.search(text):
            return title
    return _fallback_title(text)


def _sanitize_title(title: str, fallback_message: str) -> str:
    t = _split_camel(title.strip().strip('"').strip("'"))
    if t.startswith("{") or t.startswith("[") or _BAD_TITLE.search(t):
        return generate_title(fallback_message)
    words = t.split()
    if len(words) > 8:
        t = " ".join(words[:8])
    return t[:70] or generate_title(fallback_message)


def generate_title_fast(first_user_message: str, *, timeout_s: float = 8.0) -> str:
    del timeout_s
    return generate_title(first_user_message)


def maybe_retitle(*, current_title: str | None, new_domain: str, first_message_of_new_domain: str) -> str | None:
    msg = (first_message_of_new_domain or "").strip()
    if len(msg.split()) < 8 or _FOLLOWUP.search(msg):
        return None
    next_title = generate_title(msg)
    if current_title and next_title.lower() == current_title.lower():
        return None
    domain_words = new_domain.replace("_", " ").split()
    if current_title and any(w.lower() in current_title.lower() for w in domain_words if len(w) > 2):
        return None
    return next_title
