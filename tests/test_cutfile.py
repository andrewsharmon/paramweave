import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ParamWeave"))

from paramweave.app import cutfile as cf
from paramweave.app import sketch_model as sm

SVG = "{http://www.w3.org/2000/svg}"


def read_dxf(text):
    """Tiny DXF reader: (header vars, layers, entities as dicts of group codes)."""
    lines = text.splitlines()
    pairs = [(int(lines[i].strip()), lines[i + 1].strip()) for i in range(0, len(lines) - 1, 2)]
    header, layers, entities = {}, [], []
    section = current = None
    var = None
    for code, value in pairs:
        if code == 0 and value == "SECTION":
            section = "?"
        elif code == 2 and section == "?":
            section = value
        elif code == 0 and value in ("ENDSEC", "EOF"):
            section = current = None
        elif section == "HEADER":
            if code == 9:
                var = value
            else:
                header[var] = value
        elif section == "TABLES" and code == 0 and value == "LAYER":
            current = {}
            layers.append(current)
        elif section == "TABLES" and current is not None and code == 2:
            current["name"] = value
        elif section == "ENTITIES":
            if code == 0:
                current = {"type": value}
                entities.append(current)
            else:
                current[code] = value if code == 8 else float(value)
    return header, layers, entities


def box_panels():
    return [
        ("Bottom", sm.finger_panel(160, 100, 3, [("in", 7), ("in", 5), ("in", 7), ("in", 5)])),
        ("Front", sm.finger_panel(160, 70, 3, [("out", 7), ("out", 3), ("out", 7), ("out", 3)])),
        ("Left", sm.finger_panel(100, 70, 3, [("out", 5), ("in", 3), ("out", 5), ("in", 3)])),
    ]


class GeometryTests(unittest.TestCase):
    def test_construction_and_points_are_not_cut(self):
        geo = sm.combine([sm.line(0, 0, 10, 0), sm.line(0, 0, 0, 5, construction=True), sm.point(3, 3)])
        self.assertEqual(["line"], [e["type"] for e in cf.cut_elements(geo)])
        with self.assertRaises(cf.CutFileError):
            cf.bounds(cf.cut_elements(sm.combine([sm.point(1, 1)])))

    def test_arc_bounds_include_axis_extremes(self):
        # Quarter arc from 45 to 135 degrees passes the top of the circle.
        (x0, y0, x1, y1) = cf.bounds(cf.cut_elements(sm.arc(0, 0, 10, 45, 135)))
        self.assertAlmostEqual(10.0, y1)
        self.assertAlmostEqual(-7.0710678, x0, places=6)
        self.assertAlmostEqual(7.0710678, y0, places=6)

    def test_layout_packs_rows_without_overlap(self):
        placed = cf.layout(box_panels(), sheet_width=300, gap=5)
        self.assertEqual(["Bottom", "Front", "Left"], [p.name for p in placed])  # tallest first
        rects = []
        for p in placed:
            x0, y0, x1, y1 = cf.bounds(p.elements)
            rects.append((x0 + p.dx, y0 + p.dy, x1 + p.dx, y1 + p.dy))
            self.assertGreaterEqual(rects[-1][0], -1e-9)
            self.assertGreaterEqual(rects[-1][1], -1e-9)
        for i, a in enumerate(rects):
            self.assertLessEqual(a[2], 300 + 1e-9)
            for b in rects[i + 1:]:
                overlap = a[0] < b[2] + 5 - 1e-9 and b[0] < a[2] + 5 - 1e-9 and a[1] < b[3] + 5 - 1e-9 and b[1] < a[3] + 5 - 1e-9
                self.assertFalse(overlap, (a, b))

    def test_layout_validation(self):
        with self.assertRaises(cf.CutFileError):
            cf.layout([], 100, 5)
        with self.assertRaises(cf.CutFileError):
            cf.layout(box_panels(), 0, 5)
        with self.assertRaises(cf.CutFileError):
            cf.layout(box_panels(), 100, -1)


