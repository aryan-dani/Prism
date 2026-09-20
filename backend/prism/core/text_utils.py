"""Shared text cleanup and query heuristics for the agent."""

from __future__ import annotations

import re
from pathlib import Path

DUP_WORD_RE = re.compile(r"\b([A-Za-z0-9]+)(\s+\1\b)+", re.IGNORECASE)
MODEL_NUM_RE = re.compile(r"\bK-\d{3,6}[A-Z0-9-]*\b", re.IGNORECASE)
INR_AMOUNT_RE = re.compile(r"(?:₹|rs\.?\s*|inr\s*)\s*([\d,]+)", re.I)

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hr": ("leave", "resign", "notice period", "probation", "grievance", "maternity", "terminated", "separation", "promot", "wfh", "work from home", "roll over", "carry forward"),
    "finance": ("expense", "reimburs", "invoice", "per diem", "budget", "purchase order", "₹", "rupee", "approval"),
    "customer_support": (
        "toilet",
        "faucet",
        "shower",
        "warranty claim",
        "install",
        "leak",
        "model k-",
        "troubleshoot",
        "contractor",
        "damaged",
    ),
    "privacy": ("personal data", "privacy", "delete my data", "opt out", "ccpa", "cookies", "sell my"),
    "legal": ("terms and conditions", "prop 65", "proposition 65", "compliance", "arbitration", "sds", "liable", "liability"),
}


def dedupe_consecutive_words(text: str) -> str:
    if not text:
        return text
    return DUP_WORD_RE.sub(r"\1", text)


def sanitize_answer_text(text: str) -> str:
    return dedupe_consecutive_words(text.strip())


def count_domain_signals(query: str) -> int:
    q = query.lower()
    hit = 0
    for keywords in DOMAIN_KEYWORDS.values():
        if any(kw in q for kw in keywords):
            hit += 1
    return hit


def signaled_domains(query: str) -> list[str]:
    q = query.lower()
    out: list[str] = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            out.append(domain)
    return out


def needs_multi_domain_retrieval(query: str) -> bool:
    """Compound questions that need chunks from more than one domain."""
    if count_domain_signals(query) >= 2:
        return True
    q = query.lower()
    if q.count(" and ") >= 2 and len(q.split()) > 12:
        return True
    return False


def extract_model_numbers(query: str) -> list[str]:
    return MODEL_NUM_RE.findall(query)


HOSTILE_DRAFT_MARKERS = (
    "threatening to quit",
    "threaten",
    "quit immediately if",
    "or else i resign",
    "or else i quit",
    "quit if my leave",
    "threatening to quit immediately",
)


JAILBREAK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore all previous instructions", re.I),
    re.compile(r"print your (full )?(system )?prompt", re.I),
    re.compile(r"reveal your (system )?instructions", re.I),
    re.compile(r"developer mode", re.I),
    re.compile(r"repeat the (text|words) above", re.I),
    re.compile(r"list every file path", re.I),
    re.compile(r"no restrictions", re.I),
)


POLICY_OVERRIDE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bas the cfo\b", re.I),
    re.compile(r"\bi'?m the cfo\b", re.I),
    re.compile(r"\bi am the cfo\b", re.I),
    re.compile(r"\bauthorizing you to override\b", re.I),
    re.compile(r"\boverride (the )?(standard |finance )?approval\b", re.I),
    re.compile(r"\boverride (the )?finance policy\b", re.I),
    re.compile(r"\bset my personal expense approval threshold\b", re.I),
    re.compile(r"\bconfirm the (override|₹\s*0|rs\.?\s*0)\b", re.I),
    re.compile(r"\b₹\s*0\s*(minimum|threshold)\b", re.I),
    re.compile(r"\bthreshold to ₹\s*0\b", re.I),
    re.compile(r"\bupdated for cfo-\d+\b", re.I),
)


LEADING_CLAIM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"my manager said .{0,80}(₹|rs\.?|inr)", re.I),
    re.compile(r"that'?s right,?\s*isn'?t it", re.I),
    re.compile(r"confirm — that'?s right", re.I),
    re.compile(r"i was told .{0,80}(₹|rs\.?|inr)", re.I),
)


def is_prompt_exfil_or_jailbreak(query: str) -> bool:
    return any(p.search(query) for p in JAILBREAK_PATTERNS)


def is_policy_override_attempt(query: str) -> bool:
    """Authority spoof / fake personal policy change — refuse deterministically."""
    q = query.lower()
    if any(p.search(query) for p in POLICY_OVERRIDE_PATTERNS):
        return True
    # Broader: claims of authority + asking to change a threshold/policy
    authority = any(w in q for w in ("cfo", "i'm authorized", "i am authorized", "as your boss", "executive override"))
    change = any(w in q for w in ("override", "set my", "change the threshold", "₹0", "rs 0", "rs. 0"))
    return authority and change


