"""JSON renderer -- validated before returning (round-trips through json.loads)."""

from __future__ import annotations

import json

from prism.core.answer import CanonicalAnswer


def render(answer: CanonicalAnswer) -> str:
    text = answer.model_dump_json(indent=2, exclude_none=True)
    json.loads(text)  # validate: raises if the pydantic serialization ever produced non-parseable output
    return text
