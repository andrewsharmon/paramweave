"""Capture and resolve FreeCAD object/sub-element references."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, Optional, Tuple

import FreeCAD as App
import FreeCADGui as Gui


def _vec(v) -> list[float]:
    return [float(v.x), float(v.y), float(v.z)]


def shape_signature(shape) -> Dict[str, Any]:
    sig: Dict[str, Any] = {"shape_type": str(getattr(shape, "ShapeType", "Unknown"))}
    for attr, key in (("Area", "area"), ("Length", "length"), ("Volume", "volume")):
        try:
            sig[key] = float(getattr(shape, attr))
        except Exception:
            pass
    try:
        sig["center"] = _vec(shape.CenterOfMass)
    except Exception:
        pass
    try:
        bb = shape.BoundBox
        sig["bbox"] = [float(bb.XMin), float(bb.YMin), float(bb.ZMin), float(bb.XMax), float(bb.YMax), float(bb.ZMax)]
    except Exception:
        pass
    return sig


def capture_single_selection() -> Dict[str, Any]:
    selections = Gui.Selection.getSelectionEx()
    if len(selections) != 1:
        raise ValueError("Select exactly one FreeCAD object or sub-element")
    sel = selections[0]
    obj = sel.Object
    subname = sel.SubElementNames[0] if sel.SubElementNames else ""
    if len(sel.SubElementNames) > 1:
        raise ValueError("Starter currently supports one selected sub-element at a time")
    shape = sel.SubObjects[0] if sel.SubObjects else getattr(obj, "Shape", None)
    if shape is None:
        raise ValueError("Selected object does not expose a Part shape")
    return {
        "document_label": getattr(obj.Document, "Label", ""),
        "object_name": obj.Name,
        "object_label": obj.Label,
        "subelement": subname,
        "signature": shape_signature(shape),
    }


def _candidate_shapes(obj, shape_type: str):
    shape = getattr(obj, "Shape", None)
    if shape is None:
        return []
    if shape_type == "Face":
        return [(f"Face{i}", s) for i, s in enumerate(shape.Faces, 1)]
    if shape_type == "Edge":
        return [(f"Edge{i}", s) for i, s in enumerate(shape.Edges, 1)]
    if shape_type == "Vertex":
        return [(f"Vertex{i}", s) for i, s in enumerate(shape.Vertexes, 1)]
    return []


def _relative_error(a: float, b: float, floor: float = 1e-9) -> float:
    return abs(a - b) / max(abs(a), abs(b), floor)


def signature_score(reference: Dict[str, Any], candidate: Dict[str, Any]) -> float:
    if reference.get("shape_type") != candidate.get("shape_type"):
        return float("inf")
    score = 0.0
    weight = 0.0
    for key in ("area", "length", "volume"):
        if key in reference and key in candidate:
            score += 4.0 * _relative_error(float(reference[key]), float(candidate[key]))
            weight += 4.0
    if "center" in reference and "center" in candidate:
        ra = reference["center"]
        ca = candidate["center"]
        dist = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(ra, ca)))
        scale = 1.0
        if "bbox" in reference:
            b = reference["bbox"]
            scale = max(math.dist(b[:3], b[3:]), 1e-9)
        score += 2.0 * dist / scale
        weight += 2.0
    return score / weight if weight else float("inf")


def resolve_reference(document, ref: Dict[str, Any], allow_recovery: bool = True):
    obj = document.getObject(str(ref.get("object_name", "")))
    if obj is None:
        raise LookupError(f"Referenced object no longer exists: {ref.get('object_name')}")

    sub = str(ref.get("subelement", "") or "")
    if not sub:
        shape = getattr(obj, "Shape", None)
        if shape is None:
            raise LookupError(f"Referenced object has no Shape: {obj.Name}")
        return obj, "", shape

    try:
        shape = obj.getSubObject(sub)
        if shape is not None and not shape.isNull():
            return obj, sub, shape
    except Exception:
        pass

    if not allow_recovery:
        raise LookupError(f"Referenced sub-element no longer resolves: {obj.Name}.{sub}")

    sig = dict(ref.get("signature", {}))
    candidates = []
    for name, shape in _candidate_shapes(obj, sig.get("shape_type", "")):
        score = signature_score(sig, shape_signature(shape))
        if math.isfinite(score):
            candidates.append((score, name, shape))
    candidates.sort(key=lambda item: item[0])

    # Conservative starter threshold. Production code should use FreeCAD's
    # topology-naming facilities and expose ambiguous repairs to the user.
    if not candidates or candidates[0][0] > 1e-5:
        raise LookupError(f"Could not recover reference: {obj.Name}.{sub}")
    if len(candidates) > 1 and abs(candidates[1][0] - candidates[0][0]) < 1e-8:
        raise LookupError(f"Ambiguous recovered reference: {obj.Name}.{sub}")
    _, recovered_name, recovered_shape = candidates[0]
    return obj, recovered_name, recovered_shape


def select_reference(document, ref: Dict[str, Any]) -> None:
    obj, sub, _ = resolve_reference(document, ref, allow_recovery=False)
    Gui.Selection.clearSelection()
    if sub:
        Gui.Selection.addSelection(obj, sub)
    else:
        Gui.Selection.addSelection(obj)
