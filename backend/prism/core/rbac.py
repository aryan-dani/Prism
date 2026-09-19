"""Role-based access control for Prism.

ACL is enforced at the Chroma/BM25 retrieval layer via boolean `role_*`
metadata flags (same pattern as `domain_*`). UI filtering is extra, not
the control plane.
"""

from __future__ import annotations

from typing import Any

ROLES = (
    "customer",
    "general_employee",
    "hr_staff",
    "finance_staff",
)

PUBLIC_DOMAINS = frozenset({"customer_support", "privacy", "legal"})
INTERNAL_POLICY_DOMAINS = frozenset({"hr", "finance"})

# Cumulative: each role may retrieve chunks tagged with these role flags.
ROLE_SEES_ROLE_TAGS: dict[str, frozenset[str]] = {
    "customer": frozenset({"customer"}),
    "general_employee": frozenset({"customer", "general_employee"}),
    # hr_staff sees public + policy + hr_record chunks (tagged role_hr_staff)
    "hr_staff": frozenset({"customer", "general_employee", "hr_staff"}),
    # finance_staff sees public + policy + compensation (not hr_record-only)
    "finance_staff": frozenset({"customer", "general_employee", "finance_staff"}),
}

DEMO_PASSWORD = "Prism2026!"

SEED_USERS: list[dict[str, str]] = [
    {"email": "priya.customer@prism.local", "name": "Priya Shah", "role": "customer"},
    {"email": "omar.customer@prism.local", "name": "Omar Khan", "role": "customer"},
    {"email": "mei.customer@prism.local", "name": "Mei Chen", "role": "customer"},
    {"email": "alex.employee@prism.local", "name": "Alex Rao", "role": "general_employee"},
    {"email": "jordan.employee@prism.local", "name": "Jordan Patel", "role": "general_employee"},
    {"email": "sam.employee@prism.local", "name": "Sam Iyer", "role": "general_employee"},
    {"email": "riya.hr@prism.local", "name": "Riya Menon", "role": "hr_staff"},
    {"email": "dev.hr@prism.local", "name": "Dev Kulkarni", "role": "hr_staff"},
    {"email": "nina.hr@prism.local", "name": "Nina Bose", "role": "hr_staff"},
    {"email": "arun.finance@prism.local", "name": "Arun Desai", "role": "finance_staff"},
    {"email": "leah.finance@prism.local", "name": "Leah Pinto", "role": "finance_staff"},
    {"email": "vikram.finance@prism.local", "name": "Vikram Shah", "role": "finance_staff"},
]


def normalize_role(role: str | None) -> str:
    r = (role or "").strip().lower()
    if r in ROLES:
        return r
    # aliases
    aliases = {
        "employee": "general_employee",
        "general": "general_employee",
        "hr": "hr_staff",
        "finance": "finance_staff",
    }
    return aliases.get(r, "customer")


def may_access_domain(role: str, domain: str | None) -> bool:
    """Whether this role may ask questions in a domain at all."""
    role = normalize_role(role)
    if not domain or domain == "uploaded":
        return True
    if domain in PUBLIC_DOMAINS:
        return True
    if domain in INTERNAL_POLICY_DOMAINS:
        return role != "customer"
    return False


def domains_for_role(role: str) -> list[str]:
    role = normalize_role(role)
    out = list(PUBLIC_DOMAINS)
    if role != "customer":
        out.extend(sorted(INTERNAL_POLICY_DOMAINS))
    # preserve a stable order matching DOMAINS preference
    order = ["hr", "finance", "customer_support", "privacy", "legal"]
    return [d for d in order if d in out]


