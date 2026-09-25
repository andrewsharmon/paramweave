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

OUT_PATH = os.environ.get("PARAMWEAVE_TEST_OUT") or os.path.join(tempfile.gettempdir(), "paramweave_gui_smoke.jsonl")
WORK_DIR = os.environ.get("PARAMWEAVE_TEST_WORKDIR") or tempfile.mkdtemp(prefix="paramweave_gui_")
TIMEOUT_S = float(os.environ.get("PARAMWEAVE_TEST_TIMEOUT", "180"))

_out = open(OUT_PATH, "w")
_failures = []


def record(name, ok, detail=""):
    _out.write(json.dumps({"check": name, "ok": bool(ok), "detail": detail}) + "\n")
    _out.flush()
    if not ok:
        _failures.append(name)


def check(name):
    def wrap(fn):
        def run():
            try:
                detail = fn()
                record(name, True, detail or "")
            except Exception:
                record(name, False, traceback.format_exc())
        run.__name__ = fn.__name__
        CHECKS.append(run)
        return fn
    return wrap


CHECKS = []


def pump(rounds=10):
    for _ in range(rounds):
        QtWidgets.QApplication.processEvents()
        time.sleep(0.005)


def expect(cond, message):
    if not cond:
        raise AssertionError(message)


def left_button():
    return getattr(getattr(QtCore.Qt, "MouseButton", QtCore.Qt), "LeftButton")


def no_modifier():
    return getattr(getattr(QtCore.Qt, "KeyboardModifier", QtCore.Qt), "NoModifier")


def main_window():
    return Gui.getMainWindow()


def paramweave_docks():
    from paramweave.constants import DOCK_OBJECT_NAME

    return [d for d in main_window().findChildren(QtWidgets.QDockWidget) if d.objectName() == DOCK_OBJECT_NAME]


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


def ws():
    from paramweave.gui.workspace import workspace

    return workspace()


def node_status(node_id):
    item = ws().scene.node_items.get(node_id)
    return getattr(item, "status", None)


def no_button():
    return getattr(getattr(QtCore.Qt, "MouseButton", QtCore.Qt), "NoButton")


def send_mouse(view, event_type, pos, button, buttons):
    """Deliver a mouse event straight to the graph viewport.

    QTest routes synthetic clicks through the window system, and on macOS the
    first press of a freshly launched (inactive) FreeCAD window is dropped.
    sendEvent still exercises the real QGraphicsView -> scene -> item dispatch.
    """
    from PySide import QtGui

    local = QtCore.QPointF(pos)
    global_pos = QtCore.QPointF(view.viewport().mapToGlobal(pos))
    event = QtGui.QMouseEvent(event_type, local, global_pos, button, buttons, no_modifier())
    QtWidgets.QApplication.sendEvent(view.viewport(), event)
    pump(2)


class _PressProbe(QtCore.QObject):
    def __init__(self):
        super().__init__()
        self.pressed = False

    def eventFilter(self, _obj, event):
        if event.type() == getattr(QtCore.QEvent, "Type", QtCore.QEvent).MouseButtonPress:
            self.pressed = True
        return False


REROUTED_PRESSES = []


def click_viewport(view, pos, attempts=5):
    """Click the graph viewport, retrying presses FreeCAD reroutes elsewhere.

    Observed on FreeCAD 1.1.3/macOS: shortly after a 3D view is created, a
    synthetic press sent to the graph viewport can be re-dispatched by
    FreeCAD's application-level event filters to the 3D viewer, so the graph
    never sees it. A real pointer is unaffected. The probe below only checks
    that the press reached the viewport; if ParamWeave then ignores it, the
    test still fails.
    """
    types = getattr(QtCore.QEvent, "Type", QtCore.QEvent)
    probe = _PressProbe()
    view.viewport().installEventFilter(probe)
    try:
        for attempt in range(attempts):
            probe.pressed = False
            send_mouse(view, types.MouseButtonPress, pos, left_button(), left_button())
            send_mouse(view, types.MouseButtonRelease, pos, left_button(), no_button())
            if probe.pressed:
                return
            REROUTED_PRESSES.append((pos.x(), pos.y()))
            pump(20)
        raise AssertionError(f"press at {pos} never reached the graph viewport")
    finally:
        view.viewport().removeEventFilter(probe)


def click_scene_point(scene_pos):
    view = ws().view
    view.ensureVisible(QtCore.QRectF(scene_pos.x() - 5, scene_pos.y() - 5, 10, 10))
    pump(3)
    click_viewport(view, view.mapFromScene(scene_pos))


def click_port(node, direction, port):
    item = ws().scene.node_items[node.id].port(direction, port)
    expect(item is not None, f"missing port {direction}:{port} on {node.label}")
    click_scene_point(item.scenePos())


def selection_pairs():
    pairs = []
    for sel in Gui.Selection.getSelectionEx("", 0):
        names = list(sel.SubElementNames) or [""]
        for sub in names:
            pairs.append((sel.ObjectName, sub))
    return pairs


def resolved_selection_pairs():
    pairs = []
    for sel in Gui.Selection.getSelectionEx():
        names = list(sel.SubElementNames) or [""]
        for sub in names:
            pairs.append((sel.Object.Name, sub))
    return pairs


def selected_node_ids():
    from paramweave.gui.items import NodeItem

    return sorted(i.node_id for i in ws().scene.selectedItems() if isinstance(i, NodeItem))


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
    undo_before = doc.UndoCount
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
    expect(doc.UndoCount == undo_before + 1, f"drag created {doc.UndoCount - undo_before} undo steps")
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


def _finish():
    for doc_name in list(App.listDocuments()):
        try:
            App.closeDocument(doc_name)
        except Exception:
            pass
    record("__summary__", not _failures, f"failures={_failures}")
    _out.close()
    os._exit(1 if _failures else 0)


def _run_all():
    for fn in CHECKS:
        fn()
        pump()
    _finish()


def _watchdog():
    record("__timeout__", False, f"GUI smoke test exceeded {TIMEOUT_S}s")
    _out.close()
    os._exit(3)


_timer = threading.Timer(TIMEOUT_S, _watchdog)
_timer.daemon = True
_timer.start()
QtCore.QTimer.singleShot(0, _run_all)
