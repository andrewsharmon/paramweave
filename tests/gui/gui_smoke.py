"""ParamWeave GUI smoke test, executed inside a full FreeCAD GUI session.

Do not run this with ordinary Python. Use ``tools/run_freecad_tests.py --gui``,
which launches FreeCAD with an isolated user home, symlinks the workbench into
that home's ``Mod`` directory and passes this file as a startup macro.

Results are written as JSON lines to ``$PARAMWEAVE_TEST_OUT`` as each check
finishes, so a hard crash still leaves a record of how far the run got.
"""

import json
import os
import sys
import tempfile
import threading
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

try:  # QtTest is not re-exported by FreeCAD's PySide shim.
    from PySide6 import QtTest
except ImportError:  # pragma: no cover - Qt5 builds
    from PySide2 import QtTest

sys.path.insert(0, os.path.join(os.environ["PARAMWEAVE_ROOT"], "tests", "gui"))
from gui_harness import *  # noqa: E402,F401,F403  (shared click/record helpers)

# Count observer registrations made by the workbench. This wraps the real
# FreeCAD registration functions so the observers still work normally.
_selection_observers = []
_document_observers = []
_orig_add_sel = Gui.Selection.addObserver
_orig_add_doc = App.addDocumentObserver


def _counting_add_sel(observer, *args):
    _selection_observers.append(observer)
    return _orig_add_sel(observer, *args)


def _counting_add_doc(observer, *args):
    _document_observers.append(observer)
    return _orig_add_doc(observer, *args)


Gui.Selection.addObserver = _counting_add_sel
App.addDocumentObserver = _counting_add_doc


STATE = {}


@check("workbench activates and creates a single dock")
def _activate():
    Gui.activateWorkbench("ParamWeaveWorkbench")
    pump()
    docks = paramweave_docks()
    expect(len(docks) == 1, f"expected 1 dock, found {len(docks)}")
    expect(docks[0].isVisible(), "dock is not visible")
    area = main_window().dockWidgetArea(docks[0])
    right = getattr(getattr(QtCore.Qt, "DockWidgetArea", QtCore.Qt), "RightDockWidgetArea")
    expect(area == right, f"dock is in area {area}, expected right")


@check("reactivating the workbench 10x does not duplicate docks or observers")
def _reactivate():
    for _ in range(10):
        Gui.activateWorkbench("PartWorkbench")
        pump(2)
        Gui.activateWorkbench("ParamWeaveWorkbench")
        pump(2)
    docks = paramweave_docks()
    expect(len(docks) == 1, f"expected 1 dock, found {len(docks)}")
    expect(len(_selection_observers) == 1, f"selection observers registered: {len(_selection_observers)}")
    expect(len(_document_observers) <= 1, f"document observers registered: {len(_document_observers)}")
    return f"selection observers={len(_selection_observers)} document observers={len(_document_observers)}"


@check("toggle command hides and shows the dock")
def _toggle():
    dock = paramweave_docks()[0]
    Gui.runCommand("ParamWeave_ToggleGraph")
    pump()
    expect(not dock.isVisible(), "dock still visible after toggle")
    Gui.runCommand("ParamWeave_ToggleGraph")
    pump()
    expect(dock.isVisible(), "dock hidden after second toggle")
    expect(len(paramweave_docks()) == 1, "toggle created another dock")


@check("merely viewing a document does not modify it")
def _view_no_modify():
    doc = App.newDocument("PWViewOnly")
    pump()
    expect(doc.getObject("ParamWeaveGraph") is None, "graph store object created on bind")
    App.closeDocument(doc.Name)
    pump()


@check("Box + Cylinder wired into Cut by clicking ports")
def _build_cut():
    doc = App.newDocument("PWSmoke")
    pump()
    w = ws()
    box = w.add_node("primitive.box", position=(0.0, 0.0))
    cyl = w.add_node("primitive.cylinder", position=(0.0, 160.0))
    cut = w.add_node("boolean.cut", position=(320.0, 60.0))
    STATE.update(doc=doc, box=box, cyl=cyl, cut=cut)
    pump()
    click_port(box, "out", "shape")
    click_port(cut, "in", "base")
    click_port(cyl, "out", "shape")
    click_port(cut, "in", "tool")
    expect(len(w.model.edges) == 2, f"expected 2 edges, found {len(w.model.edges)}")
    return f"rerouted synthetic presses retried: {len(REROUTED_PRESSES)}"


