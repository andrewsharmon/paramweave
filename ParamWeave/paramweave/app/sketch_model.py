"""UI- and FreeCAD-independent sketch description passed between sketch nodes.

A *sketch geometry* value is a plain dict flowing along ``Sketch.Geometry``
wires::

    {
        "elements": [
            {"type": "line", "start": [x, y], "end": [x, y], "construction": False},
            {"type": "circle", "center": [x, y], "radius": r},
            {"type": "arc", "center": [x, y], "radius": r,
             "start_angle": deg, "end_angle": deg},       # counter-clockwise
            {"type": "point", "at": [x, y]},
        ],
        "constraints": [
            {"type": "Coincident", "refs": [[0, 2], [1, 1]]},
            {"type": "Radius", "refs": [[2]], "value": 5.0, "name": "r"},
        ],
    }

Coordinates are sketch-local millimetres; angles are degrees. Constraint
``refs`` are ``[element_index]`` or ``[element_index, point_pos]`` using
Sketcher's point positions (1 start, 2 end, 3 center). Negative indices are
the sketch axes (-1 horizontal, -2 vertical) and are left alone by
re-indexing. The value is copied, never mutated, by every helper here.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, Iterable, List, Optional

ELEMENT_TYPES = ("line", "circle", "arc", "point")

# Constraint types the FreeCAD adapter knows how to rebuild. Anything else read
# from a document sketch is refused rather than silently dropped.
CONSTRAINT_TYPES = (
    "Coincident",
    "Horizontal",
    "Vertical",
    "Parallel",
    "Perpendicular",
    "Tangent",
    "Equal",
    "PointOnObject",
    "Symmetric",
    "Block",
    "Distance",
    "DistanceX",
    "DistanceY",
    "Radius",
    "Diameter",
    "Angle",
)
DIMENSIONAL_TYPES = ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle")

START, END, CENTER = 1, 2, 3


class SketchDataError(ValueError):
    pass


def empty() -> Dict[str, Any]:
    return {"elements": [], "constraints": []}


def _xy(value, what: str) -> List[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise SketchDataError(f"{what} must be [x, y]")
    try:
        xy = [float(v) for v in value]
    except (TypeError, ValueError) as exc:
        raise SketchDataError(f"{what} must be numeric") from exc
    if not all(math.isfinite(v) for v in xy):
        raise SketchDataError(f"{what} must be finite")
    return xy


def validate(geometry: Any) -> Dict[str, Any]:
    """Raise SketchDataError unless ``geometry`` is a well-formed sketch value."""
    if not isinstance(geometry, dict):
        raise SketchDataError("sketch geometry must be an object")
    elements = geometry.get("elements")
    constraints = geometry.get("constraints")
    if not isinstance(elements, list) or not isinstance(constraints, list):
        raise SketchDataError("sketch geometry needs 'elements' and 'constraints' lists")
    for i, el in enumerate(elements):
        if not isinstance(el, dict) or el.get("type") not in ELEMENT_TYPES:
            raise SketchDataError(f"element {i}: unsupported element {el!r}")
        kind = el["type"]
        if kind == "line":
            if _xy(el.get("start"), f"element {i} start") == _xy(el.get("end"), f"element {i} end"):
                raise SketchDataError(f"element {i}: line has zero length")
        elif kind == "point":
            _xy(el.get("at"), f"element {i} point")
        else:
            _xy(el.get("center"), f"element {i} center")
            radius = el.get("radius")
            if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not radius > 0:
                raise SketchDataError(f"element {i}: radius must be > 0")
    count = len(elements)
    for i, con in enumerate(constraints):
        if not isinstance(con, dict) or con.get("type") not in CONSTRAINT_TYPES:
            raise SketchDataError(f"constraint {i}: unsupported constraint {con!r}")
        refs = con.get("refs")
        if not isinstance(refs, list) or not refs:
            raise SketchDataError(f"constraint {i}: refs must be a non-empty list")
        for ref in refs:
            if (
                not isinstance(ref, list)
                or len(ref) not in (1, 2)
                or not all(isinstance(v, int) and not isinstance(v, bool) for v in ref)
            ):
                raise SketchDataError(f"constraint {i}: bad ref {ref!r}")
            if ref[0] >= count or ref[0] < -2:
                raise SketchDataError(f"constraint {i}: element {ref[0]} does not exist")
        if con["type"] in DIMENSIONAL_TYPES:
            value = con.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise SketchDataError(f"constraint {i}: {con['type']} needs a finite value")
    return geometry


# -- element builders ------------------------------------------------------


def line(x1: float, y1: float, x2: float, y2: float, construction: bool = False) -> Dict[str, Any]:
    return validate(
        {
            "elements": [{"type": "line", "start": [x1, y1], "end": [x2, y2], "construction": construction}],
            "constraints": [],
        }
    )


def circle(cx: float, cy: float, radius: float, construction: bool = False) -> Dict[str, Any]:
    return validate(
        {
            "elements": [{"type": "circle", "center": [cx, cy], "radius": radius, "construction": construction}],
            "constraints": [],
        }
    )


def arc(cx: float, cy: float, radius: float, start_angle: float, end_angle: float, construction: bool = False):
    if math.isclose(start_angle % 360.0, end_angle % 360.0):
        raise SketchDataError("arc start and end angles must differ (use a circle)")
    return validate(
        {
            "elements": [
                {
                    "type": "arc",
                    "center": [cx, cy],
                    "radius": radius,
                    "start_angle": start_angle,
                    "end_angle": end_angle,
                    "construction": construction,
                }
            ],
            "constraints": [],
        }
    )


def point(x: float, y: float) -> Dict[str, Any]:
    return validate({"elements": [{"type": "point", "at": [x, y]}], "constraints": []})


def polyline(points: List[List[float]], closed: bool, construction: bool = False) -> Dict[str, Any]:
    """Consecutive line segments joined end-to-start by Coincident constraints."""
    if len(points) < 2:
        raise SketchDataError("a polyline needs at least two points")
    pts = [list(p) for p in points]
    if closed:
        pts.append(pts[0])
    elements = [
        {"type": "line", "start": list(a), "end": list(b), "construction": construction} for a, b in zip(pts, pts[1:])
    ]
    constraints = [{"type": "Coincident", "refs": [[i, END], [i + 1, START]]} for i in range(len(elements) - 1)]
    if closed:
        constraints.append({"type": "Coincident", "refs": [[len(elements) - 1, END], [0, START]]})
    return validate({"elements": elements, "constraints": constraints})


def rectangle(x: float, y: float, width: float, height: float, construction: bool = False) -> Dict[str, Any]:
    if not width > 0 or not height > 0:
        raise SketchDataError("rectangle width and height must be > 0")
    geo = polyline([[x, y], [x + width, y], [x + width, y + height], [x, y + height]], True, construction)
    geo["constraints"] += [
        {"type": "Horizontal", "refs": [[0]]},
        {"type": "Vertical", "refs": [[1]]},
        {"type": "Horizontal", "refs": [[2]]},
        {"type": "Vertical", "refs": [[3]]},
    ]
    return geo


def regular_polygon(cx: float, cy: float, radius: float, sides: int, rotation: float = 0.0, construction=False):
    if isinstance(sides, bool) or not isinstance(sides, int) or sides < 3:
        raise SketchDataError("a polygon needs an integer number of sides >= 3")
    if not radius > 0:
        raise SketchDataError("polygon radius must be > 0")
    pts = []
    for k in range(sides):
        a = math.radians(rotation) + 2.0 * math.pi * k / sides
        pts.append([cx + radius * math.cos(a), cy + radius * math.sin(a)])
    geo = polyline(pts, True, construction)
    geo["constraints"] += [{"type": "Equal", "refs": [[0], [i]]} for i in range(1, sides)]
    return geo


# -- modifiers -------------------------------------------------------------


def _shift_ref(ref: List[int], offset: int) -> List[int]:
    return [ref[0] + offset] + ref[1:] if ref[0] >= 0 else list(ref)


def combine(parts: Iterable[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """Concatenate sketch values, re-indexing each part's constraints."""
    out = empty()
    for part in parts:
        if part is None:
            continue
        validate(part)
        offset = len(out["elements"])
        out["elements"] += copy.deepcopy(part["elements"])
        for con in part["constraints"]:
            con = copy.deepcopy(con)
            con["refs"] = [_shift_ref(r, offset) for r in con["refs"]]
            out["constraints"].append(con)
    return out


