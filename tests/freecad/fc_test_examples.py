"""FreeCAD console tests for the bundled example graphs."""

import unittest

import FreeCAD as App

from paramweave.app.evaluator import OK, GraphEvaluator, find_generated
from paramweave.app.model import GraphModel
from paramweave.examples import finger_box
from paramweave.nodes.core import register_core_nodes

register_core_nodes()

PANELS = ("bottom", "front", "back", "left", "right", "lid")


class FingerBoxTests(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("PWFingerBox")

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)

    def _check_box(self, g, ids, L, W, H, t, lid=True):
        ev = GraphEvaluator(self.doc, g)
        out = ev.evaluate_all()
        self.assertEqual({OK}, {r.status for r in ev.results.values()}, {g.nodes[k].label: r.message for k, r in ev.results.items() if r.status != OK})
        panels = [out[ids[k]]["shape"] for k in PANELS if k in ids]
        for shape in panels:
            self.assertTrue(shape.isValid())
            self.assertEqual(1, len(shape.Solids))
        inner = (L - 2 * t) * (W - 2 * t) * (H - (2 if lid else 1) * t)
        shell = L * W * H - inner
        total = sum(s.Volume for s in panels)
        self.assertAlmostEqual(shell, total, places=4)  # no gaps...
        fused = panels[0].fuse(panels[1:])
        self.assertAlmostEqual(total, fused.Volume, places=4)  # ...and no overlaps
        bb = fused.BoundBox
        self.assertAlmostEqual(L, bb.XLength, places=6)
        self.assertAlmostEqual(W, bb.YLength, places=6)
        self.assertAlmostEqual(H, bb.ZLength, places=6)
        return out

    def test_default_box_tiles_exactly(self):
        g = GraphModel()
        ids = finger_box.build(g)
        d = finger_box.DEFAULTS
        self._check_box(g, ids, d["length"], d["width"], d["height"], d["thickness"])
        for key in PANELS:
            sketch = find_generated(self.doc, ids[f"{key}_sketch"])
            self.assertEqual("Sketcher::SketchObject", sketch.TypeId)
            self.assertFalse(sketch.Visibility)
            self.assertTrue(find_generated(self.doc, ids[key]).Visibility)

    def test_changing_constants_regenerates_in_place(self):
        g = GraphModel()
        ids = finger_box.build(g)
        GraphEvaluator(self.doc, g).evaluate_all()
        count = len(self.doc.Objects)
        g.nodes[ids["t"]].params["value"] = 6.0
        g.nodes[ids["L"]].params["value"] = 200.0
        g.nodes[ids["nL_raw"]].params["value"] = 8.0  # forced odd -> 9
        out = self._check_box(g, ids, 200.0, 100.0, 70.0, 6.0)
        self.assertEqual(count, len(self.doc.Objects))
        self.assertEqual(9.0, out[ids["nL"]]["value"])

    def test_open_top_box(self):
        g = GraphModel()
        ids = finger_box.build(g, lid=False, fingers_height=5)
        self._check_box(g, ids, 160.0, 100.0, 70.0, 3.0, lid=False)


if __name__ == "__main__":
    unittest.main()
