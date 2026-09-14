"""Phase 1 quality gate: sample and hand-review chunks from every domain
before Phase 2 is allowed to start (per the plan's "don't start Phase 2
until Phase 1's knowledge base is genuinely solid" rule).

Run: uv run python -m prism.ingest.validate

For each domain, samples up to 20 random records and writes a Markdown
report to eval/results/validation_<domain>.md with:
    - required-field fill-rates (title/source_url/text non-empty, etc.)
    - domain-specific heuristics (e.g. customer_support records with a
      troubleshooting type should usually have non-empty corrective_actions;
      finance/hr chunks should contain at least one heading in their title)
    - the sampled records themselves, for a human to actually read and catch
      parser bugs a fill-rate check alone would miss.

This does not "pass/fail" automatically -- it surfaces the sample for human
review, per the brief's explicit instruction not to just eyeball 2-3 records.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from prism.core.config import DOMAINS, EVAL_DIR, PROCESSED_DIR

SAMPLE_SIZE = 20


def load_domain_records(domain: str) -> list[dict]:
    records: list[dict] = []
    for path in sorted(PROCESSED_DIR.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                all_domains = {rec["domain"], *(rec.get("also_domains") or [])}
                if domain in all_domains:
                    records.append(rec)
    return records


def _nonempty(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return len(v) > 0
    return True


def fill_rates(records: list[dict], fields: list[str]) -> dict[str, float]:
    n = len(records) or 1
    return {f: sum(1 for r in records if _nonempty(r.get(f))) / n for f in fields}


def domain_specific_checks(domain: str, records: list[dict]) -> list[str]:
    notes: list[str] = []
    if domain == "customer_support":
        troubleshooting = [r for r in records if r.get("type") == "troubleshooting"]
        if troubleshooting:
            rate = fill_rates(troubleshooting, ["corrective_actions", "issue_description"])
            notes.append(
                f"troubleshooting records ({len(troubleshooting)}): "
                f"corrective_actions filled {rate['corrective_actions']:.0%}, "
                f"issue_description filled {rate['issue_description']:.0%}"
            )
        videos = [r for r in records if r.get("type") == "video"]
        notes.append(f"video-type records: {len(videos)} (lighter schema expected, not a failure if causes/actions are empty)")
        with_models = sum(1 for r in records if r.get("models_mentioned"))
        notes.append(f"records with at least one models_mentioned hit: {with_models}/{len(records)}")
    elif domain in ("privacy", "legal"):
        with_heading = sum(1 for r in records if r.get("heading_path"))
        notes.append(f"records with a non-empty heading_path (chunked along real section boundaries): {with_heading}/{len(records)}")
        short = [r for r in records if len(r.get("text", "")) < 60]
        notes.append(f"suspiciously short chunks (<60 chars, possible parser noise): {len(short)}")
    elif domain in ("hr", "finance"):
        with_numbers = sum(1 for r in records if any(ch.isdigit() for ch in r.get("text", "")))
        notes.append(f"records containing at least one digit (policy figures/thresholds): {with_numbers}/{len(records)}")
        synthetic = sum(1 for r in records if r.get("is_synthetic"))
        notes.append(f"is_synthetic=True: {synthetic}/{len(records)} (should be ALL of them)")
    return notes


def render_report(domain: str, records: list[dict], sample: list[dict]) -> str:
    lines = [f"# Validation report: {domain}", "", f"Total chunks in this domain: {len(records)}", ""]

    by_type = Counter(r.get("type", "?") for r in records)
    by_category = Counter(str(r.get("category", "?")) for r in records)
    lines.append(f"By type: {dict(by_type)}")
    lines.append(f"By category: {dict(by_category)}")
    lines.append("")

    rates = fill_rates(records, ["title", "source_url", "text", "type"])
    lines.append("## Required-field fill rates")
    for k, v in rates.items():
        lines.append(f"- `{k}`: {v:.0%}")
    lines.append("")

    lines.append("## Domain-specific checks")
    for note in domain_specific_checks(domain, records):
        lines.append(f"- {note}")
    lines.append("")

    lines.append(f"## Hand-review sample (n={len(sample)}, random seed=42)")
    lines.append("")
    for i, r in enumerate(sample, 1):
        lines.append(f"### Sample {i}: {r.get('title', '(no title)')}")
        lines.append(f"- id: `{r.get('id')}`")
        lines.append(f"- source_url: {r.get('source_url')}")
        lines.append(f"- type: {r.get('type')} | category: {r.get('category')} | also_domains: {r.get('also_domains')}")
        if r.get("heading_path"):
            lines.append(f"- heading_path: {r.get('heading_path')}")
        if r.get("models_mentioned"):
            lines.append(f"- models_mentioned: {r.get('models_mentioned')}")
        if r.get("causes"):
            lines.append(f"- causes: {r.get('causes')}")
        if r.get("corrective_actions"):
            lines.append(f"- corrective_actions: {r.get('corrective_actions')}")
        text = r.get("text", "")
        preview = text[:500] + ("..." if len(text) > 500 else "")
        lines.append("")
        lines.append("```")
        lines.append(preview)
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    results_dir = EVAL_DIR / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    random.seed(42)

    summary_lines = ["# Phase 1 validation summary", ""]

    for domain in DOMAINS:
        records = load_domain_records(domain)
        if not records:
            summary_lines.append(f"- **{domain}**: 0 chunks found -- run the ingest script for this domain first.")
            continue
        sample = random.sample(records, min(SAMPLE_SIZE, len(records)))
        report = render_report(domain, records, sample)
        out_path = results_dir / f"validation_{domain}.md"
        out_path.write_text(report, encoding="utf-8")
        summary_lines.append(f"- **{domain}**: {len(records)} chunks, sampled {len(sample)} for hand review -> `{out_path.relative_to(Path.cwd()) if out_path.is_absolute() else out_path}`")
        print(f"[validate] {domain}: {len(records)} chunks -> {out_path}")

    (results_dir / "validation_summary.md").write_text("\n".join(summary_lines), encoding="utf-8")
    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
