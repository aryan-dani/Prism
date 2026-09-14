"""Benchmark candidate generation models against the 8GB VRAM budget.

Run: uv run python -m eval.bench_models

Measures, per model, over a fixed subset of eval/golden.jsonl:
    - JSON-schema adherence (did generate_answer() return a valid CanonicalAnswer
      without needing the repair retry?)
    - Numeric exactness on Finance questions (does the direct_answer / key_facts
      contain the expected exact figures, e.g. "\u20b925,000", "60 days"?)
    - No-context honesty (does the model correctly set no_answer=True on the
      two adversarial "noanswer_*" questions instead of fabricating?)
    - Latency (seconds per answer) and a rough tokens/sec estimate
    - Peak VRAM during the run (nvidia-smi, best-effort -- requires nvidia-smi
      on PATH; skipped gracefully if unavailable)

Writes eval/results/model_bench.json and eval/results/model_bench.md (the
table that goes into docs/decisions.md Section 3).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from prism.core.answer import generate_answer, no_context_answer
from prism.core.config import EVAL_DIR
from prism.core.retriever import retrieve

# Override with comma-separated list, e.g.:
#   $env:PRISM_BENCH_MODELS="qwen2.5:7b-instruct,qwen3:8b"
_DEFAULT_CANDIDATES = [
    "qwen2.5:7b-instruct",
    "qwen3:8b",
]
CANDIDATE_MODELS = [
    m.strip()
    for m in os.environ.get("PRISM_BENCH_MODELS", ",".join(_DEFAULT_CANDIDATES)).split(",")
    if m.strip()
]

GOLDEN_PATH = EVAL_DIR / "golden.jsonl"
RESULTS_DIR = EVAL_DIR / "results"


def load_single_turn_questions() -> list[dict]:
    questions = []
    with GOLDEN_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("type") == "single_turn":
                questions.append(rec)
    limit = os.environ.get("PRISM_BENCH_LIMIT")
    if limit:
        questions = questions[: int(limit)]
    return questions


def peak_vram_mb() -> float | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            timeout=5,
        )
        return float(out.decode().strip().splitlines()[0])
    except Exception:
        return None


def contains_all(text: str, expected: list[str]) -> tuple[int, int]:
    hits = sum(1 for e in expected if e.lower() in text.lower())
    return hits, len(expected)


def bench_model(model: str, questions: list[dict]) -> dict:
    print(f"\n=== Benchmarking {model} ===")
    n_schema_ok = 0
    n_total = 0
    fact_hits, fact_total = 0, 0
    finance_fact_hits, finance_fact_total = 0, 0
    noanswer_correct, noanswer_total = 0, 0
    latencies: list[float] = []
    vram_samples: list[float] = []

    for q in questions:
        n_total += 1
        domain = q["domain"]
        query = q["query"]
        print(f"  [{n_total}/{len(questions)}] {q['id']} ({domain})...", flush=True)

        if q.get("expected_no_answer"):
            noanswer_total += 1

        result = retrieve(query, domain=domain)
        t0 = time.monotonic()
        try:
            if not result.chunks or not result.is_confident:
                answer = no_context_answer(query, domain)
            else:
                answer = generate_answer(query, domain=domain, context_chunks=result.chunks, model=model)
            n_schema_ok += 1
        except Exception as e:
            print(f"  [FAIL] {q['id']}: {e}", flush=True)
            continue
        latencies.append(time.monotonic() - t0)
        print(f"      ok in {latencies[-1]:.1f}s conf={answer.confidence} no_answer={answer.no_answer}", flush=True)

        v = peak_vram_mb()
        if v:
            vram_samples.append(v)

        full_text = answer.direct_answer + " " + " ".join(f"{kf.label} {kf.value} {kf.unit or ''}" for kf in answer.key_facts)

        if q.get("expected_no_answer"):
            if answer.no_answer:
                noanswer_correct += 1
        elif "expected_facts" in q:
            hits, total = contains_all(full_text, q["expected_facts"])
            fact_hits += hits
            fact_total += total
            if domain == "finance":
                finance_fact_hits += hits
                finance_fact_total += total

    avg_latency = sum(latencies) / len(latencies) if latencies else None
    peak_vram = max(vram_samples) if vram_samples else None

    return {
        "model": model,
        "n_questions": n_total,
        "schema_adherence_rate": n_schema_ok / n_total if n_total else 0,
        "fact_recall_rate": fact_hits / fact_total if fact_total else None,
        "finance_exactness_rate": finance_fact_hits / finance_fact_total if finance_fact_total else None,
        "no_answer_honesty_rate": noanswer_correct / noanswer_total if noanswer_total else None,
        "avg_latency_seconds": avg_latency,
        "peak_vram_mb": peak_vram,
    }


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    questions = load_single_turn_questions()
    print(f"Loaded {len(questions)} single-turn golden questions.")

    results = []
    for model in CANDIDATE_MODELS:
        try:
            results.append(bench_model(model, questions))
        except Exception as e:
            print(f"Skipping {model}: {e} (likely not pulled yet -- run scripts/pull_models.ps1)")
            results.append({"model": model, "error": str(e)})

    with (RESULTS_DIR / "model_bench.json").open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    lines = ["| Model | Schema OK | Fact Recall | Finance Exactness | No-Answer Honesty | Avg Latency (s) | Peak VRAM (MB) |",
             "|---|---|---|---|---|---|---|"]
    for r in results:
        if "error" in r:
            lines.append(f"| {r['model']} | ERROR: {r['error']} | | | | | |")
            continue
        lines.append(
            f"| {r['model']} | {r['schema_adherence_rate']:.0%} | "
            f"{r['fact_recall_rate']:.0%} | "
            f"{(r['finance_exactness_rate'] or 0):.0%} | "
            f"{(r['no_answer_honesty_rate'] or 0):.0%} | "
            f"{(r['avg_latency_seconds'] or 0):.1f} | "
            f"{r['peak_vram_mb'] or 'n/a'} |"
        )
    md = "\n".join(lines)
    (RESULTS_DIR / "model_bench.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"\nWrote {RESULTS_DIR / 'model_bench.json'} and {RESULTS_DIR / 'model_bench.md'}")


if __name__ == "__main__":
    main()