@check("typed ports reject an output-to-output or incompatible connection")
def _typed_ports():
    w = ws()
    measure = w.add_node("measure.shape", position=(640.0, 60.0))
    translate = w.add_node("transform.translate", position=(640.0, 260.0))
    before = len(w.model.edges)
    # Number output into a CAD.Shape input must be refused.
    click_port(measure, "out", "volume")
    click_port(translate, "in", "shape")
    expect(len(w.model.edges) == before, "incompatible Number -> CAD.Shape edge was created")
    w.scene.cancel_pending_connection()
    for node in (measure, translate):
        w.model.remove_node(node.id)
    w.scene.rebuild()
    w.persist()


@check("frame all shows every node, including ones added after the last rebuild")
def _frame_all():
    w = ws()
    far = w.add_node("primitive.box", position=(900.0, 700.0))
    pump()
    w.view.frame_all()
    pump()
    visible = w.view.mapToScene(w.view.viewport().rect()).boundingRect()
    for node_id, item in w.scene.node_items.items():
        expect(visible.contains(item.sceneBoundingRect()), f"{item.graph_node.label} outside view {visible}")
    w.delete([far.id])
    pump()


@check("evaluation creates ordinary Part::Feature objects")
def _evaluate():
    w = ws()
    doc = STATE["doc"]
    w.evaluate()
    pump()
    generated = [o for o in doc.Objects if "ParamWeaveNodeId" in o.PropertiesList]
    expect(generated, "no generated objects")
    by_node = {o.ParamWeaveNodeId: o for o in generated}
    cut = by_node.get(STATE["cut"].id)
    expect(cut is not None, "Cut produced no generated object")
    expect(cut.TypeId == "Part::Feature", f"generated type is {cut.TypeId}")
    expect(cut.Shape.isValid() and cut.Shape.Volume > 0, "cut shape invalid or empty")
    expected_volume = 10 * 10 * 10 - 3.141592653589793 * 25 * 10 / 4  # cylinder quarter overlaps box corner
    expect(abs(cut.Shape.Volume - expected_volume) < 1e-6, f"unexpected cut volume {cut.Shape.Volume}")
    group = doc.getObject("ParamWeave_Generated")
    expect(group is not None and cut in group.Group, "generated object not grouped")
    STATE["generated_names"] = sorted(o.Name for o in generated)
    for nid in (STATE["box"].id, STATE["cyl"].id, STATE["cut"].id):
        expect(node_status(nid) == "ok", f"node status {node_status(nid)!r}")
    return f"generated={STATE['generated_names']}"


@check("intermediate generated objects are hidden, terminal output visible")
def _visibility():
    doc = STATE["doc"]
    by_node = {o.ParamWeaveNodeId: o for o in doc.Objects if "ParamWeaveNodeId" in o.PropertiesList}
    expect(by_node[STATE["cut"].id].Visibility, "terminal Cut output hidden")
    expect(not by_node[STATE["box"].id].Visibility, "intermediate Box output visible")
    expect(not by_node[STATE["cyl"].id].Visibility, "intermediate Cylinder output visible")


@check("re-evaluation updates generated objects instead of duplicating")
def _reevaluate():
    w = ws()
    doc = STATE["doc"]
    w.model.nodes[STATE["box"].id].params["length"] = 20.0
    w.persist()
    w.evaluate()
    pump()
    generated = sorted(o.Name for o in doc.Objects if "ParamWeaveNodeId" in o.PropertiesList)
    expect(generated == STATE["generated_names"], f"generated objects changed: {generated}")
    box_obj = [o for o in doc.Objects if getattr(o, "ParamWeaveNodeId", None) == STATE["box"].id][0]
    expect(abs(box_obj.Shape.Volume - 2000.0) < 1e-6, f"box volume {box_obj.Shape.Volume}")


@check("editing a parameter in the property panel does not crash and persists")
def _property_edit():
    w = ws()
    box = STATE["box"]
    w.scene.select_node(box.id)
    pump()
    edits = [e for e in w.properties.findChildren(QtWidgets.QLineEdit) if e.property("paramweave_key") == "width"]
    expect(edits, "no width editor found in property panel")
    edit = edits[0]
    edit.setFocus()
    edit.selectAll()
    QtTest.QTest.keyClicks(edit, "12.5")
    QtTest.QTest.keyClick(edit, getattr(getattr(QtCore.Qt, "Key", QtCore.Qt), "Key_Return"))
    pump()
    expect(w.model.nodes[box.id].params["width"] == 12.5, f"width is {w.model.nodes[box.id].params['width']!r}")
    stored = json.loads(STATE["doc"].getObject("ParamWeaveGraph").GraphJSON)
    widths = [n["params"]["width"] for n in stored["nodes"] if n["id"] == box.id]
    expect(widths == [12.5], f"stored width {widths}")
    # Panel should still show the same node after the edit.
    expect(w.properties.node_id == box.id, "property panel lost the edited node")


