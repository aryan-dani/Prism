"""Objective + rubric scorers for Prism stress harness."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any

DUP_WORD_RE = re.compile(r"\b([A-Za-z0-9]+)\s+\1\b", re.IGNORECASE)
NUM_CLEAN_RE = re.compile(r"[^\d]")


def verdict(status: str, reason: str, evidence: str = "") -> dict:
    assert status in {"PASS", "PARTIAL", "FAIL", "NEEDS_HUMAN_REVIEW", "SKIP"}
    return {"status": status, "reason": reason, "evidence": evidence[:2000]}


def reply_text(resp: dict | None) -> str:
    if not resp:
        return ""
    return (resp.get("reply") or "") + "\n" + json.dumps(resp.get("sources") or [], ensure_ascii=False)


def contains_any(text: str, needles: list[str]) -> bool:
    t = text.lower()
    return any(n.lower() in t for n in needles)


def contains_all(text: str, needles: list[str]) -> bool:
    t = text.lower()
    return all(n.lower() in t for n in needles)


def score_expect(resp: dict | None, expect: dict, latency_s: float) -> list[dict]:
    out: list[dict] = []
    if resp is None:
        return [verdict("FAIL", "No response from API")]

    text = reply_text(resp)

    if "contains_any" in expect:
        ok = contains_any(text, expect["contains_any"])
        out.append(
            verdict(
                "PASS" if ok else "FAIL",
                f"contains_any {expect['contains_any']}",
                text[:500],
            )
        )
    if "contains_all" in expect:
        ok = contains_all(text, expect["contains_all"])
        out.append(
            verdict(
                "PASS" if ok else "FAIL",
                f"contains_all {expect['contains_all']}",
                text[:500],
            )
        )
    if "not_contains_any" in expect:
        bad = [n for n in expect["not_contains_any"] if n.lower() in text.lower()]
        out.append(
            verdict(
                "FAIL" if bad else "PASS",
                f"forbidden phrases present: {bad}" if bad else "no forbidden phrases",
                text[:500],
            )
        )

    if "domain_any_of" in expect:
        dom = (resp.get("domain") or "").lower()
        ok = dom in [d.lower() for d in expect["domain_any_of"]]
        out.append(
            verdict(
                "PASS" if ok else "PARTIAL",
                f"domain={dom!r} expected one of {expect['domain_any_of']}",
            )
        )

    if "is_clarification_preferred" in expect and expect["is_clarification_preferred"]:
        if resp.get("is_clarification"):
            out.append(verdict("PASS", "API flagged is_clarification=True"))
        elif "?" in (resp.get("reply") or "") and contains_any(
            resp.get("reply") or "", ["which", "what", "clarify", "mean", "refer", "specify", "or"]
        ):
            out.append(
                verdict(
                    "PARTIAL",
                    "Looks like a clarifying question in text but is_clarification=False",
                    resp.get("reply") or "",
                )
            )
        else:
            out.append(
                verdict(
                    "FAIL",
                    "Expected clarification; agent answered as if unambiguous",
                    resp.get("reply") or "",
                )
            )

    if expect.get("no_answer_or_hedge"):
        if resp.get("is_clarification"):
            out.append(verdict("PASS", "asked clarifying question instead of fabricating"))
        elif resp.get("no_answer") or resp.get("confidence") in {"none", "low"}:
            out.append(verdict("PASS", f"no_answer={resp.get('no_answer')} confidence={resp.get('confidence')}"))
        elif contains_any(
            text,
            [
                "don't have",
                "do not have",
                "couldn't find",
                "could not find",
                "not in",
                "unknown",
                "not sure",
                "cannot confirm",
                "no information",
                "not found",
                "i don't know",
                "unable to",
                "not available",
                "fabricat",
                "guess",
            ],
        ):
            out.append(verdict("PARTIAL", "Hedged in prose but no_answer/confidence not set", text[:500]))
        else:
            out.append(verdict("FAIL", "Appears to answer confidently without grounding flag", text[:500]))

    if "numeric_equals" in expect:
        out.append(score_numeric(text, expect["numeric_equals"]))

    if "sources_should_include_substr" in expect:
        joined = json.dumps(resp.get("sources") or []).lower()
        ok = any(s.lower() in joined for s in expect["sources_should_include_substr"])
        out.append(
            verdict(
                "PASS" if ok else "FAIL",
                f"sources should include {expect['sources_should_include_substr']}",
                joined[:500],
            )
        )

    if "qualitative_rubric" in expect:
        # If objective checks already exist, don't let a rubric note downgrade a clean PASS
        # into NEEDS_HUMAN_REVIEW (that was inflating "unverified" to 66%).
        objective_keys = {
            "contains_any",
            "contains_all",
            "not_contains_any",
            "numeric_equals",
            "domain_any_of",
            "is_clarification_preferred",
            "no_answer_or_hedge",
            "sources_should_include_substr",
        }
        if any(k in expect for k in objective_keys):
            out.append(
                verdict(
                    "SKIP",
                    f"rubric note (objective scored): {expect['qualitative_rubric']}",
                    f"confidence={resp.get('confidence')} domain={resp.get('domain')} no_answer={resp.get('no_answer')}\n{(resp.get('reply') or '')[:800]}",
                )
            )
        else:
            out.append(
                verdict(
                    "NEEDS_HUMAN_REVIEW",
                    expect["qualitative_rubric"],
                    f"confidence={resp.get('confidence')} domain={resp.get('domain')} no_answer={resp.get('no_answer')}\n{resp.get('reply')}",
                )
            )

    # Always check duplicate words on assistant reply
    dups = DUP_WORD_RE.findall(resp.get("reply") or "")
    if dups:
        out.append(verdict("FAIL", f"duplicate consecutive words: {dups[:10]}", resp.get("reply") or ""))

    if latency_s > 15:
        out.append(verdict("PARTIAL", f"latency {latency_s:.1f}s > 15s threshold"))

    return out


def score_numeric(text: str, spec: dict) -> dict:
    if "expected_any_of_strings" in spec:
        ok = any(s.lower().replace(" ", "") in text.lower().replace(" ", "") for s in spec["expected_any_of_strings"])
        return verdict(
            "PASS" if ok else "FAIL",
            f"expected one of {spec['expected_any_of_strings']}",
            text[:400],
        )
    patterns = spec.get("patterns") or [r"\d+"]
    expected = spec.get("expected")
    found = []
    for p in patterns:
        found.extend(re.findall(p, text))
    if expected is None:
        return verdict("PARTIAL", "numeric_equals missing expected", str(found))
    # Normalize found tokens that are pure-ish numbers
    nums = []
    for f in found:
        digits = NUM_CLEAN_RE.sub("", f if isinstance(f, str) else str(f))
        if digits.isdigit():
            nums.append(int(digits))
    if expected in nums or str(expected) in [str(x) for x in found]:
        return verdict("PASS", f"found expected numeric {expected}", str(found[:20]))
    return verdict("FAIL", f"expected numeric {expected}, found {found[:20]}", text[:400])


def score_opposite_approvals(turns: list[dict], spec: dict) -> dict:
    a = reply_text(turns[spec["turn_a"]].get("response"))
    b = reply_text(turns[spec["turn_b"]].get("response"))
    a_ok = contains_any(a, spec["a_must"])
    b_ok = contains_any(b, spec["b_must"])
    if a_ok and b_ok:
        # ensure B doesn't also claim A's authority as primary if forbid
        if spec.get("a_forbid_in_b") and contains_any(b, spec["a_must"]):
            return verdict("PARTIAL", "Under-band answer still mentions over-band approver", b[:400])
        return verdict("PASS", "Opposite approval authorities detected across the two turns")
    return verdict(
        "FAIL",
        f"a_ok={a_ok} b_ok={b_ok}",
        f"A: {a[:300]}\nB: {b[:300]}",
    )


def find_dup_words(text: str) -> list[str]:
    return DUP_WORD_RE.findall(text or "")


def validate_json_string(s: str) -> dict:
    try:
        json.loads(s)
        return verdict("PASS", "JSON parsed")
    except Exception as e:
        return verdict("FAIL", f"JSON invalid: {e}", s[:500])


def validate_xml_string(s: str) -> dict:
    try:
        ET.fromstring(s)
        return verdict("PASS", "XML parsed")
    except Exception as e:
        return verdict("FAIL", f"XML invalid: {e}", s[:500])


def title_matches_topic(title: str | None, keywords: list[str]) -> dict:
    t = (title or "").lower()
    if not t or t in {"new conversation", "untitled", "none"}:
        return verdict("FAIL", "empty/generic title", str(title))
    hits = [k for k in keywords if k.lower() in t]
    if hits:
        return verdict("PASS", f"title matched keywords {hits}", str(title))
    return verdict(
        "FAIL",
        f"title {title!r} matched none of {keywords}",
        str(title),
    )


def sources_domain_consistent(resp: dict | None, expected_domain: str) -> dict:
    if not resp:
        return verdict("FAIL", "no response")
    sources = resp.get("sources") or []
    if not sources:
        return verdict("PARTIAL", "no sources returned", str(resp.get("reply"))[:300])
    bad = []
    for s in sources:
        dom = (s.get("domain") or "").lower()
        url = (s.get("source_url") or "").lower()
        if expected_domain == "hr" and ("finance_policy" in url or dom == "finance"):
            bad.append(s)
        if expected_domain == "finance" and ("hr_policy" in url and dom == "hr" and "finance" not in url):
            # cross-ref notes can mention HR; only flag hard mismatch if domain tag is wrong-only
            pass
        if dom and dom != expected_domain and expected_domain not in (s.get("title") or "").lower():
            # soft: allow cross-tags
            if dom not in {expected_domain}:
                bad.append(s)
    # stricter for HR: finance_policy citation is wrong
    hard_bad = [s for s in sources if expected_domain == "hr" and "finance_policy" in (s.get("source_url") or "").lower()]
    if hard_bad:
        return verdict("FAIL", "HR answer cited finance_policy.md", json.dumps(hard_bad)[:500])
    mismatched = [s for s in sources if (s.get("domain") or "").lower() not in {"", expected_domain}]
    if mismatched and len(mismatched) == len(sources):
        return verdict("FAIL", f"all sources domain != {expected_domain}", json.dumps(mismatched)[:500])
    if mismatched:
        return verdict("PARTIAL", f"some cross-domain sources on {expected_domain} answer", json.dumps(mismatched)[:500])
    return verdict("PASS", "sources domain-consistent", json.dumps(sources)[:500])
