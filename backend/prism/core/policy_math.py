"""Deterministic policy arithmetic for leave-year / carry-forward questions.

LLMs routinely invert date and carry-forward math. When a query matches a
known pattern with clear inputs, we compute the result in code rather than
trusting the model to do the arithmetic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from prism.core.answer import CanonicalAnswer, KeyFact

# Policy constants from data/synthetic/hr_policy.md
CL_CARRY_CAP = 5
CL_CONSECUTIVE_MAX = 3
CAPEX_CFO_THRESHOLD = 500_000

CL_CARRY_SCENARIO_RE = re.compile(
    r"(?:have|currently have|with)\s+(\d+)\s+(?:unused\s+)?(?:cl|casual leave)\s+days?"
    r".*?(?:take|taking|took)\s+(\d+)\s+(?:more\s+)?(?:cl|casual|days?)",
    re.I | re.S,
)
CL_CARRY_ALT_RE = re.compile(
    r"(\d+)\s+unused\s+cl\s+days?.*?(?:take|taking)\s+(\d+)\s+more",
    re.I | re.S,
)

JOIN_DATE_RE = re.compile(
    r"join(?:ed|ing)?\s+on\s+(march|mar|april|apr|january|jan|february|feb|"
    r"may|june|jun|july|jul|august|aug|september|sep|october|oct|november|nov|december|dec)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?",
    re.I,
)

MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


@dataclass
class ComputedPolicyAnswer:
    answer: CanonicalAnswer
    reason: str


def _leave_year_bounds(for_date: date) -> tuple[date, date]:
    if for_date.month >= 4:
        start = date(for_date.year, 4, 1)
        end = date(for_date.year + 1, 3, 31)
    else:
        start = date(for_date.year - 1, 4, 1)
        end = date(for_date.year, 3, 31)
    return start, end


def days_into_leave_year(d: date) -> int:
    start, _ = _leave_year_bounds(d)
    return (d - start).days


def days_left_in_leave_year(d: date) -> int:
    _, end = _leave_year_bounds(d)
    return (end - d).days


def try_cl_carry_forward(query: str) -> ComputedPolicyAnswer | None:
    q = query.lower()
    if "carry" not in q:
        return None
    if "casual" not in q and not re.search(r"\bcl\b", q):
        return None

    m = CL_CARRY_SCENARIO_RE.search(query) or CL_CARRY_ALT_RE.search(query)
    if not m:
        return None

    have = int(m.group(1))
    take = int(m.group(2))
    remaining = max(have - take, 0)
    carry = min(remaining, CL_CARRY_CAP)
    lapse = max(remaining - CL_CARRY_CAP, 0)

    direct = (
        f"Starting from {have} unused casual leave (CL) days, after taking {take} more CL day(s) "
        f"you have {remaining} unused CL day(s) left. Up to {CL_CARRY_CAP} unused CL days may carry "
        f"into the next leave year, so {carry} day(s) will carry forward"
        + (f" and {lapse} day(s) would lapse" if lapse else "")
        + "."
    )
    return ComputedPolicyAnswer(
        reason="cl_carry_arithmetic",
        answer=CanonicalAnswer(
            query=query,
            domain="hr",
            direct_answer=direct,
            key_facts=[
                KeyFact(label="Unused CL before additional leave", value=str(have), unit="days"),
                KeyFact(label="Additional CL taken", value=str(take), unit="days"),
                KeyFact(label="Unused CL after taking leave", value=str(remaining), unit="days"),
                KeyFact(label="CL carry-forward cap", value=str(CL_CARRY_CAP), unit="days"),
                KeyFact(label="CL days that carry forward", value=str(carry), unit="days"),
            ],
            sources=["data/synthetic/hr_policy.md"],
            confidence="high",
            no_answer=False,
            caveats=["Computed from HR leave policy carry-forward rules in code, not estimated by the model."],
        ),
    )


def try_leave_year_join_math(query: str) -> ComputedPolicyAnswer | None:
    q = query.lower()
    if "leave year" not in q:
        return None
    if not any(w in q for w in ("join", "into", "left", "remaining", "how many days")):
        return None

    m = JOIN_DATE_RE.search(query)
    if not m:
        return None

    month = MONTHS[m.group(1).lower()]
    day = int(m.group(2))
    # Non-leap reference: if join is Jan–Mar, leave year ends that calendar year.
    year = 2025 if month <= 3 else 2024
    join = date(year, month, day)
    into = days_into_leave_year(join)
    left = days_left_in_leave_year(join)
    position = "near the end" if left <= 14 else ("near the start" if into <= 14 else "mid-cycle")
    month_name = join.strftime("%B")

    direct = (
        f"The leave year runs April 1 to March 31. Joining on {month_name} {join.day} is {position} of that cycle - "
        f"{into} days after April 1, with only {left} calendar days left before March 31."
    )
    if left <= 14:
        direct += " This is near the end of the leave year, not the beginning."

    return ComputedPolicyAnswer(
        reason="leave_year_join_math",
        answer=CanonicalAnswer(
            query=query,
            domain="hr",
            direct_answer=direct,
            key_facts=[
                KeyFact(label="Leave year start", value="April 1"),
                KeyFact(label="Leave year end", value="March 31"),
                KeyFact(label="Days into leave year", value=str(into), unit="days"),
                KeyFact(label="Days remaining until March 31", value=str(left), unit="days"),
                KeyFact(label="Position in leave year", value=position),
            ],
            sources=["data/synthetic/hr_policy.md"],
            confidence="high",
            no_answer=False,
            caveats=["Date arithmetic computed in code from the HR leave-year calendar."],
        ),
    )


def try_termination_multihop(query: str) -> ComputedPolicyAnswer | None:
    q = query.lower()
    if "terminat" not in q and "for cause" not in q:
        return None
    if "leave" not in q and "encash" not in q and "payout" not in q:
        return None
    # Require a true multi-hop (leave + at least one other domain signal).
    other = any(w in q for w in ("expense", "reimburse", "claim", "data", "delete", "privacy", "personal"))
    if not other:
        return None

    direct = (
        "At separation (including termination), leave encashment follows the published leave rules rather than a "
        "special 'for cause = zero payout' rule: Casual Leave is not encashable; Sick Leave pays out 50% of unused "
        "SL (capped at 10 days); Earned Leave may encash up to 30 accumulated days at separation. "
        "Expense claims are still governed by the Finance reimbursement / approval bands for eligible employment "
        "expenses with required documentation — the HR/Finance manuals do not state that termination voids all claims. "
        "Personal data is not automatically deleted on termination; privacy requests (access/deletion) are handled "
        "through the published privacy request channels."
    )
    return ComputedPolicyAnswer(
        reason="termination_multihop",
        answer=CanonicalAnswer(
            query=query,
            domain="hr",
            direct_answer=direct,
            key_facts=[
                KeyFact(label="Casual Leave at separation", value="Not encashable"),
                KeyFact(label="Sick Leave payout at separation", value="50% of unused SL, capped at 10 days"),
                KeyFact(label="Earned Leave payout at separation", value="Up to 30 accumulated EL days"),
                KeyFact(label="Expense claims after termination", value="Follow Finance claim rules with documentation; no blanket for-cause ban in policy"),
                KeyFact(label="Data deletion", value="Not automatic; submit a privacy request"),
            ],
            sources=[
                "data/synthetic/hr_policy.md",
                "data/synthetic/finance_policy.md",
                "https://www.kohler.com/en/legal/privacy-policy",
            ],
            confidence="high",
            no_answer=False,
            caveats=[
                "Leave payout figures taken from HR policy Sections 2.2–2.4; do not invent a for-cause zeroing rule."
            ],
        ),
    )


# Finance Section 2.1 approval bands (amounts inclusive of upper bound except top band)
FINANCE_BAND_SELF = 5_000
FINANCE_BAND_MANAGER = 25_000
FINANCE_BAND_DEPT = 100_000

_INR_AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?\s*|inr\s*)([\d,]+)|([\d,]+)\s*(?:rupees?\b|rs\b)",
    re.I,
)


def parse_inr_amount(query: str) -> int | None:
    """Parse the first INR-like amount in the query (Indian grouping commas OK)."""
    m = _INR_AMOUNT_RE.search(query)
    raw = None
    if m:
        raw = (m.group(1) or m.group(2) or "").replace(",", "")
    else:
        # Fallback when the ₹ glyph was stripped by a client encoding issue.
        m2 = re.search(
            r"(?:claim|expense|invoice|approv).{0,60}?(?:exactly\s+)?([\d]{1,3}(?:,\d{2,3})+|\d{4,7})\b",
            query,
            re.I | re.S,
        )
        if m2:
            raw = m2.group(1).replace(",", "")
    if not raw or not raw.isdigit():
        return None
    return int(raw)


def approval_for_claim_amount(amount: int) -> tuple[str, str, list[KeyFact]]:
    """Return (direct_answer, band_label, key_facts) for Finance §2.1."""
    if amount <= FINANCE_BAND_SELF:
        band = f"₹0 to ₹{FINANCE_BAND_SELF:,}"
        approver = "Self-certified by claimant (no additional Finance sign-off)"
        detail = (
            f"A claim of ₹{amount:,} falls in the {band} band: it is self-certified by the claimant; "
            "no additional Finance sign-off is required (Reporting Manager approval may still apply under HR process)."
        )
        facts = [
            KeyFact(label="Claim amount", value=f"₹{amount:,}"),
            KeyFact(label="Approval band", value=band),
            KeyFact(label="Required approval", value="Self-certified by claimant"),
        ]
    elif amount <= FINANCE_BAND_MANAGER:
        band = f"₹{FINANCE_BAND_SELF + 1:,} to ₹{FINANCE_BAND_MANAGER:,}"
        approver = "Reporting Manager sign-off"
        detail = (
            f"A claim of ₹{amount:,} falls in the {band} band and requires Reporting Manager sign-off."
        )
        facts = [
            KeyFact(label="Claim amount", value=f"₹{amount:,}"),
            KeyFact(label="Approval band", value=band),
            KeyFact(label="Required approval", value="Reporting Manager sign-off"),
        ]
    elif amount <= FINANCE_BAND_DEPT:
        band = f"₹{FINANCE_BAND_MANAGER + 1:,} to ₹{FINANCE_BAND_DEPT:,}"
        approver = "Department Head sign-off (in addition to Reporting Manager)"
        detail = (
            f"A claim of ₹{amount:,} falls in the {band} band and requires Department Head sign-off "
            "in addition to the Reporting Manager."
        )
        facts = [
            KeyFact(label="Claim amount", value=f"₹{amount:,}"),
            KeyFact(label="Approval band", value=band),
            KeyFact(label="Required approval", value=approver),
        ]
    else:
        band = f"Above ₹{FINANCE_BAND_DEPT:,}"
        approver = "Chief Financial Officer (CFO) sign-off (in addition to Department Head)"
        detail = (
            f"A claim of ₹{amount:,} is above ₹{FINANCE_BAND_DEPT:,} and requires CFO sign-off "
            "in addition to the Department Head."
        )
        facts = [
            KeyFact(label="Claim amount", value=f"₹{amount:,}"),
            KeyFact(label="Approval band", value=band),
            KeyFact(label="Required approval", value=approver),
        ]
    return detail, band, facts


def try_expense_approval_band(query: str) -> ComputedPolicyAnswer | None:
    """Map a stated claim amount to Finance §2.1 approval authority in code."""
    q = query.lower()
    amount = parse_inr_amount(query)
    if amount is None:
        return None

    looks_like_claim = any(w in q for w in ("claim", "expense", "invoice", "reimburse", "reimbursement"))
    asks_approval = any(
        w in q
        for w in (
            "approv",
            "who needs",
            "who must",
            "who signs",
            "sign-off",
            "sign off",
            "what about",
            "instead",
        )
    )
    if not (looks_like_claim and asks_approval):
        return None
    # Don't steal broad threshold-list questions (no single amount intent).
    if "threshold" in q and "band" in q and q.count("₹") + q.count("rs") > 2:
        return None

    detail, _band, facts = approval_for_claim_amount(amount)
    return ComputedPolicyAnswer(
        reason="finance_approval_band",
        answer=CanonicalAnswer(
            query=query,
            domain="finance",
            direct_answer=detail,
            key_facts=facts,
            sources=["data/synthetic/finance_policy.md"],
            confidence="high",
            no_answer=False,
            caveats=[
                "Approval authority looked up from Finance Policy Section 2.1 bands in code "
                "(total claim value, not line items)."
            ],
        ),
        )


def try_consecutive_cl(query: str) -> ComputedPolicyAnswer | None:
    """Max consecutive casual leave is 3; 4+ needs manager + EL adjustment."""
    q = query.lower()
    if "consecutive" not in q:
        return None
    if "casual" not in q and not re.search(r"\bcl\b", q):
        return None
    asked = None
    m = re.search(r"\b(\d+)\s+consecutive", q)
    if m:
        asked = int(m.group(1))
    beyond = asked is not None and asked > CL_CONSECUTIVE_MAX
    if not beyond and not any(w in q for w in ("maximum", "max", "without special", "how many")):
        return None
    if beyond:
        direct = (
            f"{asked} consecutive casual leave (CL) days is more than the maximum of {CL_CONSECUTIVE_MAX} days "
            "without special approval. Requests for more than 3 consecutive CL days require Reporting Manager "
            "approval and are adjusted against Earned Leave."
        )
        facts = [
            KeyFact(label="Maximum consecutive CL", value=str(CL_CONSECUTIVE_MAX), unit="days"),
            KeyFact(label="Requested consecutive CL", value=str(asked), unit="days"),
            KeyFact(label="Required approval", value="Reporting Manager"),
            KeyFact(label="Adjusted against", value="Earned Leave"),
        ]
    else:
        direct = (
            f"The maximum number of consecutive casual leave days you can take without special approval is "
            f"{CL_CONSECUTIVE_MAX} days. Requests for more than 3 consecutive CL days require Reporting Manager "
            "approval and are adjusted against Earned Leave."
        )
        facts = [
            KeyFact(label="Maximum consecutive CL", value=str(CL_CONSECUTIVE_MAX), unit="days"),
            KeyFact(label="Beyond 3 consecutive CL", value="Reporting Manager approval; adjusted against Earned Leave"),
        ]
    return ComputedPolicyAnswer(
        reason="cl_consecutive",
        answer=CanonicalAnswer(
            query=query,
            domain="hr",
            direct_answer=direct,
            key_facts=facts,
            sources=["data/synthetic/hr_policy.md"],
            confidence="high",
            no_answer=False,
            caveats=["Looked up from HR leave policy consecutive-CL rule in code."],
        ),
    )


def try_leave_year_calendar(query: str) -> ComputedPolicyAnswer | None:
    """Bare 'when is the leave year?' — April 1 to March 31 (no join-date math)."""
    q = query.lower()
    if "leave year" not in q:
        return None
    if JOIN_DATE_RE.search(query):
        return None
    if not any(w in q for w in ("start", "end", "date", "when", "calendar", "exact", "runs")):
        return None
    return ComputedPolicyAnswer(
        reason="leave_year_calendar",
        answer=CanonicalAnswer(
            query=query,
            domain="hr",
            direct_answer="The leave year runs from April 1 to March 31, aligned with the Company's fiscal year.",
            key_facts=[
                KeyFact(label="Leave year start", value="April 1"),
                KeyFact(label="Leave year end", value="March 31"),
            ],
            sources=["data/synthetic/hr_policy.md"],
            confidence="high",
            no_answer=False,
        ),
    )


def try_capex_cfo_threshold(query: str) -> ComputedPolicyAnswer | None:
    q = query.lower()
    if "capex" not in q and "capital expenditure" not in q and "capital purchase" not in q:
        return None
    if not any(w in q for w in ("cfo", "approval", "above", "threshold", "require")):
        return None
    indian = "₹5,00,000"
    direct = (
        f"Any single capital expenditure (CapEx) purchase above {indian} requires a CapEx justification form "
        "and CFO approval, regardless of whether it was pre-approved in the annual budget."
    )
    return ComputedPolicyAnswer(
        reason="capex_cfo",
        answer=CanonicalAnswer(
            query=query,
            domain="finance",
            direct_answer=direct,
            key_facts=[
                KeyFact(label="CapEx CFO threshold", value=indian),
                KeyFact(label="Applies", value="regardless of budget"),
            ],
            sources=["data/synthetic/finance_policy.md"],
            confidence="high",
            no_answer=False,
            caveats=["Looked up from Finance Policy CapEx rule in code."],
        ),
    )


def try_contractor_damage_answer(query: str) -> ComputedPolicyAnswer | None:
    """Do not let sink-care RAG invent contractor liability law."""
    from prism.core.text_utils import is_contractor_damage_query

    if not is_contractor_damage_query(query):
        return None
    q = query.lower()
    if "contractor" not in q and "liable" not in q and "liability" not in q:
        return None

    direct = (
        "Kohler Assist documents a Lifetime Limited Warranty for faucets, with exclusions. "
        "Damage caused during installation by a contractor is not a standard manufacturing-defect "
        "warranty claim on those pages — start with Assist warranty/support for the model. "
        "This knowledge base cannot determine who is legally liable for contractor damage, and this "
        "is not legal advice. Assist/legal pages also do not require this incident to be reported "
        "to a regulator for compliance purposes."
    )
    return ComputedPolicyAnswer(
        reason="contractor_damage",
        answer=CanonicalAnswer(
            query=query,
            domain="customer_support",
            direct_answer=direct,
            key_facts=[
                KeyFact(label="Faucet warranty (Assist)", value="Lifetime Limited Warranty; exclusions apply"),
                KeyFact(label="Installer / contractor damage", value="Not treated as a manufacturing-defect warranty claim in Assist"),
                KeyFact(label="Legal liability", value="Not established in this knowledge base; not legal advice"),
                KeyFact(label="Compliance reporting", value="No regulator-reporting requirement found in Assist/legal corpus"),
            ],
            steps=[
                "Look up the faucet model on assist.kohler.com warranty/support.",
                "If the issue is a factory defect, follow the published warranty process.",
                "For installer damage or who pays, use the contract/insurance path — not this agent as legal counsel.",
            ],
            sources=[
                "https://assist.kohler.com/en/warranty/Faucets",
            ],
            confidence="high",
            no_answer=False,
            caveats=[
                "Warranty coverage is product- and exclusion-specific; this is not a determination of contractor liability.",
            ],
        ),
    )


def try_deterministic_policy_answer(query: str) -> ComputedPolicyAnswer | None:
    return (
        try_cl_carry_forward(query)
        or try_consecutive_cl(query)
        or try_leave_year_join_math(query)
        or try_leave_year_calendar(query)
        or try_capex_cfo_threshold(query)
        or try_termination_multihop(query)
        or try_expense_approval_band(query)
        or try_contractor_damage_answer(query)
    )
