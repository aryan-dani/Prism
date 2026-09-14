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
    if "terminat" not in q and "for cause" not in q and "separation" not in q:
        return None
    if "leave" not in q:
        return None
    if not any(w in q for w in ("expense", "data", "delete", "privacy", "payout", "encash")):
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


def try_deterministic_policy_answer(query: str) -> ComputedPolicyAnswer | None:
    return (
        try_cl_carry_forward(query)
        or try_leave_year_join_math(query)
        or try_termination_multihop(query)
    )
