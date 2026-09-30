import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ParamWeave"))

from paramweave.app import expressions as ex
from paramweave.nodes.registry import NodeRegistry, NodeSpec, PortSpec, apply_driven_params


class ExpressionTests(unittest.TestCase):
    def test_arithmetic_and_functions(self):
        self.assertEqual(14.0, ex.evaluate("a * 2 + b", {"a": 5, "b": 4}))
        self.assertAlmostEqual(1.0, ex.evaluate("sin(90)"))
        self.assertAlmostEqual(45.0, ex.evaluate("atan2(1, 1)"))
        self.assertEqual(3.0, ex.evaluate("clamp(a, 1, 3)", {"a": 9}))
        self.assertEqual(2.0, ex.evaluate("a if a > 1 else 0", {"a": 2}))
        self.assertAlmostEqual(6.283185307179586, ex.evaluate("2 * pi"))

    def test_names_used(self):
        self.assertEqual({"a", "w"}, ex.names_used("max(a, w) * pi"))

    def test_rejects_unsafe_or_bad_input(self):
        for text in (
            "__import__('os')",
            "a.__class__",
            "[1, 2]",
            "'x'",
            "lambda: 1",
            "open('f')",
            "a",
            "1 / 0",
            "2 ** 100000",
            "",
            "1 +",
            "x" * 600,
            "sqrt(-1)",
            "True",
        ):
            with self.assertRaises(ex.ExpressionError, msg=text):
                ex.evaluate(text, {})


class DrivenParamTests(unittest.TestCase):
    def test_numeric_params_get_optional_number_ports(self):
        reg = NodeRegistry()
        spec = reg.register(
            NodeSpec(
                "t.x",
                "X",
                "T",
                inputs=[PortSpec("value", "Number")],
                default_params={"value": 1.0, "n": 3, "flag": True, "name": ""},
            )
        )
        self.assertEqual(["value", "n"], [p.name for p in spec.inputs])
        self.assertFalse(spec.input("n").required)
        self.assertTrue(spec.input("value").required)

    def test_apply_driven_params(self):
        params = {"w": 1.0, "n": 3, "flag": True}
        self.assertEqual({"w": 2.5, "n": 4, "flag": True}, apply_driven_params(params, {"w": 2.5, "n": 4.0, "flag": 0}))
        self.assertEqual(1.0, params["w"])
        with self.assertRaises(ValueError):
            apply_driven_params(params, {"n": 3.5})
        with self.assertRaises(ValueError):
            apply_driven_params(params, {"w": "x"})


if __name__ == "__main__":
    unittest.main()
