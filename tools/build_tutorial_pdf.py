#!/usr/bin/env python3
"""Render a docs/tutorial Markdown file (with its screenshots) to PDF.

Only the small Markdown subset the tutorials use is supported: ``#``/``##``
headings, paragraphs, ``-`` and ``1.`` lists (one nesting level), ``>`` notes,
pipe tables, ``![caption](path)`` images, ``**bold**`` and ```code```.

Needs reportlab and Pillow (BSD/HPND; documentation tooling only, not a
workbench dependency). Example:

    python3 -m venv /tmp/pdfenv && /tmp/pdfenv/bin/pip install reportlab pillow
    /tmp/pdfenv/bin/python tools/build_tutorial_pdf.py docs/tutorial/finger-jointed-box.md

Regenerate the screenshots first with
``python3 tools/run_freecad_tests.py --gui-script tests/gui/tutorial_finger_box.py``.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FONT_CANDIDATES = [
    # (regular, bold, italic) — any TTF with arrows/minus/multiply glyphs.
    ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", None, None),
    ("/Library/Fonts/Arial Unicode.ttf", None, None),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
]
MONO_CANDIDATES = ["/System/Library/Fonts/Supplemental/Courier New.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]

ACCENT = colors.HexColor("#2f5d8a")
MUTED = colors.HexColor("#5b6470")
RULE = colors.HexColor("#d5dbe2")
NOTE_BG = colors.HexColor("#eef3f8")
CODE_BG = "#eef0f3"


def register_fonts():
    body = bold = italic = "Helvetica"
    bold, italic = "Helvetica-Bold", "Helvetica-Oblique"
    for regular, bold_path, italic_path in FONT_CANDIDATES:
        if os.path.exists(regular):
            pdfmetrics.registerFont(TTFont("Body", regular))
            body = "Body"
            bold = italic = "Body"
            supplemental = os.path.dirname(regular)
            b = bold_path or os.path.join(supplemental, "Arial Bold.ttf")
            i = italic_path or os.path.join(supplemental, "Arial Italic.ttf")
            if os.path.exists(b):
                pdfmetrics.registerFont(TTFont("BodyBold", b))
                bold = "BodyBold"
            if os.path.exists(i):
                pdfmetrics.registerFont(TTFont("BodyItalic", i))
                italic = "BodyItalic"
            pdfmetrics.registerFontFamily("Body", normal=body, bold=bold, italic=italic, boldItalic=bold)
            break
    mono = "Courier"
    for path in MONO_CANDIDATES:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont("Mono", path))
            mono = "Mono"
            break
    return body, bold, italic, mono


BODY, BOLD, ITALIC, MONO = register_fonts()

STYLES = {
    "title": ParagraphStyle("title", fontName=BOLD, fontSize=24, leading=29, textColor=ACCENT, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName=BOLD, fontSize=15, leading=19, textColor=ACCENT, spaceBefore=14, spaceAfter=6),
    "body": ParagraphStyle("body", fontName=BODY, fontSize=10.5, leading=14.5, spaceAfter=6),
    "note": ParagraphStyle("note", fontName=BODY, fontSize=9.5, leading=13, textColor=colors.HexColor("#27394d")),
    "caption": ParagraphStyle("caption", fontName=ITALIC, fontSize=9, leading=12, textColor=MUTED, alignment=TA_CENTER, spaceBefore=3, spaceAfter=10),
    "cell": ParagraphStyle("cell", fontName=BODY, fontSize=9, leading=11.5),
    "head": ParagraphStyle("head", fontName=BOLD, fontSize=9, leading=11.5, textColor=colors.white),
}


def inline(text: str) -> str:
    """Markdown inline markup -> reportlab paragraph markup."""
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(f'<font face="{MONO}" backColor="{CODE_BG}">{html.escape(part[1:-1])}</font>')
        else:
            esc = html.escape(part)
            esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
            esc = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", esc)
            # Unicode subscript digits (CO₂) have no glyph in most fonts; use real subscripts.
            esc = re.sub("[₀-₉]+", lambda m: "<sub>" + "".join(str(ord(c) - 0x2080) for c in m.group()) + "</sub>", esc)
            out.append(esc)
    return "".join(out)


def image_flowable(path: Path, caption: str, width: float, max_height: float):
    with PILImage.open(path) as im:
        w, h = im.size
    scale = min(width / w, max_height / h)
    img = Image(str(path), width=w * scale, height=h * scale)
    img.hAlign = "CENTER"
    return KeepTogether([img, Paragraph(inline(caption), STYLES["caption"])])


def table_flowable(rows, width):
    header, *body = rows
    data = [[Paragraph(inline(c), STYLES["head"]) for c in header]]
    data += [[Paragraph(inline(c), STYLES["cell"]) for c in row] for row in body]
    table = Table(data, colWidths=[width / len(header)] * len(header), repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
                ("GRID", (0, 0), (-1, -1), 0.4, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [table, Spacer(1, 8)]


def note_flowable(text, width):
    box = Table([[Paragraph(inline(text), STYLES["note"])]], colWidths=[width])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NOTE_BG),
                ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return [box, Spacer(1, 8)]


def list_flowable(items, ordered):
    """items: [(text, [subitem texts])]"""
    flow_items = []
    for text, subs in items:
        content = [Paragraph(inline(text), STYLES["body"])]
        if subs:
            content.append(
                ListFlowable(
                    [ListItem(Paragraph(inline(s), STYLES["body"]), leftIndent=12) for s in subs],
                    bulletType="bullet",
                    start="–",
                    leftIndent=12,
                    bulletFontName=BODY,
                )
            )
        flow_items.append(ListItem(content, leftIndent=16))
    return ListFlowable(
        flow_items,
        bulletType="1" if ordered else "bullet",
        start=None if ordered else "•",
        leftIndent=16,
        bulletFontName=BODY,
        bulletFontSize=10,
    )


def parse(md: str, base: Path, width: float, max_img_h: float):
    story = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("# "):
            story.append(Paragraph(inline(stripped[2:]), STYLES["title"]))
            i += 1
        elif stripped.startswith("## "):
            title = stripped[3:]
            # The steps start on a fresh page; other sections just avoid
            # leaving a heading stranded at the bottom of a page.
            story.append(PageBreak() if title.startswith("Step 1:") else CondPageBreak(2.2 * inch))
            story.append(Paragraph(inline(title), STYLES["h2"]))
            i += 1
        elif stripped.startswith(">"):
            text = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                text.append(lines[i].strip()[1:].strip())
                i += 1
            story += note_flowable(" ".join(text), width)
        elif stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            story += table_flowable(rows, width)
        elif re.match(r"!\[", stripped):
            m = re.match(r"!\[(.*)\]\((.+)\)", stripped)
            # 3D views carry less detail than graph shots; keeping them shorter
            # lets a step's graph and model pictures share a page.
            limit = max_img_h * 0.7 if m.group(2).endswith("_3d.png") else max_img_h
            story.append(image_flowable(base / m.group(2), m.group(1), width, limit))
            i += 1
        elif re.match(r"(-|\d+\.)\s", stripped):
            ordered = bool(re.match(r"\d+\.", stripped))
            items = []
            while i < len(lines) and lines[i].strip():
                cur = lines[i]
                if re.match(r"\s{2,}-\s", cur) and items:
                    items[-1][1].append(cur.strip()[2:])
                elif re.match(r"(-|\d+\.)\s", cur.strip()):
                    items.append((re.sub(r"^(-|\d+\.)\s+", "", cur.strip()), []))
                else:
                    break
                i += 1
            story.append(list_flowable(items, ordered))
            story.append(Spacer(1, 6))
        else:
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"(#|>|\||!\[|-\s|\d+\.\s)", lines[i].strip()):
                para.append(lines[i].strip())
                i += 1
            story.append(Paragraph(inline(" ".join(para)), STYLES["body"]))
    return story


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("markdown", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="default: next to the Markdown file")
    args = parser.parse_args()
    src = args.markdown.resolve()
    out = (args.output or src.with_suffix(".pdf")).resolve()
    md = src.read_text(encoding="utf-8")
    title = re.search(r"^# (.+)$", md, re.M).group(1)

    margin = 0.75 * inch
    doc = SimpleDocTemplate(
        str(out),
        pagesize=letter,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=title,
        author="ParamWeave",
        subject="ParamWeave tutorial",
    )
    width = letter[0] - 2 * margin
    story = parse(md, src.parent, width, max_img_h=4.6 * inch)

    def decorate(canvas, document):
        canvas.saveState()
        canvas.setFont(BODY, 8)
        canvas.setFillColor(MUTED)
        canvas.setStrokeColor(RULE)
        canvas.line(margin, 0.55 * inch, letter[0] - margin, 0.55 * inch)
        canvas.drawString(margin, 0.4 * inch, title)
        canvas.drawRightString(letter[0] - margin, 0.4 * inch, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
