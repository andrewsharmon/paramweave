"""Sketch nodes: build sketch elements, modify them, and emit Sketcher sketches.

Element and modifier nodes pass plain ``Sketch.Geometry`` values (see
``paramweave.app.sketch_model``). Only the Sketch node creates a document
object: an ordinary ``Sketcher::SketchObject`` the user can open and inspect.
"""

from __future__ import annotations

import FreeCAD as App
import Part

from paramweave.app import sketch_adapter as sa
from paramweave.app import sketch_model as sm
from paramweave.nodes.core import _number, _positive, _require
from paramweave.nodes.registry import NodeSpec, PortSpec, registry

GEOMETRY = "Sketch.Geometry"


def _construction(node) -> bool:
    return bool(node.params.get("construction", False))


def _n(node, key, default=0.0):
    return _number(node.params.get(key, default), key)


def eval_line(_doc, node, _inputs):
    return {"geometry": sm.line(_n(node, "x1"), _n(node, "y1"), _n(node, "x2", 10.0), _n(node, "y2"), _construction(node))}


def eval_circle(_doc, node, _inputs):
    p = node.params
    return {
        "geometry": sm.circle(_n(node, "cx"), _n(node, "cy"), _positive(p.get("radius", 5.0), "radius"), _construction(node))
    }


def eval_arc(_doc, node, _inputs):
    p = node.params
    return {
        "geometry": sm.arc(
            _n(node, "cx"),
            _n(node, "cy"),
            _positive(p.get("radius", 5.0), "radius"),
            _n(node, "start_angle"),
            _n(node, "end_angle", 90.0),
            _construction(node),
        )
    }


def eval_point(_doc, node, _inputs):
    return {"geometry": sm.point(_n(node, "x"), _n(node, "y"))}


def eval_rectangle(_doc, node, _inputs):
    p = node.params
    return {
        "geometry": sm.rectangle(
            _n(node, "x"),
            _n(node, "y"),
            _positive(p.get("width", 20.0), "width"),
            _positive(p.get("height", 10.0), "height"),
            _construction(node),
        )
    }


def eval_polygon(_doc, node, _inputs):
    p = node.params
    return {
        "geometry": sm.regular_polygon(
            _n(node, "cx"),
            _n(node, "cy"),
            _positive(p.get("radius", 10.0), "radius"),
            p.get("sides", 6),
            _n(node, "rotation"),
            _construction(node),
        )
    }


def eval_finger_panel(_doc, node, _inputs):
    p = node.params
    sides = []
    for side in sm.PANEL_SIDES:
        mode = str(p.get(f"mode_{side}", "flat")).strip()
        sides.append((mode, p.get(f"fingers_{side}", 1)))
    return {
        "geometry": sm.finger_panel(
            _positive(p.get("width", 100.0), "width"),
            _positive(p.get("height", 60.0), "height"),
            _positive(p.get("thickness", 3.0), "thickness"),
            sides,
        )
    }


def eval_combine(_doc, _node, inputs):
    return {"geometry": sm.combine(inputs.get(k) for k in ("a", "b", "c", "d"))}


def eval_translate(_doc, node, inputs):
    geo = _require(inputs, "geometry")
    return {"geometry": sm.translate(geo, _n(node, "dx"), _n(node, "dy"), node.params.get("elements", ""))}


def eval_rotate(_doc, node, inputs):
    geo = _require(inputs, "geometry")
    return {
        "geometry": sm.rotate(
            geo, _n(node, "angle"), _n(node, "cx"), _n(node, "cy"), node.params.get("elements", "")
        )
    }


def eval_remove(_doc, node, inputs):
    return {"geometry": sm.remove_elements(_require(inputs, "geometry"), node.params.get("elements", ""))}


def eval_construction(_doc, node, inputs):
    geo = _require(inputs, "geometry")
    return {"geometry": sm.set_construction(geo, node.params.get("elements", ""), _construction(node))}


def eval_add_constraint(_doc, node, inputs):
    p = node.params
    con = {"type": str(p.get("constraint", "")).strip(), "refs": sm.parse_refs(p.get("refs", ""))}
    if con["type"] not in sm.CONSTRAINT_TYPES:
        raise ValueError(f"constraint must be one of: {', '.join(sm.CONSTRAINT_TYPES)}")
    if con["type"] in sm.DIMENSIONAL_TYPES:
        con["value"] = _number(p.get("value", 0.0), "value")
    name = str(p.get("name", "")).strip()
    if name:
        con["name"] = name
    return {"geometry": sm.add_constraint(_require(inputs, "geometry"), con)}


