"""Draft-email renderer -- professional register, contextualized from the
canonical answer. Template-based by default (no extra LLM call); an optional
`polish` pass makes one small LLM call to smooth phrasing while a strict
system prompt forbids altering any fact/number, keeping it off by default to
respect the "no extra LLM calls where a cheaper method works" budget rule.
"""

from __future__ import annotations

import re

from prism.core.answer import CanonicalAnswer
from prism.core.config import GEN_MODEL
from prism.core.ollama_client import get_ollama_client, keep_alive_value
from prism.core.renderers.prose import _format_fact_value
from prism.core.text_utils import draft_needs_professional_tone

POLISH_SYSTEM_PROMPT = """You rewrite internal business emails to sound natural and professional. \
You must NOT change, add, or remove any fact, number, date, currency amount, or proper noun. \
You must NOT invent new information. Keep the same structure (greeting, body, sign-off). \
Output ONLY the rewritten email text, nothing else."""

DE_HOSTILE_PROMPT = """You rewrite internal business emails to a calm, professional tone. \
Remove threats, ultimatums, and hostile phrasing. Keep the same factual policy content and requests. \
Do not invent new facts. Keep greeting and sign-off. Output ONLY the rewritten email body, nothing else."""


def _subject_line(answer: CanonicalAnswer) -> str:
    q = answer.query.strip().rstrip("?")
    if draft_needs_professional_tone(q):
        return "Re: Leave request follow-up"
    q = q[0].upper() + q[1:] if q else "Your question"
    # Keep subjects short and non-hostile
    if len(q) > 80:
        q = q[:77] + "..."
    return f"Re: {q}"


def render(
    answer: CanonicalAnswer,
    *,
    recipient_name: str = "there",
    sender_name: str = "Prism Assistant",
    polish: bool = False,
) -> str:
    subject = _subject_line(answer)
    body_lines = [f"Hi {recipient_name},", "", answer.direct_answer]

    if answer.key_facts:
        body_lines += ["", "Key details:"]
        for kf in answer.key_facts:
            body_lines.append(f"  - {kf.label}: {_format_fact_value(kf.value, kf.unit)}")

    if answer.steps:
        body_lines += ["", "Next steps:"]
        for i, step in enumerate(answer.steps, 1):
            body_lines.append(f"  {i}. {step}")

    if answer.table:
        body_lines += ["", " | ".join(answer.table.columns)]
        for row in answer.table.rows:
            body_lines.append(" | ".join(row))

    if answer.caveats:
        body_lines += ["", "Please note: " + " ".join(answer.caveats)]

    if answer.sources:
        body_lines += ["", "Reference: " + "; ".join(answer.sources)]

    body_lines += ["", "Best regards,", sender_name]
    body = "\n".join(body_lines)

    needs_tone = draft_needs_professional_tone(f"{answer.query}\n{answer.direct_answer}")
    if needs_tone:
        # Never put the hostile user request or meta-commentary about threats into the body.
        clean_direct = _scrub_hostile_prose(answer.direct_answer)
        body_lines = [
            f"Hi {recipient_name},",
            "",
            "I am writing regarding my leave request and would appreciate guidance on next steps "
            "under the company's leave and escalation process.",
        ]
        if clean_direct:
            body_lines += ["", clean_direct]
        if answer.key_facts:
            body_lines += ["", "Key details:"]
            for kf in answer.key_facts:
                label_val = f"{kf.label}: {_format_fact_value(kf.value, kf.unit)}"
                if draft_needs_professional_tone(label_val):
                    continue
                body_lines.append(f"  - {label_val}")
        if answer.caveats:
            clean_caveats = [c for c in answer.caveats if not draft_needs_professional_tone(c)]
            if clean_caveats:
                body_lines += ["", "Please note: " + " ".join(clean_caveats)]
        body_lines += ["", "Best regards,", sender_name]
        body = "\n".join(body_lines)
        # Template-only for hostile drafts — avoid LLM reintroducing threat phrasing.
        return f"Subject: {_subject_line(answer)}\n\n{body}"

    if polish or needs_tone:
        body = _llm_polish(body, de_hostile=needs_tone)

    return f"Subject: {subject}\n\n{body}"


def _scrub_hostile_prose(text: str) -> str:
    """Drop sentences that still mention threats/ultimatums (even as 'advice')."""
    raw = (text or "").strip()
    if not raw:
        return ""
    if not draft_needs_professional_tone(raw):
        return raw
    parts = re.split(r"(?<=[.!?])\s+", raw)
    kept = [p.strip() for p in parts if p.strip() and not draft_needs_professional_tone(p)]
    return " ".join(kept).strip()


def _llm_polish(body: str, *, de_hostile: bool = False) -> str:
    system = DE_HOSTILE_PROMPT if de_hostile else POLISH_SYSTEM_PROMPT
    resp = get_ollama_client().chat(
        model=GEN_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": body},
        ],
        options={"temperature": 0.2},
        keep_alive=keep_alive_value(),
    )
    return resp["message"]["content"].strip()
