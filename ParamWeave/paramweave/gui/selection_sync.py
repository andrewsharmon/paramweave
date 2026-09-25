"""Synchronization between FreeCAD selection and graph reference nodes."""

from __future__ import annotations

import FreeCAD as App
import FreeCADGui as Gui


class SelectionObserver:
    def __init__(self, workspace):
        self.workspace = workspace
        self.suspended = False

    def addSelection(self, doc_name, obj_name, sub_name, _pnt):
        if self.suspended:
            return
        ws = self.workspace
        model = ws.model
        if model is None:
            return
        for node in model.nodes.values():
            if node.type_id != "reference.geometry":
                continue
            ref = node.params.get("reference", {})
            if ref.get("object_name") == obj_name and (ref.get("subelement") or "") == (sub_name or ""):
                ws.scene.select_node(node.id)
                break

    def setSelection(self, _doc_name):
        pass

    def clearSelection(self, _doc_name):
        pass

    def removeSelection(self, _doc_name, _obj_name, _sub_name):
        pass
