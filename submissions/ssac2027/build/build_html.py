#!/usr/bin/env python
"""Build submissions/ssac2027/build/abstract.html from the filled abstract and the two
chosen exhibits, for render.mjs to print as abstract.pdf.

Reads: abstract/ssac2027_abstract.filled.md, abstract/exhibits/chosen.txt and, for each
chosen exhibit, its PNG, caption.md and alt.txt. The PNGs are embedded as base64 so the
page is self-contained. No author metadata is written anywhere in the page.

Usage, from the repository root:
  python submissions/ssac2027/build/build_html.py
  node submissions/ssac2027/build/render.mjs \
      "$PWD/submissions/ssac2027/build/abstract.html" "$PWD/submissions/ssac2027/abstract.pdf"
"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FILLED = ROOT / "abstract" / "ssac2027_abstract.filled.md"
CHOSEN = ROOT / "abstract" / "exhibits" / "chosen.txt"
OUT = Path(__file__).resolve().parent / "abstract.html"

STYLE = """
@page { size: Letter; margin: 1in; }
body { font-family: Georgia, 'Times New Roman', serif; font-size: 10.5pt; line-height: 1.34;
  color: #111; }
h1 { font-size: 15pt; line-height: 1.25; margin: 0 0 10pt 0; font-weight: 700; }
h2 { font-size: 11pt; margin: 12pt 0 4pt 0; font-weight: 700; }
p { margin: 0 0 6pt 0; }
figure { margin: 12pt 0 8pt 0; page-break-inside: avoid; }
figure:first-of-type { page-break-before: always; margin-top: 0; }
figure img { width: 6.5in; display: block; }
figcaption { font-size: 9.5pt; line-height: 1.3; color: #222; margin-top: 4pt; }"""


def body_html(md: str) -> tuple[str, str]:
    title = ""
    parts: list[str] = []
    for block in re.split(r"\n{2,}", md.strip()):
        if block.startswith("# "):
            title = block[2:].strip()
            parts.append(f"<h1>{html.escape(title)}</h1>")
        elif block.startswith("## "):
            parts.append(f"<h2>{html.escape(block[3:].strip())}</h2>")
        else:
            parts.append(f"<p>{html.escape(' '.join(block.split()))}</p>")
    return title, "".join(parts)


def figure_html(folder: Path) -> str:
    # The exhibit and its caption are one image (exhibit-with-caption.png, written by
    # bake_captions.mjs), so the upload's text layer holds only the abstract's words.
    png = folder / f"{folder.name}.png"
    baked = Path(__file__).resolve().parent / f"{folder.name}-with-caption.png"
    src = baked if baked.exists() else png
    data = base64.b64encode(src.read_bytes()).decode("ascii")
    caption = " ".join((folder / "caption.md").read_text().split())
    alt = " ".join((folder / "alt.txt").read_text().split())
    if baked.exists():
        alt_all = html.escape(alt + " " + caption, quote=True)
        return f'<figure><img src="data:image/png;base64,{data}" alt="{alt_all}"></figure>'
    return (
        f'<figure><img src="data:image/png;base64,{data}" alt="{html.escape(alt, quote=True)}">'
        f"<figcaption>{html.escape(caption)}</figcaption></figure>"
    )


def main() -> None:
    title, body = body_html(FILLED.read_text())
    chosen = [
        line.split()[1]
        for line in CHOSEN.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    figures = "".join(figure_html(ROOT / "abstract" / "exhibits" / name) for name in chosen)
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title><style>{STYLE}</style></head>"
        f"<body>{body}{figures}</body></html>"
    )
    OUT.write_text(page)
    n = figures.count("<figure>")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(page):,} bytes, {n} exhibit(s))")


if __name__ == "__main__":
    main()
