import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ParamWeave"))

from paramweave.app import cutfile, fit_test
from paramweave.app import sketch_model as sm
from paramweave.app.model import GraphModel
from paramweave.examples import kerf_test


def _path(geo):
    """Walk a closed outline in order, returning (element, forward) pairs.

    Uses the Coincident chain: each constraint joins one element's path end
    to the next element's path start.
    """
    out = []
    for con in geo["constraints"]:
        (i, pos), _ = con["refs"]
        # The ref names the element's path end: END means it runs start -> end.
        out.append((geo["elements"][i], pos == sm.END))
    return out


def _point(el, pos):
    if el["type"] == "line":
        return el["start"] if pos == sm.START else el["end"]
    a = math.radians(el["start_angle"] if pos == sm.START else el["end_angle"])
    return [el["center"][0] + el["radius"] * math.cos(a), el["center"][1] + el["radius"] * math.sin(a)]


def _area(geo):
    """Signed area of a closed line/arc loop (Green's theorem, arcs sampled finely)."""
    total = 0.0
    for el, forward in _path(geo):
        if el["type"] == "line":
            pts = [el["start"], el["end"]]
        else:
            a0, a1 = el["start_angle"], el["end_angle"]
            sweep = (a1 - a0) % 360.0
            pts = [_point({**el, "start_angle": a0 + sweep * k / 2000.0}, sm.START) for k in range(2001)]
        if not forward:
            pts = pts[::-1]
        total += sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(pts, pts[1:])) / 2
    return total


class CornerReliefTests(unittest.TestCase):
    SIDES = [("out", 5), ("in", 3), ("out", 5), ("in", 3)]

    def test_outline_is_a_closed_chain(self):
        for style in sm.CORNER_STYLES:
            geo = sm.finger_panel(50, 20, 2, self.SIDES, 0.1, style, 1.0)
            path = _path(geo)
            self.assertEqual(len(geo["elements"]), len(path))
            for con in geo["constraints"]:
                (i, pi), (j, pj) = con["refs"]
                a, b = _point(geo["elements"][i], pi), _point(geo["elements"][j], pj)
                self.assertAlmostEqual(0.0, math.dist(a, b), places=9, msg=style)

    def test_relief_areas(self):
        r = 0.5
        base = sm.finger_panel(50, 20, 2, self.SIDES)
        reflex = sum(1 for e in base["elements"]) // 2 - 2
        nominal = _area(base)
        dog = _area(sm.finger_panel(50, 20, 2, self.SIDES, 0.0, "dogbone", 2 * r))
        self.assertAlmostEqual(nominal - reflex * r * r * (math.pi / 2 - 1), dog, places=4)
        for style in ("tbone_depth", "tbone_side"):
            tb = _area(sm.finger_panel(50, 20, 2, self.SIDES, 0.0, style, 2 * r))
            self.assertAlmostEqual(nominal - reflex * math.pi * r * r / 2, tb, places=4)

    def test_every_sharp_inside_corner_is_on_its_relief_circle(self):
        base = sm.finger_panel(30, 20, 3, [("out", 3), ("flat", 1), ("flat", 1), ("flat", 1)])
        corners = [e["start"] for e in base["elements"]]
        for style in ("dogbone", "tbone_depth", "tbone_side"):
            geo = sm.finger_panel(30, 20, 3, [("out", 3), ("flat", 1), ("flat", 1), ("flat", 1)], 0.0, style, 2.0)
            arcs = [e for e in geo["elements"] if e["type"] == "arc"]
            self.assertEqual(2, len(arcs))
            for arc in arcs:
                on = [c for c in corners if abs(math.dist(c, arc["center"]) - arc["radius"]) < 1e-9]
                self.assertEqual(1, len(on), style)

    def test_tbone_direction(self):
        # One finger in the middle of the top edge ("in", 3): slots at both ends,
        # finger in the middle. Inside corners sit at the finger's base (y = 17).
        sides = [("flat", 1), ("flat", 1), ("out", 3), ("flat", 1)]
        depth = sm.finger_panel(30, 20, 3, sides, 0.0, "tbone_depth", 2.0)
        side = sm.finger_panel(30, 20, 3, sides, 0.0, "tbone_side", 2.0)
        for arc in (e for e in depth["elements"] if e["type"] == "arc"):
            self.assertAlmostEqual(17.0, arc["center"][1])  # on the slot bottom: relief goes deeper
        for arc in (e for e in side["elements"] if e["type"] == "arc"):
            self.assertAlmostEqual(18.0, arc["center"][1])  # on the finger wall

    def test_tool_too_large(self):
        with self.assertRaisesRegex(sm.SketchDataError, "too large"):
            sm.finger_panel(30, 20, 3, [("out", 3)] + [("flat", 1)] * 3, 0.0, "tbone_side", 4.0)
        with self.assertRaisesRegex(sm.SketchDataError, "diameter"):
            sm.finger_panel(30, 20, 3, [("out", 3)] + [("flat", 1)] * 3, 0.0, "dogbone", 0.0)
        with self.assertRaisesRegex(sm.SketchDataError, "corner style"):
            sm.finger_panel(30, 20, 3, [("out", 3)] + [("flat", 1)] * 3, 0.0, "round", 1.0)


