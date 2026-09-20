"""Export the system handbook as a designed A4 PDF (Chromium print).

Unlike scripts/export_pdfs.py (xhtml2pdf — ignores max-width, blows diagrams
up to full pages), this path uses the same Playwright + print-CSS approach as
the jury deck so type stays vector and figures stay constrained.

  python scripts/export_system_guide.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
MD = DOCS / "system_guide.md"
HTML_OUT = ASSETS / "_system_guide.html"
PDF_OUT = DOCS / "pdf" / "system_guide.pdf"

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
  font-size: 11.15pt;
  line-height: 1.5;
  font-optical-sizing: auto;
  -webkit-font-smoothing: antialiased;
  orphans: 2;
  widows: 2;
}
@page { size: A4; margin: 14mm 16mm 26mm 16mm; }

.handbook { max-width: 100%; width: 100%; padding-bottom: 4px; }

/* Flow like a printed book. A heading never sits alone at the bottom. */
.chapter, .subsec {
  break-inside: auto;
  page-break-inside: auto;
}
h2, h3, h4 {
  break-after: avoid;
  page-break-after: avoid;
}
.example {
  break-inside: auto;
  page-break-inside: auto;
}
.example > h4, .example > :first-child {
  break-after: avoid;
  page-break-after: avoid;
}
.closing {
  break-inside: avoid;
  page-break-inside: avoid;
}

/* Cards share the content column. No full-bleed chrome. */
.opening { width: 100%; }
.cover {
  width: 100%;
  margin: 0 0 14px;
  padding: 20px 22px 18px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background:
    radial-gradient(circle at 0% 0%, rgba(15, 92, 76, 0.12), transparent 48%),
    linear-gradient(165deg, #f4f0e8, #faf7f1);
}
.cover .kicker {
  font-family: var(--font);
  font-size: 9pt;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 10px;
}
.cover h1 {
  font-family: var(--display);
  font-weight: 400;
  font-size: 32pt;
  line-height: 1.05;
  letter-spacing: -0.02em;
  color: #16201c;
  margin: 0 0 12px;
  border: 0;
  padding: 0;
}
.cover .lede {
  font-size: 11.5pt;
  line-height: 1.45;
  color: #3f4a44;
  margin: 0 0 12px;
  max-width: none;
}
.cover .pills { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; }
.cover .pill {
  background: var(--wash);
  color: var(--accent);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 8.5pt;
  font-weight: 650;
}
.toc-card {
  width: 100%;
  margin: 0 0 14px;
  padding: 12px 20px 10px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: var(--panel);
}
.toc-card > h2 {
  margin-top: 0;
  padding-top: 2px;
}

/* ── Type ── */
h1 {
  font-family: var(--display);
  font-size: 22pt; font-weight: 400;
  color: #16201c; margin: 0 0 8px;
}
h2 {
  font-family: var(--display);
  font-size: 17.5pt; font-weight: 400;
  color: var(--accent);
  margin: 12px 0 8px;
  padding: 4px 0 4px;
  border-bottom: 1.5px solid #cfe3dc;
  page-break-before: auto;
  page-break-after: auto;
  break-after: auto;
}
h3 {
  font-size: 12.2pt; font-weight: 700;
  color: #0f5c4c; margin: 14px 0 7px;
  page-break-after: avoid; break-after: avoid;
}
h4 {
  font-size: 11pt; font-weight: 700;
  color: #16362e; margin: 10px 0 5px;
  page-break-after: avoid; break-after: avoid;
}
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
pre {
  background: #1c2420; color: #e8efe9;
  border-radius: 10px; padding: 10px 12px;
  font-family: Consolas, monospace;
  font-size: 8.2pt; line-height: 1.4;
  white-space: pre-wrap;
  margin: 0 0 10px;
  break-inside: avoid; page-break-inside: avoid;
}
pre code { background: none; color: inherit; padding: 0; }
blockquote {
  margin: 8px 0 10px;
  padding: 8px 12px;
  border-left: 3px solid var(--accent);
  background: var(--panel);
  color: #3f4a44;
  border-radius: 0 10px 10px 0;
  break-inside: avoid; page-break-inside: avoid;
}
blockquote.pull {
  font-family: var(--display);
  font-size: 12.5pt;
  line-height: 1.28;
  color: #16201c;
  background: var(--wash);
}

/* ── Tables ── */
table {
  width: 100%;
  border-collapse: collapse;
  margin: 6px 0 10px;
  font-size: 9.3pt;
  background: var(--panel);
}
table {
  break-inside: avoid;
  page-break-inside: avoid;
}
thead { break-after: avoid; page-break-after: avoid; }
tr { break-inside: auto; page-break-inside: auto; }
th, td {
  border: 1px solid var(--line);
  padding: 6px 8px;
  vertical-align: top;
  text-align: left;
}
th {
  background: #d7ebe4;
  color: var(--accent);
  font-weight: 750;
  font-size: 8pt;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
tr:nth-child(even) td { background: #f3efe6; }

/* ── Figures ── */
.fig {
  margin: 4px 0 8px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 8px 10px 6px;
  break-inside: avoid;
  page-break-inside: avoid;
}
.fig img, .fig svg {
  display: block;
  margin: 0 auto;
  width: 100%;
  height: auto;
  max-width: 100%;
  object-fit: contain;
}
.fig-diagram svg, .fig-diagram img { max-height: 188px; }
.fig-diagram svg text { fill: #1c2420; }
.fig-shot img { max-height: 156px; object-fit: contain; background: #f3efe6; border-radius: 6px; }
.with-fig, .keep-head {
  break-inside: avoid;
  page-break-inside: avoid;
}
.with-fig.pair .fig-diagram svg,
.with-fig.pair .fig-diagram img { max-height: 132px; }
.fig figcaption {
  margin: 5px 2px 0;
  font-size: 8pt;
  font-weight: 550;
  color: var(--muted);
  text-align: center;
}
.fig-row {
  display: flex;
  gap: 10px;
  align-items: stretch;
  margin: 6px 0 10px;
  break-inside: avoid;
  page-break-inside: avoid;
}
.fig-row .fig { flex: 1; margin: 0; min-width: 0; }
.fig-row .fig-diagram svg, .fig-row .fig-diagram img { max-height: 210px; }

/* ── Worked examples ── */
.example {
  margin: 6px 0 8px;
  padding: 8px 12px 6px;
  background: #f4faf7;
  border: 1px solid #c5ddd4;
  border-left: 4px solid var(--accent);
  border-radius: 0 12px 12px 0;
}
.example h4 {
  margin: 0 0 6px;
  color: var(--accent);
  font-size: 10.2pt;
}
.example table { margin-bottom: 6px; }
.example > :last-child { margin-bottom: 2px; }

.toc {
  columns: 2;
  column-gap: 28px;
  margin: 0;
  width: 100%;
}
.toc ol { margin: 0; padding-left: 20px; }
.toc li { break-inside: avoid; margin: 0 0 8px; font-size: 11pt; line-height: 1.35; }
.readout {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 0;
  width: 100%;
}
.readout > div {
  flex: 1 1 42%;
  min-width: 0;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
}
.readout h3 {
  margin: 0 0 4px;
  font-size: 10.5pt;
  font-family: var(--font);
  border: 0;
  padding: 0;
}
.readout p { margin: 0; font-size: 10.2pt; color: #3f4a44; }
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Prism System Handbook</title>
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


def _abs_asset(src: str) -> Path:
    raw = src.strip()
    if raw.startswith("docs/"):
        path = ROOT / raw
    elif raw.startswith("assets/"):
        path = DOCS / raw
    else:
        path = ASSETS / Path(raw).name
    return path if path.exists() else ASSETS / Path(raw).name


def _prepare_svg(path: Path, slug: str) -> str:
    """Inline mermaid SVG so Chromium print keeps paths/text as vectors.

    Do not rewrite fragment ids. Mermaid CSS is keyed to the render id,
    and a naive '#diagram' replace poisons '#diagram_architecture'.
    """
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"<\?xml[^>]*\?>", "", raw).strip()
    _ = slug

    def fix_open(m: re.Match) -> str:
        tag = m.group(0)
        tag = re.sub(r'\swidth="[^"]*"', "", tag)
        tag = re.sub(r'\sheight="[^"]*"', "", tag)
        if re.search(r'\sclass="', tag):
            tag = re.sub(r'\sclass="([^"]*)"', r' class="diagram-svg \1"', tag, count=1)
        else:
            tag = tag.replace("<svg", '<svg class="diagram-svg"', 1)
        if "preserveAspectRatio=" not in tag:
            tag = tag.replace("<svg", '<svg preserveAspectRatio="xMidYMid meet"', 1)
        tag = tag.replace("<svg", '<svg width="100%"', 1)
        return tag

    return re.sub(r"<svg\b[^>]*>", fix_open, raw, count=1)


def _wrap_images(html: str) -> str:
    def one(m: re.Match) -> str:
        tag = m.group(0)
        src_m = re.search(r'src="([^"]+)"', tag)
        alt_m = re.search(r'alt="([^"]*)"', tag)
        path = _abs_asset(src_m.group(1)) if src_m else ASSETS / "missing.png"
        alt = alt_m.group(1) if alt_m else ""
        kind = "fig-shot" if "screenshot" in path.name else "fig-diagram"
        svg_path = path.with_suffix(".svg")
        if kind == "fig-diagram" and svg_path.exists():
            inner = _prepare_svg(svg_path, path.stem.replace("-", "_"))
        else:
            inner = f'<img src="{path.name}" alt="{alt}" />'
        return (
            f'<figure class="fig {kind}">'
            f"{inner}"
            f"<figcaption>{alt}</figcaption>"
            f"</figure>"
        )

    html = re.sub(r"<p>\s*(<img\b[^>]*>)\s*</p>", r"\1", html)
    html = re.sub(r"<img\b[^>]*>", one, html)
    return html


def _wrap_examples(html: str) -> str:
    html = re.sub(
        r"<p><strong>(Worked example[^<]*)</strong></p>",
        r"<h4>\1</h4>",
        html,
    )
    parts = re.split(r"(?=<h[2-4]\b)", html)
    out: list[str] = []
    for part in parts:
        if re.match(r"<h4[^>]*>Worked example", part):
            out.append(f'<section class="example">{part}</section>')
        else:
            out.append(part)
    return "".join(out)


def _wrap_sections(html: str) -> str:
    """Group headings for styling. Pages flow; headings stay with the next block."""
    parts = re.split(r"(?=<h[23]\b)", html)
    out: list[str] = []
    for part in parts:
        if re.match(r"<h3\b", part):
            out.append(f'<section class="subsec">{part}</section>')
        elif re.match(r"<h2\b", part):
            head = part[:120]
            if "Contents</h2>" in head or "Table of contents" in head:
                out.append(part)
                continue
            if "Closing:" in head:
                rest_idx = parts.index(part)
                out.append(
                    '<section class="closing">' + "".join(parts[rest_idx:]) + "</section>"
                )
                break
            out.append(f'<section class="chapter">{part}</section>')
        else:
            out.append(part)
    html = "".join(out)
    html = re.sub(
        r'<section class="chapter">(<h2[^>]*>[\s\S]*?</h2>)\s*</section>\s*'
        r'<section class="subsec">',
        r'<section class="subsec">\1',
        html,
    )
    return _glue_heading_figures(html)


def _glue_heading_figures(html: str) -> str:
    """Keep a heading with the figure that follows it. Never scan inside SVGs."""
    heading_re = re.compile(r"<h[234]\b[^>]*>[\s\S]*?</h[234]>")
    h3_re = re.compile(r"<h3\b[^>]*>[\s\S]*?</h3>")
    fig_re = re.compile(r'<figure class="fig\b[^"]*"[^>]*>[\s\S]*?</figure>')
    p_re = re.compile(
        r"<p>(?:[^<]|<(?:strong|em|code|a|/strong|/em|/code|/a)\b[^>]*>)*</p>"
    )

    out: list[str] = []
    i = 0
    while True:
        m = heading_re.search(html, i)
        if not m:
            out.append(html[i:])
            break
        out.append(html[i : m.start()])
        head = m.group(0)
        if "Contents</h2>" in head or "Table of contents" in head:
            out.append(head)
            i = m.end()
            continue

        cursor = m.end()
        p_at = cursor + re.match(r"\s*", html[cursor:]).end()
        pm = p_re.match(html, p_at)
        lead = html[cursor:pm.end()] if pm else ""
        fig_at = pm.end() if pm else cursor

        figs: list[str] = []
        pos = fig_at + re.match(r"\s*", html[fig_at:]).end()
        while len(figs) < 2:
            fm = fig_re.match(html, pos)
            if not fm:
                break
            figs.append(fm.group(0))
            pos = fm.end() + re.match(r"\s*", html[fm.end() :]).end()

        if figs:
            cls = "with-fig pair" if len(figs) > 1 else "with-fig"
            out.append(f'<div class="{cls}">{head}{lead}{"".join(figs)}</div>')
            i = pos
            continue

        # Chapter title sitting on the last line, subsection on the next page.
        if head.startswith("<h2"):
            h3_at = (pm.end() if pm else m.end()) + re.match(
                r"\s*", html[(pm.end() if pm else m.end()) :]
            ).end()
            h3m = h3_re.match(html, h3_at)
            if h3m:
                p2_at = h3m.end() + re.match(r"\s*", html[h3m.end() :]).end()
                p2 = p_re.match(html, p2_at)
                chunk = head + lead + html[(pm.end() if pm else m.end()) : (p2.end() if p2 else h3m.end())]
                out.append(f'<div class="keep-head">{chunk}</div>')
                i = p2.end() if p2 else h3m.end()
                continue

        if pm:
            out.append(f'<div class="keep-head">{head}{lead}</div>')
            i = pm.end()
        else:
            out.append(head)
            i = m.end()
    return "".join(out)


def _cover_and_toc(html: str) -> str:
    html = re.sub(r"<h1[^>]*>[\s\S]*?</h1>\s*", "", html, count=1)
    html = re.sub(
        r"<p><strong>Interview line:</strong>\s*“([\s\S]*?)”</p>",
        r'<blockquote class="pull">\1</blockquote>',
        html,
    )
    html = re.sub(
        r"<p><strong>Interview line:</strong>\s*([\s\S]*?)</p>",
        r'<blockquote class="pull">\1</blockquote>',
        html,
    )

    # Drop the markdown title/intro so it does not reprint under the masthead.
    html = re.sub(
        r"^[\s\S]*?(?=<h2[^>]*>Table of contents</h2>)",
        "",
        html,
        count=1,
    )

    opening = """
