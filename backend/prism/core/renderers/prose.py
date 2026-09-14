"""Default prose renderer -- pure template composition over CanonicalAnswer, no LLM call."""

from __future__ import annotations

import re

from prism.core.answer import CanonicalAnswer


def _format_fact_value(value: str, unit: str | None) -> str:
    if not unit:
        return value
    if value.lower().endswith(unit.lower()):
        return value
    if re.search(rf"\b{re.escape(unit)}\b", value, re.I):
        return value
    return f"{value} {unit}".strip()


def render(answer: CanonicalAnswer) -> str:
    lines: list[str] = [answer.direct_answer]

    if answer.no_answer and answer.clarification_question:
        lines.append("")
        lines.append(answer.clarification_question)

    if answer.key_facts:
        lines.append("")
        for kf in answer.key_facts:
            lines.append(f"- {kf.label}: {_format_fact_value(kf.value, kf.unit)}")

    if answer.steps:
        lines.append("")
        for i, step in enumerate(answer.steps, 1):
            lines.append(f"{i}. {step}")

    if answer.table:
        lines.append("")
        lines.append(" | ".join(answer.table.columns))
        lines.append(" | ".join("---" for _ in answer.table.columns))
        for row in answer.table.rows:
            lines.append(" | ".join(row))

    if answer.caveats:
        lines.append("")
        lines.append("Note: " + " ".join(answer.caveats))

    if answer.sustainability_note:
        lines.append("")
        lines.append(answer.sustainability_note)

    if answer.sources:
        lines.append("")
        lines.append("Sources: " + ", ".join(answer.sources))

    return "\n".join(lines).strip()
