"""Shared text cleanup and query heuristics for the agent."""

from __future__ import annotations

import re

DUP_WORD_RE = re.compile(r"\b([A-Za-z0-9]+)(\s+\1\b)+", re.IGNORECASE)
MODEL_NUM_RE = re.compile(r"\bK-\d{3,6}[A-Z0-9-]*\b", re.IGNORECASE)
INR_AMOUNT_RE = re.compile(r"(?:₹|rs\.?\s*|inr\s*)\s*([\d,]+)", re.I)

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "hr": ("leave", "resign", "notice period", "probation", "grievance", "maternity", "terminated", "separation"),
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


def is_contractor_damage_query(query: str) -> bool:
    q = query.lower()
    return ("faucet" in q or "toilet" in q or "product" in q) and (
        "contractor" in q or "damaged" in q or "liability" in q or "liable" in q
    )


VAGUE_NEW_SESSION_PATTERNS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r"^can i get an extension\??$", re.I), ["hr", "finance", "customer_support"]),
    (re.compile(r"^what'?s covered under my plan\??$", re.I), ["hr", "customer_support", "legal"]),
    (re.compile(r"^is that allowed\??$", re.I), ["hr", "finance", "customer_support", "legal"]),
]


def vague_new_session_clarify(query: str, *, has_prior_turns: bool) -> list[str] | None:
    if has_prior_turns:
        return None
    q = query.strip()
    for pattern, domains in VAGUE_NEW_SESSION_PATTERNS:
        if pattern.search(q):
            return domains
    return None
