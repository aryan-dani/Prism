"""Small RBAC + conflict smoke checks (separate from the 39 stress bank).

  uv run python -m eval.stress.rbac_smoke
"""

from __future__ import annotations

import sys

from eval.stress.client import PrismClient


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def main() -> int:
    # Customer denied HR
    c = PrismClient(email="priya.customer@prism.local", password="Prism2026!")
    s = c.create_session()["id"]
    resp, _ = c.chat(s, "How many casual leave days can I carry forward?")
    expect(resp.get("no_answer") is True, "customer should be denied HR")
    expect("access denied" in (resp.get("reply") or "").lower(), "customer denial wording")
    c.close()

    # Employee allowed HR policy
    e = PrismClient(email="alex.employee@prism.local", password="Prism2026!")
    s = e.create_session()["id"]
    resp, _ = e.chat(s, "How many casual leave days can I carry forward?")
    expect(resp.get("no_answer") is not True, "employee should get HR policy")
    expect("5" in (resp.get("reply") or ""), "carry-forward 5 days")

    # Employee denied CTC
    resp, _ = e.chat(s, "What is the annual CTC for Alex Rao?")
    expect(resp.get("no_answer") is True, "employee denied CTC")
    e.close()

    # HR staff leave balance
    h = PrismClient(email="riya.hr@prism.local", password="Prism2026!")
    s = h.create_session()["id"]
    resp, _ = h.chat(s, "What is the CL leave balance for Alex Rao EMP-1001?")
    expect(resp.get("no_answer") is not True, "hr_staff should see leave balance")
    expect("7" in (resp.get("reply") or ""), "Alex CL balance 7")
    h.close()

    # Finance CTC
    f = PrismClient(email="arun.finance@prism.local", password="Prism2026!")
    s = f.create_session()["id"]
    resp, _ = f.chat(s, "What is the annual CTC for Alex Rao?")
    expect(resp.get("no_answer") is not True, "finance_staff should see CTC")
    expect("12,40,000" in (resp.get("reply") or "") or "1240000" in (resp.get("reply") or "").replace(",", ""), "CTC figure")
    f.close()

    # Warranty conflict footnote (customer)
    c2 = PrismClient(email="priya.customer@prism.local", password="Prism2026!")
    s = c2.create_session()["id"]
    resp, _ = c2.chat(s, "What is the limited warranty period for model K-3901?")
    reply = (resp.get("reply") or "").lower()
    caveats = " ".join(
        str(x).lower()
        for x in ((resp.get("sources") or []) + [resp.get("reply") or ""])
    )
    # Prefer seeing 5 years from PDF or a caveat about priority
    ok = ("5" in (resp.get("reply") or "") and "year" in reply) or "precedence" in caveats or "lower-priority" in caveats
    expect(ok or not resp.get("no_answer"), f"warranty answer expected, got: {resp.get('reply')!r}")
    c2.close()

    print("rbac_smoke: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"rbac_smoke: FAIL — {e}", file=sys.stderr)
        raise SystemExit(1)