class DxfTests(unittest.TestCase):
    def test_entities_layers_and_units(self):
        panels = box_panels()
        text = cf.export(panels, "dxf", sheet_width=1000, gap=10)
        header, layers, entities = read_dxf(text)
        self.assertEqual("AC1009", header["$ACADVER"])
        self.assertEqual("4", header["$INSUNITS"])
        self.assertEqual(["Bottom", "Front", "Left"], [l["name"] for l in layers])
        expected = sum(len(cf.cut_elements(g)) for _n, g in panels)
        self.assertEqual(expected, len(entities))
        self.assertEqual({"LINE"}, {e["type"] for e in entities})
        # Each panel is a closed chain: every end point is some line's start point.
        for layer in ("Bottom", "Front", "Left"):
            lines = [e for e in entities if e[8] == layer]
            starts = {(round(e[10], 6), round(e[20], 6)) for e in lines}
            ends = {(round(e[11], 6), round(e[21], 6)) for e in lines}
            self.assertEqual(starts, ends)
        self.assertTrue(text.endswith("EOF\n"))

    def test_arcs_and_circles(self):
        geo = sm.combine([sm.circle(0, 0, 4), sm.arc(10, 0, 3, 350, 20)])
        _h, _l, entities = read_dxf(cf.export([("A", geo)], "dxf"))
        circle, arc = entities
        self.assertEqual(("CIRCLE", 4.0), (circle["type"], circle[40]))
        self.assertEqual(("ARC", 350.0, 20.0), (arc["type"], arc[50], arc[51]))

    def test_layer_names_are_sanitised_and_unique(self):
        geo = sm.line(0, 0, 1, 0)
        _h, layers, _e = read_dxf(cf.export([("Left panel!", geo), ("left panel?", geo), ("", geo)], "dxf"))
        self.assertEqual(["Left_panel", "left_panel_2", "PANEL"], [l["name"] for l in layers])


class SvgTests(unittest.TestCase):
    def test_well_formed_mm_sheet(self):
        text = cf.export(box_panels(), "svg", sheet_width=1000, gap=10)
        root = ET.fromstring(text.encode())
        self.assertTrue(root.get("width").endswith("mm"))
        w = float(root.get("width")[:-2])
        self.assertEqual(f"0 0 {root.get('viewBox').split()[2]} {root.get('viewBox').split()[3]}", root.get("viewBox"))
        self.assertAlmostEqual(160 + 10 + 160 + 10 + 100 + 4, w, places=6)
        groups = root.findall(f"{SVG}g/{SVG}g")
        self.assertEqual(["Bottom", "Front", "Left"], [g.find(f"{SVG}title").text for g in groups])
        paths = root.findall(f".//{SVG}path")
        self.assertEqual(sum(len(cf.cut_elements(g)) for _n, g in box_panels()), len(paths))
        style = root.find(f"{SVG}g")
        self.assertEqual(("none", "#ff0000"), (style.get("fill"), style.get("stroke")))

    def test_arc_flags_and_y_flip(self):
        text = cf.export([("A", sm.arc(0, 0, 10, 0, 270))], "svg")
        d = ET.fromstring(text.encode()).find(f".//{SVG}path").get("d")
        # Large arc (270 degrees), sweep flag 0 after flipping y.
        self.assertIn(" A 10 10 0 1 0 ", d)

    def test_names_are_escaped(self):
        text = cf.export([("<b>&\"x\"", sm.line(0, 0, 5, 0))], "svg")
        root = ET.fromstring(text.encode())  # would fail if not escaped
        self.assertEqual('<b>&"x"', root.find(f".//{SVG}title").text)

    def test_unknown_format(self):
        with self.assertRaises(cf.CutFileError):
            cf.export(box_panels(), "pdf")


if __name__ == "__main__":
    unittest.main()