@check("invalid dimension reports a node error and blocks downstream nodes")
def _invalid_dimension():
    w = ws()
    box = STATE["box"]
    w.model.nodes[box.id].params["height"] = -1.0
    w.persist()
    w.evaluate()
    pump()
    expect(node_status(box.id) == "error", f"box status {node_status(box.id)!r}")
    expect(node_status(STATE["cut"].id) == "blocked", f"cut status {node_status(STATE['cut'].id)!r}")
    w.model.nodes[box.id].params["height"] = 10.0
    w.persist()
    w.evaluate()
    pump()
    expect(node_status(box.id) == "ok", "box did not recover after fixing height")


@check("graph edits are undoable and redoable through FreeCAD")
def _undo_redo():
    w = ws()
    doc = STATE["doc"]
    before = len(w.model.nodes)
    Gui.runCommand("ParamWeave_AddFuse")
    pump()
    expect(len(w.model.nodes) == before + 1, "command did not add a node")
    expect(doc.UndoNames and doc.UndoNames[0].startswith("ParamWeave: Add"), f"undo stack {doc.UndoNames[:3]}")
    doc.undo()
    pump()
    expect(len(w.model.nodes) == before, f"after undo: {len(w.model.nodes)} nodes")
    expect(len(w.scene.node_items) == before, "scene not refreshed after undo")
    doc.redo()
    pump()
    expect(len(w.model.nodes) == before + 1, f"after redo: {len(w.model.nodes)} nodes")
    fuse = [n for n in w.model.nodes.values() if n.type_id == "boolean.fuse"][0]
    w.delete([fuse.id])
    pump()
    expect(len(w.model.nodes) == before, "delete did not remove the node")


@check("dragging a node with the mouse persists its position as one undo step")
def _drag_node():
    w = ws()
    doc = STATE["doc"]
    cut = STATE["cut"]
    item = w.scene.node_items[cut.id]
    view = w.view
    start_scene = item.scenePos() + QtCore.QPointF(40.0, 10.0)  # header area
    view.ensureVisible(item)
    pump()
    start = view.mapFromScene(start_scene)
    types = getattr(QtCore.QEvent, "Type", QtCore.QEvent)
    old_pos = list(w.model.nodes[cut.id].position)
    send_mouse(view, types.MouseButtonPress, start, left_button(), left_button())
    for step in range(1, 6):
        send_mouse(view, types.MouseMove, start + QtCore.QPoint(8 * step, 6 * step), no_button(), left_button())
    send_mouse(view, types.MouseButtonRelease, start + QtCore.QPoint(40, 30), left_button(), no_button())
    new_pos = w.model.nodes[cut.id].position
    expect(new_pos != old_pos, f"node did not move: {old_pos} -> {new_pos}")
    stored = json.loads(doc.getObject("ParamWeaveGraph").GraphJSON)
    stored_pos = [n["position"] for n in stored["nodes"] if n["id"] == cut.id][0]
    expect(stored_pos == new_pos, f"stored position {stored_pos} != model {new_pos}")
    # UndoCount saturates at FreeCAD's max stack size, so inspect the top entries.
    names = list(doc.UndoNames)
    expect(names and names[0] == "ParamWeave: Move node", f"top undo entry {names[:1]}")
    expect(len(names) < 2 or names[1] != "ParamWeave: Move node", f"drag recorded several move steps: {names[:3]}")
    return f"{old_pos} -> {new_pos}"


@check("graph survives save / close / reopen")
def _persistence():
    w = ws()
    doc = STATE["doc"]
    path = os.path.join(WORK_DIR, "paramweave_smoke.FCStd")
    before = w.model.to_dict()
    doc.saveAs(path)
    App.closeDocument(doc.Name)
    pump()
    expect(not w.model.nodes, "graph still shows nodes of the closed document")
    reopened = App.openDocument(path)
    pump()
    expect(w.model.to_dict() == before, "reopened graph differs from saved graph")
    expect(set(w.scene.node_items) == set(before_id["id"] for before_id in before["nodes"]), "scene not rebuilt")
    STATE["doc"] = reopened
    STATE["path"] = path


@check("switching documents never writes one document's graph into another")
def _doc_switch():
    w = ws()
    graph_doc = STATE["doc"]
    other = App.newDocument("PWOther")
    pump()
    expect(not w.model.nodes, "new document shows another document's graph")
    w.add_node("primitive.box", position=(0.0, 0.0))
    pump()
    Gui.setActiveDocument(graph_doc.Name)
    pump()
    expect(App.ActiveDocument.Name == graph_doc.Name, f"active document is {App.ActiveDocument.Name}")
    stored = json.loads(graph_doc.getObject("ParamWeaveGraph").GraphJSON)
    expect(len(stored["nodes"]) == 3, f"graph document now stores {len(stored['nodes'])} nodes")
    other_stored = json.loads(other.getObject("ParamWeaveGraph").GraphJSON)
    expect(len(other_stored["nodes"]) == 1, f"other document stores {len(other_stored['nodes'])} nodes")
    App.closeDocument(other.Name)
    pump()
    App.setActiveDocument(graph_doc.Name)
    pump()
    expect(len(w.model.nodes) == 3, "graph not rebound after closing the other document")


