"""Export the prompts handbook as a designed A4 PDF (Chromium print).

Live SYSTEM_PROMPT / titler / email / anchors are imported from the
backend package so this PDF cannot drift from shipped code.

    python scripts/export_prompts.py
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
MD = DOCS / "prompts.md"
HTML_OUT = ASSETS / "_prompts.html"
PDF_OUT = DOCS / "pdf" / "prompts.pdf"
PREVIEW = ASSETS / "_prompts_preview"

CSS = """
:root {
  --font: "DM Sans", "Segoe UI", sans-serif;
  --display: "Instrument Serif", Georgia, serif;
  --ink: #1c2420;
  --muted: #5c665f;
  --accent: #0f5c4c;
  --panel: #faf7f1;
  --line: #d5cebf;
  --wash: #eaf6f1;
}
* { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
html, body {
  margin: 0; padding: 0;
  background: #fffefb;
  font-family: var(--font);
  color: var(--ink);
  font-size: 11.2pt;
  line-height: 1.5;
  font-optical-sizing: auto;
  -webkit-font-smoothing: antialiased;
  orphans: 4;
  widows: 4;
}
@page { size: A4; margin: 14mm 16mm 32mm 16mm; }

.handbook { max-width: 100%; width: 100%; }
.chapter { break-inside: auto; page-break-inside: auto; }
.subsec {
  break-inside: avoid;
  page-break-inside: avoid;
}
.subsec:has(.prompt-card-flow) {
  break-inside: auto;
  page-break-inside: auto;
}
.chapter > h2, .subsec > h3, h2, h3, h4 {
  break-after: avoid;
  page-break-after: avoid;
}
h2 + *, h3 + *, h4 + * {
  break-before: avoid;
  page-break-before: avoid;
}
.example, .prompt-card {
  break-inside: avoid;
  page-break-inside: avoid;
}
.prompt-card-flow, pre {
  break-inside: auto;
  page-break-inside: auto;
}
.recon {
  break-inside: avoid;
  page-break-inside: avoid;
}
.recon > h3, .recon .badge-recon {
  break-after: avoid;
  page-break-after: avoid;
}
/* Keep chapter 4 heading with brief 1; do not start a chapter under a card. */
.keep-start {
  break-inside: avoid;
  page-break-inside: avoid;
}
.chapter:has(+ .recon) {
  break-after: avoid;
  page-break-after: avoid;
}
.recon + .chapter {
  break-before: page;
  page-break-before: always;
}

.opening { width: 100%; }
.cover {
  width: 100%;
  margin: 0 0 14px;
  padding: 22px 24px 20px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background:
    radial-gradient(circle at 0% 0%, rgba(15, 92, 76, 0.12), transparent 48%),
    linear-gradient(165deg, #f4f0e8, #faf7f1);
}
.cover .kicker {
  font-size: 9.5pt; font-weight: 700; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--accent); margin: 0 0 10px;
}
.cover h1 {
  font-family: var(--display); font-weight: 400;
  font-size: 30pt; line-height: 1.05; letter-spacing: -0.02em;
  color: #16201c; margin: 0 0 12px; border: 0; padding: 0;
}
.cover .lede { font-size: 12pt; line-height: 1.45; color: #3f4a44; margin: 0 0 12px; }
.cover .pills { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; }
.cover .pill {
  background: var(--wash); color: var(--accent); border-radius: 999px;
  padding: 4px 10px; font-size: 8.5pt; font-weight: 650;
}
.toc-card {
  width: 100%; margin: 0 0 14px; padding: 12px 20px 10px;
  border: 1px solid var(--line); border-radius: 16px; background: var(--panel);
}
.toc-card > h2 { margin-top: 0; padding-top: 2px; }

h1 { font-family: var(--display); font-size: 22pt; font-weight: 400; color: #16201c; margin: 0 0 8px; }
h2 {
  font-family: var(--display); font-size: 18pt; font-weight: 400;
  color: var(--accent); margin: 14px 0 8px; padding: 4px 0;
  border-bottom: 1.5px solid #cfe3dc;
}
h3 { font-size: 12.4pt; font-weight: 700; color: #0f5c4c; margin: 14px 0 7px; }
h4 { font-size: 11.2pt; font-weight: 700; color: #16362e; margin: 10px 0 5px; }
p { margin: 0 0 8px; }
ul, ol { margin: 0 0 9px; padding-left: 18px; }
li { margin: 0 0 3px; }
hr { display: none; }
a { color: var(--accent); text-decoration: none; }
code {
  font-family: Consolas, "Courier New", monospace;
  font-size: 0.88em;
  background: rgba(15, 92, 76, 0.08);
  padding: 1px 5px; border-radius: 4px;
}
pre, .prompt-card {
  background: #1c2420; color: #e8efe9;
  border-radius: 10px; padding: 12px 14px;
  font-family: Consolas, monospace;
  font-size: 8.6pt; line-height: 1.42;
  white-space: pre-wrap;
  margin: 0 0 10px;
}
.prompt-card-flow {
  background: transparent;
  color: inherit;
  padding: 0;
  margin: 0 0 10px;
}
.prompt-card-flow .lbl {
  color: var(--accent);
  margin: 0 0 6px;
}
.prompt-card-flow pre {
  margin: 0;
}
pre code { background: none; color: inherit; padding: 0; }
.prompt-card .lbl {
  display: block; font-family: var(--font);
  font-size: 8pt; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; color: #7dcebc; margin: 0 0 8px;
}
blockquote {
  margin: 8px 0 10px; padding: 8px 12px;
  border-left: 3px solid var(--accent);
  background: var(--panel); color: #3f4a44;
  border-radius: 0 10px 10px 0;
}
blockquote.pull {
  font-family: var(--display); font-size: 13pt; line-height: 1.28;
  color: #16201c; background: var(--wash);
}

table {
  width: 100%; border-collapse: collapse;
  margin: 6px 0 12px; font-size: 9.5pt; background: var(--panel);
  break-inside: auto;
  page-break-inside: auto;
}
thead { display: table-header-group; }
tr { break-inside: avoid; page-break-inside: avoid; }
th, td { border: 1px solid var(--line); padding: 7px 8px; vertical-align: top; text-align: left; }
th {
  background: #d7ebe4; color: var(--accent); font-weight: 750;
  font-size: 8pt; letter-spacing: 0.04em; text-transform: uppercase;
}
tr:nth-child(even) td { background: #f3efe6; }

.example {
  margin: 8px 0 12px; padding: 10px 14px 8px;
  background: #f4faf7; border: 1px solid #c5ddd4;
  border-left: 4px solid var(--accent); border-radius: 0 12px 12px 0;
}
.example h4 { margin: 0 0 6px; color: var(--accent); font-size: 10.4pt; }

.recon {
  margin: 10px 0 14px; padding: 12px 14px 10px;
  background: #faf7f1; border: 1px solid var(--line); border-radius: 12px;
}
.recon > h3, .recon > h4 { margin-top: 0; }
.badge-recon {
  display: inline-block; font-size: 8pt; font-weight: 800;
  letter-spacing: 0.07em; text-transform: uppercase;
  background: #f3e0d2; color: #8a4b12;
  border-radius: 999px; padding: 2px 8px; margin: 0 0 8px;
}

.toc { columns: 2; column-gap: 28px; margin: 0; }
.toc ol { margin: 0; padding-left: 20px; }
.toc li { break-inside: avoid; margin: 0 0 8px; font-size: 11pt; line-height: 1.35; }
.readout { display: flex; flex-wrap: wrap; gap: 10px; margin: 0; }
.readout > div {
  flex: 1 1 42%; min-width: 0;
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 12px; padding: 12px 14px;
}
.readout h3 { margin: 0 0 4px; font-size: 10.5pt; font-family: var(--font); border: 0; padding: 0; }
.readout p { margin: 0; font-size: 10.2pt; color: #3f4a44; }
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Prism Prompts, Instructions and Workflows</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet" />
  <style>{css}</style>
</head>
<body>
<article class="handbook">
{body}
</article>
</body>
</html>
"""


def _browser(p):
    try:
        return p.chromium.launch(channel="chrome")
    except Exception:
        return p.chromium.launch()


def _card(label: str, body: str, *, flow: bool | None = None) -> str:
    text = body.strip()
    if flow is None:
        flow = text.count("\n") > 24 or len(text) > 1200
    lbl = html.escape(label)
    body_html = html.escape(text)
    if flow:
        return (
            f'<div class="prompt-card-flow"><span class="lbl">{lbl}</span>'
            f"<pre><code>{body_html}</code></pre></div>"
        )
    return f'<div class="prompt-card"><span class="lbl">{lbl}</span>{body_html}</div>'


def _live_payload() -> dict:
    dump = r"""
import json
import inspect
from types import SimpleNamespace
from prism.core.answer import SYSTEM_PROMPT, _build_user_prompt
from prism.core.titler import TITLE_SYSTEM_PROMPT
from prism.core.renderers.email import POLISH_SYSTEM_PROMPT, DE_HOSTILE_PROMPT
from prism.core.router import ANCHOR_PHRASES

chunk = SimpleNamespace(
    metadata={
        "title": "Finance Policy 2.1",
        "source_url": "data/synthetic/finance_policy.md",
        "domain": "finance",
    },
    text="Claims from Rs. 25,001 to Rs. 100,000 require Department Head and Reporting Manager sign-off.",
)
filled = _build_user_prompt(
    "Who approves a claim for exactly Rs. 25,001?",
    "finance",
    [chunk],
    extra_notes=["Example extra note for the PDF."],
)
print(json.dumps({
    "SYSTEM_PROMPT": SYSTEM_PROMPT,
    "USER_PROMPT_TEMPLATE": inspect.getsource(_build_user_prompt),
    "USER_PROMPT_FILLED": filled,
    "TITLE_SYSTEM_PROMPT": TITLE_SYSTEM_PROMPT,
    "POLISH_SYSTEM_PROMPT": POLISH_SYSTEM_PROMPT,
    "DE_HOSTILE_PROMPT": DE_HOSTILE_PROMPT,
    "ANCHOR_PHRASES": ANCHOR_PHRASES,
}))
"""
    backend = ROOT / "backend"
    r = subprocess.run(
        ["uv", "run", "--project", str(backend), "python", "-c", dump],
        cwd=str(backend),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"live prompt import failed:\n{r.stderr}")
    line = r.stdout.strip().splitlines()[-1]
    return json.loads(line)


def _anchors_html(phrases: dict) -> str:
    rows = []
    for domain, items in phrases.items():
        body = "\n".join(f"- {p}" for p in items)
        rows.append(_card(f"ANCHOR_PHRASES · {domain}", body))
    return "\n".join(rows)


def _extra_notes_html() -> str:
    text = (ROOT / "backend" / "prism" / "core" / "agent.py").read_text(encoding="utf-8")
    notes: list[str] = []
    # upload block
    if "Answer ONLY from those uploaded chunks" in text:
        notes.append(
            "Upload: Answer ONLY from those uploaded chunks. Do not use Kohler/Meridian "
            "enterprise knowledge bases unless the same fact appears in the upload."
        )
    for needle, label in [
        ("The latest message is a follow-up", "Anaphora follow-up"),
        ("The user asserted", "Leading number"),
        ("false or loaded premise", "Loaded privacy premise"),
        ("JSON fields that are NOT policy concepts", "Invented JSON fields"),
        ("contractor damage", "Contractor damage"),
        ("For termination leave payout", "Termination + leave"),
        ("YES OR NO ONLY", "Yes/no constraint"),
        ("manager email summarizing", "Session email"),
    ]:
        if needle in text:
            notes.append(f"{label}: present in agent.py (see extra_notes.append near retrieve).")
    body = "\n".join(f"- {n}" for n in notes)
    return _card("extra_notes detectors (live source: agent.py)", body)


def _inject_live(html_body: str, live: dict) -> str:
    repl = {
        "SYSTEM_PROMPT": _card("prism/core/answer.py · SYSTEM_PROMPT (live)", live["SYSTEM_PROMPT"]),
        "USER_PROMPT_TEMPLATE": (
            _card("prism/core/answer.py · _build_user_prompt (source)", live["USER_PROMPT_TEMPLATE"])
            + _card("Filled example (dummy Finance chunk)", live["USER_PROMPT_FILLED"])
        ),
        "TITLE_SYSTEM_PROMPT": _card("prism/core/titler.py · TITLE_SYSTEM_PROMPT (live)", live["TITLE_SYSTEM_PROMPT"]),
        "POLISH_SYSTEM_PROMPT": _card(
            "prism/core/renderers/email.py · POLISH_SYSTEM_PROMPT (off by default)",
            live["POLISH_SYSTEM_PROMPT"],
        ),
        "DE_HOSTILE_PROMPT": _card(
            "prism/core/renderers/email.py · DE_HOSTILE_PROMPT (off by default)",
            live["DE_HOSTILE_PROMPT"],
        ),
        "ANCHOR_PHRASES": _anchors_html(live["ANCHOR_PHRASES"]),
        "EXTRA_NOTES": _extra_notes_html(),
    }
    for key, block in repl.items():
        html_body = html_body.replace(f"<p><!-- LIVE:{key} --></p>", block)
        html_body = html_body.replace(f"<!-- LIVE:{key} -->", block)
    return html_body


def _wrap_examples(html_body: str) -> str:
    html_body = html_body.replace("<p><strong>Worked example.</strong>", "<h4>Worked example.</h4><p>")
    parts = re.split(r"(?=<h[2-4]\b)", html_body)
    out: list[str] = []
    for part in parts:
        if re.match(r"<h4[^>]*>Worked example", part):
            out.append(f'<section class="example">{part}</section>')
        else:
            out.append(part)
    return "".join(out)


def _wrap_sections(html_body: str) -> str:
    parts = re.split(r"(?=<h[23]\b)", html_body)
    out: list[str] = []
    for part in parts:
        if re.match(r"<h3\b", part):
            if re.match(r"<h3[^>]*>Reconstructed brief", part):
                out.append(
                    '<section class="recon"><span class="badge-recon">Reconstructed</span>'
                    f"{part}</section>"
                )
            else:
                out.append(f'<section class="subsec">{part}</section>')
        elif re.match(r"<h2\b", part):
            if "Contents</h2>" in part[:120] or "Table of contents" in part[:160]:
                out.append(part)
            else:
                out.append(f'<section class="chapter">{part}</section>')
        else:
            out.append(part)
    glued = "".join(out)
    return re.sub(
        r'(<section class="chapter"><h2 id="4-reconstructed-builder-briefs">[\s\S]*?</section>)\s*'
        r'(<section class="recon">[\s\S]*?</section>)',
        r'<div class="keep-start">\1\2</div>',
        glued,
        count=1,
    )


def _cover_and_toc(html_body: str) -> str:
    html_body = re.sub(r"<h1[^>]*>[\s\S]*?</h1>\s*", "", html_body, count=1)
    html_body = re.sub(
        r"<p><strong>Interview line:</strong>\s*([\s\S]*?)</p>",
        r'<blockquote class="pull">\1</blockquote>',
        html_body,
    )
    html_body = re.sub(
        r"^[\s\S]*?(?=<h2[^>]*>Table of contents</h2>)",
        "",
        html_body,
        count=1,
    )
    opening = """
<div class="opening">
<div class="cover">
  <p class="kicker">Kohler-MITWPU · Track 3 · Required prompts PDF</p>
  <h1>Prompts, instructions and workflows</h1>
  <p class="lede">How Prism was briefed, which models built it, and the exact strings Ollama sees on a turn. The workflow chip on every reply maps to a section here.</p>
  <div class="pills">
    <span class="pill">Builder briefs reconstructed</span>
    <span class="pill">Runtime prompts live from code</span>
    <span class="pill">Non-LLM gates first</span>
    <span class="pill">Cursor · Stitch · Ollama</span>
  </div>
</div>
"""
    readout = """
<div class="readout">
  <div><h3>Chip to chapter</h3><p>The UI chip is <code>ChatResponse.workflow</code>. Chapter 12 is the index.</p></div>
  <div><h3>Live strings</h3><p>System, title, email, and anchors are imported from Python at export time.</p></div>
  <div><h3>Reconstructed</h3><p>Builder briefs are labeled. They are not pasted chat logs.</p></div>
  <div><h3>File first</h3><p>Each heading names the module. The PDF is the map. The repo is the proof.</p></div>
</div>
</div>
"""
    html_body = re.sub(
        r"<h2[^>]*>Table of contents</h2>([\s\S]*?)(?=<hr\s*/?>|<h2)",
        lambda m: (
            opening
            + '<div class="toc-card"><h2>Contents</h2>\n<div class="toc">'
            + m.group(1)
            + "</div></div>\n"
            + readout
        ),
        html_body,
        count=1,
    )
    return html_body


def build_html() -> str:
    import markdown2

    text = MD.read_text(encoding="utf-8")
    text = text.replace("\u2014", " - ").replace("\u2013", "-")
    body = markdown2.markdown(text, extras=["tables", "fenced-code-blocks", "strike", "header-ids"])
    live = _live_payload()
    body = _inject_live(body, live)
    body = _wrap_examples(body)
    body = _cover_and_toc(body)
    body = _wrap_sections(body)
    return TEMPLATE.format(css=CSS, body=body)


def write_html() -> None:
    HTML_OUT.write_text(build_html(), encoding="utf-8")
    print(f"wrote {HTML_OUT}")


def _ensure_html() -> None:
    try:
        write_html()
    except ModuleNotFoundError:
        backend = ROOT / "backend"
        r = subprocess.run(
            ["uv", "run", "--project", str(backend), "python", str(Path(__file__).resolve()), "--write-html"],
            cwd=str(backend),
        )
        if r.returncode != 0:
            raise SystemExit("prompts HTML build failed (need markdown2 via backend uv)")


FOOTER_MM = 32.0
_CREAM = (1.0, 0.9961, 0.9843)
_INK = (0.247, 0.290, 0.267)
_LINE = (0.812, 0.784, 0.722)


def _stamp_footers(path: Path) -> None:
    """Paint an opaque footer band over Chromium bleed, then draw the chrome."""
    import fitz

    doc = fitz.open(path)
    n = doc.page_count
    footer_h = FOOTER_MM / 25.4 * 72
    inset = 16 / 25.4 * 72
    spacer = 8 / 25.4 * 72
    tmp = path.with_suffix(".stamped.pdf")
    for i, page in enumerate(doc):
        r = page.rect
        band = fitz.Rect(0, r.height - footer_h, r.width, r.height)
        shape = page.new_shape()
        shape.draw_rect(band)
        shape.finish(color=_CREAM, fill=_CREAM, width=0)
        y_line = r.height - footer_h + spacer
        shape.draw_line(fitz.Point(inset, y_line), fitz.Point(r.width - inset, y_line))
        shape.finish(color=_LINE, width=0.6)
        shape.commit()
        page.insert_text(
            fitz.Point(inset, y_line + 13),
            "Prompts and workflows",
            fontsize=9,
            fontname="times-roman",
            color=_INK,
        )
        label = f"{i + 1} / {n}"
        tw = fitz.get_text_length(label, fontname="times-roman", fontsize=9)
        page.insert_text(
            fitz.Point(r.width - inset - tw, y_line + 13),
            label,
            fontsize=9,
            fontname="times-roman",
            color=_INK,
        )
    doc.save(tmp, deflate=True, garbage=3)
    doc.close()
    tmp.replace(path)


def export_pdf() -> None:
    from playwright.sync_api import sync_playwright

    _ensure_html()
    PDF_OUT.parent.mkdir(parents=True, exist_ok=True)
    url = HTML_OUT.resolve().as_uri()
    with sync_playwright() as p:
        browser = _browser(p)
        page = browser.new_page(viewport={"width": 980, "height": 1380})
        page.goto(url, wait_until="networkidle")
        page.evaluate("() => document.fonts.ready")
        page.pdf(
            path=str(PDF_OUT),
            format="A4",
            print_background=True,
            prefer_css_page_size=True,
            display_header_footer=False,
            margin={"top": "14mm", "bottom": "32mm", "left": "16mm", "right": "16mm"},
        )
        browser.close()
    _stamp_footers(PDF_OUT)
    print(f"wrote {PDF_OUT} ({PDF_OUT.stat().st_size // 1024} KB)")


def preview_pages() -> None:
    from playwright.sync_api import sync_playwright

    PREVIEW.mkdir(parents=True, exist_ok=True)
    for old in PREVIEW.glob("page_*.png"):
        old.unlink()
    url = HTML_OUT.resolve().as_uri()
    with sync_playwright() as p:
        browser = _browser(p)
        page = browser.new_page(viewport={"width": 794, "height": 1123}, device_scale_factor=2)
        page.goto(url, wait_until="networkidle")
        page.evaluate("() => document.fonts.ready")
        page.emulate_media(media="print")
        dest = PREVIEW / "page_01.png"
        page.screenshot(path=str(dest), clip={"x": 0, "y": 0, "width": 794, "height": 1123})
        print(f"  preview {dest.name}")
        for name, sel in [
            ("page_02.png", "section.recon"),
            ("page_03.png", "div.prompt-card"),
        ]:
            el = page.query_selector(sel)
            if el:
                el.scroll_into_view_if_needed()
                el.screenshot(path=str(PREVIEW / name))
                print(f"  preview {name}")
        browser.close()


def main() -> None:
    if not MD.exists():
        raise SystemExit(f"missing {MD}")
    if "--write-html" in sys.argv:
        write_html()
        return
    export_pdf()
    if "--preview" in sys.argv or True:
        try:
            preview_pages()
        except Exception as exc:
            print(f"preview skipped ({exc!r})")


if __name__ == "__main__":
    main()