def eval_set_constraint(_doc, node, inputs):
    p = node.params
    value = _number(p.get("value", 0.0), "value")
    return {"geometry": sm.set_constraint_value(_require(inputs, "geometry"), str(p.get("name", "")).strip(), value)}


def eval_dimension(_doc, node, inputs):
    name = str(node.params.get("name", "")).strip()
    if ("geometry" in inputs) == ("object" in inputs):
        raise ValueError("connect exactly one of 'geometry' (graph sketch) or 'object' (document sketch)")
    if "geometry" in inputs:
        return {"value": sm.constraint_value(inputs["geometry"], name)}
    return {"value": sa.read_datum(_sketch_object(inputs), name)}


def eval_measure_element(_doc, node, inputs):
    p = node.params
    return {
        "value": sm.element_quantity(
            _require(inputs, "geometry"), p.get("element", 0), str(p.get("quantity", "length")).strip()
        )
    }


def _sketch_object(inputs):
    obj = _require(inputs, "object")
    if getattr(obj, "TypeId", "") != "Sketcher::SketchObject":
        raise ValueError(f"'{getattr(obj, 'Label', obj)}' is not a Sketcher sketch; reference the whole sketch object")
    return obj


def eval_read_sketch(_doc, _node, inputs):
    obj = _sketch_object(inputs)
    return {"geometry": sa.read_sketch(obj), "placement": App.Placement(obj.Placement)}


def eval_drive_constraint(_doc, node, inputs):
    obj = _sketch_object(inputs)
    p = node.params
    value = _number(p.get("value", 0.0), "value")
    if sa.drive_datum(obj, str(p.get("name", "")).strip(), value):
        obj.recompute()
    return {"object": obj, "shape": obj.Shape}


def eval_sketch(_doc, node, inputs):
    geo = sm.validate(_require(inputs, "geometry"))
    if "placement" in inputs:
        placement = inputs["placement"]
        if not isinstance(placement, App.Placement):
            raise ValueError("placement input must be a FreeCAD Placement")
    else:
        placement = sa.plane_placement(node.params.get("plane", "XY"), _n(node, "offset"))
    return {"geometry": geo, "placement": placement}


def materialize_sketch(sketch, values):
    warning = sa.write_sketch(sketch, values["geometry"], values["placement"])
    out = {"shape": sketch.Shape.copy(), "object": sketch}
    if warning:
        out["_warning"] = warning
    return out


def eval_extrude(_doc, node, inputs):
    shape = _require(inputs, "shape")
    length = _positive(node.params.get("length", 10.0), "length")
    wires = [w for w in shape.Wires if w.isClosed()]
    if not wires:
        raise ValueError("extrude needs at least one closed wire")
    face = Part.makeFace(wires, "Part::FaceMakerBullseye")
    normal = face.Faces[0].normalAt(0, 0)
    # A face's normal follows its wire winding. Sketch shapes carry the sketch
    # placement, so extrude along the sketch's +Z (the plane normal) instead.
    plane_z = shape.Placement.Rotation.multVec(App.Vector(0, 0, 1))
    if normal.dot(plane_z) < 0:
        normal = normal * -1
    if node.params.get("reversed", False):
        normal = normal * -1
    return {"shape": face.extrude(normal * length)}


def _geometry_modifier(type_id, title, evaluate, params, extra_inputs=()):
    return NodeSpec(
        type_id,
        title,
        "Sketch",
        inputs=[PortSpec("geometry", GEOMETRY), *extra_inputs],
        outputs=[PortSpec("geometry", GEOMETRY)],
        default_params=params,
        evaluate=evaluate,
    )


def _element(type_id, title, evaluate, params):
    return NodeSpec(
        type_id,
        title,
        "Sketch Elements",
        outputs=[PortSpec("geometry", GEOMETRY)],
        default_params=params,
        evaluate=evaluate,
    )


