"""FreeCAD console tests for the bundled example graphs."""

import os
import shutil
import tempfile
import unittest

import FreeCAD as App

from paramweave.app import cutfile
from paramweave.app.evaluator import OK, GraphEvaluator, find_generated
from paramweave.app.model import GraphModel
from paramweave.app.persistence import GraphStore
from paramweave.examples import finger_box
from paramweave.nodes.core import register_core_nodes

register_core_nodes()

PANELS = ("bottom", "front", "back", "left", "right", "lid")


TUTORIAL_FCSTD = os.path.join(os.environ["PARAMWEAVE_ROOT"], "docs", "tutorial", "finger-jointed-box.FCStd")


class TutorialFileTests(unittest.TestCase):
    """The FCStd shipped with the tutorial opens, re-evaluates and is a valid box."""

    def setUp(self):
        # Work on a copy so the shipped file is never modified by tests.
        self.tmp = tempfile.mkdtemp(prefix="pw_tut_")
        self.path = os.path.join(self.tmp, "box.FCStd")
        shutil.copy(TUTORIAL_FCSTD, self.path)

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_opens_with_geometry_without_evaluating(self):
        doc = App.openDocument(self.path)
        sketches = [o for o in doc.Objects if o.TypeId == "Sketcher::SketchObject"]
        panels = [o for o in doc.Objects if o.TypeId == "Part::Feature"]
        self.assertEqual((6, 6), (len(sketches), len(panels)))
        self.assertTrue(all(p.Shape.isValid() and len(p.Shape.Solids) == 1 for p in panels))
        self.assertEqual("", doc.License)

    def test_kerf_in_the_file_grows_the_panels(self):
        doc = App.openDocument(self.path)
        model = GraphStore(doc).load()
        (kerf,) = [n for n in model.nodes.values() if n.label == "Kerf k"]
        panels = [n.id for n in model.nodes.values() if n.type_id == "sketch.extrude"]
        nominal = GraphEvaluator(doc, model).evaluate_all()
        nominal_volume = sum(nominal[p]["shape"].Volume for p in panels)
        kerf.params["value"] = 0.2
        ev = GraphEvaluator(doc, model)
        grown = ev.evaluate_all()
        self.assertEqual({OK}, {r.status for r in ev.results.values()})
        self.assertGreater(sum(grown[p]["shape"].Volume for p in panels), nominal_volume)

    def test_graph_loads_and_re_evaluates_in_place(self):
        doc = App.openDocument(self.path)
        model = GraphStore(doc).load()
        self.assertEqual((33, 79), (len(model.nodes), len(model.edges)))
        kerf = [n for n in model.nodes.values() if n.label == "Kerf k"]
        self.assertEqual(1, len(kerf), "the tutorial file must include the Kerf k constant")
        self.assertEqual(6, sum(1 for e in model.edges.values() if e.src_node == kerf[0].id and e.dst_port == "kerf"))
        count = len(doc.Objects)
        ev = GraphEvaluator(doc, model)
        out = ev.evaluate_all()
        self.assertEqual({OK}, {r.status for r in ev.results.values()})
        self.assertEqual(count, len(doc.Objects))
        panels = [out[n.id]["shape"] for n in model.nodes.values() if n.type_id == "sketch.extrude"]
        total = sum(p.Volume for p in panels)
        L, W, H, t = 160.0, 100.0, 70.0, 3.0
        self.assertAlmostEqual(L * W * H - (L - 2 * t) * (W - 2 * t) * (H - 2 * t), total, places=4)
        self.assertAlmostEqual(total, panels[0].fuse(panels[1:]).Volume, places=4)


class CutFileTests(unittest.TestCase):
    """Cut files from the example box read back correctly in FreeCAD's own DXF importer."""

    def setUp(self):
        self.doc = App.newDocument("PWCut")
        self.tmp = tempfile.mkdtemp(prefix="pw_cut_")

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _panels(self, kerf=0.0):
        g = GraphModel()
        ids = finger_box.build(g, kerf=kerf)
        out = GraphEvaluator(self.doc, g).evaluate_all()
        return [(g.nodes[ids[f"{k}_sketch"]].label, out[ids[f"{k}_sketch"]]["geometry"]) for k in PANELS]

    @staticmethod
    def _length(panels):
        total = 0.0
        for _name, geo in panels:
            for el in cutfile.cut_elements(geo):
                (x0, y0), (x1, y1) = el["start"], el["end"]
                total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        return total

    def test_dxf_imports_into_freecad_with_every_edge(self):
        import Import

        panels = self._panels(kerf=0.15)
        path = os.path.join(self.tmp, "box.dxf")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(cutfile.export(panels, "dxf", sheet_width=600, gap=5))
        target = App.newDocument("PWCutImport")
        Import.readDXF(path, target.Name)
        target.recompute()
        edges = [e for o in target.Objects if hasattr(o, "Shape") for e in o.Shape.Edges]
        expected = sum(len(cutfile.cut_elements(g)) for _n, g in panels)
        self.assertEqual(expected, len(edges))
        self.assertAlmostEqual(self._length(panels), sum(e.Length for e in edges), places=4)
        bb = App.BoundBox()
        for e in edges:
            bb.add(e.BoundBox)
        self.assertLessEqual(bb.XMax, 600.0 + 1e-6)
        self.assertGreaterEqual(min(bb.XMin, bb.YMin), -1e-6)

    def test_svg_has_one_group_per_panel(self):
        import xml.etree.ElementTree as ET

        root = ET.fromstring(cutfile.export(self._panels(), "svg").encode())
        titles = [t.text for t in root.iter("{http://www.w3.org/2000/svg}title")]
        self.assertEqual(sorted(f"{k.capitalize()} sketch" for k in PANELS), sorted(titles))


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

    def test_kerf_grows_every_panel_by_half_kerf(self):
        g = GraphModel()
        ids = finger_box.build(g)
        out = GraphEvaluator(self.doc, g).evaluate_all()
        t = finger_box.DEFAULTS["thickness"]
        nominal = {k: out[ids[k]]["shape"].Volume for k in PANELS}
        perimeter = {k: out[ids[f"{k}_sketch"]]["shape"].Length for k in PANELS}
        g.nodes[ids["k"]].params["value"] = 0.2
        ev = GraphEvaluator(self.doc, g)
        out = ev.evaluate_all()
        self.assertEqual({OK}, {r.status for r in ev.results.values()})
        d = 0.1
        for k in PANELS:
            expected = nominal[k] + (perimeter[k] * d + 4 * d * d) * t
            self.assertAlmostEqual(expected, out[ids[k]]["shape"].Volume, places=4, msg=k)

    def test_open_top_box(self):
        g = GraphModel()
        ids = finger_box.build(g, lid=False, fingers_height=5)
        self._check_box(g, ids, 160.0, 100.0, 70.0, 3.0, lid=False)


if __name__ == "__main__":
    unittest.main()
