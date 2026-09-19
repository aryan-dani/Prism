"""Deterministic water-waste estimates for Customer Support leak/drip answers.

Same idea as `policy_math.py`: published numbers in code, not an LLM call.
Assumptions are EPA WaterSense / EPA "Fix a Leak" figures, cited in the note
so the user (and judges) can see the conversion is not invented by the model.

Sources (public, US customary → liters):
  - Dripping faucet at ~1 drip/second: more than 3,000 gallons/year
    (EPA WaterSense). 3,000 gal/yr ≈ 11,356 L/yr ≈ 31 L/day ≈ 940 L/month.
  - Continuously running toilet: about 200 gallons/day
    (EPA "Fix a Leak Week"). 200 gal/day ≈ 757 L/day ≈ 23,000 L/month.

These are order-of-magnitude estimates, not a sensor reading. The note is
appended to CanonicalAnswer.sustainability_note and never injected into the
LLM's own text.
"""

from __future__ import annotations

import re

from prism.core.answer import CanonicalAnswer

# EPA WaterSense: 3,000 gallons/year at 1 drip/second.
DRIP_LITERS_PER_DAY = 31
DRIP_LITERS_PER_MONTH = 940
# EPA Fix-a-Leak: ~200 gallons/day for a running toilet.
RUNNING_TOILET_LITERS_PER_DAY = 757
RUNNING_TOILET_LITERS_PER_MONTH = 23_000

_LEAK_RE = re.compile(
    r"\b(leak|leaking|drip|dripping|running toilet|toilet (?:is |keeps )?running|"
    r"water running|constantly running|sporadically running)\b",
    re.I,
)
_TOILET_RE = re.compile(r"\b(toilet|flapper|fill valve|flush valve|canister seal)\b", re.I)
_FAUCET_RE = re.compile(r"\b(faucet|tap|spout|aerator|showerhead|shower)\b", re.I)


def looks_like_water_waste(query: str, *, domain: str | None, answer: CanonicalAnswer | None = None) -> bool:
    if (domain or (answer.domain if answer else "") or "") != "customer_support":
        return False
    blob = " ".join(
        p
        for p in (
            query,
            (answer.direct_answer if answer else ""),
            " ".join(answer.steps) if answer and answer.steps else "",
        )
        if p
    )
    return bool(_LEAK_RE.search(blob))


def sustainability_note_for(query: str, *, domain: str | None, answer: CanonicalAnswer) -> str | None:
    if answer.no_answer:
        return None
    if not looks_like_water_waste(query, domain=domain, answer=answer):
        return None
    blob = f"{query} {answer.direct_answer}"
    if _TOILET_RE.search(blob) and not _FAUCET_RE.search(blob):
        return (
            "Water conservation estimate (EPA Fix a Leak, not a meter reading): "
            f"a continuously running toilet can waste about {RUNNING_TOILET_LITERS_PER_DAY:,} L/day "
            f"(~{RUNNING_TOILET_LITERS_PER_MONTH:,} L/month). Fixing it is both a support issue and a "
            "measurable water-saving action."
        )
    return (
        "Water conservation estimate (EPA WaterSense, not a meter reading): "
        f"a faucet dripping at ~1 drip/second can waste about {DRIP_LITERS_PER_DAY} L/day "
        f"(~{DRIP_LITERS_PER_MONTH} L/month, ~3,000 gallons/year). Repairing the drip cuts that waste."
    )


def attach_sustainability_note(answer: CanonicalAnswer, *, query: str, domain: str | None) -> CanonicalAnswer:
    """Fill sustainability_note in-place when the CS answer is about a leak/drip."""
    if answer.sustainability_note:
        return answer
    note = sustainability_note_for(query, domain=domain or answer.domain, answer=answer)
    if note:
        answer.sustainability_note = note
    return answer
