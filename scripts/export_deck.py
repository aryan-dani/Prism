"""Export the landscape jury deck as a high-DPI PDF.

Primary path: 3x lossless PNG screenshots packed with img2pdf
(true PNG embed, 432 DPI on a 13.333in x 7.5in page). Type stays
sharp on zoom; product shots are not JPEG-downsampled.

Preview PNGs land in docs/assets/_deck_preview/ (gitignored).

    python scripts/export_deck.py
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs" / "assets" / "deck.html"
OUT = ROOT / "docs" / "pdf" / "deck.pdf"
PREVIEW = ROOT / "docs" / "assets" / "_deck_preview"


def _browser(p):
    try:
        return p.chromium.launch(channel="chrome")
    except Exception:
        return p.chromium.launch()


def _screenshot_slides() -> list[Path]:
    from playwright.sync_api import sync_playwright

    PREVIEW.mkdir(parents=True, exist_ok=True)
    for old in PREVIEW.glob("slide_*.png"):
        old.unlink()

    url = HTML.resolve().as_uri()
    pngs: list[Path] = []
    with sync_playwright() as p:
        browser = _browser(p)
        page = browser.new_page(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=3,
        )
        page.goto(url, wait_until="networkidle")
        page.evaluate("() => document.fonts.ready")
        page.wait_for_function(
            "() => [...document.images].every(i => i.complete && i.naturalWidth > 0)",
            timeout=15000,
        )
        page.wait_for_timeout(400)
        slides = page.query_selector_all(".slide")
        if len(slides) != 10:
            raise SystemExit(f"expected 10 slides, found {len(slides)}")
        for i, slide in enumerate(slides, 1):
            dest = PREVIEW / f"slide_{i:02d}.png"
            slide.screenshot(path=str(dest), type="png")
            pngs.append(dest)
            print(f"  captured {dest.name}")
        browser.close()
    return pngs


def _pack_png_pdf(pngs: list[Path]) -> None:
    packer = r"""
from pathlib import Path
import img2pdf
pngs = %s
out = Path(%s)
out.parent.mkdir(parents=True, exist_ok=True)
page_w, page_h = 13.333 * 72, 7.5 * 72
def layout(imgwidthpx, imgheightpx, ndpi):
    return page_w, page_h, page_w, page_h
with open(out, "wb") as f:
    f.write(img2pdf.convert(pngs, layout_fun=layout))
print(f"packed {out} ({out.stat().st_size // 1024} KB)")
""" % (repr([str(p) for p in pngs]), repr(str(OUT)))
    backend = ROOT / "backend"
    r = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(backend),
            "--with",
            "img2pdf",
            "python",
            "-c",
            packer,
        ],
        cwd=str(ROOT),
    )
    if r.returncode != 0:
        raise SystemExit("PDF pack failed")


def main() -> None:
    if not HTML.exists():
        raise SystemExit(f"missing deck HTML: {HTML}")
    print("capturing 10 slides at 3x lossless PNG ...")
    pngs = _screenshot_slides()
    print("packing PNG pages with img2pdf (432 DPI, lossless) ...")
    _pack_png_pdf(pngs)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
