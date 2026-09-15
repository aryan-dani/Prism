"""Export docs/*.md to PDF via markdown2 + xhtml2pdf (pure Python, Windows-safe).

Run:
  uv run python -m scripts.export_pdfs
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown2
from xhtml2pdf import pisa

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = ROOT / "docs" / "pdf"

CSS = """
@page { size: A4; margin: 1.6cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 11pt; color: #1c2420; line-height: 1.45; }
h1 { font-size: 20pt; color: #0f5c4c; }
h2 { font-size: 14pt; color: #0f5c4c; margin-top: 1.2em; }
h3 { font-size: 12pt; }
code, pre { font-family: Courier, monospace; font-size: 9pt; }
pre { background: #f3efe6; padding: 8px; border: 1px solid #d5cebf; }
table { border-collapse: collapse; width: 100%; margin: 0.8em 0; }
th, td { border: 1px solid #d5cebf; padding: 6px 8px; vertical-align: top; }
th { background: #d7ebe4; }
blockquote { border-left: 3px solid #0f5c4c; margin-left: 0; padding-left: 10px; color: #4a554e; }
"""


def md_to_pdf(md_path: Path, pdf_path: Path) -> None:
    text = md_path.read_text(encoding="utf-8")
    # Strip mermaid / overly complex fences for PDF friendliness
    text = re.sub(r"```mermaid[\s\S]*?```", "_([diagram omitted in PDF — see Markdown source])_", text)
    html_body = markdown2.markdown(text, extras=["tables", "fenced-code-blocks", "strike"])
    html = f"<html><head><meta charset='utf-8'/><style>{CSS}</style></head><body>{html_body}</body></html>"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with pdf_path.open("wb") as out:
        result = pisa.CreatePDF(html, dest=out, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"PDF export failed for {md_path}: {result.err}")
    print(f"wrote {pdf_path}")


def main() -> None:
    targets = [
        DOCS / "architecture.md",
        DOCS / "prompts.md",
        DOCS / "decisions.md",
        DOCS / "demo_script.md",
        DOCS / "deck.md",
    ]
    for md in targets:
        if md.exists():
            md_to_pdf(md, OUT / f"{md.stem}.pdf")


if __name__ == "__main__":
    main()
