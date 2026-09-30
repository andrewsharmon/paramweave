"""Build the finger-jointed box using only GUI interactions, capturing screenshots.

This both verifies that the box can be made entirely from the ParamWeave GUI
and produces the images for the tutorial in ``docs/tutorial/``. Every graph
change goes through what a user does: canvas context menu entries (the same
signal a menu click emits), clicking ports, typing into the property panel,
clicking nodes and wires, Ctrl+D, Delete, dragging nodes and the Evaluate
button.

Run: python3 tools/run_freecad_tests.py --gui-script tests/gui/tutorial_finger_box.py
Screenshots go to $PARAMWEAVE_TUTORIAL_OUT (default docs/tutorial/images).
"""

import os
import sys

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

try:
    from PySide6 import QtTest
except ImportError:  # pragma: no cover - Qt5 builds
    from PySide2 import QtTest

ROOT = os.environ["PARAMWEAVE_ROOT"]
sys.path.insert(0, os.path.join(ROOT, "tests", "gui"))
from gui_harness import *  # noqa: E402,F401,F403

OUT = os.environ.get("PARAMWEAVE_TUTORIAL_OUT") or os.path.join(ROOT, "docs", "tutorial", "images")
os.makedirs(OUT, exist_ok=True)

Qt = QtCore.Qt
KEY = getattr(Qt, "Key", Qt)
MOD = getattr(Qt, "KeyboardModifier", Qt)
TYPES = getattr(QtCore.QEvent, "Type", QtCore.QEvent)

COL, ROW = 300.0, 260.0
N = {}  # tutorial name -> GraphNode
STEPS = []  # (number, title, images) for the tutorial log


# -- GUI actions ------------------------------------------------------------


def add(name, type_id, col, row, label):
    """Add a node the way the canvas context menu does, then rename it."""
    w = ws()
    before = set(w.model.nodes)
    entries = {t for _c, _t, t in w.view.node_menu_entries}
    expect(type_id in entries, f"{type_id} is not offered in the canvas context menu")
    w.view.addNodeRequested.emit(type_id, QtCore.QPointF(col * COL, row))
    pump(3)
    (new_id,) = set(w.model.nodes) - before
    N[name] = w.model.nodes[new_id]
    set_text(name, "__label__", label)
    return N[name]


def click_node(name, modifier=None):
    """Click a node header, retrying clicks FreeCAD reroutes (see gui_harness.click_viewport)."""
    for _attempt in range(5):
        _click_node_once(name, modifier)
        if N[name].id in ws().scene.selected_node_ids():
            return
        pump(20)
    raise AssertionError(f"clicking {name} never selected it")


def _click_node_once(name, modifier=None):
    item = ws().scene.node_items[N[name].id]
    pos = item.scenePos() + QtCore.QPointF(60.0, 12.0)
    view = ws().view
    view.ensureVisible(QtCore.QRectF(pos.x() - 5, pos.y() - 5, 10, 10))
    pump(2)
    local = view.mapFromScene(pos)
    mods = modifier if modifier is not None else no_modifier()
    for kind, buttons in ((TYPES.MouseButtonPress, left_button()), (TYPES.MouseButtonRelease, no_button())):
        ev = QtGui.QMouseEvent(kind, QtCore.QPointF(local), QtCore.QPointF(view.viewport().mapToGlobal(local)), left_button(), buttons, mods)
        QtWidgets.QApplication.sendEvent(view.viewport(), ev)
        pump(2)


def select(name):
    click_node(name)
    expect(ws().properties.node_id == N[name].id, f"clicking {name} did not select it")


def set_text(name, key, text):
    """Select the node, type into its property editor and press Return."""
    if ws().properties.node_id != N[name].id:
        select(name)
    edits = [e for e in ws().properties.findChildren(QtWidgets.QLineEdit) if e.property("paramweave_key") == key and e.isVisible()]
    expect(edits, f"{name}: no editable '{key}' field")
    edit = edits[0]
    expect(edit.isEnabled(), f"{name}: '{key}' is driven by a wire")
    edit.setFocus()
    edit.selectAll()
    QtTest.QTest.keyClicks(edit, text)
    QtTest.QTest.keyClick(edit, KEY.Key_Return)
    pump(3)
    if key == "__label__":
        expect(N[name].label == text, f"label not set: {N[name].label!r}")
    else:
        value = ws().model.nodes[N[name].id].params[key]
        expect(str(value) == text or (isinstance(value, float) and float(text) == value), f"{name}.{key} = {value!r}, typed {text!r}")


