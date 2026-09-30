import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ParamWeave"))

from paramweave.app.model import GraphModel
from paramweave.examples import finger_box


class FingerBoxExampleTests(unittest.TestCase):
    def test_graph_is_valid_and_serializable(self):
        g = GraphModel()
        ids = finger_box.build(g)
        order = g.topological_order()
        self.assertEqual(len(g.nodes), len(order))
        self.assertEqual(8 + 7 + 6 * 3, len(g.nodes))
        self.assertEqual(79, len(g.edges))
        self.assertEqual(g.to_dict(), GraphModel.from_json(g.to_json()).to_dict())
        # Every panel depends on the thickness constant.
        t = ids["t"]
        for key in ("bottom", "front", "back", "left", "right", "lid"):
            self.assertTrue(any(e.src_node == t and e.dst_node == ids[key] for e in g.edges.values()))
            self.assertTrue(
                any(e.src_node == ids["k"] and e.dst_node == ids[f"{key}_profile"] and e.dst_port == "kerf" for e in g.edges.values())
            )

    def test_without_lid(self):
        g = GraphModel()
        ids = finger_box.build(g, lid=False, thickness=4.0)
        self.assertNotIn("lid", ids)
        self.assertEqual(4.0, g.nodes[ids["t"]].params["value"])
        self.assertEqual("flat", g.nodes[ids["front_profile"]].params["mode_top"])


if __name__ == "__main__":
    unittest.main()
