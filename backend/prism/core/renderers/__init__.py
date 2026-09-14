"""Renderer dispatch -- every format is a pure function over the same
CanonicalAnswer object (Piece 8). No retrieval, no LLM call (except the
optional email polish pass), when reformatting a previous answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from prism.core.answer import CanonicalAnswer
from prism.core.renderers import excel as excel_renderer
from prism.core.renderers import email as email_renderer
from prism.core.renderers import json_ as json_renderer
from prism.core.renderers import prose as prose_renderer
from prism.core.renderers import xml_ as xml_renderer

FormatName = Literal["prose", "json", "xml", "excel", "email"]

ALL_FORMATS: list[FormatName] = ["prose", "json", "xml", "excel", "email"]


@dataclass
class RenderResult:
    format: FormatName
    content: str | bytes
    mime_type: str
    is_binary: bool = False
    filename: str | None = None


def available_formats(answer: CanonicalAnswer) -> list[FormatName]:
    """Formats that make sense for this particular answer (Excel is gated on
    the answer actually being tabular/multi-fact, per the Phase 2 quality bar)."""
    formats: list[FormatName] = ["prose", "json", "xml", "email"]
    if excel_renderer.can_render(answer):
        formats.append("excel")
    return formats


def render(answer: CanonicalAnswer, fmt: FormatName, **kwargs) -> RenderResult:
    if fmt == "prose":
        return RenderResult(format=fmt, content=prose_renderer.render(answer), mime_type="text/plain")
    if fmt == "json":
        return RenderResult(format=fmt, content=json_renderer.render(answer), mime_type="application/json")
    if fmt == "xml":
        return RenderResult(format=fmt, content=xml_renderer.render(answer), mime_type="application/xml")
    if fmt == "email":
        return RenderResult(
            format=fmt,
            content=email_renderer.render(answer, **kwargs),
            mime_type="text/plain",
        )
    if fmt == "excel":
        if not excel_renderer.can_render(answer):
            raise ValueError("This answer isn't tabular/detailed enough for an Excel export.")
        return RenderResult(
            format=fmt,
            content=excel_renderer.render(answer),
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            is_binary=True,
            filename="prism_answer.xlsx",
        )
    raise ValueError(f"Unknown format: {fmt}")
