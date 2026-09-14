"""XML renderer -- xml.etree.ElementTree, escaping handled by the library."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from xml.dom import minidom

from prism.core.answer import CanonicalAnswer


def render(answer: CanonicalAnswer) -> str:
    root = ET.Element("prismAnswer")
    ET.SubElement(root, "query").text = answer.query
    ET.SubElement(root, "domain").text = answer.domain
    ET.SubElement(root, "confidence").text = answer.confidence
    ET.SubElement(root, "noAnswer").text = str(answer.no_answer).lower()
    ET.SubElement(root, "directAnswer").text = answer.direct_answer

    facts_el = ET.SubElement(root, "keyFacts")
    for kf in answer.key_facts:
        fact_el = ET.SubElement(facts_el, "fact")
        ET.SubElement(fact_el, "label").text = kf.label
        ET.SubElement(fact_el, "value").text = kf.value
        if kf.unit:
            ET.SubElement(fact_el, "unit").text = kf.unit
        if kf.source_id:
            ET.SubElement(fact_el, "sourceId").text = kf.source_id

    steps_el = ET.SubElement(root, "steps")
    for i, step in enumerate(answer.steps, 1):
        step_el = ET.SubElement(steps_el, "step")
        step_el.set("number", str(i))
        step_el.text = step

    if answer.table:
        table_el = ET.SubElement(root, "table")
        cols_el = ET.SubElement(table_el, "columns")
        for c in answer.table.columns:
            ET.SubElement(cols_el, "column").text = c
        rows_el = ET.SubElement(table_el, "rows")
        for row in answer.table.rows:
            row_el = ET.SubElement(rows_el, "row")
            for cell in row:
                ET.SubElement(row_el, "cell").text = cell

    caveats_el = ET.SubElement(root, "caveats")
    for c in answer.caveats:
        ET.SubElement(caveats_el, "caveat").text = c

    sources_el = ET.SubElement(root, "sources")
    for s in answer.sources:
        ET.SubElement(sources_el, "source").text = s

    if answer.sustainability_note:
        ET.SubElement(root, "sustainabilityNote").text = answer.sustainability_note

    rough = ET.tostring(root, encoding="unicode")
    return minidom.parseString(rough).toprettyxml(indent="  ").strip()
