"""ParamWeave dock/workspace controller."""

from __future__ import annotations

import copy

import FreeCAD as App
import FreeCADGui as Gui

from paramweave.app.evaluator import GraphEvaluator
from paramweave.app.model import GraphModel
from paramweave.app.persistence import GraphStore
from paramweave.app.references import capture_single_selection, select_reference
from paramweave.constants import DOCK_OBJECT_NAME
from paramweave.gui.qt import QtCore, QtWidgets, dock_area, orientation
from paramweave.gui.properties import PropertyPanel
from paramweave.gui.scene import GraphScene
from paramweave.gui.selection_sync import SelectionObserver
from paramweave.gui.view import GraphView
from paramweave.nodes.core import register_core_nodes
from paramweave.nodes.registry import registry


class GraphWorkspace:
    def __init__(self):
        register_core_nodes()
        self.dock = None
        self.scene = GraphScene()
        self.view = GraphView(self.scene)
        self.properties = PropertyPanel()
        self.model = GraphModel()
        self.store = None
        self._selection_observer = SelectionObserver(self)
        self._observer_installed = False
        self.scene.modelChanged.connect(self.persist)
        self.scene.nodeSelectionChanged.connect(self._on_graph_selection)
        self.properties.parameterChanged.connect(self._on_parameter_changed)

    def _ensure_dock(self):
        if self.dock is not None:
            return self.dock
        main = Gui.getMainWindow()
        dock = QtWidgets.QDockWidget("ParamWeave", main)
        dock.setObjectName(DOCK_OBJECT_NAME)
        container = QtWidgets.QWidget(dock)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QtWidgets.QSplitter(orientation("Vertical"), container)
        splitter.addWidget(self.view)
        splitter.addWidget(self.properties)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)
        dock.setWidget(container)
        main.addDockWidget(dock_area("RightDockWidgetArea"), dock)
        try:
            main.resizeDocks([dock], [520], orientation("Horizontal"))
        except Exception:
            pass
        self.dock = dock
        return dock

    def activate(self):
        self._ensure_dock().show()
        self.bind_active_document()
        if not self._observer_installed:
            Gui.Selection.addObserver(self._selection_observer)
            self._observer_installed = True

    def toggle(self):
        dock = self._ensure_dock()
        if dock.isVisible():
            dock.hide()
        else:
            dock.show()
            self.bind_active_document()

    def bind_active_document(self):
        doc = App.ActiveDocument
        if doc is None:
            self.store = None
            self.model = GraphModel()
        else:
            self.store = GraphStore(doc)
            try:
                self.model = self.store.load()
            except Exception:
                # Bad embedded data should be surfaced, not automatically overwritten.
                self.model = GraphModel()
        self.scene.set_model(self.model)
        self.properties.set_model(self.model)

    def persist(self):
        if self.store is None or self.store.document is not App.ActiveDocument:
            if App.ActiveDocument is None:
                return
            self.store = GraphStore(App.ActiveDocument)
        self.store.save(self.model)

    def add_node(self, type_id: str, position=None, params=None):
        if App.ActiveDocument is None:
            App.newDocument("ParamWeave")
            self.bind_active_document()
        spec = registry.get(type_id)
        pos = position or self._suggest_position()
        merged = copy.deepcopy(spec.default_params)
        if params:
            merged.update(params)
        node = self.model.create_node(type_id, spec.title, pos, merged)
        self.scene.add_node(node)
        self.properties.set_node(node.id)
        return node

    def _suggest_position(self):
        center = self.view.mapToScene(self.view.viewport().rect().center())
        return (center.x(), center.y())

    def add_reference_from_selection(self):
        ref = capture_single_selection()
        return self.add_node("reference.geometry", params={"reference": ref})

    def evaluate(self):
        if App.ActiveDocument is None:
            raise RuntimeError("No active FreeCAD document")
        evaluator = GraphEvaluator(App.ActiveDocument, self.model)
        outputs = evaluator.evaluate_all()
        if evaluator.errors:
            message = "\n".join(f"{self.model.nodes[nid].label}: {msg}" for nid, msg in evaluator.errors.items())
            QtWidgets.QMessageBox.warning(Gui.getMainWindow(), "ParamWeave evaluation", message)
        return outputs

    def _on_graph_selection(self, node_id):
        self.properties.set_node(node_id)
        if node_id is None or App.ActiveDocument is None:
            return
        node = self.model.nodes.get(node_id)
        if node is None or node.type_id != "reference.geometry":
            return
        ref = node.params.get("reference", {})
        if not ref:
            return
        try:
            self._selection_observer.suspended = True
            select_reference(App.ActiveDocument, ref)
        except Exception as exc:
            App.Console.PrintWarning(f"ParamWeave: reference selection failed: {exc}\n")
        finally:
            self._selection_observer.suspended = False

    def _on_parameter_changed(self):
        # Rebuild to refresh labels; preserve serialized positions from the model.
        self.persist()
        self.scene.rebuild()


_INSTANCE = None


def workspace() -> GraphWorkspace:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = GraphWorkspace()
    return _INSTANCE
