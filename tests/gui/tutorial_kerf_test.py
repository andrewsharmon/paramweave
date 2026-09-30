"""Build the kerf fit test using only GUI interactions, capturing screenshots.

Verifies the kerf test can be made entirely from the ParamWeave GUI (context
menu, ports, property panel, corner-style dropdown, Ctrl+D, dragging,
Evaluate) and produces the images for ``docs/tutorial/kerf-fit-test.md``.

Run: python3 tools/run_freecad_tests.py --gui-script tests/gui/tutorial_kerf_test.py
Screenshots go to $PARAMWEAVE_TUTORIAL_OUT (default docs/tutorial/images) as
``kerf_*.png``; the finished document is saved next to that folder as
kerf-fit-test.FCStd and its cut sheet as kerf-fit-test.svg.
"""

import json
import os
import sys

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui

ROOT = os.environ["PARAMWEAVE_ROOT"]
sys.path.insert(0, os.path.join(ROOT, "tests", "gui"))
from gui_harness import *  # noqa: E402,F401,F403
import tutorial_harness  # noqa: E402
from tutorial_harness import *  # noqa: E402,F401,F403

tutorial_harness.set_output(os.environ.get("PARAMWEAVE_TUTORIAL_OUT") or os.path.join(ROOT, "docs", "tutorial", "images"))
OUT = tutorial_harness.OUT
TUTORIAL_DIR = os.path.dirname(OUT)

Qt = QtCore.Qt
ROW = 380.0  # a Kerf Fit Test node is about 300 units tall

CONSTANTS = [
    ("t", "Thickness t", "3"),
    ("f", "Finger width", "10"),
    ("k0", "First kerf", "0"),
    ("dk", "Kerf step", "0.05"),
    ("n", "Kerf steps", "5"),
    ("d", "Tool diameter", "3.175"),
]
EXPRESSIONS = [
    ("h", "Coupon height", "max(20, 4 * a + 4)", [("t", "a")]),
    ("y90", "90° set y", "2 * a + 8", [("h", "a")]),
    ("y45", "45° set y", "a + 3 * b + 4", [("y90", "a"), ("f", "b")]),
]
COUPON_WIRES = [
    ("t", "thickness"),
    ("f", "finger_width"),
    ("h", "coupon_height"),
    ("k0", "kerf_start"),
    ("dk", "kerf_step"),
    ("n", "count"),
    ("d", "tool_diameter"),
]
SETS = ("c0", "c90", "c45")


def chain(key):
    return [f"{key}_coupons", f"{key}_sketch", key]


def solid(key):
    from paramweave.app.evaluator import find_generated

    return find_generated(App.ActiveDocument, N[key].id).Shape


def top_view(cx, cy, height):
    """Straight-down orthographic view of the XY plane centered on (cx, cy), ``height`` mm tall.

    Set directly on the camera: viewTop() animates, and saveImage() can
    capture it half-turned.
    """
    from pivy import coin  # noqa: F401  (loads the SWIG wrappers getCameraNode needs)

    view = Gui.activeDocument().activeView()
    view.setAnimationEnabled(False)
    view.setCameraType("Orthographic")
    cam = view.getCameraNode()
    cam.orientation.setValue(0.0, 0.0, 0.0, 1.0)
    cam.position.setValue(cx, cy, 200.0)
    cam.nearDistance.setValue(1.0)
    cam.farDistance.setValue(400.0)
    cam.focalDistance.setValue(200.0)
    cam.height.setValue(height)
    pump(10)
    return view


def svg_to_png(svg_path, png_path, width_px=1600):
    """Render the exported cut sheet for the tutorial (white background)."""
    try:
        from PySide6 import QtSvg
    except ImportError:  # pragma: no cover - Qt5 builds
        from PySide2 import QtSvg
    with open(svg_path, encoding="utf-8") as fh:
        text = fh.read()
    # Hairline cut strokes vanish at screen resolution; thicken for the picture only.
    text = text.replace('stroke-width="0.01"', 'stroke-width="0.4"')
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(text.encode("utf-8")))
    expect(renderer.isValid(), "exported SVG does not parse")
    size = renderer.defaultSize()
    height = int(width_px * size.height() / max(1, size.width()))
    image = QtGui.QImage(width_px, height, QtGui.QImage.Format.Format_ARGB32)
    image.fill(QtGui.QColor("white"))
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    image.save(png_path)


@step(1, "Start a new document with the graph pane")
def _s1():
    mw = main_window()
    mw.showNormal()
    mw.resize(1700, 1000)
    Gui.activateWorkbench("ParamWeaveWorkbench")
    pump(10)
    App.newDocument("KerfFitTest")
    pump(10)
    ws().bind_active_document(force=True)
    dock = paramweave_docks()[0]
    dock.show()
    mw.resizeDocks([dock], [900], Qt.Horizontal)
    pump(10)
    return []


@step(2, "Add the constants")
def _s2():
    for i, (name, label, value) in enumerate(CONSTANTS):
        add(name, "value.number", 0, i * 90.0, label)
        set_text(name, "value", value)
    select("dk")
    return shot("kerf_02_constants", [n for n, *_ in CONSTANTS])


@step(3, "Add the expressions that size and stack the coupon sets")
def _s3():
    for i, (name, label, text, inputs) in enumerate(EXPRESSIONS):
        add(name, "value.expression", 1, i * 150.0, label)
        set_text(name, "expression", text)
        for src, port in inputs:
            wire(src, "value", name, port)
    select("y45")
    return shot("kerf_03_expressions", [n for n, *_ in CONSTANTS] + [n for n, *_ in EXPRESSIONS])


