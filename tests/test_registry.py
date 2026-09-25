import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ParamWeave"))

from paramweave.app.model import GraphModel
from paramweave.nodes.registry import NodeRegistry, NodeSpec, PortSpec, placeholder_spec, types_compatible


class RegistryTests(unittest.TestCase):
    def test_register_and_lookup(self):
        reg = NodeRegistry()
        spec = reg.register(NodeSpec("x.y", "XY", "Test", outputs=[PortSpec("out", "Number")]))
        self.assertIs(spec, reg.get("x.y"))
        self.assertIs(spec, reg.find("x.y"))
        self.assertIsNone(reg.find("missing"))
        with self.assertRaises(KeyError):
            reg.get("missing")
        with self.assertRaises(ValueError):
            reg.register(NodeSpec("x.y", "Again", "Test"))

    def test_port_lookup(self):
        spec = NodeSpec("x", "X", "T", inputs=[PortSpec("a", "Number")], outputs=[PortSpec("b", "CAD.Shape")])
        self.assertEqual("Number", spec.input("a").type_name)
        self.assertEqual("CAD.Shape", spec.output("b").type_name)
        self.assertIsNone(spec.input("b"))

    def test_types_compatible(self):
        self.assertTrue(types_compatible("CAD.Solid", "CAD.Shape"))
        self.assertTrue(types_compatible("Number", "Number"))
        self.assertTrue(types_compatible("Any", "CAD.Shape"))
        self.assertTrue(types_compatible("Number", "Any"))
        self.assertFalse(types_compatible("Number", "CAD.Shape"))
        self.assertFalse(types_compatible("CAD.Shape", "CAD.Solid"))

    def test_placeholder_spec_infers_ports_from_edges(self):
        g = GraphModel()
        up = g.create_node("known.a", "A")
        unknown = g.create_node("future.thing", "Future")
        down = g.create_node("known.b", "B")
        g.connect(up.id, "out", unknown.id, "in_1")
        g.connect(unknown.id, "result", down.id, "in")
        spec = placeholder_spec(unknown.id, unknown.type_id, g)
        self.assertTrue(spec.placeholder)
        self.assertFalse(spec.generates_object)
        self.assertEqual(["in_1"], [p.name for p in spec.inputs])
        self.assertEqual(["result"], [p.name for p in spec.outputs])
        self.assertTrue(all(p.type_name == "Any" for p in spec.inputs + spec.outputs))


if __name__ == "__main__":
    unittest.main()
