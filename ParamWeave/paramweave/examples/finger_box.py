"""Example graph: a fully parameterized finger-jointed box.

Eight constants drive everything: outer length/width/height, material
thickness, laser kerf and the number of fingers along each axis. Expressions force the
finger counts odd and compute the panel plane offsets. Each of the six panels
is a Finger Joint Panel -> Sketch -> Extrude chain, so every panel is also an
ordinary Sketcher sketch (handy for laser-cutting export).

Pure Python: it only writes graph data (type ids and params), so it can be
built and checked without FreeCAD.

Joint scheme (mating edges always use opposite modes and the same count):

* bottom and lid: every edge starts with a slot (``in``);
* front/back: every edge starts with a finger (``out``);
* left/right: bottom/top edges ``out``, vertical edges ``in``.

With odd counts each box corner cube belongs to exactly one panel (front or
back), so the panels never overlap and leave no gaps.
"""

from __future__ import annotations

from typing import Dict

from paramweave.app.model import GraphModel

DEFAULTS = {
    "length": 160.0,
    "width": 100.0,
    "height": 70.0,
    "thickness": 3.0,
    "kerf": 0.0,
    "fingers_length": 7,
    "fingers_width": 5,
    "fingers_height": 3,
    # Inside-corner relief for milling ("none" for lasers); see sketch_model.CORNER_STYLES.
    "corner_style": "none",
    "tool_diameter": 3.175,
}

ODD = "max(1, 2 * floor(a / 2) + 1)"

COL = 300.0  # column spacing
ROW = 300.0  # panel row spacing (leaves room for each panel's frame)

# Frame geometry around node columns; nodes are 180 wide. Frames group the
# graph visually only: a node belongs to a frame when its position is inside.
NODE_W = 180.0
FRAME_PAD = 30.0
FRAME_TITLE = 50.0
PANEL_COLORS = {"bottom": "blue", "lid": "blue", "front": "green", "back": "green", "left": "orange", "right": "orange"}


def build(model: GraphModel, origin=(0.0, 0.0), lid: bool = True, **overrides) -> Dict[str, str]:
    """Add the box graph to ``model``; return node ids keyed by role."""
    values = {**DEFAULTS, **overrides}
    ox, oy = origin
    ids: Dict[str, str] = {}

    def node(key, type_id, label, col, row, params):
        ids[key] = model.create_node(type_id, label, (ox + col * COL, oy + row), params).id
        return ids[key]

    def wire(src, dst, port, src_port="value"):
        model.connect(ids[src], src_port, ids[dst], port)

    def frame(label, col0, col1, top, bottom, color, note=""):
        x = ox + col0 * COL - FRAME_PAD
        y = oy + top - FRAME_TITLE
        width = (col1 - col0) * COL + NODE_W + 2 * FRAME_PAD
        height = bottom - top + FRAME_TITLE + FRAME_PAD
        ids[f"frame:{label}"] = model.create_frame(label, [x, y, width, height], color, note).id

    # -- constants ----------------------------------------------------------
    constants = [
        ("L", "Length L", "length"),
        ("W", "Width W", "width"),
        ("H", "Height H", "height"),
        ("t", "Thickness t", "thickness"),
        ("k", "Kerf k", "kerf"),
        ("nL_raw", "Fingers along L", "fingers_length"),
        ("nW_raw", "Fingers along W", "fingers_width"),
        ("nH_raw", "Fingers along H", "fingers_height"),
    ]
    for i, (key, label, name) in enumerate(constants):
        node(key, "value.number", label, 0, i * 90.0, {"value": float(values[name])})
    frame("Constants", 0, 0, 0.0, (len(constants) - 1) * 90.0 + 58.0, "yellow", "Edit these, then Evaluate.")

    # -- functions ------------------------------------------------------------
    exprs = [
        ("nL", "Odd fingers L", ODD, ["nL_raw"]),
        ("nW", "Odd fingers W", ODD, ["nW_raw"]),
        ("nH", "Odd fingers H", ODD, ["nH_raw"]),
        ("front_off", "Front plane (y = t)", "-a", ["t"]),
        ("back_off", "Back plane (y = W)", "-a", ["W"]),
        ("right_off", "Right plane (x = L - t)", "a - b", ["L", "t"]),
        ("lid_off", "Lid plane (z = H - t)", "a - b", ["H", "t"]),
    ]
    for i, (key, label, text, inputs) in enumerate(exprs):
        node(key, "value.expression", label, 1, i * 150.0, {"expression": text})
        for src, port in zip(inputs, "abcd"):
            wire(src, key, port)
    frame("Derived values", 1, 1, 0.0, (len(exprs) - 1) * 150.0 + 124.0, "purple")

    # -- panels: (key, label, width, height, fingers b/r/t/l, modes b/r/t/l, plane, offset) --
    lid_mode = "out" if lid else "flat"
    panels = [
        ("bottom", "Bottom", "L", "W", ("nL", "nW", "nL", "nW"), ("in",) * 4, "XY", None),
        ("front", "Front", "L", "H", ("nL", "nH", "nL", "nH"), ("out", "out", lid_mode, "out"), "XZ", "front_off"),
        ("back", "Back", "L", "H", ("nL", "nH", "nL", "nH"), ("out", "out", lid_mode, "out"), "XZ", "back_off"),
        ("left", "Left", "W", "H", ("nW", "nH", "nW", "nH"), ("out", "in", lid_mode, "in"), "YZ", None),
        ("right", "Right", "W", "H", ("nW", "nH", "nW", "nH"), ("out", "in", lid_mode, "in"), "YZ", "right_off"),
    ]
    if lid:
        panels.append(("lid", "Lid", "L", "W", ("nL", "nW", "nL", "nW"), ("in",) * 4, "XY", "lid_off"))

    sides = ("bottom", "right", "top", "left")
    for i, (key, label, w, h, fingers, modes, plane, offset) in enumerate(panels):
        row = i * ROW
        params = {"width": 1.0, "height": 1.0, "thickness": 1.0, "kerf": 0.0}
        params.update(corner_style=values["corner_style"], tool_diameter=float(values["tool_diameter"]))
        params.update({f"fingers_{s}": 1 for s in sides})
        params.update({f"mode_{s}": m for s, m in zip(sides, modes)})
        node(f"{key}_profile", "sketch.finger_panel", f"{label} profile", 2, row, params)
        wire(w, f"{key}_profile", "width")
        wire(h, f"{key}_profile", "height")
        wire("t", f"{key}_profile", "thickness")
        wire("k", f"{key}_profile", "kerf")
        for s, n in zip(sides, fingers):
            wire(n, f"{key}_profile", f"fingers_{s}")

        node(f"{key}_sketch", "sketch.sketch", f"{label} sketch", 3, row, {"plane": plane, "offset": 0.0})
        wire(f"{key}_profile", f"{key}_sketch", "geometry", "geometry")
        if offset:
            wire(offset, f"{key}_sketch", "offset")

        node(key, "sketch.extrude", f"{label} panel", 4, row, {"length": 1.0, "reversed": False})
        wire(f"{key}_sketch", key, "shape", "shape")
        wire("t", key, "length")
        frame(f"{label} panel", 2, 4, row, row + 212.0, PANEL_COLORS[key])
    return ids