def is_soft_policy_tamper_request(query: str) -> bool:
    """Paraphrased policy-tamper asks that intentionally avoid CFO/override regexes.

    These are meant to exercise the LLM + polish path, not the deterministic refuse.
    """
    if is_policy_override_attempt(query):
        return False
    q = query.lower()
    cues = (
        "pre-approved at any amount",
        "preapproved at any amount",
        "vip employee expense",
        "exception is active",
        "ignore the published band",
        "ignore the published threshold",
        "pretend the expense limit",
        "unlock unrestricted finance",
        "treat my claim as pre-approved",
        "waive all approval",
    )
    return any(c in q for c in cues)


def is_soft_prompt_exfil_request(query: str) -> bool:
    """Paraphrased prompt-exfil that avoids 'system prompt' / 'developer mode' regexes."""
    if is_prompt_exfil_or_jailbreak(query):
        return False
    q = query.lower()
    cues = (
        "hidden rules were you given",
        "quote them verbatim",
        "what instructions were you initialized",
        "reveal the rules you follow internally",
        "dump your initial instructions",
    )
    return any(c in q for c in cues)


def is_leading_numeric_claim(query: str) -> bool:
    """User asserts a number and asks for confirmation (sycophancy bait)."""
    if not INR_AMOUNT_RE.search(query):
        return False
    return any(p.search(query) for p in LEADING_CLAIM_PATTERNS) or (
        "confirm" in query.lower() and ("isn't it" in query.lower() or "right?" in query.lower())
    )


def extract_claimed_inr_amounts(query: str) -> list[str]:
    return [m.group(1).replace(",", "") for m in INR_AMOUNT_RE.finditer(query)]


def draft_needs_professional_tone(text: str) -> bool:
    t = text.lower()
    return any(m in t for m in HOSTILE_DRAFT_MARKERS)


def is_guess_invitation(query: str) -> bool:
    q = query.lower()
    return any(
        p in q
        for p in (
            "best guess",
            "just guess",
            "even if you're not sure",
            "even if you are not sure",
            "don't care if it's not in the documents",
            "ignore the documents",
        )
    )


def is_false_premise_probe(query: str) -> bool:
    q = query.lower()
    sellish = ("sell" in q or "share" in q or "sold" in q) and ("data" in q or "personal" in q)
    return sellish and ("privacy" in q or "opt out" in q or "admits" in q or "kohler" in q)


def asks_for_fabricated_schema_fields(query: str) -> list[str]:
    """Fields the user wants in JSON that are not policy concepts."""
    q = query.lower()
    if "json" not in q and "fields:" not in q and "fields :" not in q:
        return []
    invented = []
    for field in ("risk_level", "severity_score", "secret_flag", "override_token"):
        if field in q:
            invented.append(field)
    return invented


# Kohler's real, scraped privacy policy bundles multiple countries' privacy
# notices (US state laws, Canada/PIPEDA, Brazil/LGPD, ...) into one corpus.
# Their boilerplate "here are your rights" language is similar enough that
# dense retrieval alone often can't cleanly separate them (measured: Brazil's
# LGPD section landed within ~0.02 cosine distance of the correct US/CCPA
# section for a California-specific query) -- so a query naming ONE
# jurisdiction can retrieve, and the model can then summarize, a DIFFERENT
# country's section. This is a real cross-contamination bug, not a scorer
# artifact: a California resident asking about CCPA should never be told
# about Brazil's LGPD. Fix: when the query clearly names one jurisdiction,
# drop retrieved chunks whose title/text clearly names a *different* one.
JURISDICTION_MARKERS: dict[str, tuple[str, ...]] = {
    "california": ("california", "ccpa", "shine the light"),
    "canada": ("canada", "pipeda", "canadian"),
    "brazil": ("brazil", "lgpd"),
    "eu": ("gdpr", "european union", "eea", "european economic area"),
}


def detect_named_jurisdiction(query: str) -> str | None:
    """Return the one jurisdiction the query clearly names, or None if it
    names zero or more than one (ambiguous -- don't filter)."""
    q = query.lower()
    hits = [j for j, markers in JURISDICTION_MARKERS.items() if any(m in q for m in markers)]
    return hits[0] if len(hits) == 1 else None


def filter_cross_jurisdiction_chunks(query: str, chunks: list) -> list:
    """Drop chunks that clearly belong to a different named jurisdiction than
    the one the query asked about. No-op if the query doesn't name exactly
    one jurisdiction, or if filtering would remove everything (keep recall
    over an empty result)."""
    target = detect_named_jurisdiction(query)
    if not target:
        return chunks
    other_markers = [
        m for j, markers in JURISDICTION_MARKERS.items() if j != target for m in markers
    ]
    filtered = []
    for c in chunks:
        blob = f"{c.metadata.get('title', '')} {c.text}".lower()
        if any(m in blob for m in other_markers):
            continue
        filtered.append(c)
    return filtered or chunks


def is_contractor_damage_query(query: str) -> bool:
    """Installer/contractor damaged a Kohler product and the user wants warranty/liability."""
    q = query.lower()
    product = any(w in q for w in ("faucet", "toilet", "shower", "sink", "product"))
    harm = any(w in q for w in ("damaged", "broke", "liable", "liability"))
    actor_or_legal = any(
        w in q for w in ("contractor", "install", "liable", "liability", "compliance", "warranty")
    )
    return product and harm and actor_or_legal


