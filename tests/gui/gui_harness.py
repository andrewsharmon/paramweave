"""Shared helpers for ParamWeave scripts that run inside a FreeCAD GUI session.

Imported by ``gui_smoke.py`` and ``tutorial_finger_box.py``; see
``tools/run_freecad_tests.py``. Results are JSON lines in ``$PARAMWEAVE_TEST_OUT``.
"""

import json
import os
import tempfile
import threading
import time
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

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
    record("__timeout__", False, f"GUI script exceeded {TIMEOUT_S}s")
    _out.close()
    os._exit(3)


def start():
    """Run every registered check once the event loop starts, then quit FreeCAD."""
    timer = threading.Timer(TIMEOUT_S, _watchdog)
    timer.daemon = True
    timer.start()
    QtCore.QTimer.singleShot(0, _run_all)
