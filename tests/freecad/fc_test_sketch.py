"""FreeCAD console tests for sketch nodes (run via tools/run_freecad_tests.py)."""

import os
import tempfile
import unittest

import FreeCAD as App
import Part
import Sketcher

from paramweave.app.evaluator import OK, WARNING, ERROR, GraphEvaluator, find_generated
from paramweave.app.model import GraphModel
from paramweave.app.persistence import GraphStore
from paramweave.app import sketch_adapter as sa
from paramweave.nodes.core import register_core_nodes

register_core_nodes()


def _whole_ref(name):
    return {"reference": {"object_name": name, "subelement": ""}}


class SketchNodeTests(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("PWSketch")
        self.doc.UndoMode = 1

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)

    def _sketches(self):
        return [o for o in self.doc.Objects if o.TypeId == "Sketcher::SketchObject"]

    def _rect_extrude_graph(self):
        g = GraphModel()
        rect = g.create_node("sketch.rectangle", "Rect", (0, 0), {"x": 0.0, "y": 0.0, "width": 20.0, "height": 10.0})
        hole = g.create_node("sketch.circle", "Hole", (0, 100), {"cx": 10.0, "cy": 5.0, "radius": 2.0})
        both = g.create_node("sketch.combine", "Combine", (150, 50), {})
        sketch = g.create_node("sketch.sketch", "Profile", (300, 50), {"plane": "XY", "offset": 0.0})
        ext = g.create_node("sketch.extrude", "Pad", (450, 50), {"length": 5.0, "reversed": False})
        g.connect(rect.id, "geometry", both.id, "a")
        g.connect(hole.id, "geometry", both.id, "b")
        g.connect(both.id, "geometry", sketch.id, "geometry")
        g.connect(sketch.id, "shape", ext.id, "shape")
        return g, rect, sketch, ext

    def test_elements_to_sketch_to_extrude(self):
        g, rect, sketch, ext = self._rect_extrude_graph()
        ev = GraphEvaluator(self.doc, g)
        out = ev.evaluate_all()
        self.assertEqual({OK}, {r.status for r in ev.results.values()}, ev.results)
        obj = find_generated(self.doc, sketch.id)
        self.assertEqual("Sketcher::SketchObject", obj.TypeId)
        self.assertEqual(5, obj.GeometryCount)
        self.assertEqual(8, obj.ConstraintCount)
        self.assertFalse(obj.Visibility)  # consumed by the extrude
        expected = (20 * 10 - 3.141592653589793 * 4) * 5
        self.assertAlmostEqual(expected, out[ext.id]["shape"].Volume, places=6)

        g.nodes[rect.id].params["width"] = 30.0
        GraphEvaluator(self.doc, g).evaluate_all()
        self.assertEqual(1, len(self._sketches()), "sketch must be updated, not duplicated")
        self.assertAlmostEqual(30.0, find_generated(self.doc, sketch.id).Shape.BoundBox.XLength, places=9)

    def test_plane_and_offset(self):
        g = GraphModel()
        line = g.create_node("sketch.line", "L", (0, 0), {"x1": 0.0, "y1": 0.0, "x2": 0.0, "y2": 10.0})
        sk = g.create_node("sketch.sketch", "S", (0, 0), {"plane": "XZ", "offset": 3.0})
        g.connect(line.id, "geometry", sk.id, "geometry")
        out = GraphEvaluator(self.doc, g).evaluate_all()
        bb = out[sk.id]["shape"].BoundBox
        self.assertAlmostEqual(10.0, bb.ZLength, places=9)
        self.assertAlmostEqual(-3.0, bb.YMin, places=9)

    def test_constraints_named_and_set(self):
        g = GraphModel()
        c = g.create_node("sketch.circle", "C", (0, 0), {"cx": 0.0, "cy": 0.0, "radius": 5.0})
        add = g.create_node("sketch.add_constraint", "R", (0, 0), {"constraint": "Radius", "refs": "0", "value": 5.0, "name": "r"})
        setv = g.create_node("sketch.set_constraint", "Set r", (0, 0), {"name": "r", "value": 7.0})
        sk = g.create_node("sketch.sketch", "S", (0, 0), {"plane": "XY", "offset": 0.0})
        g.connect(c.id, "geometry", add.id, "geometry")
        g.connect(add.id, "geometry", setv.id, "geometry")
        g.connect(setv.id, "geometry", sk.id, "geometry")
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual(OK, ev.results[sk.id].status, ev.results[sk.id].message)
        obj = find_generated(self.doc, sk.id)
        self.assertAlmostEqual(7.0, obj.Geometry[0].Radius, places=9)
        self.assertEqual("r", obj.Constraints[0].Name)

    def test_conflicting_constraints_warn(self):
        g = GraphModel()
        ln = g.create_node("sketch.line", "L", (0, 0), {"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0})
        h = g.create_node("sketch.add_constraint", "H", (0, 0), {"constraint": "Horizontal", "refs": "0", "value": 0.0, "name": ""})
        v = g.create_node("sketch.add_constraint", "V", (0, 0), {"constraint": "Vertical", "refs": "0", "value": 0.0, "name": ""})
        sk = g.create_node("sketch.sketch", "S", (0, 0), {"plane": "XY", "offset": 0.0})
        g.connect(ln.id, "geometry", h.id, "geometry")
        g.connect(h.id, "geometry", v.id, "geometry")
        g.connect(v.id, "geometry", sk.id, "geometry")
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual(WARNING, ev.results[sk.id].status)
        self.assertIn("sketch:", ev.results[sk.id].message)

    def _user_sketch(self):
        sk = self.doc.addObject("Sketcher::SketchObject", "UserSketch")
        sk.Placement = App.Placement(App.Vector(0, 0, 4), App.Rotation())
        sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)), False)
        sk.addGeometry(Part.Circle(App.Vector(20, 0, 0), App.Vector(0, 0, 1), 3), False)
        sk.addGeometry(Part.ArcOfCircle(Part.Circle(App.Vector(0, 20, 0), App.Vector(0, 0, 1), 4), 0.0, 1.5), True)
        sk.addConstraint(Sketcher.Constraint("Horizontal", 0))
        i = sk.addConstraint(Sketcher.Constraint("Radius", 1, 3.0))
        sk.renameConstraint(i, "hole")
        sk.addConstraint(Sketcher.Constraint("PointOnObject", 0, 1, -1))
        self.doc.recompute()
        return sk

    def test_read_modify_and_rebuild_document_sketch(self):
        user = self._user_sketch()
        g = GraphModel()
        ref = g.create_node("reference.geometry", "Ref", (0, 0), _whole_ref(user.Name))
        read = g.create_node("sketch.read", "Read", (0, 0), {})
        move = g.create_node("sketch.translate", "Move", (0, 0), {"dx": 5.0, "dy": 0.0, "elements": "1"})
        setv = g.create_node("sketch.set_constraint", "Hole", (0, 0), {"name": "hole", "value": 1.5})
        out = g.create_node("sketch.sketch", "Copy", (0, 0), {"plane": "XY", "offset": 0.0})
        g.connect(ref.id, "object", read.id, "object")
        g.connect(read.id, "geometry", move.id, "geometry")
        g.connect(move.id, "geometry", setv.id, "geometry")
        g.connect(setv.id, "geometry", out.id, "geometry")
        g.connect(read.id, "placement", out.id, "placement")
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual({OK}, {r.status for r in ev.results.values()}, {k: r.message for k, r in ev.results.items()})
        copy = find_generated(self.doc, out.id)
        self.assertEqual(3, copy.GeometryCount)
        self.assertTrue(copy.getConstruction(2))
        self.assertAlmostEqual(25.0, copy.Geometry[1].Center.x, places=9)
        self.assertAlmostEqual(1.5, copy.Geometry[1].Radius, places=9)
        self.assertAlmostEqual(4.0, copy.Placement.Base.z, places=9)
        self.assertEqual(["hole"], [c.Name for c in copy.Constraints if c.Name])
        # The user's sketch is only read, never changed.
        self.assertAlmostEqual(3.0, user.Geometry[1].Radius, places=9)

    def test_read_round_trips_arcs(self):
        user = self._user_sketch()
        geo = sa.read_sketch(user)
        arc = geo["elements"][2]
        self.assertAlmostEqual(0.0, arc["start_angle"], places=9)
        self.assertAlmostEqual(85.94366926962348, arc["end_angle"], places=9)

    def test_read_refuses_unsupported_geometry(self):
        user = self._user_sketch()
        user.addGeometry(Part.Ellipse(App.Vector(0, 0, 0), 5, 2), False)
        with self.assertRaisesRegex(ValueError, "Ellipse"):
            sa.read_sketch(user)

    def test_drive_named_constraint_on_document_sketch(self):
        user = self._user_sketch()
        g = GraphModel()
        ref = g.create_node("reference.geometry", "Ref", (0, 0), _whole_ref(user.Name))
        drive = g.create_node("sketch.drive_constraint", "Drive", (0, 0), {"name": "hole", "value": 4.5})
        g.connect(ref.id, "object", drive.id, "object")
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual(OK, ev.results[drive.id].status, ev.results[drive.id].message)
        self.assertAlmostEqual(4.5, user.Geometry[1].Radius, places=9)
        g.nodes[drive.id].params["name"] = "nope"
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual(ERROR, ev.results[drive.id].status)
        self.assertIn("hole", ev.results[drive.id].message)

    def test_drive_from_measured_number(self):
        user = self._user_sketch()
        g = GraphModel()
        box = g.create_node("primitive.box", "Box", (0, 0), {"length": 2.0, "width": 3.0, "height": 1.0})
        measure = g.create_node("measure.shape", "Measure", (0, 0), {})
        ref = g.create_node("reference.geometry", "Ref", (0, 0), _whole_ref(user.Name))
        drive = g.create_node("sketch.drive_constraint", "Drive", (0, 0), {"name": "hole", "value": 1.0})
        g.connect(box.id, "shape", measure.id, "shape")
        g.connect(measure.id, "volume", drive.id, "value")
        g.connect(ref.id, "object", drive.id, "object")
        GraphEvaluator(self.doc, g).evaluate_all()
        self.assertAlmostEqual(6.0, user.Geometry[1].Radius, places=9)

    def test_dimensions_from_constant_expression_and_spreadsheet(self):
        sheet = self.doc.addObject("Spreadsheet::Sheet", "Spreadsheet")
        sheet.set("A1", "4 mm")
        sheet.setAlias("A1", "wall")
        self.doc.recompute()
        g = GraphModel()
        width = g.create_node("value.number", "Width", (0, 0), {"value": 30.0})
        wall = g.create_node("value.document", "Wall", (0, 0), {"object": "Spreadsheet", "property": "wall"})
        height = g.create_node("value.expression", "Height", (0, 0), {"expression": "a / 2 - b"})
        sides = g.create_node("value.expression", "Sides", (0, 0), {"expression": "b + 2"})
        rect = g.create_node("sketch.rectangle", "Rect", (0, 0), {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0})
        poly = g.create_node("sketch.polygon", "Poly", (0, 0), {"cx": 0.0, "cy": 0.0, "radius": 1.0, "sides": 3, "rotation": 0.0})
        g.connect(width.id, "value", rect.id, "width")
        g.connect(width.id, "value", height.id, "a")
        g.connect(wall.id, "value", height.id, "b")
        g.connect(wall.id, "value", sides.id, "b")
        g.connect(height.id, "value", rect.id, "height")
        g.connect(sides.id, "value", poly.id, "sides")
        ev = GraphEvaluator(self.doc, g)
        out = ev.evaluate_all()
        self.assertEqual({OK}, {r.status for r in ev.results.values()}, {k: r.message for k, r in ev.results.items()})
        self.assertEqual([30.0, 11.0], out[rect.id]["geometry"]["elements"][1]["end"])
        self.assertEqual(6, len(out[poly.id]["geometry"]["elements"]))
        # Stored parameters are untouched; the wire only overrides at evaluation.
        self.assertEqual(1.0, g.nodes[rect.id].params["width"])

    def test_non_integral_value_into_integer_param_errors(self):
        g = GraphModel()
        n = g.create_node("value.number", "N", (0, 0), {"value": 4.5})
        poly = g.create_node("sketch.polygon", "Poly", (0, 0), {"cx": 0.0, "cy": 0.0, "radius": 1.0, "sides": 3, "rotation": 0.0})
        g.connect(n.id, "value", poly.id, "sides")
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual(ERROR, ev.results[poly.id].status)

    def test_referenced_dimension_drives_other_geometry(self):
        user = self._user_sketch()
        g = GraphModel()
        ref = g.create_node("reference.geometry", "Ref", (0, 0), _whole_ref(user.Name))
        dim = g.create_node("sketch.dimension", "Hole r", (0, 0), {"name": "hole"})
        read = g.create_node("sketch.read", "Read", (0, 0), {})
        seg = g.create_node("sketch.measure_element", "Seg", (0, 0), {"element": 0, "quantity": "length"})
        circle = g.create_node("sketch.circle", "C", (0, 0), {"cx": 0.0, "cy": 0.0, "radius": 1.0})
        box = g.create_node("primitive.box", "Box", (0, 0), {"length": 1.0, "width": 1.0, "height": 1.0})
        g.connect(ref.id, "object", dim.id, "object")
        g.connect(ref.id, "object", read.id, "object")
        g.connect(read.id, "geometry", seg.id, "geometry")
        g.connect(dim.id, "value", circle.id, "radius")
        g.connect(seg.id, "value", box.id, "length")
        ev = GraphEvaluator(self.doc, g)
        out = ev.evaluate_all()
        self.assertEqual({OK}, {r.status for r in ev.results.values()}, {k: r.message for k, r in ev.results.items()})
        self.assertEqual(3.0, out[circle.id]["geometry"]["elements"][0]["radius"])
        self.assertAlmostEqual(10.0, out[box.id]["shape"].BoundBox.XLength, places=9)

        g.nodes[dim.id].params["name"] = "missing"
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual(ERROR, ev.results[dim.id].status)
        self.assertIn("hole", ev.results[dim.id].message)

    def test_param_added_after_save_can_still_be_driven(self):
        # A Finger Joint Panel saved before 'kerf' existed has no such key.
        g = GraphModel()
        k = g.create_node("value.number", "k", (0, 0), {"value": 0.4})
        params = {"width": 40.0, "height": 20.0, "thickness": 2.0}
        params.update({f"fingers_{s}": 1 for s in ("bottom", "right", "top", "left")})
        params.update({f"mode_{s}": "flat" for s in ("bottom", "right", "top", "left")})
        panel = g.create_node("sketch.finger_panel", "P", (0, 0), params)
        g.connect(k.id, "value", panel.id, "kerf")
        ev = GraphEvaluator(self.doc, g)
        out = ev.evaluate_all()
        self.assertEqual(OK, ev.results[panel.id].status, ev.results[panel.id].message)
        self.assertEqual([-0.2, -0.2], out[panel.id]["geometry"]["elements"][0]["start"])
        self.assertNotIn("kerf", g.nodes[panel.id].params)  # stored data untouched

    def test_sketch_graph_survives_save_and_reopen(self):
        g, _rect, sketch, _ext = self._rect_extrude_graph()
        GraphEvaluator(self.doc, g).evaluate_all()
        GraphStore(self.doc).save(g)
        path = os.path.join(tempfile.mkdtemp(prefix="pw_fc_"), "sketch.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        restored = GraphStore(self.doc).load()
        self.assertEqual(g.to_dict(), restored.to_dict())
        ev = GraphEvaluator(self.doc, restored)
        ev.evaluate_all()
        self.assertEqual({OK}, {r.status for r in ev.results.values()})
        self.assertEqual(1, len(self._sketches()))
        self.assertEqual(5, find_generated(self.doc, sketch.id).GeometryCount)


if __name__ == "__main__":
    unittest.main()