def parse_indices(text: str, count: int) -> List[int]:
    """Parse ``"0, 2-4"`` into element indices; empty text means all elements."""
    text = str(text or "").strip()
    if not text:
        return list(range(count))
    result = set()
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            if "-" in chunk:
                lo, hi = chunk.split("-", 1)
                result.update(range(int(lo), int(hi) + 1))
            else:
                result.add(int(chunk))
        except ValueError:
            raise SketchDataError(f"bad element index list: {text!r}") from None
    bad = sorted(i for i in result if i < 0 or i >= count)
    if bad:
        raise SketchDataError(f"element indices out of range 0..{count - 1}: {bad}")
    return sorted(result)


def _move(el: Dict[str, Any], fn) -> None:
    for key in ("start", "end", "center", "at"):
        if key in el:
            el[key] = list(fn(*el[key]))


def translate(geometry: Dict[str, Any], dx: float, dy: float, indices: str = "") -> Dict[str, Any]:
    geo = copy.deepcopy(validate(geometry))
    for i in parse_indices(indices, len(geo["elements"])):
        _move(geo["elements"][i], lambda x, y: (x + dx, y + dy))
    return geo


def rotate(geometry: Dict[str, Any], angle: float, cx: float = 0.0, cy: float = 0.0, indices: str = ""):
    """Rotate elements about (cx, cy).

    Horizontal/Vertical constraints on rotated elements would fight the
    rotation, so rotating by anything but a multiple of 90 degrees drops them
    (all other constraints are rotation-invariant).
    """
    geo = copy.deepcopy(validate(geometry))
    chosen = set(parse_indices(indices, len(geo["elements"])))
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)

    def rot(x, y):
        x, y = x - cx, y - cy
        return cx + c * x - s * y, cy + s * x + c * y

    for i in chosen:
        el = geo["elements"][i]
        _move(el, rot)
        if el["type"] == "arc":
            el["start_angle"] = el["start_angle"] + angle
            el["end_angle"] = el["end_angle"] + angle
    quarter = round(angle / 90.0)
    if not math.isclose(angle, quarter * 90.0, abs_tol=1e-9):
        geo["constraints"] = [
            con
            for con in geo["constraints"]
            if not (con["type"] in ("Horizontal", "Vertical") and any(r[0] in chosen for r in con["refs"]))
        ]
    elif quarter % 2:
        swap = {"Horizontal": "Vertical", "Vertical": "Horizontal"}
        for con in geo["constraints"]:
            if con["type"] in swap and any(r[0] in chosen for r in con["refs"]):
                con["type"] = swap[con["type"]]
    return geo


