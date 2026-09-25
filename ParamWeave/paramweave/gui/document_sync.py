"""Keep the graph workspace bound to the active FreeCAD document.

Callbacks only schedule work: FreeCAD emits several of these signals while a
document is half-created or half-restored, so the workspace rebinds from the
Qt event loop once the document is in a consistent state.
"""

from __future__ import annotations

import FreeCAD as App


class DocumentObserver:
    def __init__(self, workspace):
        self.workspace = workspace

    def _safe(self, fn, *args):
        try:
            fn(*args)
        except Exception as exc:  # observers must never raise into FreeCAD
            App.Console.PrintWarning(f"ParamWeave: document sync failed: {exc}\n")

    def slotActivateDocument(self, _doc):
        self._safe(self.workspace.schedule_rebind)

    def slotCreatedDocument(self, _doc):
        self._safe(self.workspace.schedule_rebind)

    def slotFinishRestoreDocument(self, _doc):
        self._safe(self.workspace.schedule_rebind)

    def slotDeletedDocument(self, doc):
        self._safe(self.workspace.on_document_deleted, doc.Name)

    def slotRelabelDocument(self, _doc):
        self._safe(self.workspace.update_status_label)

    def slotUndoDocument(self, doc):
        self._safe(self.workspace.schedule_reload, doc.Name)

    def slotRedoDocument(self, doc):
        self._safe(self.workspace.schedule_reload, doc.Name)