def wire(src, src_port, dst, dst_port):
    click_port(N[src], "out", src_port)
    click_port(N[dst], "in", dst_port)
    pump(2)
    expect(
        any(
            e.src_node == N[src].id and e.src_port == src_port and e.dst_node == N[dst].id and e.dst_port == dst_port
            for e in ws().model.edges.values()
        ),
        f"wire {src}.{src_port} -> {dst}.{dst_port} was not made",
    )


def delete_wire(dst, dst_port):
    from paramweave.gui.items import ConnectionItem

    w = ws()
    (edge,) = [e for e in w.model.edges.values() if e.dst_node == N[dst].id and e.dst_port == dst_port]
    item = w.scene.edge_items[edge.id]
    for pct in (0.9, 0.8, 0.7, 0.95, 0.6, 0.5):
        pos = item.path().pointAtPercent(pct)
        w.scene.clearSelection()
        click_scene_point(pos)
        chosen = [i for i in w.scene.selectedItems() if isinstance(i, ConnectionItem)]
        if [i.edge_id for i in chosen] == [edge.id]:
            break
    else:
        raise AssertionError(f"could not click the wire into {dst}.{dst_port}")
    press(KEY.Key_Delete)
    expect(edge.id not in w.model.edges, "wire was not deleted")


def press(key, modifiers=None):
    view = ws().view
    view.setFocus()
    pump(3)
    mods = modifiers if modifiers is not None else no_modifier()
    # Real keystrokes go through the window system: QTest.keyClick sends the
    # ShortcutOverride + KeyPress sequence a user's key press produces.
    QtTest.QTest.keyClick(view, key, mods)
    pump(5)


def duplicate(names, new_names, labels):
    w = ws()
    click_node(names[0])
    for name in names[1:]:
        click_node(name, MOD.ControlModifier)
    expect(sorted(w.scene.selected_node_ids()) == sorted(N[n].id for n in names), "multi-select failed")
    before = set(w.model.nodes)
    press(KEY.Key_D, MOD.ControlModifier)
    new = set(w.model.nodes) - before
    expect(
        len(new) == len(names),
        f"Ctrl+D made {len(new)} nodes; status={w.status_label.text()!r}; "
        f"focus={QtWidgets.QApplication.focusWidget()}; selected={[w.model.nodes[i].label for i in w.scene.selected_node_ids()]}",
    )
    by_label = {w.model.nodes[i].label: w.model.nodes[i] for i in new}
    for old, new_name, label in zip(names, new_names, labels):
        (copy,) = [n for lbl, n in by_label.items() if lbl.startswith(N[old].label + " ")]
        N[new_name] = copy
        set_text(new_name, "__label__", label)


def drag(name, col, row):
    """Drag a node by its header to its column/row."""
    w = ws()
    item = w.scene.node_items[N[name].id]
    grab = item.scenePos() + QtCore.QPointF(60.0, 12.0)
    target = QtCore.QPointF(col * COL + 60.0, row + 12.0)
    view = w.view
    view.fitInView(QtCore.QRectF(grab, target).normalized().adjusted(-150, -150, 150, 150), Qt.KeepAspectRatio)
    pump(3)

    def send(kind, scene_pt, buttons):
        local = view.mapFromScene(scene_pt)
        ev = QtGui.QMouseEvent(kind, QtCore.QPointF(local), QtCore.QPointF(view.viewport().mapToGlobal(local)), left_button() if kind != TYPES.MouseMove else no_button(), buttons, no_modifier())
        QtWidgets.QApplication.sendEvent(view.viewport(), ev)
        pump(1)

    send(TYPES.MouseButtonPress, grab, left_button())
    for k in range(1, 11):
        send(TYPES.MouseMove, grab + (target - grab) * (k / 10.0), left_button())
    send(TYPES.MouseButtonRelease, target, no_button())
    pump(3)
    pos = ws().model.nodes[N[name].id].position
    # Mouse positions are whole view pixels, so at small zoom a drag can land a
    # few scene units off; that is just as good for a tutorial layout.
    expect(abs(pos[0] - col * COL) < 8 and abs(pos[1] - row) < 8, f"{name} dragged to {pos}")


def evaluate():
    buttons = [b for b in paramweave_docks()[0].findChildren(QtWidgets.QPushButton) if b.text() == "Evaluate"]
    expect(buttons, "Evaluate button not found")
    buttons[0].click()
    pump(20)
    bad = {n.label: node_status(n.id) for n in ws().model.nodes.values() if node_status(n.id) != "ok"}
    expect(not bad, f"nodes not ok after Evaluate: {bad}")


