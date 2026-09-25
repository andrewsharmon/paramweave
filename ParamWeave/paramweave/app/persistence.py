"""Embedded graph persistence inside a FreeCAD document."""

from __future__ import annotations

from contextlib import contextmanager

import FreeCAD as App

from paramweave.constants import STORE_OBJECT_NAME
from paramweave.app.model import SCHEMA_VERSION, GraphModel

# Output: changing the JSON does not touch/recompute the owner object.
# NoRecompute: never schedule a recompute for this property.
_STORE_PROPERTY_STATUS = ["Output", "NoRecompute"]
_READ_ONLY = 1


@contextmanager
def transaction(document, name: str):
    """Group document changes into one undoable step.

    If another transaction is already active (e.g. a caller grouped several
    operations), the changes join it instead of opening a nested one.
    """
    own = App.getActiveTransaction() is None and not document.HasPendingTransaction
    if own:
        document.openTransaction(name)
    try:
        yield
    except Exception:
        if own:
            document.abortTransaction()
        raise
    else:
        if own:
            document.commitTransaction()


class GraphStore:
    """Reads/writes the graph JSON held by one document's ParamWeaveGraph object."""

    def __init__(self, document):
        self.document = document

    @property
    def document_name(self) -> str:
        return self.document.Name

    def object(self):
        return self.document.getObject(STORE_OBJECT_NAME)

    def _create_object(self):
        obj = self.document.addObject("App::FeaturePython", STORE_OBJECT_NAME)
        obj.Label = "ParamWeave Graph Data"
        return obj

    @staticmethod
    def _ensure_properties(obj):
        # Also repairs store objects written by older versions or by hand.
        for prop, kind, doc in (
            ("GraphJSON", "App::PropertyString", "Serialized graph JSON (managed by ParamWeave)"),
            ("SchemaVersion", "App::PropertyInteger", "Graph schema version"),
        ):
            if prop not in obj.PropertiesList:
                obj.addProperty(kind, prop, "ParamWeave", doc)
                obj.setPropertyStatus(prop, _STORE_PROPERTY_STATUS)
                obj.setEditorMode(prop, _READ_ONLY)

    def load(self) -> GraphModel:
        """Return the stored graph, or an empty graph if the document has none.

        Never creates the store object: viewing a document must not modify it.
        Raises GraphValidationError if the embedded data is malformed; callers
        must then avoid overwriting it.
        """
        obj = self.object()
        if obj is None:
            return GraphModel()
        return GraphModel.from_json(getattr(obj, "GraphJSON", "") or "")

    def save(self, model: GraphModel) -> None:
        obj = self.object()
        text = model.to_json()
        if obj is None:
            if not model.nodes:
                return  # nothing worth creating a store object for
            obj = self._create_object()
        self._ensure_properties(obj)
        if obj.GraphJSON != text:
            obj.GraphJSON = text
        if obj.SchemaVersion != SCHEMA_VERSION:
            obj.SchemaVersion = SCHEMA_VERSION
