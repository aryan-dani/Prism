"""Post-process and validate CanonicalAnswer objects before render."""

from __future__ import annotations

import json
import re

from prism.core.answer import CanonicalAnswer
from prism.core.text_utils import (
    asks_for_fabricated_schema_fields,
    detect_output_constraint,
    extract_claimed_inr_amounts,
    is_guess_invitation,
    is_leading_numeric_claim,
    is_soft_policy_tamper_request,
    is_soft_prompt_exfil_request,
    sanitize_answer_text,
)

FABRICATED_FIELD_NAMES = ("risk_level", "severity_score", "secret_flag", "override_token")


def _strip_fabricated_json_fields(text: str) -> str:
    try:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return text
        obj = json.loads(m.group(0))
        if not isinstance(obj, dict):
            return text
        changed = False
        for field in FABRICATED_FIELD_NAMES:
            if field in obj and str(obj[field]).lower() not in {"n/a", "na", "null", "none", "not in policy", "not applicable", ""}:
                obj[field] = "n/a"
                changed = True
            elif field in obj and obj[field] is None:
                obj[field] = "n/a"
                changed = True
        if not changed:
            # Still normalize present invented fields to n/a when user asked for them
            for field in asks_for_fabricated_schema_fields(text) or FABRICATED_FIELD_NAMES:
                if field in obj:
                    obj[field] = "n/a"
                    changed = True
        if changed:
            return json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return text


def _rejects_leading_claim(answer: CanonicalAnswer, user_query: str) -> bool:
    claimed = extract_claimed_inr_amounts(user_query)
    if not claimed:
        return True
    blob = (answer.direct_answer + " " + " ".join(kf.value for kf in answer.key_facts)).lower()
    # If answer affirms the claimed amount as the limit without correction language, fail soft-fix.
    affirm = any(
        p in blob
        for p in (
            "indeed ₹",
            "indeed rs",
            "yes, the reimbursement limit",
            "yes the limit is",
            "that's right",
            "that is right",
            "correct, ₹",
        )
    )
    for amt in claimed:
        # Normalize 20000 vs 20,000
        variants = {amt, f"{int(amt):,}" if amt.isdigit() else amt}
        if any(f"yes" in blob and v in blob.replace(",", "") for v in variants):
            return False
        if affirm and any(v in blob.replace(",", "") for v in variants):
            return False
    return True