def _make_ref_doc():
    doc = App.newDocument("PWRefs")
    box = doc.addObject("Part::Box", "RefBox")
    container = doc.addObject("App::Part", "Container")
    cyl = doc.addObject("Part::Cylinder", "NestedCyl")
    container.addObject(cyl)
    doc.recompute()
    pump()
    return doc


@check("reference nodes from whole object, face, edge and vertex selection")
def _references():
    doc = _make_ref_doc()
    w = ws()
    created = {}
    for key, sub in (("object", ""), ("face", "Face1"), ("edge", "Edge3"), ("vertex", "Vertex2")):
        Gui.Selection.clearSelection()
        if sub:
            Gui.Selection.addSelection(doc.Name, "RefBox", sub)
        else:
            Gui.Selection.addSelection(doc.Name, "RefBox")
        pump()
        node = w.add_reference_from_selection()
        ref = node.params["reference"]
        expect(ref["object_name"] == "RefBox", f"{key}: object {ref['object_name']}")
        expect((ref.get("subelement") or "") == sub, f"{key}: sub {ref.get('subelement')!r}")
        created[key] = node
    # Nested selection path as produced by clicking inside an App::Part container.
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, "Container", "NestedCyl.Face1")
    pump()
    nested = w.add_reference_from_selection()
    ref = nested.params["reference"]
    expect(ref["object_name"] == "NestedCyl" and ref["subelement"] == "Face1", f"nested ref {ref}")
    created["nested"] = nested
    STATE.update(ref_doc=doc, refs=created)
    return ", ".join(f"{k}={v.params['reference'].get('subelement') or '<object>'}" for k, v in created.items())


@check("graph -> viewport: selecting a reference node selects FreeCAD geometry")
def _graph_to_viewport():
    w = ws()
    for key, expected in (("face", ("RefBox", "Face1")), ("edge", ("RefBox", "Edge3")), ("object", ("RefBox", ""))):
        Gui.Selection.clearSelection()
        w.scene.clearSelection()
        pump()
        w.scene.select_node(STATE["refs"][key].id)
        pump()
        pairs = resolved_selection_pairs()
        expect(pairs == [expected], f"{key}: FreeCAD selection {pairs}")
    Gui.Selection.clearSelection()
    w.scene.clearSelection()
    pump()
    w.scene.select_node(STATE["refs"]["nested"].id)
    pump()
    pairs = resolved_selection_pairs()
    expect(pairs == [("NestedCyl", "Face1")], f"nested: FreeCAD selection {pairs}")


@check("viewport -> graph: selecting FreeCAD geometry selects reference node")
def _viewport_to_graph():
    w = ws()
    doc = STATE["ref_doc"]
    for key, (obj, sub) in (("edge", ("RefBox", "Edge3")), ("vertex", ("RefBox", "Vertex2"))):
        w.scene.clearSelection()
        Gui.Selection.clearSelection()
        pump()
        Gui.Selection.addSelection(doc.Name, obj, sub)
        pump()
        expect(selected_node_ids() == [STATE["refs"][key].id], f"{key}: graph selection {selected_node_ids()}")
        expect(resolved_selection_pairs() == [(obj, sub)], f"{key}: FreeCAD selection disturbed {resolved_selection_pairs()}")
    w.scene.clearSelection()
    Gui.Selection.clearSelection()
    pump()
    Gui.Selection.addSelection(doc.Name, "Container", "NestedCyl.Face1")
    pump()
    expect(selected_node_ids() == [STATE["refs"]["nested"].id], f"nested: graph selection {selected_node_ids()}")


@check("viewport multi-selection is not collapsed by graph sync")
def _multi_select():
    w = ws()
    doc = STATE["ref_doc"]
    Gui.Selection.clearSelection()
    pump()
    Gui.Selection.addSelection(doc.Name, "RefBox", "Edge3")
    Gui.Selection.addSelection(doc.Name, "RefBox", "Face1")
    pump()
    pairs = sorted(resolved_selection_pairs())
    expect(pairs == [("RefBox", "Edge3"), ("RefBox", "Face1")], f"FreeCAD selection {pairs}")


@check("reference evaluation does not create generated copies")
def _reference_eval():
    w = ws()
    doc = STATE["ref_doc"]
    w.evaluate()
    pump()
    generated = [o.Name for o in doc.Objects if "ParamWeaveNodeId" in o.PropertiesList]
    expect(not generated, f"reference nodes generated objects: {generated}")
    for key, node in STATE["refs"].items():
        expect(node_status(node.id) == "ok", f"{key} status {node_status(node.id)!r}")


