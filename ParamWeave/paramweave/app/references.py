"""Capture and resolve FreeCAD object/sub-element references.

Resolution (``resolve_reference``) only needs the FreeCAD application layer so
it works in console mode. Capturing from and pushing to the GUI selection
imports FreeCADGui lazily.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Tuple

import FreeCAD as App

# Geometric recovery accepts a candidate only if its signature score is at or
# below this value and no other candidate is also within it.
RECOVERY_TOLERANCE = 1e-5


def _vec(v) -> list:
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
    import FreeCADGui as Gui

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

    # Conservative starter policy. Production code should use FreeCAD's
    # topology-naming facilities and expose ambiguous repairs to the user.
    matches = [c for c in candidates if c[0] <= RECOVERY_TOLERANCE]
    if not matches:
        raise LookupError(f"Referenced sub-element no longer exists and could not be recovered: {obj.Name}.{sub}")
    if len(matches) > 1:
        names = ", ".join(name for _, name, _ in matches)
        raise LookupError(f"Ambiguous reference {obj.Name}.{sub}: {len(matches)} equally good candidates ({names}); repair manually")
    _, recovered_name, recovered_shape = matches[0]
    return obj, recovered_name, recovered_shape


def selection_target(doc_name: str, obj_name: str, sub_name: str) -> Tuple[str, str]:
    """Map a selection-observer callback to ``(object_name, element_name)``.

    Observers usually receive already-resolved names, but a full subname path
    such as ``Container`` + ``NestedCyl.Face1`` is resolved to the leaf object
    here so it compares equal to captured references.
    """
    sub = sub_name or ""
    if "." not in sub:
        return obj_name, sub
    try:
        obj = App.getDocument(doc_name).getObject(obj_name)
        leaf, _mapped, element = obj.resolveSubElement(sub)
        if leaf is not None:
            return leaf.Name, (element or "").lstrip("?")
    except Exception:
        pass
    return obj_name, sub


def select_reference(document, ref: Dict[str, Any], clear: bool = True) -> None:
    import FreeCADGui as Gui

    obj, sub, _ = resolve_reference(document, ref, allow_recovery=False)
    if clear:
        Gui.Selection.clearSelection()
    if sub:
        Gui.Selection.addSelection(obj, sub)
    else:
        Gui.Selection.addSelection(obj)