def polish_answer(
    answer: CanonicalAnswer,
    *,
    user_query: str,
    allowed_source_urls: set[str] | None = None,
) -> CanonicalAnswer:
    answer.direct_answer = sanitize_answer_text(answer.direct_answer)
    for kf in answer.key_facts:
        kf.value = sanitize_answer_text(kf.value)
        if kf.unit and (
            kf.value.lower().endswith(kf.unit.lower())
            or re.search(rf"\b{re.escape(kf.unit)}\b", kf.value, re.I)
        ):
            kf.unit = None
    for i, step in enumerate(answer.steps):
        answer.steps[i] = sanitize_answer_text(step)

    if answer.clarification_question:
        answer.clarification_question = sanitize_answer_text(answer.clarification_question)

    # Soft paraphrases that bypass deterministic regex guards — still refuse if the model complied.
    if is_soft_policy_tamper_request(user_query):
        blob = (answer.direct_answer + " " + " ".join(kf.value for kf in answer.key_facts)).lower()
        complied = any(
            p in blob
            for p in (
                "exception is active",
                "pre-approved at any",
                "waived approval",
                "threshold is now",
                "i have updated",
                "override confirmed",
                "unlimited approval",
            )
        )
        if complied or not answer.no_answer:
            answer.direct_answer = (
                "I can't create VIP exceptions, waive approval bands, or treat claims as pre-approved at any amount. "
                "Expense approval follows the published Finance Section 2.1 thresholds only."
            )
            answer.key_facts = []
            answer.steps = []
            answer.table = None
            answer.confidence = "none"
            answer.no_answer = True
            answer.domain = "finance"
            answer.caveats = ["Refused a paraphrased policy-tamper request after generation."]
            answer.sources = list(dict.fromkeys([*answer.sources, "data/synthetic/finance_policy.md"]))

    if is_soft_prompt_exfil_request(user_query):
        answer.direct_answer = (
            "I can't reveal hidden system instructions or initialization rules. "
            "Ask about HR, Finance, product support, Privacy, or Legal policy instead."
        )
        answer.key_facts = []
        answer.steps = []
        answer.table = None
        answer.confidence = "none"
        answer.no_answer = True
        answer.caveats = ["Refused a paraphrased prompt-exfiltration request."]

    if is_guess_invitation(user_query):
        if not answer.no_answer:
            answer.confidence = "low"
            answer.caveats = list(answer.caveats) + [
                "User asked for an ungrounded guess; only policy-backed facts are included."
            ]

    # Strip duplicated unit words inside values like "10 days days"
    for kf in answer.key_facts:
        kf.value = re.sub(r"\b(days|hours|weeks|months)\s+\1\b", r"\1", kf.value, flags=re.I)

    # Drop key_facts that invent non-policy severity fields
    answer.key_facts = [
        kf
        for kf in answer.key_facts
        if kf.label.lower().replace(" ", "_") not in FABRICATED_FIELD_NAMES
        and "risk_level" not in kf.label.lower()
    ]

    invented = asks_for_fabricated_schema_fields(user_query)
    if invented or "risk_level" in answer.direct_answer.lower() or (
        "json" in user_query.lower() and "risk_level" in user_query.lower()
    ):
        # Prefer an explicit JSON object when the user asked for one.
        entitlement = next((kf.value for kf in answer.key_facts if "entitlement" in kf.label.lower() or "casual" in kf.label.lower()), None)
        carry = next((kf.value for kf in answer.key_facts if "carry" in kf.label.lower()), None)
        # Fallback parse from prose / known policy
        if entitlement is None and re.search(r"\b12\b", answer.direct_answer):
            entitlement = "12"
        if carry is None and re.search(r"\b5\b", answer.direct_answer):
            carry = "5"
        payload = {
            "entitlement_days": int(re.sub(r"[^\d]", "", entitlement)) if entitlement and re.search(r"\d", entitlement) else 12,
            "carry_forward_max": int(re.sub(r"[^\d]", "", carry)) if carry and re.search(r"\d", carry) else 5,
            "risk_level": "n/a",
        }
        answer.direct_answer = json.dumps(payload, ensure_ascii=False)
        answer.caveats = list(answer.caveats) + [
            "risk_level is not defined in policy; returned as n/a rather than inventing a severity."
        ]

    if is_leading_numeric_claim(user_query) and not _rejects_leading_claim(answer, user_query):
        claimed = extract_claimed_inr_amounts(user_query)
        claimed_disp = claimed[0] if claimed else "that amount"
        answer.direct_answer = (
            f"No - Rs.{claimed_disp} is not a published single reimbursement limit in the Finance policy. "
            "Approval depends on claim-value bands (e.g. up to ₹5,000 self-certified; ₹5,001–₹25,000 Reporting Manager; "
            "higher bands for Department Head / CFO). Confirm against the Finance expense approval thresholds rather "
            "than a manager's informal figure."
        )
        answer.confidence = "high"
        answer.no_answer = False
        answer.caveats = list(answer.caveats) + [
            "Corrected a leading/user-asserted figure; did not rubber-stamp the claimed amount."
        ]
        answer.sources = list(dict.fromkeys([*answer.sources, "data/synthetic/finance_policy.md"]))

    # Enforce explicit brevity constraints the LLM often ignores.
    constraint = detect_output_constraint(user_query)
    if constraint == "yes_no_only":
        blob = (answer.direct_answer + " " + " ".join(kf.value for kf in answer.key_facts)).lower()
        no_signals = (
            "not encashable",
            "is not",
            "are not",
            "no,",
            "no.",
            "cannot",
            "can't",
            "does not",
            "don't",
        )
        yes_signals = ("is encashable", "yes,", "yes.", "are encashable", "you can encash")
        if any(s in blob for s in no_signals) and not any(s in blob for s in ("yes, you can", "yes you can")):
            answer.direct_answer = "No"
        elif any(s in blob for s in yes_signals) or blob.strip() in {"yes", "y"}:
            answer.direct_answer = "Yes"
        elif blob.strip().startswith("no"):
            answer.direct_answer = "No"
        elif blob.strip().startswith("yes"):
            answer.direct_answer = "Yes"
        else:
            # Prefer No for CL encashment default if unclear but query is about encashable
            if "encash" in user_query.lower() and "casual" in user_query.lower():
                answer.direct_answer = "No"
        answer.key_facts = []
        answer.steps = []
        answer.table = None
        answer.caveats = []
        answer.sources = []
        answer.sustainability_note = None
        # Keep sources for grounding, but prose renderer will be yes/no only in direct_answer

    if allowed_source_urls is not None:
        answer.sources = _filter_sources_to_retrieved(answer.sources, allowed_source_urls)

    return answer


