"""Per-domain fact diagnosis for the golden set: *why* does an expected fact miss?

Run: uv run python -m eval.diagnose_facts
     $env:PRISM_DIAG_DOMAINS="finance,hr"   # optional filter
     $env:PRISM_DIAG_AGENT="0"               # skip the full handle_turn pass

For every single-turn golden question this runs the same retrieve + generate
path as `bench_models.py`, plus (for HR / Finance) the full agent `handle_turn`
so deterministic guards (policy_math) are measured too. Each expected fact is
classified so the fix is obvious instead of guessed:

    RETRIEVAL_MISS  the fact's numbers are not in the retrieved context
                    -> patch the synthetic policy markdown / rebuild index
    GEN_MISS        numbers in context but not in the answer
                    -> model didn't surface them; prompt/agent territory
    PHRASING        numbers present in the answer, exact phrase is not
                    -> scorer artifact ("₹5,001 to ₹25,000" vs "₹5,001 – ₹25,000")
    PASS            exact phrase present

Writes eval/results/fact_diagnosis.{json,md}. Read-only w.r.t. the agent.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict

from prism.core.answer import generate_answer, no_context_answer
from prism.core.config import EVAL_DIR
from prism.core.retriever import retrieve
from prism.core.text_utils import filter_cross_jurisdiction_chunks

GOLDEN_PATH = EVAL_DIR / "golden.jsonl"
RESULTS_DIR = EVAL_DIR / "results"

AGENT_DOMAINS = {"hr", "finance"}

_NUM_RE = re.compile(r"\d[\d,\.]*")
_WORD_RE = re.compile(r"[a-z]{3,}")


def _digits(s: str) -> list[str]:
    """Numeric tokens with separators stripped: '₹5,001 – ₹25,000' -> ['5001', '25000']."""
    out = []
    for m in _NUM_RE.findall(s):
        d = m.replace(",", "").rstrip(".")
        if d.replace(".", "").isdigit():
            out.append(d)
    return out


def _norm(s: str) -> str:
    s = s.lower().replace("₹", " ").replace("rs.", " ").replace("inr", " ")
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def fact_present_exact(text: str, fact: str) -> bool:
    return _norm(fact) in _norm(text)


def fact_present_loose(text: str, fact: str) -> bool:
    """Numbers (if any) must all appear; otherwise >= 60% of content words."""
    t = _norm(text)
    nums = _digits(fact)
    if nums:
        t_nums = set(_digits(t))
        return all(n in t_nums for n in nums)
    words = _WORD_RE.findall(_norm(fact))
    if not words:
        return _norm(fact) in t
    hits = sum(1 for w in words if w in t)
    return hits / len(words) >= 0.6


def classify(fact: str, *, context: str, answer_text: str) -> str:
    if fact_present_exact(answer_text, fact):
        return "PASS"
    if not fact_present_loose(context, fact):
        return "RETRIEVAL_MISS"
    if not fact_present_loose(answer_text, fact):
        return "GEN_MISS"
    return "PHRASING"


def answer_text_of(answer) -> str:
    parts = [answer.direct_answer]
    parts += [f"{kf.label} {kf.value} {kf.unit or ''}" for kf in answer.key_facts]
    parts += list(answer.steps or [])
    if answer.table:
        parts += [" ".join(answer.table.columns)]
        parts += [" ".join(r) for r in answer.table.rows]
    return " ".join(p for p in parts if p)


def load_golden() -> list[dict]:
    records = []
    with GOLDEN_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return [r for r in records if r.get("type") == "single_turn"]


def run_agent(query: str):
    from prism.core.agent import handle_turn
    from prism.core.memory import SessionState

    session = SessionState(session_id=f"diag-{int(time.time() * 1000)}")
    result = handle_turn(session, query)
    return result.answer, result.domain


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    domains_filter = {
        d.strip() for d in os.environ.get("PRISM_DIAG_DOMAINS", "").split(",") if d.strip()
    }
    use_agent = os.environ.get("PRISM_DIAG_AGENT", "1") != "0"

    records = load_golden()
    if domains_filter:
        records = [r for r in records if r["domain"] in domains_filter]
    print(f"Diagnosing {len(records)} golden questions...")

    rows: list[dict] = []
    for i, q in enumerate(records, 1):
        domain, query = q["domain"], q["query"]
        print(f"  [{i}/{len(records)}] {q['id']} ({domain})", flush=True)

        result = retrieve(query, role="general_employee", domain=domain)
        result.chunks = filter_cross_jurisdiction_chunks(query, result.chunks)
        context = "\n".join(c.text for c in result.chunks)

        if not result.chunks or not result.is_confident:
            bench_answer = no_context_answer(query, domain)
        else:
            bench_answer = generate_answer(query, domain=domain, context_chunks=result.chunks)
        bench_text = answer_text_of(bench_answer)

        agent_text, agent_domain = None, None
        if use_agent and domain in AGENT_DOMAINS and not q.get("expected_no_answer"):
            try:
                a, agent_domain = run_agent(query)
                agent_text = answer_text_of(a) if a else ""
            except Exception as e:  # keep diagnosing
                agent_text = f"(agent error: {e})"

        row = {
            "id": q["id"],
            "domain": domain,
            "query": query,
            "retrieval_confident": result.is_confident,
            "best_dense_distance": result.best_dense_distance,
            "bench_no_answer": bench_answer.no_answer,
            "agent_domain": agent_domain,
            "facts": [],
        }

        if q.get("expected_no_answer"):
            row["expected_no_answer"] = True
            row["honesty_ok"] = bool(bench_answer.no_answer)
        else:
            for fact in q.get("expected_facts", []):
                entry = {
                    "fact": fact,
                    "bench": classify(fact, context=context, answer_text=bench_text),
                    "in_context_loose": fact_present_loose(context, fact),
                }
                if agent_text is not None:
                    entry["agent"] = classify(fact, context=context, answer_text=agent_text)
                row["facts"].append(entry)
        row["bench_answer"] = bench_text[:600]
        if agent_text is not None:
            row["agent_answer"] = agent_text[:600]
        rows.append(row)

    # ---- aggregate -------------------------------------------------------
    by_domain: dict[str, Counter] = defaultdict(Counter)
    by_domain_agent: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        for f in r["facts"]:
            by_domain[r["domain"]][f["bench"]] += 1
            if "agent" in f:
                by_domain_agent[r["domain"]][f["agent"]] += 1

    def rate(c: Counter, key: str) -> str:
        total = sum(c.values())
        return f"{c[key] / total:.0%}" if total else "n/a"

    def loose_rate(c: Counter) -> str:
        total = sum(c.values())
        return f"{(c['PASS'] + c['PHRASING']) / total:.0%}" if total else "n/a"

    lines = [
        "# Golden-set fact diagnosis (per domain)",
        "",
        "Exact = bench scorer phrase match. Loose = all numbers (or most content words) present.",
        "Classes: PASS / PHRASING (scorer artifact) / GEN_MISS (in context, not in answer) / RETRIEVAL_MISS (not in context).",
        "",
        "## Bench path (retrieve + generate, no agent guards)",
        "",
        "| Domain | Facts | Exact | Loose | PHRASING | GEN_MISS | RETRIEVAL_MISS |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for d in sorted(by_domain):
        c = by_domain[d]
        lines.append(
            f"| {d} | {sum(c.values())} | {rate(c, 'PASS')} | {loose_rate(c)} | "
            f"{c['PHRASING']} | {c['GEN_MISS']} | {c['RETRIEVAL_MISS']} |"
        )
    if by_domain_agent:
        lines += [
            "",
            "## Agent path (`handle_turn`, incl. policy_math) — HR / Finance only",
            "",
            "| Domain | Facts | Exact | Loose | PHRASING | GEN_MISS | RETRIEVAL_MISS |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for d in sorted(by_domain_agent):
            c = by_domain_agent[d]
            lines.append(
                f"| {d} | {sum(c.values())} | {rate(c, 'PASS')} | {loose_rate(c)} | "
                f"{c['PHRASING']} | {c['GEN_MISS']} | {c['RETRIEVAL_MISS']} |"
            )

    lines += ["", "## Per-fact misses (anything not PASS on the bench path)", ""]
    for r in rows:
        misses = [f for f in r["facts"] if f["bench"] != "PASS"]
        if r.get("expected_no_answer"):
            lines.append(f"- `{r['id']}` ({r['domain']}) expected no-answer → honesty_ok={r['honesty_ok']}")
            continue
        if not misses:
            continue
        lines.append(f"### `{r['id']}` ({r['domain']}) — {r['query']}")
        lines.append(
            f"- retrieval confident={r['retrieval_confident']} dist={r['best_dense_distance']}"
            + (f" · agent_domain={r['agent_domain']}" if r.get("agent_domain") else "")
        )
        for f in misses:
            agent = f" · agent={f['agent']}" if "agent" in f else ""
            lines.append(f"- **{f['bench']}**{agent} — `{f['fact']}`")
        lines.append(f"- bench answer: {r['bench_answer'][:300]}")
        if r.get("agent_answer"):
            lines.append(f"- agent answer: {r['agent_answer'][:300]}")
        lines.append("")

    md = "\n".join(lines)
    (RESULTS_DIR / "fact_diagnosis.md").write_text(md, encoding="utf-8")
    with (RESULTS_DIR / "fact_diagnosis.json").open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    print("\n" + md)
    print(f"\nWrote {RESULTS_DIR / 'fact_diagnosis.md'}")


if __name__ == "__main__":
    main()
