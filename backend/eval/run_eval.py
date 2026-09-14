"""End-to-end agent evaluation: routing accuracy, retrieval hit-rate, and the
multi-turn behaviors from the golden set (domain switch, anaphora,
clarification, reformat-without-re-retrieval, domain persistence, email
drafting).

Run: uv run python -m eval.run_eval
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from prism.core.agent import handle_turn
from prism.core.config import EVAL_DIR
from prism.core.embeddings import embed_one
from prism.core.memory import SessionState
from prism.core.retriever import retrieve
from prism.core.router import route, score_by_hit_votes

GOLDEN_PATH = EVAL_DIR / "golden.jsonl"
RESULTS_DIR = EVAL_DIR / "results"


def load_golden() -> list[dict]:
    records = []
    with GOLDEN_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def eval_single_turn(records: list[dict]) -> dict:
    single = [r for r in records if r.get("type") == "single_turn"]
    routing_correct = 0
    routing_total = 0
    hit_at_5 = 0
    hit_total = 0
    latencies = []

    for r in single:
        domain = r["domain"]
        query = r["query"]
        t0 = time.monotonic()

        query_embedding = embed_one(query)
        agnostic = retrieve(query, domain=None, top_k=10).chunks
        votes = score_by_hit_votes(agnostic)
        route_result = route(query_embedding, hit_votes=votes)
        latencies.append(time.monotonic() - t0)

        if not r.get("expected_no_answer"):
            routing_total += 1
            if route_result.domain == domain:
                routing_correct += 1

            hit_total += 1
            top5_domains = {c.metadata.get("domain") for c in agnostic[:5]}
            if domain in top5_domains:
                hit_at_5 += 1

    return {
        "routing_accuracy": routing_correct / routing_total if routing_total else None,
        "hit_at_5": hit_at_5 / hit_total if hit_total else None,
        "avg_routing_latency_s": sum(latencies) / len(latencies) if latencies else None,
        "n_single_turn": len(single),
    }


def eval_multi_turn(records: list[dict]) -> list[dict]:
    multi = [r for r in records if r.get("type") == "multi_turn"]
    results = []

    for scenario in multi:
        session = SessionState(session_id=f"eval-{scenario['id']}")
        turn_results = []
        passed = True

        for turn_spec in scenario["turns"]:
            query = turn_spec["query"]
            try:
                result = handle_turn(session, query)
            except Exception as e:
                turn_results.append({"query": query, "error": str(e)})
                passed = False
                continue

            check = {"query": query, "domain": result.domain, "is_clarification": result.is_clarification, "is_reformat": result.is_reformat}

            if "expected_domain" in turn_spec and result.domain != turn_spec["expected_domain"]:
                check["FAIL"] = f"expected domain {turn_spec['expected_domain']}, got {result.domain}"
                passed = False
            if turn_spec.get("expect_clarification") and not result.is_clarification:
                check["FAIL"] = "expected clarification, did not get one"
                passed = False
            if turn_spec.get("is_reformat") and not result.is_reformat:
                check["FAIL"] = "expected a reformat (no re-retrieval), but retrieval ran again"
                passed = False
            if "expected_format" in turn_spec and result.render_result.format != turn_spec["expected_format"]:
                check["FAIL"] = f"expected format {turn_spec['expected_format']}, got {result.render_result.format}"
                passed = False

            turn_results.append(check)

        results.append({"id": scenario["id"], "description": scenario.get("description", ""), "passed": passed, "turns": turn_results})

    return results


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    records = load_golden()

    single_report = eval_single_turn(records)
    multi_report = eval_multi_turn(records)

    n_multi_passed = sum(1 for r in multi_report if r["passed"])

    report = {
        "single_turn": single_report,
        "multi_turn_pass_rate": n_multi_passed / len(multi_report) if multi_report else None,
        "multi_turn_details": multi_report,
    }

    with (RESULTS_DIR / "agent_eval.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    lines = [
        "# Prism Agent Evaluation",
        "",
        "## Single-turn retrieval/routing",
        f"- Routing accuracy: {single_report['routing_accuracy']}",
        f"- Hit@5: {single_report['hit_at_5']}",
        f"- Avg routing latency (s): {single_report['avg_routing_latency_s']}",
        "",
        "## Multi-turn scenarios",
        f"- Pass rate: {n_multi_passed}/{len(multi_report)}",
        "",
    ]
    for r in multi_report:
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(f"### [{status}] {r['id']} -- {r['description']}")
        for t in r["turns"]:
            lines.append(f"- {json.dumps(t)}")
        lines.append("")

    (RESULTS_DIR / "agent_eval.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
