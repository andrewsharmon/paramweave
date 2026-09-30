"""Flat cut files (DXF and SVG) from sketch geometry values.

Pure Python, no FreeCAD: it works on the ``Sketch.Geometry`` values sketch
nodes produce (see ``sketch_model``). Each sketch is laid flat in its own
local coordinates, then panels are packed into rows on a sheet of a given
width. Construction elements and points are not cut and are skipped.

Units are millimetres. DXF output is AutoCAD R12 ASCII (LINE / ARC /
CIRCLE), which laser and CNC software reads widely. SVG output uses mm
dimensions and red hairline strokes, a common "cut" convention.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple
from xml.sax.saxutils import escape, quoteattr

from paramweave.app import sketch_model as sm

CUT_COLOR = "#ff0000"
HAIRLINE_MM = 0.01


class CutFileError(ValueError):
    pass


@dataclass
class Placed:
    name: str
    elements: List[Dict]
    dx: float  # translation applied to sketch-local coordinates
    dy: float
    width: float
    height: float


# -- geometry ---------------------------------------------------------------


def cut_elements(geometry: Dict) -> List[Dict]:
    """Elements that are actually cut: no construction geometry, no points."""
    sm.validate(geometry)
    return [e for e in geometry["elements"] if e["type"] != "point" and not e.get("construction", False)]


def _arc_points(el) -> List[Tuple[float, float]]:
    cx, cy = el["center"]
    r = float(el["radius"])
    start = float(el["start_angle"])
    sweep = (float(el["end_angle"]) - start) % 360.0
    pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in (start, start + sweep)]
    # Axis extremes the arc passes through.
    for k in range(4):
        angle = 90.0 * k
        if (angle - start) % 360.0 <= sweep:
            pts.append((cx + r * math.cos(math.radians(angle)), cy + r * math.sin(math.radians(angle))))
    return pts


def bounds(elements: Iterable[Dict]) -> Tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) of the cut elements."""
    xs, ys = [], []
    for el in elements:
        kind = el["type"]
        if kind == "line":
            pts = [tuple(el["start"]), tuple(el["end"])]
        elif kind == "circle":
            (cx, cy), r = el["center"], float(el["radius"])
            pts = [(cx - r, cy - r), (cx + r, cy + r)]
        elif kind == "arc":
            pts = _arc_points(el)
        else:
            continue
        xs += [p[0] for p in pts]
        ys += [p[1] for p in pts]
    if not xs:
        raise CutFileError("nothing to cut: the sketch has no non-construction lines, arcs or circles")
    return min(xs), min(ys), max(xs), max(ys)


def layout(panels: Sequence[Tuple[str, Dict]], sheet_width: float = 600.0, gap: float = 5.0) -> List[Placed]:
    """Pack panels into rows (tallest first) starting at the origin.

    ``panels`` is ``[(name, sketch geometry value)]``. Rows are at most
    ``sheet_width`` wide; a panel wider than the sheet gets a row of its own.
    """
    if not sheet_width > 0 or not gap >= 0 or not math.isfinite(sheet_width) or not math.isfinite(gap):
        raise CutFileError("sheet width must be > 0 and gap >= 0")
    if not panels:
        raise CutFileError("no sketches to export")
    items = []
    for name, geometry in panels:
        elements = cut_elements(geometry)
        x0, y0, x1, y1 = bounds(elements)
        items.append((name, elements, x0, y0, x1 - x0, y1 - y0))
    # Tallest first keeps rows tight; the sort is stable for equal heights.
    items.sort(key=lambda item: -item[5])
    placed: List[Placed] = []
    x = y = row_height = 0.0
    for name, elements, x0, y0, w, h in items:
        if x > 0 and x + w > sheet_width:
            y += row_height + gap
            x = row_height = 0.0
        placed.append(Placed(name, elements, x - x0, y - y0, w, h))
        x += w + gap
        row_height = max(row_height, h)
    return placed


def sheet_size(placed: Sequence[Placed]) -> Tuple[float, float]:
    width = max(p.dx + bounds(p.elements)[2] for p in placed)
    height = max(p.dy + bounds(p.elements)[3] for p in placed)
    return width, height


# -- DXF --------------------------------------------------------------------


def _layer(name: str, used: set) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:60] or "PANEL"
    layer, i = base, 2
    while layer.upper() in used:
        layer = f"{base}_{i}"
        i += 1
    used.add(layer.upper())
    return layer


