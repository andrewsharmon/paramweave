"""Cuttable kerf fit test: finger-joint coupon pairs over a range of kerf values.

Pure Python, no FreeCAD. One call builds one *set*: ``count`` pairs of a tab
coupon (fingers ``out`` on its top edge) and a slot coupon (``in`` on its
bottom edge), each pair drawn with kerf ``kerf_start + i * kerf_step``. Pair
``i`` is marked with ``i + 1`` small holes on both coupons so it can be told
apart after cutting. The whole set is rotated by ``angle`` and moved so its
bounding box starts at ``(x, y)``.

Why the angle matters: a finger's width is set by the cuts along its walls,
which run perpendicular to the joint edge. A set at 0 degrees (joint edge
along X) therefore measures the kerf of Y moves, 90 degrees the kerf of X
moves, and 45 degrees the kerf when both axes move together. Laser beams are
rarely perfectly round and the two gantry axes rarely behave identically, so
these can differ; see docs/tutorial/kerf-fit-test.md.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from paramweave.app import cutfile
from paramweave.app import sketch_model as sm

MAX_COUNT = 12
MARK_PITCH_MIN = 3.0  # center spacing of the index holes (mm), before tool allowance


def kerf_values(kerf_start: float, kerf_step: float, count: int) -> List[float]:
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_COUNT:
        raise sm.SketchDataError(f"count must be a whole number from 1 to {MAX_COUNT}, got {count!r}")
    for name, v in (("kerf start", kerf_start), ("kerf step", kerf_step)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise sm.SketchDataError(f"{name} must be a finite number")
    values = [round(kerf_start + i * kerf_step, 9) for i in range(count)]
    if min(values) < 0:
        raise sm.SketchDataError("every kerf value in the test must be >= 0; raise kerf start or the step")
    return values


def _marks(count: int, cx: float, cy: float, radius: float, pitch: float) -> List[Dict[str, Any]]:
    x0 = cx - (count - 1) * pitch / 2.0
    return [sm.circle(x0 + j * pitch, cy, radius) for j in range(count)]


def coupon_set(
    thickness: float = 3.0,
    finger_width: float = 10.0,
    fingers: int = 3,
    coupon_height: float = 20.0,
    kerf_start: float = 0.0,
    kerf_step: float = 0.05,
    count: int = 5,
    angle: float = 0.0,
    x: float = 0.0,
    y: float = 0.0,
    gap: float = 4.0,
    corner_style: str = "none",
    tool_diameter: float = 0.0,
) -> Dict[str, Any]:
    """Sketch geometry for one orientation of the kerf fit test (see module doc)."""
    kerfs = kerf_values(kerf_start, kerf_step, count)
    if not finger_width > 0 or not coupon_height > 0 or not thickness > 0:
        raise sm.SketchDataError("thickness, finger width and coupon height must be > 0")
    if not coupon_height > 3 * thickness:
        raise sm.SketchDataError("coupon height must be more than three times the thickness (room for the marks)")
    if not gap > max(kerfs):
        raise sm.SketchDataError("gap between coupons must be larger than the largest kerf")
    width = fingers * finger_width
    tool_r = tool_diameter / 2.0 if corner_style != "none" else 0.0
    # Holes must be wider than a milling tool to be cut at all.
    mark_r = max(0.75, tool_r + 0.25)
    pitch_marks = max(MARK_PITCH_MIN, 2 * mark_r + 1.5)
    if count * pitch_marks + 2 * thickness > width:
        raise sm.SketchDataError(
            f"{count} index holes need {count * pitch_marks + 2 * thickness:g} mm; coupons are {width:g} mm wide "
            "(use fewer kerf steps, wider fingers or more fingers)"
        )
    flat = ("flat", 1)
    pair_height = 2 * coupon_height + gap
    # Each pair turned by ``angle`` fits in a turned (width x pair_height)
    # rectangle, grown by the largest kerf. Pairs sit in one row along X at the
    # smallest pitch that keeps those rectangles ``gap`` apart: either their
    # bounding boxes clear each other, or they clear along one of the turned
    # rectangle's own axes (tighter for diagonal pairs, which then nest).
    grow = max(kerfs)
    a = math.radians(angle)
    c, s_ = abs(math.cos(a)), abs(math.sin(a))
    w, h = width + grow, pair_height + grow
    options = [w * c + h * s_ + gap]
    if c > 1e-9:
        options.append((w + gap) / c)
    if s_ > 1e-9:
        options.append((h + gap) / s_)
    pitch = min(options)
    parts = []
    for i, k in enumerate(kerfs):
        tab = sm.finger_panel(
            width, coupon_height, thickness, [flat, flat, ("out", fingers), flat], k, corner_style, tool_diameter
        )
        slot = sm.finger_panel(
            width, coupon_height, thickness, [("in", fingers), flat, flat, flat], k, corner_style, tool_diameter
        )
        slot = sm.translate(slot, 0.0, coupon_height + gap)
        marks = _marks(i + 1, width / 2.0, (coupon_height - thickness) / 2.0, mark_r, pitch_marks)
        marks += _marks(i + 1, width / 2.0, coupon_height + gap + (coupon_height + thickness) / 2.0, mark_r, pitch_marks)
        pair = sm.combine([tab, slot, *marks])
        if angle:
            # Turn about the pair's center so every pair lands on the same row.
            pair = sm.rotate(pair, angle, width / 2.0, pair_height / 2.0)
        parts.append(sm.translate(pair, i * pitch, 0.0))
    geo = sm.combine(parts)
    x0, y0, _x1, _y1 = cutfile.bounds(cutfile.cut_elements(geo))
    return sm.translate(geo, x - x0, y - y0)
