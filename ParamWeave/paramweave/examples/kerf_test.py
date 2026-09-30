"""Example graph: a cuttable kerf fit test at 0, 90 and 45 degrees.

Cut it, push each tab coupon into its slot coupon and keep the kerf value of
the pair that fits the way you want; use that value as ``Kerf k`` in the
finger box (or any Finger Joint Panel). Each orientation is a Kerf Fit Test
-> Sketch -> Extrude chain, so the three sets export as three cut sketches.

Constants: thickness, finger width, first kerf, kerf step, number of steps
and the corner tool diameter. Expressions size the coupons for the thickness
and stack the three sets. Each set is a compact horizontal strip (pairs
turned in place), so the strips stack into one rectangular sheet. Corner relief
is chosen with the ``corner_style`` dropdown on each Kerf Fit Test node
(``none`` for lasers; ``dogbone``/``tbone_*`` for milling).

Pure Python: it only writes graph data, like ``finger_box``.
See docs/tutorial/kerf-fit-test.md for why the three angles matter.
"""

from __future__ import annotations

from typing import Dict

from paramweave.app.model import GraphModel

DEFAULTS = {
    "thickness": 3.0,
    "finger_width": 10.0,
    "kerf_start": 0.0,
    "kerf_step": 0.05,
    "count": 5,
    "tool_diameter": 3.175,
    "corner_style": "none",
}

ANGLES = (0.0, 90.0, 45.0)
GAP = 4.0  # between coupons inside a set
SET_GAP = 4.0  # between set strips (same as between coupons)

COL = 300.0
NODE_W = 180.0
FRAME_PAD = 30.0
FRAME_TITLE = 50.0
ROW = 380.0  # a Kerf Fit Test node is ~300 tall


def build(model: GraphModel, origin=(0.0, 0.0), **overrides) -> Dict[str, str]:
    """Add the kerf test graph to ``model``; return node ids keyed by role."""
    values = {**DEFAULTS, **overrides}
    ox, oy = origin
    ids: Dict[str, str] = {}

    def node(key, type_id, label, col, row, params):
        ids[key] = model.create_node(type_id, label, (ox + col * COL, oy + row), params).id

    def wire(src, dst, port, src_port="value"):
        model.connect(ids[src], src_port, ids[dst], port)

    def frame(label, col0, col1, top, bottom, color, note=""):
        rect = [
            ox + col0 * COL - FRAME_PAD,
            oy + top - FRAME_TITLE,
            (col1 - col0) * COL + NODE_W + 2 * FRAME_PAD,
            bottom - top + FRAME_TITLE + FRAME_PAD,
        ]
        ids[f"frame:{label}"] = model.create_frame(label, rect, color, note).id

    constants = [
        ("t", "Thickness t", "thickness"),
        ("f", "Finger width", "finger_width"),
        ("k0", "First kerf", "kerf_start"),
        ("dk", "Kerf step", "kerf_step"),
        ("n", "Kerf steps", "count"),
        ("d", "Tool diameter", "tool_diameter"),
    ]
    for i, (key, label, name) in enumerate(constants):
        node(key, "value.number", label, 0, i * 90.0, {"value": float(values[name])})
    frame("Constants", 0, 0, 0.0, (len(constants) - 1) * 90.0 + 58.0, "yellow", "Edit these, then Evaluate.")

    exprs = [
        ("h", "Coupon height", "max(20, 4 * a + 4)", ["t"]),
        # Height of a 0-degree set is two coupons plus the gap.
        ("y90", "90° set y", f"2 * a + {GAP + SET_GAP:g}", ["h"]),
        # A 90-degree strip is one coupon wide (3 fingers) tall.
        ("y45", "45° set y", f"a + 3 * b + {SET_GAP:g}", ["y90", "f"]),
    ]
    for i, (key, label, text, inputs) in enumerate(exprs):
        node(key, "value.expression", label, 1, i * 150.0, {"expression": text})
        for src, port in zip(inputs, "abcd"):
            wire(src, key, port)
    frame("Derived values", 1, 1, 0.0, (len(exprs) - 1) * 150.0 + 124.0, "purple")

    colors = {0.0: "green", 90.0: "orange", 45.0: "blue"}
    for i, angle in enumerate(ANGLES):
        key = f"set{angle:g}"
        row = i * ROW
        params = {
            "thickness": 1.0,
            "finger_width": 1.0,
            "fingers": 3,
            "coupon_height": 20.0,
            "kerf_start": 0.0,
            "kerf_step": 0.05,
            "count": 5,
            "angle": angle,
            "x": 0.0,
            "y": 0.0,
            "gap": GAP,
            "corner_style": values["corner_style"],
            "tool_diameter": 3.175,
        }
        node(f"{key}_coupons", "sketch.kerf_test", f"Coupons {angle:g}°", 2, row, params)
        for src, port in (
            ("t", "thickness"),
            ("f", "finger_width"),
            ("h", "coupon_height"),
            ("k0", "kerf_start"),
            ("dk", "kerf_step"),
            ("n", "count"),
            ("d", "tool_diameter"),
        ):
            wire(src, f"{key}_coupons", port)
        if angle == 90.0:
            wire("y90", f"{key}_coupons", "y")
        elif angle == 45.0:
            wire("y45", f"{key}_coupons", "y")
        node(f"{key}_sketch", "sketch.sketch", f"Kerf test {angle:g}°", 3, row, {"plane": "XY", "offset": 0.0})
        wire(f"{key}_coupons", f"{key}_sketch", "geometry", "geometry")
        node(key, "sketch.extrude", f"Kerf test {angle:g}° solid", 4, row, {"length": 1.0, "reversed": False})
        wire(f"{key}_sketch", key, "shape", "shape")
        wire("t", key, "length")
        note = "Joint edge along X: fit measures Y-axis kerf." if angle == 0.0 else (
            "Joint edge along Y: fit measures X-axis kerf." if angle == 90.0 else "Diagonal: both axes move together."
        )
        frame(f"{angle:g}° set", 2, 4, row, row + 300.0, colors[angle], note)
    return ids