# -- screenshots -----------------------------------------------------------


def focus(names, margin=60.0):
    view = ws().view
    rect = QtCore.QRectF()
    for name in names:
        rect = rect.united(ws().scene.node_items[N[name].id].sceneBoundingRect())
    view.fitInView(rect.adjusted(-margin, -margin, margin, margin), Qt.KeepAspectRatio)
    pump(5)


def render_graph(names, margin=40.0, width_px=1600):
    """Render just the part of the scene holding ``names`` (crisp, any zoom)."""
    scene = ws().scene
    rect = QtCore.QRectF()
    for name in names:
        rect = rect.united(scene.node_items[N[name].id].sceneBoundingRect())
    rect = rect.adjusted(-margin, -margin, margin, margin)
    # Widen tall selections (e.g. one column of nodes) to a landscape frame.
    min_width = rect.height() * 1.25
    if rect.width() < min_width:
        rect.adjust(-(min_width - rect.width()) / 2, 0, (min_width - rect.width()) / 2, 0)
    scale = min(2.5, width_px / rect.width())
    image = QtGui.QImage(int(rect.width() * scale), int(rect.height() * scale), QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtGui.QColor("#202328"))
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
    scene.render(painter, QtCore.QRectF(0, 0, image.width(), image.height()), rect)
    painter.end()
    return image


def panel_image():
    """The property panel's whole form (every field, no scrolling) at 1:1 pixels."""
    image = ws().properties._body.grab().toImage()
    image.setDevicePixelRatio(1.0)
    return image