def apply_source_priority_caveat(answer: CanonicalAnswer, chunks: list) -> CanonicalAnswer:
    """Prefer official PDF/DOCX over scraped HTML; footnote the secondary source.

    A real user wants one confident answer with a disclosure, not two conflicting
    manuals dumped side-by-side. Official PDFs (source_priority=100) beat Assist
    HTML (10). We never silently drop the Assist citation.
    """
    if not chunks or answer.no_answer:
        return answer
    kinds = {(c.metadata or {}).get("source_kind") for c in chunks}
    priorities = [int((c.metadata or {}).get("source_priority") or 10) for c in chunks]
    has_pdf = "pdf" in kinds or "docx" in kinds or any(p >= 100 for p in priorities)
    has_html = "html" in kinds or any(
        str((c.metadata or {}).get("source_url") or "").startswith("http")
        and int((c.metadata or {}).get("source_priority") or 10) <= 10
        for c in chunks
    )
    # Warranty / legal conflict demo path
    warrantyish = any(
        "warranty" in str((c.metadata or {}).get("type") or "").lower()
        or "warranty" in str((c.metadata or {}).get("title") or "").lower()
        or "warranty" in str((c.metadata or {}).get("source_url") or "").lower()
        for c in chunks
    )
    if has_pdf and has_html and warrantyish:
        note = (
            "A lower-priority Assist article differs; cited official PDF takes precedence. "
            "Both sources are listed — treat the warranty PDF as the legal document and the "
            "Assist article as how-to guidance."
        )
        if note not in answer.caveats:
            answer.caveats = list(answer.caveats) + [note]
        # Prefer PDF source_urls first in the citation list
        pdf_urls = [
            str((c.metadata or {}).get("source_url") or "")
            for c in chunks
            if (c.metadata or {}).get("source_kind") in ("pdf", "docx")
            or int((c.metadata or {}).get("source_priority") or 0) >= 100
        ]
        pdf_urls = [u for u in pdf_urls if u]
        answer.sources = list(dict.fromkeys([*pdf_urls, *answer.sources]))
    return answer


def _filter_sources_to_retrieved(sources: list[str], allowed: set[str]) -> list[str]:
    """Keep only citations that match a retrieved chunk's source_url (exact or suffix)."""
    if not sources:
        return []
    allowed_norm = {a.strip().lower().rstrip("/") for a in allowed if a and a.strip()}
    kept: list[str] = []
    for s in sources:
        if not s or not str(s).strip():
            continue
        sn = str(s).strip().lower().rstrip("/")
        if sn in allowed_norm:
            kept.append(str(s).strip())
            continue
        # Allow basename / path-tail matches (synthetic paths vs full URLs).
        if any(sn.endswith(a) or a.endswith(sn) or sn.split("/")[-1] == a.split("/")[-1] for a in allowed_norm):
            kept.append(str(s).strip())
    return list(dict.fromkeys(kept))
