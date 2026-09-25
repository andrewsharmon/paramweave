import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ParamWeave"))

from paramweave.app.model import GraphModel, GraphValidationError


class GraphModelTests(unittest.TestCase):
    def test_round_trip(self):
        g = GraphModel()
        a = g.create_node("test.a", "A", (1, 2), {"x": 3})
        b = g.create_node("test.b", "B", (4, 5), {})
        g.connect(a.id, "out", b.id, "in")
        restored = GraphModel.from_json(g.to_json())
        self.assertEqual(g.to_dict(), restored.to_dict())

    def test_remove_node_removes_edges(self):
        g = GraphModel()
        a = g.create_node("a", "A")
        b = g.create_node("b", "B")
        g.connect(a.id, "out", b.id, "in")
        g.remove_node(a.id)
        self.assertEqual({}, g.edges)

    def test_single_incoming_edge(self):
        g = GraphModel()
        a = g.create_node("a", "A")
        b = g.create_node("b", "B")
        c = g.create_node("c", "C")
        g.connect(a.id, "out", c.id, "in")
        with self.assertRaises(GraphValidationError):
            g.connect(b.id, "out", c.id, "in")

    def test_cycle_rejected(self):
        g = GraphModel()
        a = g.create_node("a", "A")
        b = g.create_node("b", "B")
        c = g.create_node("c", "C")
        g.connect(a.id, "out", b.id, "in")
        g.connect(b.id, "out", c.id, "in")
        with self.assertRaises(GraphValidationError):
            g.connect(c.id, "out", a.id, "in")

    def test_topological_order(self):
        g = GraphModel()
        a = g.create_node("a", "A")
        b = g.create_node("b", "B")
        c = g.create_node("c", "C")
        g.connect(a.id, "out", c.id, "left")
        g.connect(b.id, "out", c.id, "right")
        order = g.topological_order()
        self.assertLess(order.index(a.id), order.index(c.id))
        self.assertLess(order.index(b.id), order.index(c.id))


if __name__ == "__main__":
    unittest.main()
