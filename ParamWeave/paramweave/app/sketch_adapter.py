"""Convert between ParamWeave sketch values and Sketcher::SketchObject."""

from __future__ import annotations

import math

import FreeCAD as App
import Part

from paramweave.app import sketch_model as sm

GEO_UNDEF = -2000  # Sketcher's "no element" index
PLANES = {
    "XY": App.Rotation(),
    "XZ": App.Rotation(App.Vector(1, 0, 0), 90),
    "YZ": App.Rotation(0.5, 0.5, 0.5, 0.5),
}


def plane_placement(plane: str, offset: float = 0.0) -> "App.Placement":
    key = str(plane).strip().upper()
    if key not in PLANES:
        raise ValueError(f"plane must be one of {', '.join(PLANES)}, got {plane!r}")
    rot = PLANES[key]
    return App.Placement(rot.multVec(App.Vector(0, 0, float(offset))), rot)


def _v(xy) -> "App.Vector":
    return App.Vector(float(xy[0]), float(xy[1]), 0.0)


def _part_geometry(el):
    kind = el["type"]
    if kind == "line":
        return Part.LineSegment(_v(el["start"]), _v(el["end"]))
    if kind == "circle":
        return Part.Circle(_v(el["center"]), App.Vector(0, 0, 1), float(el["radius"]))
    if kind == "arc":
        start = float(el["start_angle"])
        sweep = (float(el["end_angle"]) - start) % 360.0
        circle = Part.Circle(_v(el["center"]), App.Vector(0, 0, 1), float(el["radius"]))
        return Part.ArcOfCircle(circle, math.radians(start), math.radians(start + sweep))
    if kind == "point":
        return Part.Point(_v(el["at"]))
    raise ValueError(f"unsupported sketch element {kind!r}")


def _sketcher_constraint(con):
    import Sketcher

    args = [v for ref in con["refs"] for v in ref]
    if con["type"] in sm.DIMENSIONAL_TYPES:
        value = float(con["value"])
        args.append(math.radians(value) if con["type"] == "Angle" else value)
    return Sketcher.Constraint(con["type"], *args)


def write_sketch(sketch, geometry, placement=None) -> str:
    """Replace the sketch's geometry/constraints; return a warning ('' if solved cleanly)."""
    sm.validate(geometry)
    if placement is not None and not sketch.Placement.isSame(placement, 1e-12):
        sketch.Placement = placement
    sketch.deleteAllGeometry()
    if sketch.ConstraintCount:
        sketch.Constraints = []
    for el in geometry["elements"]:
        sketch.addGeometry(_part_geometry(el), bool(el.get("construction", False)))
    for con in geometry["constraints"]:
        try:
            index = sketch.addConstraint(_sketcher_constraint(con))
        except Exception as exc:
            raise ValueError(f"cannot add {con['type']} constraint {con['refs']}: {exc}") from exc
        if con.get("name"):
            sketch.renameConstraint(index, str(con["name"]))
        if con.get("driving") is False:
            sketch.setDriving(index, False)
    status = sketch.solve()
    sketch.recompute()
    problems = []
    if status != 0:
        problems.append(f"solver failed (code {status})")
    for attr, what in (("Conflicting", "conflicting"), ("Redundant", "redundant"), ("MalformedConstraints", "malformed")):
        found = list(getattr(sketch, attr, []) or [])
        if found:
            problems.append(f"{what} constraints {found}")
    return "sketch: " + "; ".join(problems) if problems else ""


def _angle(center, p) -> float:
    return math.degrees(math.atan2(p.y - center.y, p.x - center.x))