<div class="opening">
<div class="cover">
  <p class="kicker">Kohler-MITWPU · Track 3 · Interview handbook</p>
  <h1>Prism System Handbook</h1>
  <p class="lede">From the case-study brief to every subsystem, with a concrete query and what Prism actually says or does. Teaching pass, not the 4-slide jury pitch.</p>
  <div class="pills">
    <span class="pill">Five domains + uploads</span>
    <span class="pill">CanonicalAnswer to five formats</span>
    <span class="pill">RBAC at retrieval</span>
    <span class="pill">Local, 8GB VRAM</span>
  </div>
</div>
"""
    readout = """
<div class="readout">
  <div><h3>Build order</h3><p>Chapters follow how the project was actually built, not a generic RAG textbook outline.</p></div>
  <div><h3>Worked examples</h3><p>Each major idea shows what you type, which gate fires, and what Prism says or does.</p></div>
  <div><h3>File paths</h3><p><code>agent.py</code>, <code>router.py</code>, <code>rbac.py</code> and the rest are there so you can open the module in an interview.</p></div>
  <div><h3>File first</h3><p>When a judge asks how, open the path in the heading. The PDF is the map, the repo is the proof.</p></div>
</div>
</div>
"""
    html = re.sub(
        r"<h2[^>]*>Table of contents</h2>([\s\S]*?)(?=<hr\s*/?>|<h2)",
        lambda m: (
            opening
            + '<div class="toc-card"><h2>Contents</h2>\n<div class="toc">'
            + m.group(1)
            + "</div></div>\n"
            + readout
        ),
        html,
        count=1,
    )
    return html


def build_html() -> str:
    import markdown2

    text = MD.read_text(encoding="utf-8")
    text = text.replace("\u2014", " - ").replace("\u2013", "-")
    body = markdown2.markdown(text, extras=["tables", "fenced-code-blocks", "strike", "header-ids"])
    body = _wrap_images(body)
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
            cwd=str(ROOT),
        )
        if r.returncode != 0:
            raise SystemExit("handbook HTML build failed (need markdown2 via backend uv)")


def _chrome(kind: str) -> str:
    """Footer only. Georgia embeds in the PDF; Google Fonts do not load here."""
    if kind == "header":
        return "<div></div>"
    return (
        "<style>html,body{margin:0;padding:0;width:100%}</style>"
        '<div style="width:100%;height:100%;box-sizing:border-box;padding:0 16mm 8px;'
        "font-family:Georgia,'Times New Roman',serif;font-size:10pt;"
        "letter-spacing:0.02em;color:#3f4a44;display:flex;align-items:flex-end;"
        'justify-content:space-between;">'
        "<span>System guide</span>"
        '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
    )


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
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=_chrome("footer"),
            margin={"top": "14mm", "bottom": "26mm", "left": "16mm", "right": "16mm"},
        )
        browser.close()
    print(f"wrote {PDF_OUT} ({PDF_OUT.stat().st_size // 1024} KB)")


def main() -> None:
    if not MD.exists():
        raise SystemExit(f"missing {MD}")
    if "--write-html" in sys.argv:
        write_html()
        return
    export_pdf()


if __name__ == "__main__":
    main()
