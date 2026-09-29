"""One-page-plus Orion travel policy PDF for the session-upload demo."""

from __future__ import annotations

import io
import shutil
from pathlib import Path

from xhtml2pdf import pisa

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "backend" / "eval" / "fixtures" / "orion_travel_policy.pdf"
DESKTOP = Path.home() / "Desktop" / "orion_travel_policy.pdf"

HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
@page { size: A4; margin: 18mm 16mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; color: #1a1a1a; line-height: 1.45; }
h1 { font-size: 18pt; margin: 0 0 4px 0; }
.sub { color: #444; font-size: 10pt; margin-bottom: 14px; }
h2 { font-size: 12.5pt; margin: 16px 0 6px 0; border-bottom: 1px solid #ccc; padding-bottom: 3px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 10px 0; }
th, td { border: 1px solid #bbb; padding: 6px 8px; text-align: left; font-size: 10.5pt; }
th { background: #f0f0f0; }
.note { font-size: 9.5pt; color: #333; margin-top: 18px; padding: 8px; border: 1px solid #aaa; }
</style>
</head>
<body>
<h1>Orion Tools Pvt Ltd</h1>
<div class="sub">Travel and Reimbursement Policy (2026) &mdash; internal draft. Not a Kohler or Meridian document.</div>

<h2>1. Per diem</h2>
<p>Domestic per diem is <b>INR 3,250</b> per day for metro cities and <b>INR 2,100</b> for non-metro cities. Per diem is paid without receipts. Alcohol is never reimbursable.</p>

<h2>2. Approval bands</h2>
<p>These bands apply to the <b>total claim value</b>, not line items. They are Orion-only and are not the Meridian Finance Section 2.1 bands.</p>
<table>
<tr><th>Claim amount</th><th>Required approval</th></tr>
<tr><td>Up to INR 8,000</td><td>Reporting Manager</td></tr>
<tr><td>INR 8,001 to INR 60,000</td><td>Department Head</td></tr>
<tr><td>Above INR 60,000</td><td>VP Finance plus a pre-approval memo</td></tr>
</table>
<p>Example: a claim of <b>INR 45,000</b> requires Department Head sign-off. A claim of <b>INR 70,000</b> requires VP Finance and a pre-approval memo.</p>

<h2>3. Submission deadline</h2>
<p>All travel claims must be submitted within <b>21 calendar days</b> of return. Late claims are rejected unless the Department Head records a written exception.</p>

<h2>4. Hotel caps</h2>
<p>Metro hotel cap is <b>INR 9,500</b> per night. Non-metro hotel cap is <b>INR 6,000</b> per night. Amounts above the cap are employee-borne unless pre-approved by VP Finance.</p>

<h2>5. International travel</h2>
<p>International tickets require VP Finance pre-approval. The international per diem is <b>USD 85</b> per day. Personal stopovers are not reimbursable.</p>

<div class="note">
<b>Demo note:</b> This file is a session-scoped upload fixture. Prism should answer from <code>upload://orion_travel_policy.pdf</code> and must not mix these numbers with the five published knowledge bases.
</div>
</body>
</html>
"""


def main() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    result = pisa.CreatePDF(HTML, dest=buf, encoding="utf-8")
    if result.err:
        raise SystemExit(f"xhtml2pdf failed with {result.err} error(s)")
    DEST.write_bytes(buf.getvalue())
    print(f"wrote {DEST} ({DEST.stat().st_size} bytes)")
    try:
        shutil.copy2(DEST, DESKTOP)
        print(f"copied {DESKTOP}")
    except OSError as exc:
        print(f"desktop copy skipped: {exc}")


if __name__ == "__main__":
    main()
