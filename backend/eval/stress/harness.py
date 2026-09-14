"""
Prism automated stress-test harness.

Run (API must already be up on :8000):
  cd backend
  uv run python -m eval.stress.harness

Optional:
  $env:PRISM_STRESS_LIMIT="5"          # first N cases only (smoke)
  $env:PRISM_STRESS_BASE="http://127.0.0.1:8000"
  $env:PRISM_STRESS_CATEGORIES="1_numeric_boundary,6_hallucination_honesty"

Writes:
  eval/results/stress/run_<timestamp>/
    results.jsonl
    report.md
    raw/<case_id>.json
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from eval.stress.client import PrismClient, SessionLog, TurnLog
from eval.stress.question_bank import build_bank
from eval.stress.scorers import (
    find_dup_words,
    score_expect,
    score_opposite_approvals,
    sources_domain_consistent,
    title_matches_topic,
    validate_json_string,
    validate_xml_string,
    verdict,
)

RESULTS_ROOT = Path(__file__).resolve().parents[1] / "results" / "stress"


def _filter_bank(bank: list[dict]) -> list[dict]:
    cats = os.environ.get("PRISM_STRESS_CATEGORIES")
    if cats:
        allow = {c.strip() for c in cats.split(",") if c.strip()}
        bank = [c for c in bank if c["category"] in allow]
    limit = os.environ.get("PRISM_STRESS_LIMIT")
    if limit:
        bank = bank[: int(limit)]
    return bank


def run_simple_case(client: PrismClient, case: dict) -> dict:
    created = client.create_session()
    sid = created["id"]
    slog = SessionLog(session_id=sid)
    scores: list[dict] = []

    turn_expects = case.get("turn_expects") or {}

    for i, turn in enumerate(case.get("turns") or []):
        msg = turn["message"]
        try:
            resp, latency = client.chat(sid, msg)
            err = None
        except Exception as e:
            resp, latency, err = None, 0.0, str(e)
        tlog = TurnLog(
            turn_index=i,
            message=msg,
            request={"message": msg},
            response=resp,
            error=err,
            latency_s=latency,
            timestamp=time.time(),
        )
        slog.turns.append(tlog)

        if i == 0 and resp:
            # refresh title from session
            try:
                state = client.get_session(sid)
                slog.title_after_first = state.get("title") or resp.get("title")
            except Exception:
                slog.title_after_first = resp.get("title")

        expect = turn.get("expect") or turn_expects.get(str(i)) or turn_expects.get(i)
        if expect and resp:
            for s in score_expect(resp, expect, latency):
                scores.append({**s, "turn": i, "scorer": "expect"})
        elif expect and not resp:
            scores.append({**verdict("FAIL", f"turn {i} error: {err}"), "turn": i})

    # post scorers
    for post in case.get("post") or []:
        scores.extend(run_post(client, sid, slog, post))

    return finalize_case(case, slog, scores)


def run_post(client: PrismClient, sid: str, slog: SessionLog, post: dict) -> list[dict]:
    out: list[dict] = []
    ptype = post["type"]

    if ptype == "opposite_approvals":
        turn_dicts = [{"response": t.response} for t in slog.turns]
        out.append({**score_opposite_approvals(turn_dicts, post), "scorer": ptype})

    elif ptype == "check_dup_words_all_turns":
        found = []
        for t in slog.turns:
            if t.response:
                d = find_dup_words(t.response.get("reply") or "")
                if d:
                    found.append({"turn": t.turn_index, "dups": d, "reply": t.response.get("reply")})
        if found:
            out.append({**verdict("FAIL", "duplicate-word artifacts", json.dumps(found, ensure_ascii=False)[:1500]), "scorer": ptype})
        else:
            out.append({**verdict("PASS", "no duplicate consecutive words"), "scorer": ptype})

    elif ptype == "latency_series_flag":
        latencies = [t.latency_s for t in slog.turns if t.response]
        threshold = post.get("threshold_s", 15)
        over = [i for i, x in enumerate(latencies) if x > threshold]
        climbing = False
        if post.get("flag_if_climbing") and len(latencies) >= 6:
            first = sum(latencies[:3]) / 3
            last = sum(latencies[-3:]) / 3
            climbing = last > first * 1.5 and last - first > 3
        status = "PASS"
        reasons = [f"latencies={[round(x,1) for x in latencies]}"]
        if over:
            status = "PARTIAL"
            reasons.append(f"turns over {threshold}s: {over}")
        if climbing:
            status = "FAIL" if status != "PASS" else "PARTIAL"
            reasons.append("latency appears to climb across the session")
        out.append({**verdict(status, "; ".join(reasons)), "scorer": ptype})

    elif ptype == "cold_query_after":
        first_lat = slog.turns[0].latency_s if slog.turns else None
        created = client.create_session()
        resp, latency = client.chat(created["id"], post["message"])
        note = f"cold_latency={latency:.1f}s first_turn_latency={first_lat}"
        if first_lat and latency > first_lat * 2 and latency - first_lat > 5:
            out.append({**verdict("PARTIAL", f"cold query much slower than start — possible resource pressure; {note}", resp.get("reply", "")[:300]), "scorer": ptype})
        else:
            out.append({**verdict("PASS", note), "scorer": ptype})

    elif ptype == "render_formats_and_diff_facts":
        blobs = {}
        for fmt in post.get("formats") or []:
            data, lat, ctype = client.render(sid, fmt)
            blobs[fmt] = {"data": data, "latency_s": lat, "ctype": ctype}
        must = post.get("must_appear_in_all") or []
        missing = {}
        for fmt, blob in blobs.items():
            text = json.dumps(blob["data"], ensure_ascii=False).lower()
            miss = [m for m in must if m.lower() not in text]
            if miss:
                missing[fmt] = miss
        if missing:
            out.append({**verdict("FAIL", f"fact drift / missing across formats: {missing}", json.dumps(blobs, ensure_ascii=False)[:1500]), "scorer": ptype})
        else:
            out.append({**verdict("PASS", f"required facts present in {list(blobs)}"), "scorer": ptype})

    elif ptype == "json_valid_render":
        data, _, _ = client.render(sid, "json")
        content = data.get("content") if isinstance(data, dict) else None
        if content is None:
            out.append({**verdict("FAIL", f"no json content: {data}"), "scorer": ptype})
        else:
            out.append({**validate_json_string(content), "scorer": ptype})

    elif ptype == "xml_valid_render":
        data, _, _ = client.render(sid, "xml")
        content = data.get("content") if isinstance(data, dict) else None
        if content is None:
            out.append({**verdict("FAIL", f"no xml content: {data}"), "scorer": ptype})
        else:
            out.append({**validate_xml_string(content), "scorer": ptype})

    elif ptype == "render_json_and_check_risk_level":
        # Prefer chat reply if user asked for JSON inline; also try render
        last = slog.turns[-1].response or {}
        reply = last.get("reply") or ""
        data, _, _ = client.render(sid, "json")
        content = data.get("content") if isinstance(data, dict) else ""
        blob = content or reply
        risk = None
        try:
            # try extract JSON object
            m = re.search(r"\{[\s\S]*\}", blob)
            obj = json.loads(m.group(0) if m else blob)
            risk = obj.get("risk_level")
        except Exception:
            pass
        if risk is None or str(risk).lower() in {"n/a", "na", "null", "none", "not applicable", "not in policy", ""}:
            out.append({**verdict("PASS", f"risk_level omitted or N/A ({risk!r})", blob[:500]), "scorer": ptype})
        else:
            out.append(
                {
                    **verdict(
                        "FAIL",
                        f"risk_level fabricated with {risk!r} — policy has no risk_level field",
                        blob[:800],
                    ),
                    "scorer": ptype,
                }
            )

    elif ptype == "try_excel_download_graceful":
        # Prefer chat-turn decline over download behavior
        last = slog.turns[-1].response or {}
        reply = (last.get("reply") or "").lower()
        if last.get("is_reformat") and any(
            p in reply for p in ("isn't tabular", "not tabular", "not detailed enough", "try json")
        ):
            out.append({**verdict("PASS", "chat declined Excel as non-tabular", reply[:400]), "scorer": ptype})
            return out
        data, lat, status = client.download(sid, "excel")
        if status >= 400:
            out.append({**verdict("PASS", f"Excel declined gracefully status={status}", json.dumps(data)[:400]), "scorer": ptype})
        else:
            out.append(
                {
                    **verdict(
                        "PARTIAL",
                        f"Excel download succeeded for non-tabular answer (nbytes={data.get('nbytes')}) — check if forced table",
                        json.dumps(data)[:400],
                    ),
                    "scorer": ptype,
                }
            )

    elif ptype == "render_email_tone_check":
        data, _, _ = client.render(sid, "email")
        content = (data.get("content") if isinstance(data, dict) else "") or ""
        hostile = ["threatening to quit", "or else", "i will quit immediately", "quit if my leave"]
        if any(h in content.lower() for h in hostile):
            out.append({**verdict("FAIL", "email preserved hostile framing", content[:800]), "scorer": ptype})
        else:
            out.append({**verdict("PASS", "email draft has no hostile framing markers", content[:800]), "scorer": ptype})

    elif ptype == "sources_domain_match":
        last = slog.turns[-1].response
        out.append({**sources_domain_consistent(last, post["expected_domain"]), "scorer": ptype})

    elif ptype == "domain_changed_across_turns":
        domains = [(t.response or {}).get("domain") for t in slog.turns if t.response]
        distinct = {d for d in domains if d}
        need = post.get("min_distinct_domains", 2)
        out.append(
            {
                **verdict(
                    "PASS" if len(distinct) >= need else "PARTIAL",
                    f"domains seen: {domains} distinct={distinct}",
                ),
                "scorer": ptype,
            }
        )

    else:
        out.append({**verdict("SKIP", f"unknown post scorer {ptype}"), "scorer": ptype})

    return out


def run_multi_session(client: PrismClient, case: dict) -> dict:
    ms = case["multi_session"]
    scores: list[dict] = []
    sessions_raw = []

    if "messages" in ms and ms.get("compare") == "titles_match_topics":
        for msg, kws in zip(ms["messages"], ms["topic_keywords"]):
            created = client.create_session()
            sid = created["id"]
            resp, latency = client.chat(sid, msg)
            state = client.get_session(sid)
            title = state.get("title") or resp.get("title")
            sessions_raw.append({"session_id": sid, "message": msg, "title": title, "response": resp, "latency_s": latency})
            scores.append({**title_matches_topic(title, kws), "scorer": "title_topic_match", "message": msg})
        # also check titles are unique-ish
        titles = [s["title"] for s in sessions_raw]
        if len(titles) != len(set(titles)):
            scores.append({**verdict("FAIL", f"duplicate titles across rapid sessions: {titles}"), "scorer": "title_uniqueness"})
        else:
            scores.append({**verdict("PASS", f"titles unique: {titles}"), "scorer": "title_uniqueness"})
        return finalize_multi(case, sessions_raw, scores)

    if "sessions" in ms:
        msg = ms["message"]
        replies = []
        for _ in range(ms["sessions"]):
            created = client.create_session()
            resp, latency = client.chat(created["id"], msg)
            sessions_raw.append({"session_id": created["id"], "response": resp, "latency_s": latency})
            replies.append((resp or {}).get("reply") or "")
        must = ms.get("must_share") or []
        ok = all(all(m.lower() in r.lower() for m in must) for r in replies)
        scores.append(
            {
                **verdict("PASS" if ok else "FAIL", f"must_share {must} across sessions", json.dumps(replies, ensure_ascii=False)[:1500]),
                "scorer": "facts_must_match",
            }
        )
        return finalize_multi(case, sessions_raw, scores)

    if "messages" in ms and ms.get("compare") == "facts_must_match":
        replies = []
        for msg in ms["messages"]:
            created = client.create_session()
            resp, latency = client.chat(created["id"], msg)
            sessions_raw.append({"session_id": created["id"], "message": msg, "response": resp, "latency_s": latency})
            replies.append((resp or {}).get("reply") or "")
        must = ms.get("must_share") or []
        ok = all(all(m.lower() in r.lower() for m in must) for r in replies)
        scores.append(
            {
                **verdict("PASS" if ok else "FAIL", f"must_share {must} across phrasings", json.dumps(replies, ensure_ascii=False)[:1500]),
                "scorer": "facts_must_match",
            }
        )
        return finalize_multi(case, sessions_raw, scores)

    return finalize_multi(case, sessions_raw, [{**verdict("SKIP", "unhandled multi_session shape"), "scorer": "multi"}])


def finalize_case(case: dict, slog: SessionLog, scores: list[dict]) -> dict:
    return {
        "id": case["id"],
        "category": case["category"],
        "title": case["title"],
        "session_id": slog.session_id,
        "session_title": slog.title_after_first,
        "turns": [
            {
                "turn_index": t.turn_index,
                "message": t.message,
                "latency_s": t.latency_s,
                "error": t.error,
                "response": t.response,
            }
            for t in slog.turns
        ],
        "scores": scores,
        "rollup": rollup(scores),
    }


def finalize_multi(case: dict, sessions_raw: list, scores: list[dict]) -> dict:
    return {
        "id": case["id"],
        "category": case["category"],
        "title": case["title"],
        "sessions": sessions_raw,
        "scores": scores,
        "rollup": rollup(scores),
    }


def rollup(scores: list[dict]) -> str:
    # Worst wins: FAIL > PARTIAL > NEEDS_HUMAN_REVIEW > PASS > SKIP
    order = {"FAIL": 0, "PARTIAL": 1, "NEEDS_HUMAN_REVIEW": 2, "PASS": 3, "SKIP": 4}
    if not scores:
        return "SKIP"
    return min((s.get("status") or "SKIP" for s in scores), key=lambda x: order.get(x, 9))


def write_report(run_dir: Path, results: list[dict], meta: dict) -> Path:
    # category summary
    from collections import Counter, defaultdict

    by_cat: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        by_cat[r["category"]][r["rollup"]] += 1

    # sort categories by FAIL count desc, then PARTIAL
    cat_order = sorted(
        by_cat.keys(),
        key=lambda c: (-by_cat[c]["FAIL"], -by_cat[c]["PARTIAL"], -by_cat[c]["NEEDS_HUMAN_REVIEW"], c),
    )

    lines = []
    lines.append(f"# Prism Stress-Test Report")
    lines.append("")
    lines.append(f"- Generated: `{meta['generated_at']}`")
    lines.append(f"- API: `{meta['base_url']}`")
    lines.append(f"- Health: `{json.dumps(meta.get('health'), ensure_ascii=False)}`")
    lines.append(f"- Cases run: **{len(results)}**")
    lines.append(f"- Wall time: **{meta.get('wall_s', 0):.0f}s**")
    lines.append("")
    lines.append("## Summary by category")
    lines.append("")
    lines.append("| Category | PASS | PARTIAL | FAIL | NEEDS_HUMAN_REVIEW | SKIP |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    totals = Counter()
    for c in cat_order:
        ctr = by_cat[c]
        lines.append(
            f"| {c} | {ctr['PASS']} | {ctr['PARTIAL']} | {ctr['FAIL']} | {ctr['NEEDS_HUMAN_REVIEW']} | {ctr['SKIP']} |"
        )
        totals.update(ctr)
    lines.append(
        f"| **TOTAL** | **{totals['PASS']}** | **{totals['PARTIAL']}** | **{totals['FAIL']}** | **{totals['NEEDS_HUMAN_REVIEW']}** | **{totals['SKIP']}** |"
    )
    lines.append("")

    # Failures first
    lines.append("## FAIL and PARTIAL detail (worst categories first)")
    lines.append("")
    for c in cat_order:
        cat_results = [r for r in results if r["category"] == c and r["rollup"] in {"FAIL", "PARTIAL"}]
        if not cat_results:
            continue
        lines.append(f"### {c}")
        lines.append("")
        for r in cat_results:
            lines.append(f"#### `{r['id']}` — {r['title']} → **{r['rollup']}**")
            lines.append("")
            for s in r.get("scores") or []:
                if s.get("status") in {"FAIL", "PARTIAL", "NEEDS_HUMAN_REVIEW"}:
                    lines.append(f"- **{s['status']}** [{s.get('scorer','')}] {s.get('reason')}")
                    if s.get("evidence"):
                        lines.append("")
                        lines.append("```")
                        lines.append(str(s["evidence"])[:1500])
                        lines.append("```")
                        lines.append("")
            # attach last reply snippets
            if r.get("turns"):
                for t in r["turns"]:
                    resp = t.get("response") or {}
                    lines.append(f"**Turn {t['turn_index']}** ({t.get('latency_s', 0):.1f}s) user: {t['message']}")
                    lines.append("")
                    lines.append("```")
                    lines.append((resp.get("reply") or t.get("error") or "")[:1200])
                    lines.append("```")
                    lines.append("")
                    lines.append(
                        f"domain=`{resp.get('domain')}` confidence=`{resp.get('confidence')}` "
                        f"clarification=`{resp.get('is_clarification')}` no_answer=`{resp.get('no_answer')}` "
                        f"title=`{r.get('session_title')}`"
                    )
                    lines.append("")
            lines.append("---")
            lines.append("")

    # Human review section
    lines.append("## NEEDS_HUMAN_REVIEW items")
    lines.append("")
    any_hr = False
    for r in results:
        reviews = [s for s in r.get("scores") or [] if s.get("status") == "NEEDS_HUMAN_REVIEW"]
        if not reviews:
            continue
        any_hr = True
        lines.append(f"### `{r['id']}` ({r['category']})")
        for s in reviews:
            lines.append(f"- Rubric: {s.get('reason')}")
            lines.append("")
            lines.append("```")
            lines.append(str(s.get("evidence") or "")[:1500])
            lines.append("```")
            lines.append("")
    if not any_hr:
        lines.append("_None._")
        lines.append("")

    lines.append("## All case rollups")
    lines.append("")
    for r in results:
        lines.append(f"- `{r['id']}` [{r['category']}]: **{r['rollup']}**")

    path = run_dir / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> None:
    base = os.environ.get("PRISM_STRESS_BASE", "http://127.0.0.1:8000")
    client = PrismClient(base_url=base)
    health = client.health()
    print(f"API health: {health}", flush=True)

    bank = _filter_bank(build_bank())
    print(f"Running {len(bank)} cases sequentially...", flush=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RESULTS_ROOT / f"run_{stamp}"
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    results = []
    t0 = time.perf_counter()
    jsonl_path = run_dir / "results.jsonl"

    with jsonl_path.open("w", encoding="utf-8") as jf:
        for i, case in enumerate(bank, 1):
            print(f"\n[{i}/{len(bank)}] {case['id']} ({case['category']})...", flush=True)
            try:
                if "multi_session" in case:
                    result = run_multi_session(client, case)
                else:
                    result = run_simple_case(client, case)
            except Exception as e:
                result = {
                    "id": case["id"],
                    "category": case["category"],
                    "title": case["title"],
                    "scores": [{**verdict("FAIL", f"harness exception: {e}"), "scorer": "harness"}],
                    "rollup": "FAIL",
                    "error": str(e),
                }
            results.append(result)
            jf.write(json.dumps(result, ensure_ascii=False) + "\n")
            jf.flush()
            (raw_dir / f"{case['id']}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"  -> {result['rollup']}", flush=True)

    wall = time.perf_counter() - t0
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base,
        "health": health,
        "wall_s": wall,
        "n_cases": len(results),
    }
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    report = write_report(run_dir, results, meta)
    # stable pointer
    latest = RESULTS_ROOT / "LATEST_REPORT.md"
    latest.write_text(report.read_text(encoding="utf-8"), encoding="utf-8")
    (RESULTS_ROOT / "latest_run.txt").write_text(str(run_dir), encoding="utf-8")

    print(f"\nDone in {wall:.0f}s", flush=True)
    print(f"Report: {report}", flush=True)
    print(f"Copy:   {latest}", flush=True)
    client.close()


if __name__ == "__main__":
    main()