@check("deleting referenced geometry marks reference nodes broken")
def _broken_reference():
    w = ws()
    doc = STATE["ref_doc"]
    doc.removeObject("RefBox")
    doc.recompute()
    pump()
    w.evaluate()
    pump()
    for key in ("object", "face", "edge", "vertex"):
        nid = STATE["refs"][key].id
        expect(node_status(nid) == "error", f"{key} status {node_status(nid)!r}")
        item = w.scene.node_items[nid]
        expect("no longer exists" in item.toolTip(), f"{key} tooltip {item.toolTip()!r}")
    expect(node_status(STATE["refs"]["nested"].id) == "ok", "unrelated nested reference affected")


@check("malformed embedded graph is surfaced and never overwritten")
def _malformed_graph():
    w = ws()
    doc = App.newDocument("PWMalformed")
    pump()
    store = doc.addObject("App::FeaturePython", "ParamWeaveGraph")
    store.addProperty("App::PropertyString", "GraphJSON", "ParamWeave", "")
    bad = '{"schema_version": 1, "nodes": [{"id": "x", "type_id": "primitive.box", "position": "__import__(\'os\')"}], "edges": []}'
    store.GraphJSON = bad
    w.bind_active_document(force=True)
    pump()
    expect(w.load_error, "no load error reported")
    expect("could not be loaded" in w.status_label.text(), f"status label {w.status_label.text()!r}")
    try:
        w.add_node("primitive.box")
    except Exception:
        pass
    pump()
    expect(store.GraphJSON == bad, "malformed graph data was overwritten")
    App.closeDocument(doc.Name)
    pump()


@check("unknown node types are preserved and drawn as placeholders")
def _unknown_type():
    import uuid

    w = ws()
    doc = App.newDocument("PWUnknown")
    pump()
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    graph = {
        "schema_version": 1,
        "nodes": [
            {"id": a, "type_id": "future.widget", "label": "Future", "position": [0, 0], "params": {"k": 1}},
            {"id": b, "type_id": "boolean.cut", "label": "Cut", "position": [300, 0], "params": {}},
        ],
        "edges": [{"id": str(uuid.uuid4()), "src_node": a, "src_port": "result", "dst_node": b, "dst_port": "base"}],
    }
    store = doc.addObject("App::FeaturePython", "ParamWeaveGraph")
    store.addProperty("App::PropertyString", "GraphJSON", "ParamWeave", "")
    store.GraphJSON = json.dumps(graph)
    w.bind_active_document(force=True)
    pump()
    expect(not w.load_error, f"load error: {w.load_error}")
    expect(node_status(a) == "unknown", f"placeholder status {node_status(a)!r}")
    expect(len(w.scene.edge_items) == 1, "edge to placeholder not drawn")
    w.evaluate()
    pump()
    expect(node_status(b) == "blocked" or node_status(b) == "error", f"cut status {node_status(b)!r}")
    w.persist()
    saved = json.loads(store.GraphJSON)
    expect([n for n in saved["nodes"] if n["id"] == a][0]["params"] == {"k": 1}, "placeholder params lost")
    App.closeDocument(doc.Name)
    pump()


@check("Number wired into a sketch dimension makes it read-only; Sketch node makes a Sketcher sketch")
def _sketch_driven():
    w = ws()
    doc = App.newDocument("PWSketchSmoke")
    pump()
    w.bind_active_document(force=True)
    pump()
    num = w.add_node("value.number", position=(0.0, 0.0))
    rect = w.add_node("sketch.rectangle", position=(260.0, 0.0))
    sk = w.add_node("sketch.sketch", position=(520.0, 0.0))
    pump()
    w.properties.set_node(rect.id)
    pump()

    def width_edit():
        return [e for e in w.properties.findChildren(QtWidgets.QLineEdit) if e.property("paramweave_key") == "width" and e.isVisible()]

    expect(width_edit() and width_edit()[0].isEnabled(), "width editor should start editable")
    click_port(num, "out", "value")
    click_port(rect, "in", "width")
    click_port(rect, "out", "geometry")
    click_port(sk, "in", "geometry")
    expect(len(w.model.edges) == 2, f"expected 2 edges, found {len(w.model.edges)}")
    pump()
    expect(width_edit() and not width_edit()[0].isEnabled(), "wired width editor should be read-only")
    w.evaluate()
    pump()
    obj = [o for o in doc.Objects if o.TypeId == "Sketcher::SketchObject"]
    expect(len(obj) == 1, f"expected one sketch, found {len(obj)}")
    expect(abs(obj[0].Shape.BoundBox.XLength - 10.0) < 1e-9, f"width not driven: {obj[0].Shape.BoundBox.XLength}")
    expect(node_status(sk.id) == "ok", f"sketch status {node_status(sk.id)!r}")
    App.closeDocument(doc.Name)
    pump()


