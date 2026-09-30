import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ParamWeave"))

from paramweave.app import sketch_model as sm


class SketchModelTests(unittest.TestCase):
    def test_rectangle_is_closed_and_constrained(self):
        geo = sm.rectangle(0, 0, 20, 10)
        self.assertEqual(4, len(geo["elements"]))
        self.assertEqual([20.0, 10.0], [float(v) for v in geo["elements"][1]["end"]])
        kinds = [c["type"] for c in geo["constraints"]]
        self.assertEqual(4, kinds.count("Coincident"))
        self.assertEqual(2, kinds.count("Horizontal"))
        self.assertIn({"type": "Coincident", "refs": [[3, 2], [0, 1]]}, geo["constraints"])

    def test_combine_reindexes_constraints_but_not_axes(self):
        a = sm.line(0, 0, 10, 0)
        a["constraints"].append({"type": "PointOnObject", "refs": [[0, 1], [-1]]})
        rect = sm.rectangle(0, 0, 5, 5)
        out = sm.combine([a, None, rect])
        self.assertEqual(5, len(out["elements"]))
        self.assertEqual([[0, 1], [-1]], out["constraints"][0]["refs"])
        self.assertEqual([[1, 2], [2, 1]], out["constraints"][1]["refs"])
        # Inputs are not mutated.
        self.assertEqual([[0, 2], [1, 1]], rect["constraints"][0]["refs"])

    def test_remove_drops_constraints_and_reindexes(self):
        geo = sm.combine([sm.circle(0, 0, 3), sm.rectangle(0, 0, 5, 5)])
        out = sm.remove_elements(geo, "0")
        self.assertEqual(4, len(out["elements"]))
        self.assertIn({"type": "Coincident", "refs": [[0, 2], [1, 1]]}, out["constraints"])
        out = sm.remove_elements(geo, "1")
        self.assertEqual(
            [
                {"type": "Coincident", "refs": [[1, 2], [2, 1]]},
                {"type": "Coincident", "refs": [[2, 2], [3, 1]]},
                {"type": "Vertical", "refs": [[1]]},
                {"type": "Horizontal", "refs": [[2]]},
                {"type": "Vertical", "refs": [[3]]},
            ],
            out["constraints"],
        )

    def test_parse_indices(self):
        self.assertEqual([0, 2, 3, 4], sm.parse_indices("0, 2-4", 5))
        self.assertEqual([0, 1, 2], sm.parse_indices("", 3))
        with self.assertRaises(sm.SketchDataError):
            sm.parse_indices("7", 3)
        with self.assertRaises(sm.SketchDataError):
            sm.parse_indices("x", 3)

    def test_translate_selected_elements(self):
        geo = sm.combine([sm.point(1, 1), sm.circle(0, 0, 2)])
        out = sm.translate(geo, 5, -1, "1")
        self.assertEqual([1, 1], out["elements"][0]["at"])
        self.assertEqual([5, -1], out["elements"][1]["center"])

    def test_rotate_quarter_turn_swaps_horizontal_vertical(self):
        out = sm.rotate(sm.rectangle(0, 0, 20, 10), 90)
        self.assertAlmostEqual(0.0, out["elements"][0]["end"][0])
        self.assertAlmostEqual(20.0, out["elements"][0]["end"][1])
        self.assertEqual({"type": "Vertical", "refs": [[0]]}, out["constraints"][4])

    def test_rotate_odd_angle_drops_horizontal_vertical(self):
        out = sm.rotate(sm.rectangle(0, 0, 20, 10), 30)
        self.assertEqual({"Coincident"}, {c["type"] for c in out["constraints"]})

    def test_polygon(self):
        geo = sm.regular_polygon(0, 0, 10, 6)
        self.assertEqual(6, len(geo["elements"]))
        self.assertEqual(5, len([c for c in geo["constraints"] if c["type"] == "Equal"]))
        with self.assertRaises(sm.SketchDataError):
            sm.regular_polygon(0, 0, 10, 2)

    def test_constraints_and_values(self):
        geo = sm.add_constraint(sm.circle(0, 0, 5), {"type": "Radius", "refs": [[0]], "value": 5.0, "name": "r"})
        out = sm.set_constraint_value(geo, "r", 7.5)
        self.assertEqual(7.5, out["constraints"][0]["value"])
        self.assertEqual(5.0, geo["constraints"][0]["value"])
        with self.assertRaises(sm.SketchDataError):
            sm.set_constraint_value(geo, "missing", 1)
        with self.assertRaises(sm.SketchDataError):
            sm.add_constraint(geo, {"type": "Radius", "refs": [[3]], "value": 1.0})
        with self.assertRaises(sm.SketchDataError):
            sm.add_constraint(geo, {"type": "Radius", "refs": [[0]]})
        with self.assertRaises(sm.SketchDataError):
            sm.add_constraint(geo, {"type": "Bogus", "refs": [[0]]})

    def test_read_dimensions(self):
        geo = sm.add_constraint(sm.circle(0, 0, 5), {"type": "Radius", "refs": [[0]], "value": 5.0, "name": "r"})
        self.assertEqual(5.0, sm.constraint_value(geo, "r"))
        with self.assertRaisesRegex(sm.SketchDataError, "named: r"):
            sm.constraint_value(geo, "x")
        rect = sm.rectangle(1, 2, 20, 10)
        self.assertEqual(20.0, sm.element_quantity(rect, 0, "length"))
        self.assertEqual(90.0, sm.element_quantity(rect, 1, "angle"))
        self.assertEqual(2.0, sm.element_quantity(rect, 0, "y"))
        self.assertEqual(10.0, sm.element_quantity(sm.circle(0, 0, 5), 0, "diameter"))
        self.assertAlmostEqual(3.14159265, sm.element_quantity(sm.arc(0, 0, 2, 0, 90), 0, "length"))
        with self.assertRaises(sm.SketchDataError):
            sm.element_quantity(rect, 0, "radius")
        with self.assertRaises(sm.SketchDataError):
            sm.element_quantity(rect, 9, "length")

    def test_parse_refs(self):
        self.assertEqual([[0, 2], [1, 1]], sm.parse_refs("0:2 1:1"))
        self.assertEqual([[0], [-1]], sm.parse_refs("0, -1"))
        with self.assertRaises(sm.SketchDataError):
            sm.parse_refs("")
        with self.assertRaises(sm.SketchDataError):
            sm.parse_refs("0:1:2")

    def test_validation_rejects_bad_elements(self):
        for bad in (
            None,
            {"elements": [{"type": "spline"}], "constraints": []},
            {"elements": [{"type": "line", "start": [0, 0], "end": [0, 0]}], "constraints": []},
            {"elements": [{"type": "circle", "center": [0, 0], "radius": -1}], "constraints": []},
            {"elements": [{"type": "point", "at": [0, float("nan")]}], "constraints": []},
        ):
            with self.assertRaises(sm.SketchDataError):
                sm.validate(bad)


if __name__ == "__main__":
    unittest.main()
