"""Export docs/*.md to PDF via markdown2 + xhtml2pdf (pure Python, Windows-safe).

Run:
  uv run python -m scripts.export_pdfs
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown2
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xhtml2pdf import pisa

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = ROOT / "docs" / "pdf"

# Helvetica (xhtml2pdf's default) has no Rupee-sign glyph (U+20B9) -- every
# "\u20b9" figure was silently dropping from the PDF. xhtml2pdf's CSS
# @font-face resource loader is sandboxed to the project directory, so
# loading a system font via url() is blocked -- register it directly with
# reportlab (which xhtml2pdf renders through) instead, then just reference
# the family name in CSS. Segoe UI ships with Windows; swap the path if
# building on another OS.
_SEGOE = Path(r"C:\Windows\Fonts\arial.ttf")
_UNICODE_FONT = "Helvetica"
if _SEGOE.exists():
    pdfmetrics.registerFont(TTFont("PrismUnicode", str(_SEGOE)))
    _SEGOE_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")
    if _SEGOE_BOLD.exists():
        pdfmetrics.registerFont(TTFont("PrismUnicode-Bold", str(_SEGOE_BOLD)))
    # xhtml2pdf resolves font-family through reportlab's family map (which
    # covers normal/bold/italic/boldItalic) -- registerFont alone isn't
    # enough, it silently falls back to Helvetica without erroring.
    pdfmetrics.registerFontFamily(
        "PrismUnicode",
        normal="PrismUnicode",
        bold="PrismUnicode-Bold" if _SEGOE_BOLD.exists() else "PrismUnicode",
        italic="PrismUnicode",
        boldItalic="PrismUnicode-Bold" if _SEGOE_BOLD.exists() else "PrismUnicode",
    )
    _UNICODE_FONT = "PrismUnicode"

CSS = (
    """
@page { size: A4; margin: 1.6cm; }
body { font-family: '"""
    + _UNICODE_FONT
    + """'; font-size: 11pt; color: #1c2420; line-height: 1.45; }
h1 { font-size: 20pt; color: #0f5c4c; }
h2 { font-size: 14pt; color: #0f5c4c; margin-top: 1.2em; }
h3 { font-size: 12pt; }
code, pre { font-family: Courier, monospace; font-size: 9pt; }
pre { background: #f3efe6; padding: 8px; border: 1px solid #d5cebf; }
table { border-collapse: collapse; width: 100%; margin: 0.8em 0; }
th, td { border: 1px solid #d5cebf; padding: 6px 8px; vertical-align: top; }
th { background: #d7ebe4; }
blockquote { border-left: 3px solid #0f5c4c; margin-left: 0; padding-left: 10px; color: #4a554e; }
img.screenshot { max-width: 100%; border: 1px solid #d5cebf; margin: 0.6em 0; }
"""
)

# The visual jury deck, system handbook, and prompts PDF have their own exporters.


def md_to_pdf(md_path: Path, pdf_path: Path) -> None:
    text = md_path.read_text(encoding="utf-8")
    # Strip mermaid / overly complex fences for PDF friendliness
    text = re.sub(r"```mermaid[\s\S]*?```", "_([diagram omitted in PDF — see Markdown source])_", text)
    # xhtml2pdf/reportlab's TrueType text pipeline silently drops the Rupee
    # sign (U+20B9) even from fonts confirmed (via fontTools cmap) to contain
    # the glyph -- verified visually via a rasterized page render, not just
    # text extraction. Rather than depend on a fragile font-embedding
    # workaround, substitute an unambiguous ASCII form for the PDF export
    # only; the live UI and source Markdown keep the real symbol.
    text = text.replace("₹", "Rs.")
    # Resolve doc-relative image src to an absolute path so xhtml2pdf's
    # resource loader (sandboxed to the project dir, not CWD-relative) finds
    # it -- a bare relative src silently rendered as an empty broken-image box.
    text = re.sub(
        r'src="docs/([^"]+)"',
        lambda m: f'src="{(ROOT / "docs" / m.group(1)).as_posix()}"',
        text,
    )
    html_body = markdown2.markdown(text, extras=["tables", "fenced-code-blocks", "strike"])
    html = f"<html><head><meta charset='utf-8'/><style>{CSS}</style></head><body>{html_body}</body></html>"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with pdf_path.open("wb") as out:
        result = pisa.CreatePDF(html, dest=out, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"PDF export failed for {md_path}: {result.err}")
    print(f"wrote {pdf_path}")


def main() -> None:
    # deck.md / docs/pdf/deck.pdf are owned by scripts/export_deck.py
    # system_guide.md / docs/pdf/system_guide.pdf are owned by
    # scripts/export_system_guide.py
    targets = [
        DOCS / "architecture.md",
        DOCS / "decisions.md",
        DOCS / "demo_script.md",
    ]
    for md in targets:
        if md.exists():
            md_to_pdf(md, OUT / f"{md.stem}.pdf")


if __name__ == "__main__":
    main()