def read_sketch(sketch):
    """Describe a document sketch as a ParamWeave sketch value.

    Anything that cannot be represented faithfully (splines, ellipses,
    external geometry, unknown constraint kinds) raises instead of being
    dropped silently.
    """
    if getattr(sketch, "TypeId", "") != "Sketcher::SketchObject":
        raise ValueError(f"{getattr(sketch, 'Label', sketch)!r} is not a sketch")
    elements = []
    for i, geo in enumerate(sketch.Geometry):
        construction = bool(sketch.getConstruction(i)) if hasattr(sketch, "getConstruction") else False
        kind = type(geo).__name__
        if kind == "LineSegment":
            el = {"type": "line", "start": [geo.StartPoint.x, geo.StartPoint.y], "end": [geo.EndPoint.x, geo.EndPoint.y]}
        elif kind == "Circle":
            el = {"type": "circle", "center": [geo.Center.x, geo.Center.y], "radius": geo.Radius}
        elif kind == "ArcOfCircle":
            a, b = _angle(geo.Center, geo.StartPoint), _angle(geo.Center, geo.EndPoint)
            if geo.Axis.z < 0:
                a, b = b, a
            el = {"type": "arc", "center": [geo.Center.x, geo.Center.y], "radius": geo.Radius, "start_angle": a, "end_angle": b}
        elif kind == "Point":
            el = {"type": "point", "at": [geo.X, geo.Y]}
        else:
            raise ValueError(f"{sketch.Label}: element {i} is a {kind}, which ParamWeave sketches do not support yet")
        if el["type"] != "point":
            el["construction"] = construction
        elements.append(el)

    constraints = []
    for i, c in enumerate(sketch.Constraints):
        if c.Type not in sm.CONSTRAINT_TYPES:
            raise ValueError(f"{sketch.Label}: constraint {i} ({c.Type}) is not supported yet")
        refs = []
        for geo, pos in ((c.First, c.FirstPos), (c.Second, c.SecondPos), (c.Third, c.ThirdPos)):
            if geo == GEO_UNDEF:
                continue
            if geo < -2:
                raise ValueError(f"{sketch.Label}: constraint {i} ({c.Type}) uses external geometry")
            refs.append([geo, int(pos)] if int(pos) else [geo])
        con = {"type": c.Type, "refs": refs}
        if c.Type in sm.DIMENSIONAL_TYPES:
            con["value"] = math.degrees(c.Value) if c.Type == "Angle" else float(c.Value)
        if c.Name:
            con["name"] = c.Name
        if not c.Driving:
            con["driving"] = False
        constraints.append(con)
    return sm.validate({"elements": elements, "constraints": constraints})


def drive_datum(sketch, name: str, value: float) -> bool:
    """Set a named dimensional constraint on a document sketch; True if changed."""
    if getattr(sketch, "TypeId", "") != "Sketcher::SketchObject":
        raise ValueError(f"{getattr(sketch, 'Label', sketch)!r} is not a sketch")
    matches = [i for i, c in enumerate(sketch.Constraints) if c.Name == name]
    if len(matches) != 1:
        names = sorted(c.Name for c in sketch.Constraints if c.Name)
        raise ValueError(
            f"{sketch.Label} has {len(matches) or 'no'} constraint(s) named {name!r}"
            + (f" (named: {', '.join(names)})" if names else "")
        )
    index = matches[0]
    con = sketch.Constraints[index]
    if con.Type not in sm.DIMENSIONAL_TYPES:
        raise ValueError(f"constraint {name!r} is a {con.Type} constraint and has no value")
    internal = math.radians(value) if con.Type == "Angle" else float(value)
    if math.isclose(con.Value, internal, rel_tol=0, abs_tol=1e-12):
        return False
    sketch.setDatum(index, App.Units.Quantity(internal))
    return True


def read_datum(sketch, name: str) -> float:
    """Value of a named dimensional constraint on a document sketch (mm or degrees)."""
    if getattr(sketch, "TypeId", "") != "Sketcher::SketchObject":
        raise ValueError(f"{getattr(sketch, 'Label', sketch)!r} is not a sketch")
    matches = [c for c in sketch.Constraints if c.Name == name]
    if len(matches) != 1:
        names = sorted(c.Name for c in sketch.Constraints if c.Name)
        raise ValueError(
            f"{sketch.Label} has {len(matches) or 'no'} constraint(s) named {name!r}"
            + (f" (named: {', '.join(names)})" if names else "")
        )
    con = matches[0]
    if con.Type not in sm.DIMENSIONAL_TYPES:
        raise ValueError(f"constraint {name!r} is a {con.Type} constraint and has no value")
    return math.degrees(con.Value) if con.Type == "Angle" else float(con.Value)
