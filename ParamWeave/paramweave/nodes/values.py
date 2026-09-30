"""Number nodes: constants, expressions and document variables.

Their ``value`` output wires into any numeric parameter port (every numeric
parameter of every node has one), so sketch dimensions and primitive sizes can
be driven by a constant, a formula, or a spreadsheet/VarSet value.
"""

from __future__ import annotations

from paramweave.app import expressions
from paramweave.nodes.core import _number
from paramweave.nodes.registry import NodeSpec, PortSpec, registry

EXPRESSION_INPUTS = ("a", "b", "c", "d")


def eval_number(_doc, node, _inputs):
    return {"value": _number(node.params.get("value", 0.0), "value")}


def eval_expression(_doc, node, inputs):
    variables = {k: _number(inputs[k], k) for k in EXPRESSION_INPUTS if k in inputs}
    text = str(node.params.get("expression", ""))
    missing = sorted(n for n in expressions.names_used(text) if n in EXPRESSION_INPUTS and n not in variables)
    if missing:
        raise ValueError(f"expression uses unconnected input(s): {', '.join(missing)}")
    return {"value": expressions.evaluate(text, variables)}


def _find_object(doc, key: str):
    obj = doc.getObject(key)
    if obj is not None:
        return obj
    matches = doc.getObjectsByLabel(key)
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise ValueError(f"{len(matches)} objects are labelled {key!r}; use the object's internal name")
    raise ValueError(f"no document object named or labelled {key!r}")


def eval_document_value(doc, node, _inputs):
    """Read a numeric property, e.g. a Spreadsheet alias or a VarSet variable."""
    key = str(node.params.get("object", "")).strip()
    prop = str(node.params.get("property", "")).strip()
    if not key or not prop:
        raise ValueError("set 'object' (name or label) and 'property' (e.g. a spreadsheet alias)")
    obj = _find_object(doc, key)
    # Spreadsheet aliases are attributes but not listed in PropertiesList.
    if prop.startswith("_") or (prop not in obj.PropertiesList and not hasattr(obj, prop)):
        raise ValueError(f"{obj.Label} has no property or alias {prop!r}")
    value = getattr(obj, prop)
    value = getattr(value, "Value", value)  # Quantity -> internal units (mm, degrees)
    return {"value": _number(value, f"{obj.Label}.{prop}")}


def register_value_nodes() -> None:
    if registry.find("value.number") is not None:
        return
    registry.register(
        NodeSpec(
            "value.number",
            "Number",
            "Values",
            outputs=[PortSpec("value", "Number")],
            default_params={"value": 10.0},
            evaluate=eval_number,
        )
    )
    registry.register(
        NodeSpec(
            "value.expression",
            "Expression",
            "Values",
            inputs=[PortSpec(k, "Number", required=False) for k in EXPRESSION_INPUTS],
            outputs=[PortSpec("value", "Number")],
            default_params={"expression": "a * 2"},
            evaluate=eval_expression,
        )
    )
    registry.register(
        NodeSpec(
            "value.document",
            "Document Variable",
            "Values",
            outputs=[PortSpec("value", "Number")],
            default_params={"object": "Spreadsheet", "property": ""},
            evaluate=eval_document_value,
        )
    )
