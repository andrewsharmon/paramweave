"""ParamWeave dock/workspace controller.

The workspace is the only place that mutates the graph model. Every mutation
runs inside a FreeCAD transaction and is persisted to the bound document's
embedded GraphJSON, so FreeCAD's Undo/Redo covers graph edits; after an
undo/redo the model is reloaded from the document.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy

import FreeCAD as App
import FreeCADGui as Gui

from paramweave.app.evaluator import GraphEvaluator, find_generated, remove_generated
from paramweave.app.model import GraphModel
from paramweave.app.persistence import GraphStore, transaction
from paramweave.app.references import capture_single_selection, resolve_reference, selection_target
from paramweave.constants import DOCK_OBJECT_NAME, REFERENCE_NODE_TYPE
from paramweave.gui.document_sync import DocumentObserver
from paramweave.gui.properties import PropertyPanel
from paramweave.gui.qt import QtCore, QtGui, QtWidgets, dock_area, orientation
from paramweave.gui.scene import GraphScene
from paramweave.gui.selection_sync import SelectionObserver, nodes_for_selection
from paramweave.gui.view import GraphView
from paramweave.nodes.core import register_core_nodes
from paramweave.nodes.registry import registry


class GraphLoadError(RuntimeError):
    pass


class GraphWorkspace:
    def __init__(self):
        register_core_nodes()
        self.dock = None
        self.scene = GraphScene()
        self.view = GraphView(self.scene)
        self.view.node_menu_entries = [
            (spec.category, spec.title, spec.type_id)
            for spec in sorted(registry.all(), key=lambda s: (s.category, s.title))
            if spec.type_id != REFERENCE_NODE_TYPE
        ]
        self.properties = PropertyPanel()
        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        self.model = GraphModel()
        self.store = None
        self.load_error = ""
        self.statuses = {}  # node_id -> (status, message); runtime only
        self.eval_summary = ""
        self._selection_observer = SelectionObserver(self)
        self._document_observer = DocumentObserver(self)
        self._observers_installed = False
        self._rebind_pending = False
        self._reload_pending = False

        self.scene.nodeSelectionChanged.connect(self._on_graph_selection)
        self.scene.connectRequested.connect(self._guarded(self.connect))
        self.scene.nodesMoved.connect(self._guarded(self.move_nodes))
        self.scene.deleteRequested.connect(self._guarded(self.delete))
        self.view.addNodeRequested.connect(self._guarded(lambda t, pos: self.add_node(t, (pos.x(), pos.y()))))
        self.view.referenceRequested.connect(self._guarded(lambda pos: self.add_reference_from_selection((pos.x(), pos.y()))))
        self.properties.parameterEdited.connect(self._guarded(self.set_param))
        self.properties.labelEdited.connect(self._guarded(self.set_label))

    # -- dock lifecycle ---------------------------------------------------

    def _ensure_dock(self):
        if self.dock is not None:
            return self.dock
        main = Gui.getMainWindow()
        # A dock left behind by a previous (reloaded) workspace instance would
        # duplicate the pane; remove it before creating ours.
        for stale in main.findChildren(QtWidgets.QDockWidget):
            if stale.objectName() == DOCK_OBJECT_NAME:
                main.removeDockWidget(stale)
                stale.deleteLater()
        dock = QtWidgets.QDockWidget("ParamWeave", main)
        dock.setObjectName(DOCK_OBJECT_NAME)
        container = QtWidgets.QWidget(dock)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 0)
        bar.addWidget(self.status_label, 1)
        evaluate = QtWidgets.QPushButton("Evaluate")
        evaluate.setToolTip("Evaluate the graph and update generated FreeCAD objects")
        evaluate.clicked.connect(self._guarded(self.evaluate))
        bar.addWidget(evaluate)
        layout.addLayout(bar)

        splitter = QtWidgets.QSplitter(orientation("Vertical"), container)
        splitter.addWidget(self.view)
        splitter.addWidget(self.properties)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)
        splitter.setCollapsible(0, False)
        # Sizes are applied proportionally: give the graph ~70% of the height.
        splitter.setSizes([700, 300])
        layout.addWidget(splitter)
        dock.setWidget(container)
        main.addDockWidget(dock_area("RightDockWidgetArea"), dock)
        try:
            main.resizeDocks([dock], [int(main.width() * 0.4)], orientation("Horizontal"))
        except Exception:
            pass
        self.dock = dock
        return dock

    def _install_observers(self):
        if self._observers_installed:
            return
        Gui.Selection.addObserver(self._selection_observer)
        App.addDocumentObserver(self._document_observer)
        self._observers_installed = True

    def activate(self):
        self._ensure_dock().show()
        self._install_observers()
        self.bind_active_document()

    def toggle(self):
        dock = self._ensure_dock()
        if dock.isVisible():
            dock.hide()
        else:
            dock.show()
            self._install_observers()
            self.bind_active_document()

    # -- document binding -------------------------------------------------

    @property
    def document(self):
        return None if self.store is None else self.store.document

    @property
    def bound_name(self):
        return None if self.store is None else self.store.document_name

    def bind_active_document(self, force: bool = False):
        doc = App.ActiveDocument
        name = None if doc is None else doc.Name
        if not force and name == self.bound_name and (name is None or self.store is not None):
            return
        self.store = None if doc is None else GraphStore(doc)
        self.statuses = {}
        self.eval_summary = ""
        self._load_model()

    def _load_model(self, keep_statuses: bool = False):
        self.load_error = ""
        model = GraphModel()
        if self.store is not None:
            try:
                model = self.store.load()
            except Exception as exc:
                # Surface bad embedded data and refuse edits so it is never overwritten.
                self.load_error = f"Embedded graph could not be loaded; editing is disabled to preserve it. {exc}"
                App.Console.PrintError(f"ParamWeave: {self.load_error}\n")
        self.model = model
        if keep_statuses:
            self.statuses = {k: v for k, v in self.statuses.items() if k in model.nodes}
        else:
            self.statuses = {}
        self.properties.set_model(self.model)
        self.scene.set_model(self.model)
        self.scene.set_statuses(self.statuses)
        self.update_status_label()

    def schedule_rebind(self):
        if not self._rebind_pending:
            self._rebind_pending = True
            QtCore.QTimer.singleShot(0, self._run_rebind)

    def _run_rebind(self):
        self._rebind_pending = False
        self.bind_active_document()

    def schedule_reload(self, doc_name: str):
        if doc_name != self.bound_name or self._reload_pending:
            return
        self._reload_pending = True
        QtCore.QTimer.singleShot(0, self._run_reload)

    def _run_reload(self):
        self._reload_pending = False
        if self.store is not None:
            self._load_model(keep_statuses=True)

    def on_document_deleted(self, doc_name: str):
        if doc_name == self.bound_name:
            # Drop the binding immediately so nothing is written to a dying document.
            self.store = None
            self._load_model()
        self.schedule_rebind()

    def ensure_bound(self, create_document: bool = False):
        """Bind to the active document now (commands must not wait for the event loop)."""
        if create_document and App.ActiveDocument is None:
            App.newDocument("ParamWeave")
        self.bind_active_document()
        if self.store is None:
            raise RuntimeError("ParamWeave requires an active FreeCAD document")
        if self.load_error:
            raise GraphLoadError(self.load_error)
        return self.document

    def update_status_label(self):
        if self.store is None:
            text = "No document"
        else:
            text = f"{self.document.Label}: {len(self.model.nodes)} nodes, {len(self.model.edges)} wires"
            if self.eval_summary:
                text += f" — {self.eval_summary}"
        if self.load_error:
            text = f"⚠ {self.load_error}"
            self.status_label.setStyleSheet("color: #ff7070;")
        else:
            self.status_label.setStyleSheet("")
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    # -- mutations (all transactional) ------------------------------------

    @contextmanager
    def edit(self, label: str, create_document: bool = False):
        doc = self.ensure_bound(create_document=create_document)
        try:
            with transaction(doc, f"ParamWeave: {label}"):
                yield doc
                self.store.save(self.model)
        except Exception:
            # The transaction was aborted; resynchronize the in-memory model
            # with what the document actually holds.
            self._load_model(keep_statuses=True)
            raise
        self.update_status_label()

    def persist(self, label: str = "Edit graph"):
        with self.edit(label):
            pass

    def _unique_label(self, base: str) -> str:
        labels = {n.label for n in self.model.nodes.values()}
        if base not in labels:
            return base
        i = 2
        while f"{base} {i}" in labels:
            i += 1
        return f"{base} {i}"

    def add_node(self, type_id: str, position=None, params=None, label=None):
        spec = registry.get(type_id)
        with self.edit(f"Add {spec.title}", create_document=True):
            merged = copy.deepcopy(spec.default_params)
            if params:
                merged.update(params)
            pos = position if position is not None else self._suggest_position()
            node = self.model.create_node(type_id, self._unique_label(label or spec.title), pos, merged)
        self.scene.add_node(node)
        return node

    def _suggest_position(self):
        center = self.view.mapToScene(self.view.viewport().rect().center())
        # Offset successive nodes so they do not stack exactly on top of each other.
        offset = 24.0 * (len(self.model.nodes) % 8)
        return (center.x() - 90.0 + offset, center.y() - 40.0 + offset)

    def add_reference_from_selection(self, position=None):
        ref = capture_single_selection()
        sub = ref.get("subelement") or ""
        label = f"{ref.get('object_label') or ref['object_name']}{'.' + sub if sub else ''}"
        return self.add_node(REFERENCE_NODE_TYPE, position=position, params={"reference": ref}, label=label)

    def connect(self, src_node, src_port, dst_node, dst_port):
        try:
            with self.edit("Connect"):
                edge = self.model.connect(src_node, src_port, dst_node, dst_port)
        except (ValueError, KeyError) as exc:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), str(exc))
            return None
        self.scene.add_edge(edge)
        self.properties.refresh()  # a wired parameter becomes read-only
        return edge

    def move_nodes(self, moved):
        with self.edit("Move node" if len(moved) == 1 else "Move nodes"):
            for node_id, (x, y) in moved.items():
                node = self.model.nodes.get(node_id)
                if node is not None:
                    node.position = [float(x), float(y)]

    def delete(self, node_ids, edge_ids=()):
        node_ids = [n for n in node_ids if n in self.model.nodes]
        with self.edit("Delete") as doc:
            for edge_id in edge_ids:
                self.model.remove_edge(edge_id)
            for node_id in node_ids:
                self.model.remove_node(node_id)
            remove_generated(doc, node_ids)
        for node_id in node_ids:
            self.statuses.pop(node_id, None)
        self.scene.rebuild()
        self.scene.set_statuses(self.statuses)
        self.properties.refresh()

    def set_param(self, node_id, key, value):
        node = self.model.nodes.get(node_id)
        if node is None:
            return
        with self.edit(f"Edit {node.label}.{key}"):
            node.params[key] = value
        self.scene.refresh_node(node_id)

    def set_label(self, node_id, label):
        node = self.model.nodes.get(node_id)
        if node is None or not label:
            return
        with self.edit("Rename node") as doc:
            node.label = label
            obj = find_generated(doc, node_id)
            if obj is not None:
                obj.Label = label
        self.scene.refresh_node(node_id)

    # -- evaluation -------------------------------------------------------

    def evaluate(self):
        doc = self.ensure_bound()
        evaluator = GraphEvaluator(doc, self.model)
        with transaction(doc, "ParamWeave: Evaluate"):
            outputs = evaluator.evaluate_all()
        self.statuses = {nid: (r.status, r.message) for nid, r in evaluator.results.items()}
        self.scene.set_statuses(self.statuses)
        counts = {}
        for status, _msg in self.statuses.values():
            counts[status] = counts.get(status, 0) + 1
        problems = [f"{counts[s]} {s}" for s in ("error", "blocked", "warning") if counts.get(s)]
        self.eval_summary = "evaluated: " + (", ".join(problems) if problems else "all ok")
        self.update_status_label()
        return outputs

    # -- selection sync ---------------------------------------------------

    def _selection_targets(self, node_id):
        """FreeCAD (object, subelement) pairs a graph node corresponds to."""
        node = self.model.nodes.get(node_id)
        doc = self.document
        if node is None or doc is None:
            return []
        if node.type_id == REFERENCE_NODE_TYPE:
            ref = node.params.get("reference")
            if not isinstance(ref, dict) or not ref:
                return []
            try:
                obj, sub, _shape = resolve_reference(doc, ref, allow_recovery=False)
            except Exception as exc:
                App.Console.PrintWarning(f"ParamWeave: cannot select reference {node.label}: {exc}\n")
                return []
            return [(obj, sub)]
        obj = find_generated(doc, node_id)
        return [(obj, "")] if obj is not None else []

    def _on_graph_selection(self, node_ids, user_driven):
        self.properties.set_node(node_ids[0] if len(node_ids) == 1 else None)
        if not user_driven or not node_ids:
            return
        targets = [t for nid in node_ids for t in self._selection_targets(nid)]
        if not targets:
            return  # nothing geometric selected: leave FreeCAD's selection alone
        self._selection_observer.suspended = True
        try:
            Gui.Selection.clearSelection()
            for obj, sub in targets:
                if sub:
                    Gui.Selection.addSelection(obj, sub)
                else:
                    Gui.Selection.addSelection(obj)
        finally:
            self._selection_observer.suspended = False

    def resync_selection_from_freecad(self):
        doc = self.document
        if doc is None:
            return
        ids = []
        for sel in Gui.Selection.getSelectionEx(doc.Name, 0):
            for sub in list(sel.SubElementNames) or [""]:
                leaf, element = selection_target(doc.Name, sel.ObjectName, sub)
                ids.extend(nodes_for_selection(self.model, doc, leaf, element))
        self.scene.set_nodes_selected(ids, True, exclusive=True)

    # -- helpers ----------------------------------------------------------

    def _guarded(self, fn):
        """Wrap a Qt slot so errors are reported instead of escaping into Qt."""

        def slot(*args):
            try:
                return fn(*args)
            except Exception as exc:
                App.Console.PrintError(f"ParamWeave: {exc}\n")
                self.status_label.setText(f"⚠ {exc}")
                return None

        return slot


_INSTANCE = None


def workspace() -> GraphWorkspace:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = GraphWorkspace()
    return _INSTANCE