@step(4, "Add the 0° coupon set, its sketch and its solid")
def _s4():
    add("c0_coupons", "sketch.kerf_test", 2, 0, "Coupons 0°")
    for src, port in COUPON_WIRES:
        wire(src, "value", "c0_coupons", port)
    add("c0_sketch", "sketch.sketch", 3, 0, "Kerf test 0°")
    wire("c0_coupons", "geometry", "c0_sketch", "geometry")
    add("c0", "sketch.extrude", 4, 0, "Kerf test 0° solid")
    wire("c0_sketch", "shape", "c0", "shape")
    wire("t", "value", "c0", "length")
    evaluate()
    expect(len(solid("c0").Solids) == 10, "the 0° set should be five coupon pairs")
    select("c0_coupons")
    return shot("kerf_04_set0", chain("c0"), view3d=True, panel_key="corner_style")


@step(5, "Duplicate the chain for the 90° and 45° sets")
def _s5():
    for key, angle, row, y_src in (("c90", "90", 1, "y90"), ("c45", "45", 2, "y45")):
        duplicate(chain("c0"), chain(key), [f"Coupons {angle}°", f"Kerf test {angle}°", f"Kerf test {angle}° solid"])
        for i, name in enumerate(chain(key)):
            drag(name, 2 + i, row * ROW)
        set_text(f"{key}_coupons", "angle", f"{angle}.0")
        wire(y_src, "value", f"{key}_coupons", "y")
    evaluate()
    boxes = [solid(k).BoundBox for k in SETS]
    for a, b in zip(boxes, boxes[1:]):
        expect(a.YMax < b.YMin, "coupon sets overlap in the 3D view")
    sheet = boxes[0]
    for b in boxes[1:]:
        sheet.add(b)
    used = sum(solid(k).Volume for k in SETS) / 3.0
    expect(used / (sheet.XLength * sheet.YLength) > 0.5, f"coupons fill only {used / (sheet.XLength * sheet.YLength):.0%} of the sheet")
    select("c45_coupons")
    Gui.SendMsgToActiveView("ViewFit")
    files = shot("kerf_05_all_sets", chain("c45"), panel_key="angle")
    bb = solid("c0").BoundBox
    for k in SETS[1:]:
        bb.add(solid(k).BoundBox)
    # Landscape image: fit whichever of the sheet's sides is tighter.
    view = top_view(bb.Center.x, bb.Center.y, 1.08 * max(bb.YLength, bb.XLength * 1000.0 / 1600.0))
    path = os.path.join(OUT, "kerf_05_all_sets_top.png")
    view.saveImage(path, 1600, 1000, "Current")
    return files + [os.path.basename(path)]


@step(6, "Save the file and export the cut sheet")
def _s6():
    press(QtCore.Qt.Key.Key_F if hasattr(QtCore.Qt, "Key") else QtCore.Qt.Key_F)
    doc = App.ActiveDocument
    fcstd = os.path.join(TUTORIAL_DIR, "kerf-fit-test.FCStd")
    if os.path.exists(fcstd):
        os.remove(fcstd)
    doc.License = ""
    doc.LicenseURL = ""
    doc.saveCopy(fcstd)
    svg = os.path.join(TUTORIAL_DIR, "kerf-fit-test.svg")
    # A sheet just wider than the widest strip stacks the three strips into one rectangle.
    ws().export_cut_files(svg, 250.0, 4.0, False)
    expect(os.path.getsize(svg) > 0, "cut sheet was not written")
    png = os.path.join(OUT, "kerf_06_cut_sheet.png")
    svg_to_png(svg, png)
    return [os.path.basename(png), os.path.basename(fcstd), os.path.basename(svg)]


@step(7, "For milling: pick a corner style from the dropdown")
def _s7():
    before = solid("c0").Volume
    set_text("d", "value", "2")
    for key in SETS:
        set_choice(f"{key}_coupons", "corner_style", "dogbone")
    evaluate()
    expect(solid("c0").Volume < before, "dogbones did not remove material")
    select("c0_coupons")
    files = shot("kerf_07_dogbone", chain("c0"), panel_key="corner_style")
    # Close-up of one tab coupon's finger roots in the 3D view.
    bb = solid("c0").BoundBox
    # First pair: tab fingers meet the slot coupon's slots around y = 20..27.
    view = top_view(bb.XMin + 15.0, bb.YMin + 22.0, 22.0)
    path = os.path.join(OUT, "kerf_07_dogbone_closeup.png")
    view.saveImage(path, 1200, 900, "Current")
    files.append(os.path.basename(path))
    for style, tag in (("tbone_depth", "kerf_07_tbone_depth_closeup.png"), ("tbone_side", "kerf_07_tbone_side_closeup.png")):
        set_choice("c0_coupons", "corner_style", style)
        evaluate()
        view.saveImage(os.path.join(OUT, tag), 1200, 900, "Current")
        files.append(tag)
    # A dropdown pick is an ordinary undoable graph edit.
    doc = App.ActiveDocument
    set_choice("c0_coupons", "corner_style", "none")
    expect(doc.UndoNames and doc.UndoNames[0].startswith("ParamWeave"), f"undo stack {doc.UndoNames[:3]}")
    doc.undo()
    pump(10)
    expect(ws().model.nodes[N["c0_coupons"].id].params["corner_style"] == "tbone_side", "undo did not restore the style")
    doc.redo()
    pump(10)
    expect(ws().model.nodes[N["c0_coupons"].id].params["corner_style"] == "none", "redo did not reapply the style")
    return files


@check("tutorial log written")
def _log():
    with open(os.path.join(OUT, "kerf_steps.json"), "w") as fh:
        json.dump([{"step": n, "title": t, "images": i} for n, t, i in STEPS], fh, indent=2)


start()
