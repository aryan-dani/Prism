"""Render Prism mermaid diagrams to PNG via system Chrome + Mermaid CDN."""
from __future__ import annotations

import html
from pathlib import Path

from playwright.sync_api import sync_playwright

ASSETS = Path(__file__).resolve().parent
DIAGRAMS = [
    "diagram_architecture",
    "diagram_routing",
    "diagram_canonical_fanout",
]

TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{ margin: 0; padding: 32px; background: #ffffff; }}
    #out {{ display: inline-block; }}
  </style>
</head>
<body>
  <pre id="src" style="display:none">{definition}</pre>
  <div id="out"></div>
  <script type="module">
    import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
    mermaid.initialize({{ startOnLoad: false, theme: 'neutral', securityLevel: 'loose' }});
    const def = document.getElementById('src').textContent;
    const {{ svg }} = await mermaid.render('diagram', def);
    const out = document.getElementById('out');
    out.innerHTML = svg;
    out.dataset.ready = '1';
  </script>
</body>
</html>
"""


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1200}, device_scale_factor=2)
        for name in DIAGRAMS:
            definition = (ASSETS / f"{name}.mmd").read_text(encoding="utf-8")
            html_path = ASSETS / f"_render_{name}.html"
            html_path.write_text(
                TEMPLATE.format(definition=html.escape(definition)),
                encoding="utf-8",
            )
            page.goto(html_path.as_uri(), wait_until="networkidle")
            page.wait_for_selector("#out[data-ready='1']", timeout=60_000)
            out = page.locator("#out")
            png = ASSETS / f"{name}.png"
            out.screenshot(path=str(png), type="png")
            print(f"wrote {png} ({png.stat().st_size} bytes)")
        browser.close()


if __name__ == "__main__":
    main()