@check("finger-jointed box example inserts via its command and evaluates cleanly")
def _finger_box_example():
    w = ws()
    doc = App.newDocument("PWFingerBoxSmoke")
    pump()
    w.bind_active_document(force=True)
    pump()
    Gui.runCommand("ParamWeave_ExampleFingerBox")
    pump(30)
    expect(len(w.model.nodes) == 33, f"expected 33 nodes, found {len(w.model.nodes)}")
    bad = {w.model.nodes[n].label: node_status(n) for n in w.model.nodes if node_status(n) != "ok"}
    expect(not bad, f"non-ok nodes: {bad}")
    sketches = [o for o in doc.Objects if o.TypeId == "Sketcher::SketchObject"]
    expect(len(sketches) == 6, f"expected 6 panel sketches, found {len(sketches)}")
    shot = os.environ.get("PARAMWEAVE_SCREENSHOT")
    if shot:
        Gui.activeDocument().activeView().viewIsometric()
        Gui.SendMsgToActiveView("ViewFit")
        pump(10)
        main_window().grab().save(shot)
        # grab() cannot capture the OpenGL viewport; render it separately.
        Gui.activeDocument().activeView().saveImage(shot.replace(".png", "_3d.png"), 1600, 1100, "Current")
    App.closeDocument(doc.Name)
    pump()


@check("kerf fit test example inserts via its command; corner style is a dropdown")
def _kerf_test_example():
    w = ws()
    doc = App.newDocument("PWKerfTestSmoke")
    pump()
    w.bind_active_document(force=True)
    pump()
    Gui.runCommand("ParamWeave_ExampleKerfTest")
    pump(30)
    expect(len(w.model.nodes) == 18, f"expected 18 nodes, found {len(w.model.nodes)}")
    bad = {w.model.nodes[n].label: node_status(n) for n in w.model.nodes if node_status(n) != "ok"}
    expect(not bad, f"non-ok nodes: {bad}")
    sketches = [o for o in doc.Objects if o.TypeId == "Sketcher::SketchObject"]
    expect(len(sketches) == 3, f"expected 3 coupon sketches, found {len(sketches)}")
    (coupons,) = [n for n in w.model.nodes.values() if n.label == "Coupons 45°"]
    w.scene.set_nodes_selected([coupons.id], True, exclusive=True)
    w.properties.set_node(coupons.id)
    pump()
    combos = [c for c in w.properties._body.findChildren(QtWidgets.QComboBox) if c.property("paramweave_key") == "corner_style"]
    expect(len(combos) == 1, "corner_style is not shown as a dropdown")
    items = [combos[0].itemText(i) for i in range(combos[0].count())]
    expect(items == ["none", "dogbone", "tbone_depth", "tbone_side"], f"dropdown offers {items}")
    combos[0].setCurrentText("dogbone")
    pump(5)
    expect(w.model.nodes[coupons.id].params["corner_style"] == "dogbone", "dropdown pick did not reach the graph")
    doc.undo()
    pump(5)
    expect(w.model.nodes[coupons.id].params["corner_style"] == "none", "dropdown pick is not undoable")
    App.closeDocument(doc.Name)
    pump()


@check("Ctrl+D duplicates selected nodes even after a property editor had focus")
def _duplicate_shortcut():
    w = ws()
    doc = App.newDocument("PWDupSmoke")
    pump()
    w.bind_active_document(force=True)
    pump()
    num = w.add_node("value.number", position=(0.0, 0.0))
    box = w.add_node("primitive.box", position=(260.0, 0.0))
    w.connect(num.id, "value", box.id, "length")
    w.scene.select_node(box.id)
    pump()
    edits = [e for e in w.properties.findChildren(QtWidgets.QLineEdit) if e.isVisible() and e.isEnabled()]
    edits[0].setFocus()  # the user was just typing in the property panel
    pump()
    ctrl = getattr(getattr(QtCore.Qt, "KeyboardModifier", QtCore.Qt), "ControlModifier")
    keys = getattr(QtCore.Qt, "Key", QtCore.Qt)
    for _round in range(3):  # repeated presses must keep working
        before = len(w.model.nodes)
        w.view.setFocus()
        pump()
        QtTest.QTest.keyClick(w.view, keys.Key_D, ctrl)
        pump()
        expect(len(w.model.nodes) == before + 1, f"Ctrl+D made {len(w.model.nodes) - before} nodes")
    copies = [n for n in w.model.nodes.values() if n.type_id == "primitive.box"]
    expect(all(any(e.src_node == num.id for e in w.model.incoming(c.id)) for c in copies), "copy lost its input wire")
    App.closeDocument(doc.Name)
    pump()


