"""Synchronization between FreeCAD selection and graph nodes.

FreeCAD -> graph: this observer maps each selected object/sub-element to the
reference nodes that point at it and to the node that generated the object.
Graph -> FreeCAD is driven by the workspace, which suspends this observer while
it pushes a selection so the two directions never echo each other.
"""

from __future__ import annotations

import FreeCAD as App

from paramweave.app.references import selection_target
from paramweave.constants import NODE_ID_PROPERTY, REFERENCE_NODE_TYPE


def nodes_for_selection(model, document, obj_name: str, element: str):
    """Graph node ids that correspond to FreeCAD selection ``obj_name.element``."""
    matches = []
    for node in model.nodes.values():
        if node.type_id != REFERENCE_NODE_TYPE:
            continue
        ref = node.params.get("reference")
        if not isinstance(ref, dict):
            continue
        if ref.get("object_name") == obj_name and (ref.get("subelement") or "") == (element or ""):
            matches.append(node.id)
    obj = document.getObject(obj_name) if document is not None else None
    if obj is not None and NODE_ID_PROPERTY in obj.PropertiesList:
        node_id = getattr(obj, NODE_ID_PROPERTY)
        if node_id in model.nodes:
            matches.append(node_id)
    return matches


class SelectionObserver:
    def __init__(self, workspace):
        self.workspace = workspace
        self.suspended = False

    def _targets(self, doc_name, obj_name, sub_name):
        ws = self.workspace
        doc = ws.document
        if doc is None or doc.Name != doc_name:
            return []
        leaf, element = selection_target(doc_name, obj_name, sub_name)
        return nodes_for_selection(ws.model, doc, leaf, element)

    def addSelection(self, doc_name, obj_name, sub_name, _pnt):
        if self.suspended:
            return
        try:
            ids = self._targets(doc_name, obj_name, sub_name)
            if ids:
                self.workspace.scene.set_nodes_selected(ids, True)
        except Exception as exc:  # observers must never raise into FreeCAD
            App.Console.PrintWarning(f"ParamWeave: selection sync failed: {exc}\n")

    def removeSelection(self, doc_name, obj_name, sub_name):
        if self.suspended:
            return
        try:
            ids = self._targets(doc_name, obj_name, sub_name)
            if ids:
                self.workspace.scene.set_nodes_selected(ids, False)
        except Exception as exc:
            App.Console.PrintWarning(f"ParamWeave: selection sync failed: {exc}\n")

    def setSelection(self, doc_name):
        if self.suspended:
            return
        try:
            self.workspace.resync_selection_from_freecad()
        except Exception as exc:
            App.Console.PrintWarning(f"ParamWeave: selection sync failed: {exc}\n")

    def clearSelection(self, _doc_name):
        if self.suspended:
            return
        try:
            self.workspace.scene.set_nodes_selected([], exclusive=True)
        except Exception as exc:
            App.Console.PrintWarning(f"ParamWeave: selection sync failed: {exc}\n")
