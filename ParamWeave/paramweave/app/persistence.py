"""Embedded graph persistence inside a FreeCAD document."""

from __future__ import annotations

import FreeCAD as App

from paramweave.constants import SCHEMA_VERSION, STORE_OBJECT_NAME
from paramweave.app.model import GraphModel, GraphValidationError


class GraphStore:
    def __init__(self, document):
        self.document = document

    def _object(self, create: bool = True):
        obj = self.document.getObject(STORE_OBJECT_NAME)
        if obj is None and create:
            obj = self.document.addObject("App::FeaturePython", STORE_OBJECT_NAME)
            obj.Label = "ParamWeave Graph Data"
            if "GraphJSON" not in obj.PropertiesList:
                obj.addProperty("App::PropertyString", "GraphJSON", "ParamWeave", "Serialized graph JSON")
            if "SchemaVersion" not in obj.PropertiesList:
                obj.addProperty("App::PropertyInteger", "SchemaVersion", "ParamWeave", "Graph schema version")
            obj.SchemaVersion = SCHEMA_VERSION
            obj.GraphJSON = GraphModel().to_json()
        return obj

    def load(self) -> GraphModel:
        obj = self._object(create=True)
        try:
            return GraphModel.from_json(obj.GraphJSON or "")
        except Exception as exc:
            App.Console.PrintError(f"ParamWeave: could not load embedded graph: {exc}\n")
            # Preserve bad data in the document; do not overwrite it automatically.
            raise

    def save(self, model: GraphModel) -> None:
        obj = self._object(create=True)
        obj.SchemaVersion = SCHEMA_VERSION
        obj.GraphJSON = model.to_json()


def active_store(create_document: bool = False) -> GraphStore:
    doc = App.ActiveDocument
    if doc is None and create_document:
        doc = App.newDocument("ParamWeave")
    if doc is None:
        raise RuntimeError("ParamWeave requires an active FreeCAD document")
    return GraphStore(doc)