def _drag_scene(start, end, steps=8):
    """Press at ``start``, move to ``end`` and release, all in scene coordinates."""
    from PySide import QtGui

    view = ws().view
    view.fitInView(QtCore.QRectF(start, end).normalized().adjusted(-200, -200, 200, 200), getattr(QtCore.Qt, "AspectRatioMode", QtCore.Qt).KeepAspectRatio)
    pump(3)
    types = getattr(QtCore.QEvent, "Type", QtCore.QEvent)

    def send(kind, pt, button, buttons):
        local = QtCore.QPointF(view.mapFromScene(pt))
        ev = QtGui.QMouseEvent(kind, local, QtCore.QPointF(view.viewport().mapToGlobal(local.toPoint())), button, buttons, no_modifier())
        QtWidgets.QApplication.sendEvent(view.viewport(), ev)
        pump(1)

    send(types.MouseButtonPress, start, left_button(), left_button())
    for k in range(1, steps + 1):
        send(types.MouseMove, start + (end - start) * (k / steps), no_button(), left_button())
    send(types.MouseButtonRelease, end, left_button(), no_button())
    pump(3)


@check("frames: Ctrl+G wraps nodes, title drag carries them, resize, edit, delete keeps nodes, undo, duplicate")
def _frames():
    from paramweave.gui.items import FRAME_HEADER_H

    w = ws()
    doc = App.newDocument("PWFrameSmoke")
    pump()
    w.bind_active_document(force=True)
    pump()
    a = w.add_node("value.number", position=(0.0, 0.0))
    b = w.add_node("primitive.box", position=(260.0, 0.0))
    outside = w.add_node("value.number", position=(900.0, 0.0))
    w.connect(a.id, "value", b.id, "length")
    w.scene.clearSelection()
    w.scene.node_items[a.id].setSelected(True)
    w.scene.node_items[b.id].setSelected(True)
    ctrl = getattr(getattr(QtCore.Qt, "KeyboardModifier", QtCore.Qt), "ControlModifier")
    keys = getattr(QtCore.Qt, "Key", QtCore.Qt)
    w.view.setFocus()
    QtTest.QTest.keyClick(w.view, keys.Key_G, ctrl)
    pump()
    expect(len(w.model.frames) == 1, f"Ctrl+G made {len(w.model.frames)} frames")
    frame = next(iter(w.model.frames.values()))
    nodes, _ = w.model.frame_contents(frame.id)
    expect(sorted(nodes) == sorted([a.id, b.id]), "frame does not contain exactly the selected nodes")
    expect(w.properties.frame_id == frame.id, "property panel is not editing the new frame")

    # Drag the title bar: contents follow, the outside node does not.
    w.scene.clearSelection()
    item = w.scene.frame_items[frame.id]
    grab = item.scenePos() + QtCore.QPointF(60.0, FRAME_HEADER_H / 2)
    _drag_scene(grab, grab + QtCore.QPointF(0.0, 300.0))
    ay = w.model.nodes[a.id].position[1]
    expect(abs(ay - 300.0) < 10, f"node inside frame moved to y={ay}")
    expect(w.model.nodes[outside.id].position == [900.0, 0.0], "node outside the frame moved")
    edge_item = next(iter(w.scene.edge_items.values()))
    expect(abs(edge_item.path().pointAtPercent(0).y() - w.scene.node_items[a.id].port("out", "value").scenePos().y()) < 1, "wire did not follow")

    # Resize from the corner handle.
    r = w.model.frames[frame.id].rect
    corner = QtCore.QPointF(r[0] + r[2] - 5, r[1] + r[3] - 5)
    _drag_scene(corner, corner + QtCore.QPointF(150.0, 60.0))
    r2 = w.model.frames[frame.id].rect
    expect(abs(r2[2] - r[2] - 150) < 10 and abs(r2[3] - r[3] - 60) < 10, f"resize gave {r2} from {r}")

    # Edit label and color through the property panel.
    w.scene.select_node(a.id)
    w.scene.clearSelection()
    w.scene.frame_items[frame.id].setSelected(True)
    pump()
    label = [e for e in w.properties.findChildren(QtWidgets.QLineEdit) if e.property("paramweave_key") == "__label__" and e.isVisible()][0]
    label.setFocus()
    label.selectAll()
    QtTest.QTest.keyClicks(label, "Inputs")
    QtTest.QTest.keyClick(label, keys.Key_Return)
    pump()
    combo = [c for c in w.properties.findChildren(QtWidgets.QComboBox) if c.property("paramweave_key") == "color" and c.isVisible()][0]
    combo.setCurrentText("green")
    pump()
    expect((w.model.frames[frame.id].label, w.model.frames[frame.id].color) == ("Inputs", "green"), f"frame edits not applied: {w.model.frames[frame.id].label!r}, {w.model.frames[frame.id].color!r}, panel frame={w.properties.frame_id}, node={w.properties.node_id}, status={w.status_label.text()!r}")

    # Duplicate the frame: contents are copied too.
    w.view.setFocus()
    QtTest.QTest.keyClick(w.view, keys.Key_D, ctrl)
    pump()
    expect(len(w.model.frames) == 2 and len(w.model.nodes) == 5, f"duplicate gave {len(w.model.frames)} frames, {len(w.model.nodes)} nodes")

    # Delete the original frame only; its nodes stay. Undo restores it.
    w.scene.clearSelection()
    w.scene.frame_items[frame.id].setSelected(True)
    w.view.setFocus()
    QtTest.QTest.keyClick(w.view, keys.Key_Delete)
    pump()
    expect(frame.id not in w.model.frames and a.id in w.model.nodes, "delete removed nodes or kept the frame")
    doc.undo()
    pump(20)
    expect(frame.id in w.model.frames, "undo did not restore the frame")
    expect(w.model.frames[frame.id].label == "Inputs", "restored frame lost its label")
    App.closeDocument(doc.Name)
    pump()