def remove_elements(geometry: Dict[str, Any], indices: str) -> Dict[str, Any]:
    """Delete elements and every constraint that refers to them."""
    geo = copy.deepcopy(validate(geometry))
    if not str(indices or "").strip():
        raise SketchDataError("name the element indices to remove")
    doomed = set(parse_indices(indices, len(geo["elements"])))
    remap, kept = {}, []
    for i, el in enumerate(geo["elements"]):
        if i not in doomed:
            remap[i] = len(kept)
            kept.append(el)
    constraints = []
    for con in geo["constraints"]:
        if any(r[0] in doomed for r in con["refs"]):
            continue
        con["refs"] = [[remap[r[0]]] + r[1:] if r[0] >= 0 else r for r in con["refs"]]
        constraints.append(con)
    return {"elements": kept, "constraints": constraints}


def set_construction(geometry: Dict[str, Any], indices: str, construction: bool) -> Dict[str, Any]:
    geo = copy.deepcopy(validate(geometry))
    for i in parse_indices(indices, len(geo["elements"])):
        if geo["elements"][i]["type"] != "point":
            geo["elements"][i]["construction"] = bool(construction)
    return geo


def add_constraint(geometry: Dict[str, Any], constraint: Dict[str, Any]) -> Dict[str, Any]:
    geo = copy.deepcopy(validate(geometry))
    geo["constraints"].append(copy.deepcopy(constraint))
    return validate(geo)