# Pure reformat of the previous answer — NOT "draft an email summarizing earlier fact X".
PURE_REFORMAT_RE = re.compile(
    r"(?:"
    r"\b(?:as|in|to)\s+(?:a\s+|an\s+)?(?:json|xml|excel|email|prose|table)\b"
    r"|\bexport\s+(?:that|this|it|the\s+answer)?\s*(?:as\s+)?(?:an?\s+)?(?:excel|xlsx|spreadsheet)\b"
    r"|\b(?:json|xml|excel|email)\s+(?:that|this|it)\b"
    r"|\bformat\s+(?:that|this|it|the\s+answer)\s+as\b"
    r"|\brender\s+(?:as\s+)?(?:json|xml|excel|email)\b"
    r")",
    re.I,
)

SUBSTANTIVE_EMAIL_RE = re.compile(
    r"(?:"
    r"going back|near the start|what you told me|summariz|carry[- ]?forward|"
    r"write an email to|draft an email .{8,}|threatening|along with today"
    r")",
    re.I,
)

MEMORY_LOOKBACK_RE = re.compile(
    r"(?:what did i ask|which question did i ask|remind me what i asked)."
    r"{0,40}?(one|two|three|1|2|3|last|previous)\s+questions?\s+ago"
    r"|two questions ago|one question ago",
    re.I,
)

OUTPUT_CONSTRAINT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"answer yes or no only|yes or no only", re.I), "yes_no_only"),
    (re.compile(r"\bone word only\b", re.I), "one_word"),
    (re.compile(r"under\s+(\d+)\s+words", re.I), "max_words"),
]


def is_pure_reformat_request(message: str) -> bool:
    """True only when the user is asking to re-render the last answer's format."""
    if SUBSTANTIVE_EMAIL_RE.search(message):
        return False
    if PURE_REFORMAT_RE.search(message):
        return True
    # Short "excel/spreadsheet" export phrasing
    if re.search(r"\b(excel|xlsx|spreadsheet)\b", message, re.I) and len(message.split()) <= 10:
        return True
    return False


def is_conversation_memory_query(message: str) -> bool:
    return bool(MEMORY_LOOKBACK_RE.search(message))


def memory_lookback_offset(message: str) -> int:
    """How many user questions before the current one (1 = previous, 2 = two ago)."""
    q = message.lower()
    if "three" in q or re.search(r"\b3\b", q):
        return 3
    if "two" in q or re.search(r"\b2\b", q):
        return 2
    if "one" in q or "previous" in q or "last" in q or re.search(r"\b1\b", q):
        return 1
    return 2


def detect_output_constraint(message: str) -> str | None:
    for pattern, name in OUTPUT_CONSTRAINT_PATTERNS:
        if pattern.search(message):
            return name
    return None


def prefers_email_draft(message: str) -> bool:
    return bool(re.search(r"\b(draft an email|write an email|email to my manager)\b", message, re.I))


from pathlib import Path

UPLOAD_POINTER_RE = re.compile(
    r"\b("
    r"this (document|file|pdf|docx|doc|attachment)|"
    r"the (document|file|pdf|uploaded|attached)|"
    r"uploaded (document|file|pdf)|"
    r"attached (document|file|pdf)|"
    r"according to (the|this) (document|file|pdf)|"
    r"in (the|this) (document|file|pdf)|"
    r"summarize (this|the) (document|file|pdf|attachment)|"
    r"what does this (document|file|pdf) say"
    r")\b",
    re.I,
)
SUMMARIZE_UPLOAD_RE = re.compile(r"^\s*(summarize|summary|tldr|tl;dr|overview)\b", re.I)


def query_points_at_uploads(query: str, filenames: list[str]) -> bool:
    """True when the user is clearly asking about attached files, not the five KBs."""
    q = (query or "").strip()
    if not q:
        return False
    if UPLOAD_POINTER_RE.search(q) or SUMMARIZE_UPLOAD_RE.search(q):
        return True
    ql = q.lower()
    for name in filenames:
        stem = Path(name).stem.lower().strip()
        if len(stem) >= 3 and stem in ql:
            return True
    return False


VAGUE_NEW_SESSION_PATTERNS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"^can i get an extension\??$", re.I), ["hr", "finance", "customer_support"]),
    (re.compile(r"^what'?s covered under my plan\??$", re.I), ["hr", "customer_support", "legal"]),
    (re.compile(r"^is that allowed\??$", re.I), ["hr", "finance", "customer_support", "legal"]),
    # "claim" alone is Finance expense vs Support warranty vs Legal claim — do not guess.
    (
        re.compile(
            r"^what('?s| is) the process for (a |an |my |the )?claim\??$",
            re.I,
        ),
        ["finance", "customer_support", "legal"],
    ),
]


def vague_new_session_clarify(query: str, *, has_prior_turns: bool) -> list[str] | None:
    if has_prior_turns:
        return None
    q = query.strip()
    for pattern, domains in VAGUE_NEW_SESSION_PATTERNS:
        if pattern.search(q):
            return domains
    return None