@check("the tutorial's finished FCStd opens with its graph in the pane")
def _tutorial_file():
    import shutil

    src = os.path.join(os.environ["PARAMWEAVE_ROOT"], "docs", "tutorial", "finger-jointed-box.FCStd")
    path = os.path.join(WORK_DIR, "tutorial-copy.FCStd")
    shutil.copy(src, path)
    doc = App.openDocument(path)
    pump(20)
    w = ws()
    w.bind_active_document(force=True)
    pump(10)
    expect(not w.load_error, f"load error: {w.load_error}")
    expect((len(w.model.nodes), len(w.model.edges)) == (33, 79), f"graph has {len(w.model.nodes)} nodes")
    expect(len(w.scene.node_items) == 33, "graph pane did not draw the nodes")
    w.evaluate()
    pump(10)
    bad = [n.label for n in w.model.nodes.values() if node_status(n.id) != "ok"]
    expect(not bad, f"nodes not ok: {bad}")
    App.closeDocument(doc.Name)
    pump()


@check("Export Cut Files writes DXF and SVG for all panels or just a selected frame")
def _export_cut_files():
    import xml.etree.ElementTree as ET

    expect("ParamWeave_ExportCutFiles" in Gui.listCommands(), "export command is not registered")
    w = ws()
    doc = App.newDocument("PWCutSmoke")
    pump()
    w.bind_active_document(force=True)
    pump()
    Gui.runCommand("ParamWeave_ExampleFingerBox")
    pump(30)
    dxf = os.path.join(WORK_DIR, "panels.dxf")
    svg = os.path.join(WORK_DIR, "panels.svg")
    expect(w.export_cut_files(dxf, 600.0, 5.0) == 6, "DXF export did not include 6 panels")
    expect(open(dxf).read().rstrip().endswith("EOF"), "DXF is truncated")
    expect(w.export_cut_files(svg, 600.0, 5.0) == 6, "SVG export did not include 6 panels")
    ET.parse(svg)
    # Only the panels inside a selected frame.
    w.scene.clearSelection()
    (front,) = [f for f in w.model.frames.values() if f.label == "Front panel"]
    w.scene.frame_items[front.id].setSelected(True)
    pump()
    expect(w.export_cut_files(svg, 600.0, 5.0, only_selected=True) == 1, "selected-frame export should be 1 panel")
    titles = [t.text for t in ET.parse(svg).getroot().iter("{http://www.w3.org/2000/svg}title")]
    expect(titles == ["Front sketch"], f"exported {titles}")

    # The options dialog builds, shows the saved defaults, and cancels cleanly.
    seen = {}

    def close_dialog():
        dialog = QtWidgets.QApplication.activeModalWidget()
        if dialog is None:
            QtCore.QTimer.singleShot(50, close_dialog)
            return
        spins = dialog.findChildren(QtWidgets.QDoubleSpinBox)
        seen["values"] = sorted(s.value() for s in spins)
        seen["title"] = dialog.windowTitle()
        dialog.reject()

    QtCore.QTimer.singleShot(50, close_dialog)
    result = w.export_cut_files_dialog()
    expect(result is None, "canceled dialog should export nothing")
    expect(seen.get("title") == "Export Cut Files", f"dialog not shown: {seen}")
    expect(seen.get("values") == [5.0, 600.0], f"dialog defaults {seen.get('values')}")
    App.closeDocument(doc.Name)
    pump()


start()