def set_constraint_value(geometry: Dict[str, Any], name: str, value: float) -> Dict[str, Any]:
    """Change the value of the dimensional constraint called ``name``."""
    geo = copy.deepcopy(validate(geometry))
    matches = [c for c in geo["constraints"] if c.get("name") == name]
    if not matches:
        names = sorted(c["name"] for c in geo["constraints"] if c.get("name"))
        raise SketchDataError(f"no constraint named {name!r}" + (f" (named: {', '.join(names)})" if names else ""))
    if len(matches) > 1:
        raise SketchDataError(f"more than one constraint is named {name!r}")
    if matches[0]["type"] not in DIMENSIONAL_TYPES:
        raise SketchDataError(f"constraint {name!r} is a {matches[0]['type']} constraint and has no value")
    matches[0]["value"] = float(value)
    return validate(geo)


def parse_refs(text: str) -> List[List[int]]:
    """Parse ``"0:2 1:1"`` / ``"0, 3"`` into constraint refs (``index[:pos]``)."""
    refs = []
    for token in str(text or "").replace(",", " ").split():
        parts = token.split(":")
        try:
            ref = [int(p) for p in parts]
        except ValueError:
            raise SketchDataError(f"bad constraint reference {token!r}; use index or index:pos") from None
        if len(ref) > 2:
            raise SketchDataError(f"bad constraint reference {token!r}; use index or index:pos")
        refs.append(ref)
    if not refs:
        raise SketchDataError("a constraint needs at least one element reference")
    return refs


def _named(geometry: Dict[str, Any], name: str) -> Dict[str, Any]:
    matches = [c for c in geometry["constraints"] if c.get("name") == name]
    if len(matches) != 1:
        names = sorted(c["name"] for c in geometry["constraints"] if c.get("name"))
        raise SketchDataError(
            f"{len(matches) or 'no'} constraint(s) named {name!r}" + (f" (named: {', '.join(names)})" if names else "")
        )
    return matches[0]


def constraint_value(geometry: Dict[str, Any], name: str) -> float:
    """Read the value of the dimensional constraint called ``name``."""
    con = _named(validate(geometry), name)
    if con["type"] not in DIMENSIONAL_TYPES:
        raise SketchDataError(f"constraint {name!r} is a {con['type']} constraint and has no value")
    return float(con["value"])


ELEMENT_QUANTITIES = ("length", "radius", "diameter", "x", "y", "end_x", "end_y", "angle")


def element_quantity(geometry: Dict[str, Any], index: int, quantity: str) -> float:
    """Measure one element: length/radius/diameter, x/y (start, center or point), end_x/end_y, angle."""
    geo = validate(geometry)
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(geo["elements"]):
        raise SketchDataError(f"element index {index!r} out of range 0..{len(geo['elements']) - 1}")
    el = geo["elements"][index]
    kind = el["type"]
    anchor = el.get("start") or el.get("center") or el.get("at")
    if quantity == "x":
        return float(anchor[0])
    if quantity == "y":
        return float(anchor[1])
    if kind == "line":
        dx, dy = el["end"][0] - el["start"][0], el["end"][1] - el["start"][1]
        simple = {
            "length": math.hypot(dx, dy),
            "end_x": el["end"][0],
            "end_y": el["end"][1],
            "angle": math.degrees(math.atan2(dy, dx)),
        }
    elif kind in ("circle", "arc"):
        r = float(el["radius"])
        simple = {"radius": r, "diameter": 2 * r}
        if kind == "circle":
            simple["length"] = 2 * math.pi * r
        else:
            sweep = (el["end_angle"] - el["start_angle"]) % 360.0
            simple["length"] = math.radians(sweep) * r
            simple["angle"] = sweep
    else:
        simple = {}
    if quantity not in simple:
        raise SketchDataError(f"a {kind} has no {quantity!r}; choose from {', '.join(['x', 'y', *simple])}")
    return float(simple[quantity])


# -- finger joints -----------------------------------------------------------

FINGER_MODES = ("out", "in", "flat", "recessed")
PANEL_SIDES = ("bottom", "right", "top", "left")


