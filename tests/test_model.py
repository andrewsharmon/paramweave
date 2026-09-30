import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ParamWeave"))

import json
import uuid

from paramweave.app.model import SCHEMA_VERSION, GraphModel, GraphValidationError


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

    def test_duplicate_edge_rejected(self):
        g = GraphModel()
        a = g.create_node("a", "A")
        b = g.create_node("b", "B")
        g.connect(a.id, "out", b.id, "in")
        with self.assertRaises(GraphValidationError):
            g.connect(a.id, "out", b.id, "in")

    def test_self_edge_rejected(self):
        g = GraphModel()
        a = g.create_node("a", "A")
        with self.assertRaises(GraphValidationError):
            g.connect(a.id, "out", a.id, "in")

    def test_json_is_deterministic(self):
        g = GraphModel()
        for i in range(5):
            g.create_node("t", f"N{i}", (i, i), {"z": 1, "a": 2})
        self.assertEqual(g.to_json(), GraphModel.from_json(g.to_json()).to_json())
        self.assertEqual(g.to_json(), json.dumps(json.loads(g.to_json()), sort_keys=True, separators=(",", ":")))

    def test_empty_text_is_empty_graph(self):
        self.assertEqual({}, GraphModel.from_json("  ").nodes)


def _node(**overrides):
    data = {"id": str(uuid.uuid4()), "type_id": "primitive.box", "label": "Box", "position": [0, 0], "params": {}}
    data.update(overrides)
    return data


class UntrustedGraphTests(unittest.TestCase):
    """Embedded graph JSON may come from other people; reject malformed data."""

    def assertRejected(self, data):
        text = data if isinstance(data, str) else json.dumps(data)
        with self.assertRaises(GraphValidationError):
            GraphModel.from_json(text)

    def test_not_json(self):
        self.assertRejected("{not json")

    def test_not_an_object(self):
        self.assertRejected([1, 2, 3])
        self.assertRejected("\"just a string\"")

    def test_schema_version(self):
        self.assertRejected({"schema_version": SCHEMA_VERSION + 1, "nodes": [], "edges": []})
        self.assertRejected({"schema_version": "1", "nodes": [], "edges": []})
        self.assertRejected({"schema_version": True, "nodes": [], "edges": []})
        self.assertRejected({"nodes": [], "edges": []})

    def test_bad_containers(self):
        self.assertRejected({"schema_version": 1, "nodes": {}, "edges": []})
        self.assertRejected({"schema_version": 1, "nodes": [], "edges": "x"})
        self.assertRejected({"schema_version": 1, "nodes": ["x"], "edges": []})

    def test_bad_node_fields(self):
        for bad in (
            _node(id=""),
            _node(id=7),
            _node(type_id=None),
            _node(label=["x"]),
            _node(position="__import__('os')"),
            _node(position=[0]),
            _node(position=[0, "a"]),
            _node(position=[0, float("inf")]),
            _node(params="x"),
        ):
            self.assertRejected({"schema_version": 1, "nodes": [bad], "edges": []})

    def test_duplicate_node_ids(self):
        n = _node()
        self.assertRejected({"schema_version": 1, "nodes": [n, dict(n)], "edges": []})

    def _two_nodes(self):
        return _node(), _node()

    def _edge(self, a, b, **overrides):
        data = {"id": str(uuid.uuid4()), "src_node": a["id"], "src_port": "shape", "dst_node": b["id"], "dst_port": "base"}
        data.update(overrides)
        return data

    def test_bad_edges(self):
        a, b = self._two_nodes()
        good = self._edge(a, b)
        self.assertEqual(1, len(GraphModel.from_dict({"schema_version": 1, "nodes": [a, b], "edges": [good]}).edges))
        for edges in (
            [self._edge(a, b, dst_node="missing")],
            [self._edge(a, a)],
            [good, dict(good)],
            [good, self._edge(a, b)],  # same input twice
            [self._edge(a, b), self._edge(b, a, dst_port="tool")],  # cycle
            [self._edge(a, b, src_port=3)],
        ):
            self.assertRejected({"schema_version": 1, "nodes": [a, b], "edges": edges})

    def test_expression_like_strings_stay_inert(self):
        payload = "__import__('os').system('echo pwned')"
        g = GraphModel.from_dict({"schema_version": 1, "nodes": [_node(label=payload, params={"x": payload})], "edges": []})
        node = next(iter(g.nodes.values()))
        self.assertEqual(payload, node.label)
        self.assertEqual(payload, node.params["x"])

    def test_unknown_top_level_keys_are_ignored(self):
        g = GraphModel.from_dict({"schema_version": 1, "nodes": [], "edges": [], "future": {"x": 1}})
        self.assertEqual({}, g.nodes)


class EditingOperationTests(unittest.TestCase):
    def _chain(self):
        g = GraphModel()
        c = g.create_node("value.number", "C", (0, 0), {"value": 1.0})
        a = g.create_node("x.a", "A", (100, 0), {"k": [1]})
        b = g.create_node("x.b", "B", (200, 0), {})
        g.connect(c.id, "value", a.id, "w")
        g.connect(a.id, "out", b.id, "in")
        return g, c, a, b

    def test_replace_connection(self):
        g, c, a, b = self._chain()
        d = g.create_node("value.number", "D", (0, 50), {})
        with self.assertRaises(GraphValidationError):
            g.connect(d.id, "value", a.id, "w")
        g.connect(d.id, "value", a.id, "w", replace=True)
        self.assertEqual([d.id], [e.src_node for e in g.incoming(a.id)])
        with self.assertRaises(GraphValidationError):
            g.connect(d.id, "value", a.id, "w", replace=True)  # identical wire

    def test_failed_replacement_restores_old_wire(self):
        g, c, a, b = self._chain()
        with self.assertRaises(GraphValidationError):
            g.connect(b.id, "out", a.id, "w", replace=True)  # would make a cycle
        self.assertEqual([c.id], [e.src_node for e in g.incoming(a.id)])

    def test_duplicate_keeps_internal_and_incoming_wires(self):
        g, c, a, b = self._chain()
        mapping = g.duplicate([a.id, b.id], offset=(0, 100), label_for=lambda s: s + "2")
        na, nb = mapping[a.id], mapping[b.id]
        self.assertEqual("A2", g.nodes[na].label)
        self.assertEqual([100.0, 100.0], g.nodes[na].position)
        self.assertEqual([c.id], [e.src_node for e in g.incoming(na)])
        self.assertEqual([na], [e.src_node for e in g.incoming(nb)])
        self.assertEqual(5, len(g.nodes))
        # Params are deep-copied.
        g.nodes[na].params["k"].append(2)
        self.assertEqual([1], g.nodes[a.id].params["k"])
        self.assertEqual(g.to_dict(), GraphModel.from_json(g.to_json()).to_dict())


if __name__ == "__main__":
    unittest.main()