def _num(v: float) -> str:
    text = f"{v:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def to_dxf(placed: Sequence[Placed]) -> str:
    out: List[str] = []

    def pair(code, value):
        out.append(str(code))
        out.append(value if isinstance(value, str) else _num(value))

    used: set = set()
    layers = [_layer(p.name, used) for p in placed]
    pair(0, "SECTION")
    pair(2, "HEADER")
    pair(9, "$ACADVER")
    pair(1, "AC1009")
    pair(9, "$INSUNITS")
    pair(70, "4")  # millimetres
    pair(0, "ENDSEC")
    pair(0, "SECTION")
    pair(2, "TABLES")
    pair(0, "TABLE")
    pair(2, "LAYER")
    pair(70, str(len(layers)))
    for layer in layers:
        pair(0, "LAYER")
        pair(2, layer)
        pair(70, "0")
        pair(62, "1")  # red
        pair(6, "CONTINUOUS")
    pair(0, "ENDTAB")
    pair(0, "ENDSEC")
    pair(0, "SECTION")
    pair(2, "ENTITIES")
    for p, layer in zip(placed, layers):
        for el in p.elements:
            kind = el["type"]
            if kind == "line":
                pair(0, "LINE")
                pair(8, layer)
                pair(10, el["start"][0] + p.dx)
                pair(20, el["start"][1] + p.dy)
                pair(30, 0.0)
                pair(11, el["end"][0] + p.dx)
                pair(21, el["end"][1] + p.dy)
                pair(31, 0.0)
            elif kind in ("circle", "arc"):
                pair(0, "CIRCLE" if kind == "circle" else "ARC")
                pair(8, layer)
                pair(10, el["center"][0] + p.dx)
                pair(20, el["center"][1] + p.dy)
                pair(30, 0.0)
                pair(40, float(el["radius"]))
                if kind == "arc":
                    start = float(el["start_angle"]) % 360.0
                    pair(50, start)
                    pair(51, (start + (float(el["end_angle"]) - float(el["start_angle"])) % 360.0) % 360.0)
    pair(0, "ENDSEC")
    pair(0, "EOF")
    return "\n".join(out) + "\n"


# -- SVG --------------------------------------------------------------------


def to_svg(placed: Sequence[Placed], margin: float = 2.0) -> str:
    width, height = sheet_size(placed)
    total_w, total_h = width + 2 * margin, height + 2 * margin

    def pt(x, y, p):
        # SVG's y axis points down; flip so the sheet reads like the DXF.
        return f"{_num(x + p.dx + margin)} {_num(total_h - (y + p.dy + margin))}"

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_num(total_w)}mm" height="{_num(total_h)}mm" '
        f'viewBox="0 0 {_num(total_w)} {_num(total_h)}">',
        f'<g fill="none" stroke="{CUT_COLOR}" stroke-width="{HAIRLINE_MM}">',
    ]
    for index, p in enumerate(placed):
        lines.append(f"<g id={quoteattr(f'panel-{index + 1}')}><title>{escape(p.name)}</title>")
        for el in p.elements:
            kind = el["type"]
            if kind == "line":
                lines.append(f'<path d="M {pt(*el["start"], p)} L {pt(*el["end"], p)}"/>')
            elif kind == "circle":
                cx, cy = el["center"]
                lines.append(
                    f'<circle cx="{_num(cx + p.dx + margin)}" cy="{_num(total_h - (cy + p.dy + margin))}" r="{_num(el["radius"])}"/>'
                )
            elif kind == "arc":
                cx, cy = el["center"]
                r = float(el["radius"])
                start = float(el["start_angle"])
                sweep = (float(el["end_angle"]) - start) % 360.0
                a0, a1 = math.radians(start), math.radians(start + sweep)
                p0 = (cx + r * math.cos(a0), cy + r * math.sin(a0))
                p1 = (cx + r * math.cos(a1), cy + r * math.sin(a1))
                large = 1 if sweep > 180.0 else 0
                # Counter-clockwise in sketch coordinates is clockwise once y is flipped.
                lines.append(f'<path d="M {pt(*p0, p)} A {_num(r)} {_num(r)} 0 {large} 0 {pt(*p1, p)}"/>')
        lines.append("</g>")
    lines += ["</g>", "</svg>"]
    return "\n".join(lines) + "\n"


def export(panels: Sequence[Tuple[str, Dict]], fmt: str, sheet_width: float = 600.0, gap: float = 5.0) -> str:
    """Lay out ``panels`` and return the file text for ``fmt`` ('dxf' or 'svg')."""
    placed = layout(panels, sheet_width, gap)
    fmt = fmt.lower().lstrip(".")
    if fmt == "dxf":
        return to_dxf(placed)
    if fmt == "svg":
        return to_svg(placed)
    raise CutFileError(f"unsupported cut file format {fmt!r}; use dxf or svg")