def stack(top, bottom, gap=6):
    """Graph render above a property-panel grab (both already the same width)."""
    width = max(top.width(), bottom.width())
    image = QtGui.QImage(width, top.height() + gap + bottom.height(), QtGui.QImage.Format.Format_ARGB32)
    image.setDevicePixelRatio(1.0)
    image.fill(QtGui.QColor("#101216"))
    painter = QtGui.QPainter(image)
    painter.drawImage(QtCore.QPoint((width - top.width()) // 2, 0), top)
    painter.drawImage(QtCore.QPoint(0, top.height() + gap), bottom)
    painter.end()
    return image


def shot(tag, names=None, view3d=False, window=False, panel_key=None, panel=True):
    """Save screenshots for a step; returns the file names."""
    files = []
    if panel_key:
        # Scroll the property panel so the fields this step edits are in view.
        props = ws().properties
        edits = [e for e in props.findChildren(QtWidgets.QLineEdit) if e.property("paramweave_key") == panel_key]
        if edits:
            props.verticalScrollBar().setValue(props.verticalScrollBar().maximum())
            props.ensureWidgetVisible(edits[0], 0, 40)
    pump(5)
    if window:
        path = os.path.join(OUT, f"{tag}_window.png")
        grab_window(path)
        files.append(os.path.basename(path))
    elif names:
        form = panel_image() if panel else None
        image = render_graph(names, width_px=form.width() if form is not None else 1600)
        if form is not None:
            image = stack(image, form)
        path = os.path.join(OUT, f"{tag}_graph.png")
        image.save(path)
        files.append(os.path.basename(path))
    if view3d:
        v = Gui.activeDocument().activeView()
        v.viewIsometric()
        Gui.SendMsgToActiveView("ViewFit")
        pump(5)
        path = os.path.join(OUT, f"{tag}_3d.png")
        v.saveImage(path, 1500, 900, "Current")
        files.append(os.path.basename(path))
    return files


def grab_window(path):
    """Whole main window, with the OpenGL 3D view painted in (grab() leaves it blank)."""
    mw = main_window()
    pix = mw.grab()
    mdi = mw.findChild(QtWidgets.QMdiArea)
    sub = mdi.activeSubWindow() if mdi else None
    if sub is not None and sub.widget() is not None:
        target = sub.widget()
        top_left = target.mapTo(mw, QtCore.QPoint(0, 0))
        dpr = pix.devicePixelRatio()
        tmp = os.path.join(OUT, "_viewport.png")
        Gui.activeDocument().activeView().saveImage(tmp, int(target.width() * dpr), int(target.height() * dpr), "Current")
        painter = QtGui.QPainter(pix)
        painter.drawImage(QtCore.QRect(top_left, target.size()), QtGui.QImage(tmp))
        painter.end()
        os.remove(tmp)
    pix.save(path)


def step(number, title):
    def wrap(fn):
        def run():
            images = fn() or []
            STEPS.append((number, title, images))
            return ", ".join(images)

        run.__name__ = fn.__name__
        return check(f"step {number}: {title}")(run)

    return wrap


# -- the tutorial ------------------------------------------------------------

CONSTANTS = [
    ("L", "Length L", "160"),
    ("W", "Width W", "100"),
    ("H", "Height H", "70"),
    ("t", "Thickness t", "3"),
    ("nL_raw", "Fingers along L", "7"),
    ("nW_raw", "Fingers along W", "5"),
    ("nH_raw", "Fingers along H", "3"),
]
ODD = "max(1, 2 * floor(a / 2) + 1)"
EXPRESSIONS = [
    ("nL", "Odd fingers L", ODD, [("nL_raw", "a")]),
    ("nW", "Odd fingers W", ODD, [("nW_raw", "a")]),
    ("nH", "Odd fingers H", ODD, [("nH_raw", "a")]),
    ("front_off", "Front plane (y = t)", "-a", [("t", "a")]),
    ("back_off", "Back plane (y = W)", "-a", [("W", "a")]),
    ("right_off", "Right plane (x = L - t)", "a - b", [("L", "a"), ("t", "b")]),
    ("lid_off", "Lid plane (z = H - t)", "a - b", [("H", "a"), ("t", "b")]),
]


@step(1, "Open the ParamWeave workbench and the graph pane")
def _s1():
    mw = main_window()
    mw.showNormal()
    mw.resize(1700, 1000)
    Gui.activateWorkbench("ParamWeaveWorkbench")
    pump(10)
    App.newDocument("FingerBox")
    pump(10)
    ws().bind_active_document(force=True)
    dock = paramweave_docks()[0]
    dock.show()
    mw.resizeDocks([dock], [900], Qt.Horizontal)
    pump(10)
    return shot("01_workbench", window=True)


@step(2, "Add the constants")
def _s2():
    for i, (name, label, value) in enumerate(CONSTANTS):
        add(name, "value.number", 0, i * 90.0, label)
        set_text(name, "value", value)
    select("t")
    return shot("02_constants", [n for n, _l, _v in CONSTANTS])


@step(3, "Add the expressions and wire the constants into them")
def _s3():
    for i, (name, label, text, inputs) in enumerate(EXPRESSIONS):
        add(name, "value.expression", 1, i * 150.0, label)
        set_text(name, "expression", text)
        for src, port in inputs:
            wire(src, "value", name, port)
    select("right_off")
    return shot("03_expressions", [n for n, *_ in CONSTANTS] + [n for n, *_ in EXPRESSIONS])


@step(4, "Add the bottom panel profile")
def _s4():
    add("bottom_profile", "sketch.finger_panel", 2, 0, "Bottom profile")
    for side in ("bottom", "right", "top", "left"):
        set_text("bottom_profile", f"mode_{side}", "in")
    for src, port in (("L", "width"), ("W", "height"), ("t", "thickness"), ("nL", "fingers_bottom"), ("nW", "fingers_right"), ("nL", "fingers_top"), ("nW", "fingers_left")):
        wire(src, "value", "bottom_profile", port)
    select("bottom_profile")
    return shot("04_bottom_profile", ["L", "W", "t", "nL", "nW", "bottom_profile"], panel_key="mode_bottom")


@step(5, "Turn the profile into a sketch and extrude it")
def _s5():
    add("bottom_sketch", "sketch.sketch", 3, 0, "Bottom sketch")
    wire("bottom_profile", "geometry", "bottom_sketch", "geometry")
    add("bottom", "sketch.extrude", 4, 0, "Bottom panel")
    wire("bottom_sketch", "shape", "bottom", "shape")
    wire("t", "value", "bottom", "length")
    evaluate()
    select("bottom")
    return shot("05_bottom_panel", ["bottom_profile", "bottom_sketch", "bottom"], view3d=True)


@step(6, "Duplicate the bottom chain to make the lid")
def _s6():
    duplicate(["bottom_profile", "bottom_sketch", "bottom"], ["lid_profile", "lid_sketch", "lid"], ["Lid profile", "Lid sketch", "Lid panel"])
    for i, name in enumerate(("lid_profile", "lid_sketch", "lid")):
        drag(name, 2 + i, 5 * ROW)
    wire("lid_off", "value", "lid_sketch", "offset")
    evaluate()
    select("lid_sketch")
    return shot("06_lid", ["lid_profile", "lid_sketch", "lid"], view3d=True)


@step(7, "Duplicate again for the front wall and change it")
def _s7():
    duplicate(["bottom_profile", "bottom_sketch", "bottom"], ["front_profile", "front_sketch", "front"], ["Front profile", "Front sketch", "Front panel"])
    for i, name in enumerate(("front_profile", "front_sketch", "front")):
        drag(name, 2 + i, 1 * ROW)
    for side in ("bottom", "right", "top", "left"):
        set_text("front_profile", f"mode_{side}", "out")
    wire("H", "value", "front_profile", "height")  # replaces the W wire
    wire("nH", "value", "front_profile", "fingers_right")
    wire("nH", "value", "front_profile", "fingers_left")
    set_text("front_sketch", "plane", "XZ")
    wire("front_off", "value", "front_sketch", "offset")
    evaluate()
    select("front_profile")
    return shot("07_front", ["front_profile", "front_sketch", "front"], view3d=True, panel_key="mode_bottom")


@step(8, "Duplicate the front wall to make the back wall")
def _s8():
    duplicate(["front_profile", "front_sketch", "front"], ["back_profile", "back_sketch", "back"], ["Back profile", "Back sketch", "Back panel"])
    for i, name in enumerate(("back_profile", "back_sketch", "back")):
        drag(name, 2 + i, 2 * ROW)
    wire("back_off", "value", "back_sketch", "offset")
    evaluate()
    select("back_sketch")
    return shot("08_back", ["back_profile", "back_sketch", "back"], view3d=True)


@step(9, "Duplicate the front wall for the left wall and change it")
def _s9():
    duplicate(["front_profile", "front_sketch", "front"], ["left_profile", "left_sketch", "left"], ["Left profile", "Left sketch", "Left panel"])
    for i, name in enumerate(("left_profile", "left_sketch", "left")):
        drag(name, 2 + i, 3 * ROW)
    wire("W", "value", "left_profile", "width")
    wire("nW", "value", "left_profile", "fingers_bottom")
    wire("nW", "value", "left_profile", "fingers_top")
    set_text("left_profile", "mode_right", "in")
    set_text("left_profile", "mode_left", "in")
    set_text("left_sketch", "plane", "YZ")
    delete_wire("left_sketch", "offset")  # the left wall sits at x = 0
    set_text("left_sketch", "offset", "0.0")
    evaluate()
    select("left_profile")
    return shot("09_left", ["left_profile", "left_sketch", "left"], view3d=True, panel_key="mode_bottom")


@step(10, "Duplicate the left wall to make the right wall")
def _s10():
    duplicate(["left_profile", "left_sketch", "left"], ["right_profile", "right_sketch", "right"], ["Right profile", "Right sketch", "Right panel"])
    for i, name in enumerate(("right_profile", "right_sketch", "right")):
        drag(name, 2 + i, 4 * ROW)
    wire("right_off", "value", "right_sketch", "offset")
    evaluate()
    press(KEY.Key_F)
    return shot("10_complete", window=True) + shot("10_complete", view3d=True)


@step(11, "Change a constant and re-evaluate")
def _s11():
    set_text("t", "value", "6")
    set_text("nL_raw", "value", "4")
    evaluate()
    select("t")
    files = shot("11_thicker", ["t", "nL_raw", "nL"], view3d=True)
    _verify_box(160.0, 100.0, 70.0, 6.0)
    return files


def _verify_box(L, W, H, t):
    doc = App.ActiveDocument
    from paramweave.app.evaluator import find_generated

    shapes = [find_generated(doc, N[k].id).Shape for k in ("bottom", "lid", "front", "back", "left", "right")]
    total = sum(s.Volume for s in shapes)
    shell = L * W * H - (L - 2 * t) * (W - 2 * t) * (H - 2 * t)
    expect(abs(total - shell) < 1e-3, f"panel volume {total} != shell {shell}")
    fused = shapes[0].fuse(shapes[1:])
    expect(abs(fused.Volume - total) < 1e-3, "panels overlap")
    bb = fused.BoundBox
    expect(max(abs(bb.XLength - L), abs(bb.YLength - W), abs(bb.ZLength - H)) < 1e-6, f"bounds {bb}")
    nodes, edges = len(ws().model.nodes), len(ws().model.edges)
    expect((nodes, edges) == (32, 73), f"graph has {nodes} nodes / {edges} wires")


@check("tutorial log written")
def _log():
    import json

    with open(os.path.join(OUT, "steps.json"), "w") as fh:
        json.dump([{"step": n, "title": t, "images": i} for n, t, i in STEPS], fh, indent=2)


start()