def finger_depths(mode: str, count: int, thickness: float) -> List[float]:
    """Per-segment inset of one panel edge.

    ``out`` starts (and, with an odd count, ends) with a finger at the panel
    edge; ``in`` starts with a slot inset by ``thickness``; mating edges use
    opposite modes and the same count. ``flat`` is a plain edge, ``recessed``
    a plain edge inset by the full thickness.
    """
    if mode not in FINGER_MODES:
        raise SketchDataError(f"finger mode must be one of {', '.join(FINGER_MODES)}, got {mode!r}")
    if mode == "flat":
        return [0.0]
    if mode == "recessed":
        return [thickness]
    if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count % 2 == 0:
        raise SketchDataError(f"finger count must be an odd whole number >= 1, got {count!r}")
    first, second = (0.0, thickness) if mode == "out" else (thickness, 0.0)
    return [first if j % 2 == 0 else second for j in range(count)]


def offset_rectilinear(points: List[List[float]], distance: float) -> List[List[float]]:
    """Grow a counter-clockwise, axis-aligned closed outline outward by ``distance``.

    Every edge moves along its outward normal; with only right-angle corners
    each vertex simply moves by the sum of its two edges' offsets, which is
    exact for convex and reflex corners alike.
    """
    if not distance:
        return [list(p) for p in points]
    n = len(points)
    out = []
    for i in range(n):
        prev_pt, pt, next_pt = points[i - 1], points[i], points[(i + 1) % n]
        normals = []
        for a, b in ((prev_pt, pt), (pt, next_pt)):
            dx, dy = b[0] - a[0], b[1] - a[1]
            if dx and dy:
                raise SketchDataError("offset_rectilinear needs axis-aligned edges")
            length = abs(dx) + abs(dy)
            normals.append((dy / length, -dx / length))  # outward for a CCW outline
        (n1x, n1y), (n2x, n2y) = normals
        out.append([pt[0] + distance * (n1x + n2x), pt[1] + distance * (n1y + n2y)])
    return out


def finger_panel(width: float, height: float, thickness: float, sides, kerf: float = 0.0) -> Dict[str, Any]:
    """Closed outline of a ``width`` x ``height`` panel with finger-jointed edges.

    ``sides`` gives ``(mode, count)`` for bottom, right, top, left, walking
    counter-clockwise from the origin. Odd counts keep every edge pattern
    symmetric, so an edge reads the same from either end.

    ``kerf`` is the width of material the cutter removes. The outline is grown
    outward by ``kerf / 2`` so that, after cutting, fingers and slots come out
    at their nominal size and joints fit tight. The drawn panel is therefore
    ``kerf`` larger than nominal in each direction.
    """
    if not width > 0 or not height > 0:
        raise SketchDataError("panel width and height must be > 0")
    if not 0 < thickness < min(width, height) / 2.0:
        raise SketchDataError("thickness must be > 0 and less than half the panel's smaller side")
    if len(sides) != 4:
        raise SketchDataError("finger_panel needs four sides: bottom, right, top, left")
    starts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    dirs = [(1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)]
    lengths = [width, height, width, height]
    depths = [finger_depths(mode, count, thickness) for mode, count in sides]
    if isinstance(kerf, bool) or not isinstance(kerf, (int, float)) or not math.isfinite(kerf) or kerf < 0:
        raise SketchDataError("kerf must be a number >= 0")
    narrowest = min(min(lengths[s] / len(depths[s]) for s in range(4)), thickness)
    if kerf >= narrowest:
        raise SketchDataError(f"kerf {kerf:g} must be smaller than the narrowest finger or slot ({narrowest:g})")

    def at(s, u, d):
        (sx, sy), (dx, dy) = starts[s], dirs[s]
        # The inward normal of a counter-clockwise side is its direction turned left.
        return [sx + dx * u - dy * d, sy + dy * u + dx * d]

    points: List[List[float]] = []
    for s in range(4):
        # Corner: the previous side's last inset measured along this side,
        # this side's first inset measured inward.
        points.append(at(s, depths[s - 1][-1], depths[s][0]))
        segment = lengths[s] / len(depths[s])
        for j in range(len(depths[s]) - 1):
            if depths[s][j] != depths[s][j + 1]:
                u = segment * (j + 1)
                points.append(at(s, u, depths[s][j]))
                points.append(at(s, u, depths[s][j + 1]))
    return polyline(offset_rectilinear(points, kerf / 2.0), True)
