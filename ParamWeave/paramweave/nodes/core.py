"""Starter constructive/reference/measurement node implementations."""

from __future__ import annotations

import FreeCAD as App
import Part

from paramweave.app.references import resolve_reference
from paramweave.nodes.registry import NodeSpec, PortSpec, registry


def _positive(value, name: str) -> float:
    v = float(value)
    if v <= 0:
        raise ValueError(f"{name} must be > 0")
    return v


def eval_box(_doc, node, _inputs):
    p = node.params
    return {
        "shape": Part.makeBox(
            _positive(p.get("length", 10.0), "length"),
            _positive(p.get("width", 10.0), "width"),
            _positive(p.get("height", 10.0), "height"),
        )
    }


def eval_cylinder(_doc, node, _inputs):
    p = node.params
    return {
        "shape": Part.makeCylinder(
            _positive(p.get("radius", 5.0), "radius"),
            _positive(p.get("height", 10.0), "height"),
        )
    }


def _require(inputs, name: str):
    if name not in inputs:
        raise ValueError(f"Required input is not connected: {name}")
    return inputs[name]


def eval_translate(_doc, node, inputs):
    shape = _require(inputs, "shape").copy()
    p = node.params
    shape.translate(App.Vector(float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.0))))
    return {"shape": shape}


def eval_cut(_doc, _node, inputs):
    return {"shape": _require(inputs, "base").cut(_require(inputs, "tool"))}


def eval_fuse(_doc, _node, inputs):
    return {"shape": _require(inputs, "a").fuse(_require(inputs, "b"))}


def eval_reference(doc, node, _inputs):
    ref = dict(node.params.get("reference", {}))
    if not ref:
        raise ValueError("Reference node has no captured reference")
    obj, resolved_sub, shape = resolve_reference(doc, ref, allow_recovery=True)
    return {
        "shape": shape,
        "object": obj,
        "resolved_subelement": resolved_sub,
    }


def eval_measure(_doc, _node, inputs):
    shape = _require(inputs, "shape")
    out = {"shape_type": str(getattr(shape, "ShapeType", "Unknown"))}
    for attr, name in (("Length", "length"), ("Area", "area"), ("Volume", "volume")):
        try:
            out[name] = float(getattr(shape, attr))
        except Exception:
            out[name] = 0.0
    return out


def register_core_nodes() -> None:
    if registry.all():
        return
    registry.register(
        NodeSpec(
            "reference.geometry",
            "Geometry Reference",
            "Reference",
            outputs=[PortSpec("shape", "CAD.Shape"), PortSpec("object", "Any")],
            default_params={"reference": {}},
            evaluate=eval_reference,
        )
    )
    registry.register(
        NodeSpec(
            "primitive.box",
            "Box",
            "Construct",
            outputs=[PortSpec("shape", "CAD.Solid")],
            default_params={"length": 10.0, "width": 10.0, "height": 10.0},
            evaluate=eval_box,
        )
    )
    registry.register(
        NodeSpec(
            "primitive.cylinder",
            "Cylinder",
            "Construct",
            outputs=[PortSpec("shape", "CAD.Solid")],
            default_params={"radius": 5.0, "height": 10.0},
            evaluate=eval_cylinder,
        )
    )
    registry.register(
        NodeSpec(
            "transform.translate",
            "Translate",
            "Transform",
            inputs=[PortSpec("shape", "CAD.Shape")],
            outputs=[PortSpec("shape", "CAD.Shape")],
            default_params={"x": 0.0, "y": 0.0, "z": 0.0},
            evaluate=eval_translate,
        )
    )
    registry.register(
        NodeSpec(
            "boolean.cut",
            "Cut",
            "Boolean",
            inputs=[PortSpec("base", "CAD.Shape"), PortSpec("tool", "CAD.Shape")],
            outputs=[PortSpec("shape", "CAD.Shape")],
            evaluate=eval_cut,
        )
    )
    registry.register(
        NodeSpec(
            "boolean.fuse",
            "Fuse",
            "Boolean",
            inputs=[PortSpec("a", "CAD.Shape"), PortSpec("b", "CAD.Shape")],
            outputs=[PortSpec("shape", "CAD.Shape")],
            evaluate=eval_fuse,
        )
    )
    registry.register(
        NodeSpec(
            "measure.shape",
            "Measure Shape",
            "Measure",
            inputs=[PortSpec("shape", "CAD.Shape")],
            outputs=[
                PortSpec("length", "Number"),
                PortSpec("area", "Number"),
                PortSpec("volume", "Number"),
                PortSpec("shape_type", "Any"),
            ],
            evaluate=eval_measure,
        )
    )


register_core_nodes()