def default_access_roles(record: dict[str, Any]) -> list[str]:
    """Derive access_roles when a processed record omits them."""
    explicit = record.get("access_roles")
    if explicit:
        if isinstance(explicit, str):
            return [r.strip() for r in explicit.split(",") if r.strip()]
        return [str(r) for r in explicit]

    domain = (record.get("domain") or "").lower()
    source = " ".join(
        [
            str(record.get("source_url") or ""),
            str(record.get("title") or ""),
            str(record.get("id") or ""),
            str(record.get("type") or ""),
        ]
    ).lower()

    if domain == "hr" and any(k in source for k in ("employee", "record", "personnel", "hr_records")):
        return ["hr_staff"]
    if domain == "finance" and any(k in source for k in ("compensation", "salary", "ctc", "payroll")):
        return ["finance_staff"]
    if domain in ("hr", "finance"):
        return ["general_employee", "hr_staff", "finance_staff"]
    # public domains
    return list(ROLES)


def default_source_priority(record: dict[str, Any]) -> int:
    if record.get("source_priority") is not None:
        return int(record["source_priority"])
    kind = (record.get("source_kind") or "").lower()
    url = str(record.get("source_url") or "").lower()
    if kind in ("pdf", "docx") or url.endswith((".pdf", ".docx")):
        return 100
    if record.get("is_synthetic") or kind == "markdown" or url.endswith(".md"):
        return 50
    return 10


def default_source_kind(record: dict[str, Any]) -> str:
    if record.get("source_kind"):
        return str(record["source_kind"])
    url = str(record.get("source_url") or "").lower()
    if url.endswith(".pdf") or url.startswith("fixture://") and "pdf" in url:
        return "pdf"
    if url.endswith(".docx"):
        return "docx"
    if url.endswith((".md", ".markdown")) or record.get("is_synthetic"):
        return "markdown"
    return "html"


def apply_rbac_fields(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of record with access_roles / source_* filled in."""
    out = dict(record)
    roles = default_access_roles(out)
    out["access_roles"] = roles
    out["source_priority"] = default_source_priority(out)
    out["source_kind"] = default_source_kind(out)
    return out


def chroma_role_where(role: str) -> dict:
    """Chroma where clause: chunk must be tagged for this role."""
    role = normalize_role(role)
    return {f"role_{role}": True}


def chroma_where(*, role: str, domain: str | None = None) -> dict | None:
    role_clause = chroma_role_where(role)
    if domain:
        return {"$and": [{f"domain_{domain}": True}, role_clause]}
    return role_clause


def looks_like_sensitive_hr_query(query: str) -> bool:
    q = query.lower()
    named = any(
        name in q
        for name in (
            "alex rao",
            "jordan patel",
            "sam iyer",
            "riya menon",
            "dev kulkarni",
            "nina bose",
            "arun desai",
            "leah pinto",
            "vikram shah",
            "alex.employee",
            "jordan.employee",
            "sam.employee",
            "employee id",
            "emp-",
            "leave balance for",
            "personnel file",
        )
    )
    return named or ("leave balance" in q and any(x in q for x in ("for ", "of ", "employee")))


def looks_like_sensitive_finance_query(query: str) -> bool:
    q = query.lower()
    if any(k in q for k in ("ctc", "salary", "compensation", "take-home", "take home", "basic pay", "payroll")):
        return True
    return False


def access_denied_message(*, role: str, domain: str | None, query: str) -> str:
    role = normalize_role(role)
    if role == "customer" and domain in INTERNAL_POLICY_DOMAINS:
        return (
            "Access denied. Customer accounts can only query public Customer Support, "
            "Privacy, and Legal content. HR and Finance policies require an employee login."
        )
    if role == "general_employee" and looks_like_sensitive_finance_query(query):
        return (
            "Access denied. Individual compensation and salary data is restricted to Finance staff. "
            "Ask Finance, or sign in with a finance_staff account for this demo."
        )
    if role == "general_employee" and looks_like_sensitive_hr_query(query):
        return (
            "Access denied. Employee-specific HR records are restricted to HR staff. "
            "Contact HR, or sign in with an hr_staff account for this demo."
        )
    if role == "finance_staff" and looks_like_sensitive_hr_query(query) and not looks_like_sensitive_finance_query(query):
        return (
            "Access denied. Personnel / leave-balance files are restricted to HR staff. "
            "Finance staff may query compensation data and enterprise finance guidelines."
        )
    return (
        f"Access denied for role '{role}'. This content is outside your allowed knowledge domains."
    )
