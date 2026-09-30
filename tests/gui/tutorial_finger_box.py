"""Build the finger-jointed box using only GUI interactions, capturing screenshots.

This both verifies that the box can be made entirely from the ParamWeave GUI
and produces the images for the tutorial in ``docs/tutorial/``. Every graph
change goes through what a user does: canvas context menu entries (the same
signal a menu click emits), clicking ports, typing into the property panel,
clicking nodes and wires, Ctrl+D, Delete, dragging nodes and the Evaluate
button.

Run: python3 tools/run_freecad_tests.py --gui-script tests/gui/tutorial_finger_box.py
Screenshots go to $PARAMWEAVE_TUTORIAL_OUT (default docs/tutorial/images); the
finished document is saved next to that folder as finger-jointed-box.FCStd.
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
import tutorial_harness  # noqa: E402
from tutorial_harness import *  # noqa: E402,F401,F403

tutorial_harness.set_output(os.environ.get("PARAMWEAVE_TUTORIAL_OUT") or os.path.join(ROOT, "docs", "tutorial", "images"))
OUT = tutorial_harness.OUT

COL, ROW = 300.0, 260.0


# -- the tutorial ------------------------------------------------------------

CONSTANTS = [
    ("L", "Length L", "160"),
    ("W", "Width W", "100"),
    ("H", "Height H", "70"),
    ("t", "Thickness t", "3"),
    ("k", "Kerf k", "0"),
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
        set_choice("bottom_profile", f"mode_{side}", "in")
    for src, port in (("L", "width"), ("W", "height"), ("t", "thickness"), ("k", "kerf"), ("nL", "fingers_bottom"), ("nW", "fingers_right"), ("nL", "fingers_top"), ("nW", "fingers_left")):
        wire(src, "value", "bottom_profile", port)
    select("bottom_profile")
    return shot("04_bottom_profile", ["L", "W", "t", "k", "nL", "nW", "bottom_profile"], panel_key="mode_bottom")


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
        set_choice("front_profile", f"mode_{side}", "out")
    wire("H", "value", "front_profile", "height")  # replaces the W wire
    wire("nH", "value", "front_profile", "fingers_right")
    wire("nH", "value", "front_profile", "fingers_left")
    set_choice("front_sketch", "plane", "XZ")
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
    set_choice("left_profile", "mode_right", "in")
    set_choice("left_profile", "mode_left", "in")
    set_choice("left_sketch", "plane", "YZ")
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
    files = shot("10_complete", window=True) + shot("10_complete", view3d=True)
    # Ship the finished tutorial document. saveCopy leaves the working
    # document untouched and records no file name of the session's own.
    path = os.path.join(os.path.dirname(OUT), "finger-jointed-box.FCStd")
    if os.path.exists(path):
        os.remove(path)
    doc = App.ActiveDocument
    # FreeCAD stamps new documents "All rights reserved"; the project license
    # is undecided (see LICENSE_STATUS.md), so the example claims none.
    doc.License = ""
    doc.LicenseURL = ""
    doc.saveCopy(path)
    expect(os.path.getsize(path) > 0, "FCStd was not written")
    return files + [os.path.basename(path)]


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
    kerf_wired = [e for e in ws().model.edges.values() if e.src_node == N["k"].id and e.dst_port == "kerf"]
    expect(len(kerf_wired) == 6, f"Kerf k drives {len(kerf_wired)} panel profiles, expected 6")
    nodes, edges = len(ws().model.nodes), len(ws().model.edges)
    expect((nodes, edges) == (33, 79), f"graph has {nodes} nodes / {edges} wires")


@check("tutorial log written")
def _log():
    import json

    with open(os.path.join(OUT, "steps.json"), "w") as fh:
        json.dump([{"step": n, "title": t, "images": i} for n, t, i in STEPS], fh, indent=2)


start()