def register_sketch_nodes() -> None:
    if registry.find("sketch.sketch") is not None:
        return
    for spec in (
        _element("sketch.line", "Line", eval_line, {"x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 0.0, "construction": False}),
        _element("sketch.circle", "Circle", eval_circle, {"cx": 0.0, "cy": 0.0, "radius": 5.0, "construction": False}),
        _element(
            "sketch.arc",
            "Arc",
            eval_arc,
            {"cx": 0.0, "cy": 0.0, "radius": 5.0, "start_angle": 0.0, "end_angle": 90.0, "construction": False},
        ),
        _element("sketch.point", "Point", eval_point, {"x": 0.0, "y": 0.0}),
        _element(
            "sketch.rectangle",
            "Rectangle",
            eval_rectangle,
            {"x": 0.0, "y": 0.0, "width": 20.0, "height": 10.0, "construction": False},
        ),
        _element(
            "sketch.polygon",
            "Regular Polygon",
            eval_polygon,
            {"cx": 0.0, "cy": 0.0, "radius": 10.0, "sides": 6, "rotation": 0.0, "construction": False},
        ),
        _element(
            "sketch.finger_panel",
            "Finger Joint Panel",
            eval_finger_panel,
            {
                "width": 100.0,
                "height": 60.0,
                "thickness": 3.0,
                **{f"fingers_{side}": 5 for side in sm.PANEL_SIDES},
                **{f"mode_{side}": "out" for side in sm.PANEL_SIDES},
            },
        ),
        NodeSpec(
            "sketch.combine",
            "Combine Elements",
            "Sketch",
            inputs=[
                PortSpec("a", GEOMETRY),
                PortSpec("b", GEOMETRY, required=False),
                PortSpec("c", GEOMETRY, required=False),
                PortSpec("d", GEOMETRY, required=False),
            ],
            outputs=[PortSpec("geometry", GEOMETRY)],
            evaluate=eval_combine,
        ),
        _geometry_modifier("sketch.translate", "Move Elements", eval_translate, {"dx": 0.0, "dy": 0.0, "elements": ""}),
        _geometry_modifier(
            "sketch.rotate", "Rotate Elements", eval_rotate, {"angle": 90.0, "cx": 0.0, "cy": 0.0, "elements": ""}
        ),
        _geometry_modifier("sketch.remove", "Remove Elements", eval_remove, {"elements": "0"}),
        _geometry_modifier(
            "sketch.construction", "Set Construction", eval_construction, {"elements": "", "construction": True}
        ),
        _geometry_modifier(
            "sketch.add_constraint",
            "Add Constraint",
            eval_add_constraint,
            {"constraint": "Distance", "refs": "0", "value": 10.0, "name": ""},
        ),
        _geometry_modifier(
            "sketch.set_constraint", "Set Constraint Value", eval_set_constraint, {"name": "", "value": 10.0}
        ),
        NodeSpec(
            "sketch.read",
            "Read Sketch",
            "Sketch",
            inputs=[PortSpec("object", "Any")],
            outputs=[PortSpec("geometry", GEOMETRY), PortSpec("placement", "Placement")],
            evaluate=eval_read_sketch,
        ),
        NodeSpec(
            "sketch.dimension",
            "Sketch Dimension",
            "Sketch",
            inputs=[PortSpec("geometry", GEOMETRY, required=False), PortSpec("object", "Any", required=False)],
            outputs=[PortSpec("value", "Number")],
            default_params={"name": ""},
            evaluate=eval_dimension,
        ),
        NodeSpec(
            "sketch.measure_element",
            "Measure Element",
            "Sketch",
            inputs=[PortSpec("geometry", GEOMETRY)],
            outputs=[PortSpec("value", "Number")],
            default_params={"element": 0, "quantity": "length"},
            evaluate=eval_measure_element,
        ),
        NodeSpec(
            "sketch.drive_constraint",
            "Drive Sketch Constraint",
            "Sketch",
            inputs=[PortSpec("object", "Any")],
            outputs=[PortSpec("shape", "CAD.Shape"), PortSpec("object", "Any")],
            default_params={"name": "", "value": 10.0},
            evaluate=eval_drive_constraint,
        ),
        NodeSpec(
            "sketch.sketch",
            "Sketch",
            "Sketch",
            inputs=[PortSpec("geometry", GEOMETRY), PortSpec("placement", "Placement", required=False)],
            outputs=[PortSpec("shape", "CAD.Shape"), PortSpec("object", "Any")],
            default_params={"plane": "XY", "offset": 0.0},
            evaluate=eval_sketch,
            generates_object=True,
            generated_type="Sketcher::SketchObject",
            materialize=materialize_sketch,
        ),
        NodeSpec(
            "sketch.extrude",
            "Extrude",
            "Construct",
            inputs=[PortSpec("shape", "CAD.Shape")],
            outputs=[PortSpec("shape", "CAD.Solid")],
            default_params={"length": 10.0, "reversed": False},
            evaluate=eval_extrude,
            generates_object=True,
        ),
    ):
        registry.register(spec)
