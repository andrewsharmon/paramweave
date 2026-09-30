"""FreeCAD console tests for persistence, evaluation and reference resolution.

Run via ``python3 tools/run_freecad_tests.py`` (uses freecadcmd; no GUI).
"""

import json
import os
import tempfile
import unittest
import uuid

import FreeCAD as App
import Part

from paramweave.app.evaluator import BLOCKED, ERROR, OK, WARNING, GraphEvaluator, find_generated, remove_generated
from paramweave.app.model import GraphModel, GraphValidationError
from paramweave.app.persistence import GraphStore, transaction
from paramweave.app.references import resolve_reference, shape_signature
from paramweave.constants import STORE_OBJECT_NAME
from paramweave.nodes.core import register_core_nodes

register_core_nodes()


def _new_doc(name):
    doc = App.newDocument(name)
    doc.UndoMode = 1
    return doc


def _cut_graph():
    g = GraphModel()
    box = g.create_node("primitive.box", "Box", (0, 0), {"length": 10.0, "width": 10.0, "height": 10.0})
    cyl = g.create_node("primitive.cylinder", "Cylinder", (0, 100), {"radius": 5.0, "height": 10.0})
    cut = g.create_node("boolean.cut", "Cut", (200, 50), {})
    g.connect(box.id, "shape", cut.id, "base")
    g.connect(cyl.id, "shape", cut.id, "tool")
    return g, box, cyl, cut


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.doc = _new_doc("PWPersist")
        self.tmp = tempfile.mkdtemp(prefix="pw_fc_")

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)

    def test_load_does_not_create_store_object(self):
        model = GraphStore(self.doc).load()
        self.assertEqual({}, model.nodes)
        self.assertIsNone(self.doc.getObject(STORE_OBJECT_NAME))

    def test_saving_empty_graph_does_not_create_store_object(self):
        GraphStore(self.doc).save(GraphModel())
        self.assertIsNone(self.doc.getObject(STORE_OBJECT_NAME))

    def test_round_trip_through_fcstd(self):
        g, *_ = _cut_graph()
        GraphStore(self.doc).save(g)
        path = os.path.join(self.tmp, "persist.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        reopened = App.openDocument(path)
        restored = GraphStore(reopened).load()
        self.assertEqual(g.to_dict(), restored.to_dict())
        store = reopened.getObject(STORE_OBJECT_NAME)
        self.assertIn("ReadOnly", store.getEditorMode("GraphJSON"))
        self.assertIn("Output", store.getPropertyStatus("GraphJSON"))

    def test_frames_round_trip_through_fcstd(self):
        g, *_ = _cut_graph()
        g.create_frame("Inputs", [-30, -60, 300, 400], "green", "Primitive sizes")
        GraphStore(self.doc).save(g)
        path = os.path.join(self.tmp, "frames.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        restored = GraphStore(App.openDocument(path)).load()
        self.assertEqual(g.to_dict(), restored.to_dict())
        self.assertEqual(["Inputs"], [f.label for f in restored.frames.values()])

    def test_store_write_does_not_touch_document_recompute_state(self):
        g, *_ = _cut_graph()
        GraphStore(self.doc).save(g)
        self.doc.recompute()
        g.nodes[next(iter(g.nodes))].label = "Renamed"
        GraphStore(self.doc).save(g)
        self.assertNotIn("Touched", self.doc.getObject(STORE_OBJECT_NAME).State)

    def test_transaction_makes_graph_edit_undoable(self):
        store = GraphStore(self.doc)
        g, *_ = _cut_graph()
        with transaction(self.doc, "ParamWeave: first"):
            store.save(g)
        g.create_node("primitive.box", "Box 2", (0, 300), {})
        with transaction(self.doc, "ParamWeave: second"):
            store.save(g)
        self.assertEqual(4, len(store.load().nodes))
        self.doc.undo()
        self.assertEqual(3, len(store.load().nodes))
        self.doc.redo()
        self.assertEqual(4, len(store.load().nodes))

    def test_transaction_aborts_on_error(self):
        store = GraphStore(self.doc)
        g, *_ = _cut_graph()
        with transaction(self.doc, "ParamWeave: first"):
            store.save(g)
        with self.assertRaises(RuntimeError):
            with transaction(self.doc, "ParamWeave: broken"):
                g.create_node("primitive.box", "Box 2", (0, 300), {})
                store.save(g)
                raise RuntimeError("boom")
        self.assertEqual(3, len(store.load().nodes))

    def test_malformed_json_raises_and_is_left_intact(self):
        store_obj = self.doc.addObject("App::FeaturePython", STORE_OBJECT_NAME)
        store_obj.addProperty("App::PropertyString", "GraphJSON", "ParamWeave", "")
        store_obj.GraphJSON = "{not json"
        with self.assertRaises(GraphValidationError):
            GraphStore(self.doc).load()
        self.assertEqual("{not json", store_obj.GraphJSON)


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.doc = _new_doc("PWEval")

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)

    def _generated(self):
        return [o for o in self.doc.Objects if "ParamWeaveNodeId" in o.PropertiesList]

    def test_box_cylinder_cut(self):
        g, box, cyl, cut = _cut_graph()
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual({box.id: OK, cyl.id: OK, cut.id: OK}, {k: v.status for k, v in ev.results.items()})
        cut_obj = find_generated(self.doc, cut.id)
        self.assertEqual("Part::Feature", cut_obj.TypeId)
        self.assertAlmostEqual(1000.0 - 250.0 * 3.141592653589793 / 4, cut_obj.Shape.Volume, places=6)
        self.assertTrue(cut_obj.Visibility)
        self.assertFalse(find_generated(self.doc, box.id).Visibility)
        names = sorted(o.Name for o in self._generated())
        g.nodes[box.id].params["length"] = 20.0
        GraphEvaluator(self.doc, g).evaluate_all()
        self.assertEqual(names, sorted(o.Name for o in self._generated()))
        self.assertAlmostEqual(2000.0, find_generated(self.doc, box.id).Shape.Volume, places=6)

    def test_fuse_and_translate(self):
        g = GraphModel()
        a = g.create_node("primitive.box", "A", (0, 0), {"length": 10.0, "width": 10.0, "height": 10.0})
        b = g.create_node("primitive.box", "B", (0, 0), {"length": 10.0, "width": 10.0, "height": 10.0})
        move = g.create_node("transform.translate", "Move", (0, 0), {"x": 20.0, "y": 0.0, "z": 0.0})
        fuse = g.create_node("boolean.fuse", "Fuse", (0, 0), {})
        g.connect(b.id, "shape", move.id, "shape")
        g.connect(a.id, "shape", fuse.id, "a")
        g.connect(move.id, "shape", fuse.id, "b")
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual({}, ev.errors)
        shape = find_generated(self.doc, fuse.id).Shape
        self.assertAlmostEqual(2000.0, shape.Volume, places=6)
        self.assertAlmostEqual(30.0, shape.BoundBox.XLength, places=6)

    def test_invalid_parameter_errors_and_blocks_downstream(self):
        g, box, cyl, cut = _cut_graph()
        g.nodes[box.id].params["height"] = -1.0
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual(ERROR, ev.results[box.id].status)
        self.assertEqual(OK, ev.results[cyl.id].status)
        self.assertEqual(BLOCKED, ev.results[cut.id].status)
        self.assertIsNone(find_generated(self.doc, cut.id))

    def test_non_numeric_and_non_finite_parameters(self):
        for bad in ("abc", float("inf"), float("nan"), True, None):
            g, box, _cyl, _cut = _cut_graph()
            g.nodes[box.id].params["length"] = bad
            ev = GraphEvaluator(self.doc, g)
            ev.evaluate_all()
            self.assertEqual(ERROR, ev.results[box.id].status, f"value {bad!r}")

    def test_unconnected_required_input(self):
        g = GraphModel()
        cut = g.create_node("boolean.cut", "Cut", (0, 0), {})
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual(ERROR, ev.results[cut.id].status)
        self.assertIn("not connected", ev.results[cut.id].message)

    def test_unknown_type_is_error_not_crash(self):
        g = GraphModel()
        unknown = g.create_node("evil.__import__", "Unknown", (0, 0), {"code": "__import__('os').system('echo hi')"})
        box = g.create_node("primitive.box", "Box", (0, 0), {})
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual(ERROR, ev.results[unknown.id].status)
        self.assertEqual(OK, ev.results[box.id].status)

    def test_reference_nodes_do_not_generate_objects(self):
        target = self.doc.addObject("Part::Box", "Target")
        self.doc.recompute()
        g = GraphModel()
        ref = g.create_node("reference.geometry", "Ref", (0, 0), {"reference": {"object_name": "Target", "subelement": "Face1"}})
        measure = g.create_node("measure.shape", "Measure", (0, 0), {})
        g.connect(ref.id, "shape", measure.id, "shape")
        ev = GraphEvaluator(self.doc, g)
        outputs = ev.evaluate_all()
        self.assertEqual([], self._generated())
        self.assertAlmostEqual(target.Shape.Faces[0].Area, outputs[measure.id]["area"], places=9)

    def test_remove_generated_keeps_objects_with_dependents(self):
        g, box, cyl, cut = _cut_graph()
        GraphEvaluator(self.doc, g).evaluate_all()
        user_feature = self.doc.addObject("Part::Mirroring", "UserMirror")
        user_feature.Source = find_generated(self.doc, cut.id)
        self.doc.recompute()
        kept = remove_generated(self.doc, [box.id, cut.id])
        self.assertIsNone(find_generated(self.doc, box.id))
        self.assertIsNotNone(find_generated(self.doc, cut.id))
        self.assertEqual([find_generated(self.doc, cut.id).Name], kept)


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.doc = _new_doc("PWRefs")
        self.box = self.doc.addObject("Part::Box", "RefBox")
        self.doc.recompute()

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)

    def _ref(self, obj, sub):
        shape = obj.getSubObject(sub) if sub else obj.Shape
        return {"object_name": obj.Name, "object_label": obj.Label, "subelement": sub, "signature": shape_signature(shape)}

    def test_resolves_object_face_edge_vertex(self):
        for sub, kind in (("", "Solid"), ("Face1", "Face"), ("Edge3", "Edge"), ("Vertex2", "Vertex")):
            obj, resolved, shape = resolve_reference(self.doc, self._ref(self.box, sub))
            self.assertEqual("RefBox", obj.Name)
            self.assertEqual(sub, resolved)
            self.assertEqual(kind, shape.ShapeType)

    def test_label_change_does_not_break_reference(self):
        ref = self._ref(self.box, "Face2")
        self.box.Label = "Renamed Box"
        obj, sub, _ = resolve_reference(self.doc, ref)
        self.assertEqual(("RefBox", "Face2"), (obj.Name, sub))

    def test_deleted_object(self):
        ref = self._ref(self.box, "Face1")
        self.doc.removeObject("RefBox")
        with self.assertRaisesRegex(LookupError, "no longer exists"):
            resolve_reference(self.doc, ref)

    def _feature_with(self, shape, name="Feat"):
        feat = self.doc.addObject("Part::Feature", name)
        feat.Shape = shape
        return feat

    def test_unique_geometric_recovery(self):
        # Capture Face7 on a two-box compound, then shrink to a single box whose
        # faces include one geometrically identical to the original Face7.
        a = Part.makeBox(10, 10, 10)
        b = Part.makeBox(10, 10, 10, App.Vector(20, 0, 0))
        feat = self._feature_with(Part.makeCompound([a, b]))
        ref = self._ref(feat, "Face7")
        feat.Shape = b.copy()
        obj, sub, shape = resolve_reference(self.doc, ref)
        self.assertNotEqual("Face7", sub)
        self.assertEqual(shape_signature(shape)["center"], ref["signature"]["center"])
        with self.assertRaises(LookupError):
            resolve_reference(self.doc, ref, allow_recovery=False)

    def test_ambiguous_recovery_is_refused(self):
        a = Part.makeBox(10, 10, 10)
        b = Part.makeBox(10, 10, 10, App.Vector(20, 0, 0))
        feat = self._feature_with(Part.makeCompound([a, b]))
        ref = self._ref(feat, "Face7")
        # Face7 disappears and two coincident copies of it remain: two equally
        # good candidates, so the reference must be reported, not rebound.
        feat.Shape = Part.makeCompound([b.Faces[0].copy(), b.Faces[0].copy()])
        with self.assertRaisesRegex(LookupError, "Ambiguous"):
            resolve_reference(self.doc, ref)

    def test_no_match_is_broken(self):
        feat = self._feature_with(Part.makeCompound([Part.makeBox(10, 10, 10), Part.makeBox(5, 5, 5, App.Vector(20, 0, 0))]))
        ref = self._ref(feat, "Face9")
        feat.Shape = Part.makeBox(3, 3, 3)
        with self.assertRaisesRegex(LookupError, "could not be recovered"):
            resolve_reference(self.doc, ref)

    def test_evaluator_marks_recovery_as_warning_without_rebinding(self):
        a = Part.makeBox(10, 10, 10)
        b = Part.makeBox(10, 10, 10, App.Vector(20, 0, 0))
        feat = self._feature_with(Part.makeCompound([a, b]))
        ref = self._ref(feat, "Face7")
        g = GraphModel()
        node = g.create_node("reference.geometry", "Ref", (0, 0), {"reference": ref})
        feat.Shape = b.copy()
        ev = GraphEvaluator(self.doc, g)
        ev.evaluate_all()
        self.assertEqual(WARNING, ev.results[node.id].status)
        self.assertIn("Face7", ev.results[node.id].message)
        self.assertEqual("Face7", g.nodes[node.id].params["reference"]["subelement"])


if __name__ == "__main__":
    unittest.main()