class CouponSetTests(unittest.TestCase):
    def test_kerf_values(self):
        self.assertEqual([0.0, 0.05, 0.1], fit_test.kerf_values(0.0, 0.05, 3))
        with self.assertRaises(sm.SketchDataError):
            fit_test.kerf_values(0.0, -0.1, 3)
        with self.assertRaises(sm.SketchDataError):
            fit_test.kerf_values(0.0, 0.1, 0)

    def test_pairs_marks_and_placement(self):
        geo = fit_test.coupon_set(count=4, x=5.0, y=7.0)
        circles = [e for e in geo["elements"] if e["type"] == "circle"]
        self.assertEqual(2 * (1 + 2 + 3 + 4), len(circles))
        x0, y0, x1, y1 = cutfile.bounds(cutfile.cut_elements(geo))
        self.assertAlmostEqual(5.0, x0)
        self.assertAlmostEqual(7.0, y0)
        # Pairs are spaced for the largest kerf (0.15); the last one grows by half of it.
        self.assertAlmostEqual(3 * (30 + 0.15 + 4) + 30 + 0.075, x1 - x0, places=6)

    def test_kerf_changes_finger_width_per_pair(self):
        # Pair i's two tab fingers (3 segments: finger, gap, finger) are nominal + kerf_i wide.
        geo = fit_test.coupon_set(kerf_start=0.1, kerf_step=0.1, count=2)
        tops = [e for e in geo["elements"] if e["type"] == "line" and e["start"][1] == e["end"][1]]
        # Finger tips of the tab coupons sit near y = coupon height (20).
        widths = sorted(round(abs(e["end"][0] - e["start"][0]), 6) for e in tops if 19 < e["start"][1] < 21)
        self.assertEqual([10.1, 10.1, 10.2, 10.2], widths)

    def _size(self, geo):
        x0, y0, x1, y1 = cutfile.bounds(cutfile.cut_elements(geo))
        return x1 - x0, y1 - y0

    def test_every_orientation_is_a_compact_strip(self):
        # Pairs turn in place and sit in one row: strip height is one turned pair.
        w, h = self._size(fit_test.coupon_set(angle=90.0, kerf_step=0.0))
        self.assertAlmostEqual(30.0, h, places=6)  # a pair turned 90 is one coupon wide
        self.assertAlmostEqual(4 * (44 + 4) + 44, w, places=6)
        w, h = self._size(fit_test.coupon_set(angle=45.0, kerf_step=0.0))
        self.assertAlmostEqual((30 + 44) / math.sqrt(2), h, places=6)
        # Diagonal pairs nest: pitch is (30 + gap) * sqrt(2), far less than a bounding box.
        self.assertAlmostEqual(4 * 34 * math.sqrt(2) + (30 + 44) / math.sqrt(2), w, places=6)

    def test_turned_pairs_do_not_overlap(self):
        for angle in (15.0, 45.0, 90.0, 135.0):
            geo = fit_test.coupon_set(angle=angle, count=3)
            # Every pair's outline elements stay inside its own turned rectangle,
            # so check the pairs' centres are at least one gap apart along a separating axis.
            circles = [e["center"] for e in geo["elements"] if e["type"] == "circle"]
            self.assertEqual(2 * (1 + 2 + 3), len(circles))
            import itertools
            outlines = [e for e in geo["elements"] if e["type"] == "line"]
            per_pair = len(outlines) // 3
            pairs = [outlines[i * per_pair:(i + 1) * per_pair] for i in range(3)]
            a = math.radians(angle)
            axes = [(math.cos(a), math.sin(a)), (-math.sin(a), math.cos(a)), (1.0, 0.0)]
            for p, q in itertools.combinations(pairs, 2):
                def span(lines, ax):
                    vals = [pt[0] * ax[0] + pt[1] * ax[1] for e in lines for pt in (e["start"], e["end"])]
                    return min(vals), max(vals)
                separated = False
                for ax in axes:
                    (p0, p1), (q0, q1) = span(p, ax), span(q, ax)
                    if p1 + 4.0 - 1e-6 <= q0 or q1 + 4.0 - 1e-6 <= p0:
                        separated = True
                self.assertTrue(separated, angle)

    def test_milling_holes_fit_the_tool(self):
        geo = fit_test.coupon_set(corner_style="dogbone", tool_diameter=3.175, count=3)
        self.assertTrue(all(e["radius"] > 3.175 / 2 for e in geo["elements"] if e["type"] == "circle"))
        with self.assertRaisesRegex(sm.SketchDataError, "index holes"):
            fit_test.coupon_set(count=12)


class KerfTestExampleTests(unittest.TestCase):
    def test_graph_is_valid_and_serializable(self):
        g = GraphModel()
        ids = kerf_test.build(g)
        self.assertEqual(6 + 3 + 3 * 3, len(g.nodes))
        self.assertEqual(len(g.nodes), len(g.topological_order()))
        self.assertEqual(g.to_dict(), GraphModel.from_json(g.to_json()).to_dict())
        self.assertEqual([0.0, 90.0, 45.0], [g.nodes[ids[f"set{a}_coupons"]].params["angle"] for a in ("0", "90", "45")])
        self.assertEqual(2 + 3, len(g.frames))

    def test_corner_style_override(self):
        g = GraphModel()
        ids = kerf_test.build(g, corner_style="dogbone")
        self.assertEqual("dogbone", g.nodes[ids["set45_coupons"]].params["corner_style"])


if __name__ == "__main__":
    unittest.main()
