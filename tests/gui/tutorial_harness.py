"""GUI helpers shared by the tutorial walkthrough scripts.

Every action goes through what a user does: canvas context menu entries (the
same signal a menu click emits), clicking ports, typing into the property
panel, picking from dropdowns, clicking nodes and wires, key presses, dragging
nodes and the Evaluate button. Screenshots go to ``OUT``; scripts set it with
``set_output()`` before their first step.
"""

import os
import re

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

try:
    from PySide6 import QtTest
except ImportError:  # pragma: no cover - Qt5 builds
    from PySide2 import QtTest

from gui_harness import *  # noqa: F401,F403
from gui_harness import check, expect, left_button, main_window, no_button, no_modifier, node_status, paramweave_docks, pump, ws, click_port, click_scene_point

OUT = None


def set_output(path):
    global OUT
    OUT = path
    os.makedirs(OUT, exist_ok=True)


Qt = QtCore.Qt
KEY = getattr(Qt, "Key", Qt)
MOD = getattr(Qt, "KeyboardModifier", Qt)
TYPES = getattr(QtCore.QEvent, "Type", QtCore.QEvent)

COL = 300.0  # graph column spacing used by add() and drag()
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



def set_choice(name, key, value):
    """Select the node and pick ``value`` from its ``key`` dropdown."""
    if ws().properties.node_id != N[name].id:
        select(name)
    combos = [c for c in ws().properties.findChildren(QtWidgets.QComboBox) if c.property("paramweave_key") == key and c.isVisible()]
    expect(combos, f"{name}: no '{key}' dropdown")
    combo = combos[0]
    items = [combo.itemText(i) for i in range(combo.count())]
    expect(value in items, f"{name}.{key}: {value!r} not offered in {items}")
    combo.setFocus()
    combo.setCurrentIndex(items.index(value))  # what choosing an entry in the popup does
    pump(5)
    got = ws().model.nodes[N[name].id].params[key]
    expect(got == value, f"{name}.{key} = {got!r}, picked {value!r}")


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
        # Copies are labelled "<original> <n>"; match exactly so "A" never claims "A solid 2".
        (copy,) = [n for lbl, n in by_label.items() if re.fullmatch(re.escape(N[old].label) + r" \d+", lbl)]
        N[new_name] = copy
        set_text(new_name, "__label__", label)


def drag(name, col, row, attempts=4):
    """Drag a node by its header to its column/row.

    Retried: like clicks (see gui_harness.click_viewport), a synthetic press
    shortly after a 3D view update can be rerouted away from the graph.
    """
    for attempt in range(attempts):
        try:
            return _drag_once(name, col, row)
        except AssertionError:
            if attempt == attempts - 1:
                raise
            pump(20)


def _drag_once(name, col, row):
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
