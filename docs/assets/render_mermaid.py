"""Render Prism mermaid diagrams to SVG (vector) + PNG (markdown preview).

SVG is what the handbook PDF inlines so jury zoom stays sharp. htmlLabels
is off so node text is real SVG <text>, not foreignObject HTML that Chromium
rasters when printing.

  python docs/assets/render_mermaid.py
"""
from __future__ import annotations

import html
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

ASSETS = Path(__file__).resolve().parent
DIAGRAMS = [
    "diagram_architecture",
    "diagram_routing",
    "diagram_canonical_fanout",
    "diagram_turn_pipeline",
    "diagram_hybrid_retrieve",
    "diagram_clarify",
    "diagram_rbac",
    "diagram_ingest",
    "diagram_upload",
]

TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{ margin: 0; padding: 8px 12px; background: #ffffff; }}
    #out {{ display: inline-block; }}
  </style>
</head>
<body>
  <pre id="src" style="display:none">{definition}</pre>
  <div id="out"></div>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
    mermaid.initialize({{
      startOnLoad: false,
      theme: 'neutral',
      securityLevel: 'loose',
      htmlLabels: false,
      fontFamily: 'Segoe UI, Helvetica, Arial, sans-serif',
      flowchart: {{
        htmlLabels: false,
        curve: 'basis',
        padding: 16,
        nodeSpacing: 36,
        rankSpacing: 48,
        useMaxWidth: false,
        wrappingWidth: 400,
      }},
      themeVariables: {{
        fontSize: '18px',
        fontFamily: 'Segoe UI, Helvetica, Arial, sans-serif',
      }},
    }});
    const def = document.getElementById('src').textContent;
    const {{ svg }} = await mermaid.render('{svg_id}', def);
    const out = document.getElementById('out');
    out.innerHTML = svg;
    out.dataset.ready = '1';
  </script>
</body>
</html>
"""


def _svg_text_only(svg: str) -> str:
    """Replace mermaid foreignObject HTML labels with real SVG <text>.

    Chromium print-to-PDF rasters foreignObject, which kills zoom. SVG
    <text> stays a vector glyph in the handbook PDF.
    """

    def repl(m: re.Match) -> str:
        fo = m.group(0)
        parts = re.findall(r"<p[^>]*>(.*?)</p>", fo, flags=re.S)
        label = " ".join(re.sub(r"<[^>]+>", "", p).strip() for p in parts)
        label = html.unescape(label).strip()
        w = re.search(r'\bwidth="([\d.]+)"', fo)
        h = re.search(r'\bheight="([\d.]+)"', fo)
        width = float(w.group(1)) if w else 0.0
        height = float(h.group(1)) if h else 18.0
        return (
            f'<text x="{width / 2:.2f}" y="{height / 2 + 1:.2f}" '
            f'text-anchor="middle" dominant-baseline="central" '
            f'font-size="16" font-family="Segoe UI, Helvetica, Arial, sans-serif">'
            f"{html.escape(label)}</text>"
        )

    svg = re.sub(r"<foreignObject\b[\s\S]*?</foreignObject>", repl, svg)
    svg = re.sub(r"<filter\b[\s\S]*?</filter>", "", svg)
    svg = re.sub(r'\sfilter="url\([^)]+\)"', "", svg)
    return svg


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 2000, "height": 1400}, device_scale_factor=3)
        for name in DIAGRAMS:
            definition = (ASSETS / f"{name}.mmd").read_text(encoding="utf-8")
            html_path = ASSETS / f"_render_{name}.html"
            html_path.write_text(
                TEMPLATE.format(
                    definition=html.escape(definition),
                    svg_id=name.replace("-", "_"),
                ),
                encoding="utf-8",
            )
            page.goto(html_path.as_uri(), wait_until="networkidle")
            page.wait_for_selector("#out[data-ready='1']", timeout=60_000)
            svg = page.evaluate("() => document.querySelector('#out').innerHTML")
            svg = _svg_text_only(svg)
            svg_path = ASSETS / f"{name}.svg"
            svg_path.write_text(svg, encoding="utf-8")
            png = ASSETS / f"{name}.png"
            page.locator("#out").screenshot(path=str(png), type="png")
            print(f"wrote {svg_path.name} ({svg_path.stat().st_size} B) + {png.name}")
        browser.close()


if __name__ == "__main__":
    main()
