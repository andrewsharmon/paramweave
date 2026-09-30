"""ParamWeave dock/workspace controller.

The workspace is the only place that mutates the graph model. Every mutation
runs inside a FreeCAD transaction and is persisted to the bound document's
embedded GraphJSON, so FreeCAD's Undo/Redo covers graph edits; after an
undo/redo the model is reloaded from the document.
"""

from __future__ import annotations

from contextlib import contextmanager
import copy
import os

import FreeCAD as App
import FreeCADGui as Gui

from paramweave.app.evaluator import GraphEvaluator, find_generated, remove_generated
from paramweave.app.model import GraphModel
from paramweave.app.persistence import GraphStore, transaction
from paramweave.app.references import capture_single_selection, resolve_reference, selection_target
from paramweave.constants import DOCK_OBJECT_NAME, REFERENCE_NODE_TYPE
from paramweave.gui.document_sync import DocumentObserver
from paramweave.gui.properties import PropertyPanel
from paramweave.gui.qt import QtCore, QtGui, QtWidgets, dock_area, orientation, qenum
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
        self.view.duplicateRequested.connect(self._guarded(lambda: self.duplicate()))
        self.view.frameRequested.connect(self._guarded(lambda: self.frame_selection()))
        self.view.exportRequested.connect(self._guarded(lambda: self.export_cut_files_dialog()))
        self.view.commentRequested.connect(self._guarded(lambda pos: self.add_comment((pos.x(), pos.y()))))
        self.properties.frameEdited.connect(self._guarded(self.set_frame_field))
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

    def insert_example(self, build, label: str):
        """Add a prebuilt example graph beside the existing nodes and evaluate it."""
        right = max((n.position[0] for n in self.model.nodes.values()), default=-400.0)
        with self.edit(f"Insert example: {label}", create_document=True):
            build(self.model, origin=(right + 400.0, 0.0))
        self.scene.rebuild()
        self.evaluate()
        self.view.frame_all()

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
        """Wire an output to an input, replacing any wire already on that input."""
        replacing = any(e.dst_node == dst_node and e.dst_port == dst_port for e in self.model.edges.values())
        try:
            with self.edit("Reconnect" if replacing else "Connect"):
                edge = self.model.connect(src_node, src_port, dst_node, dst_port, replace=True)
        except (ValueError, KeyError) as exc:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), str(exc))
            return None
        if replacing:
            self.scene.rebuild()
            self.scene.set_statuses(self.statuses)
        else:
            self.scene.add_edge(edge)
        self.properties.refresh()  # a wired parameter becomes read-only
        return edge

    def duplicate(self, node_ids=None):
        """Copy the selected nodes (keeping their input wires) and select the copies."""
        frame_ids = [] if node_ids is not None else self.scene.selected_frame_ids()
        node_ids = [n for n in (node_ids if node_ids is not None else self.scene.selected_node_ids()) if n in self.model.nodes]
        # A selected frame is copied together with everything inside it.
        for frame_id in list(frame_ids):
            nodes, frames = self.model.frame_contents(frame_id)
            node_ids += [n for n in nodes if n not in node_ids]
            frame_ids += [f for f in frames if f not in frame_ids]
        if not node_ids and not frame_ids:
            return {}
        taken = {n.label for n in self.model.nodes.values()} | {f.label for f in self.model.frames.values()}

        def label_for(base):
            i = 2
            while f"{base} {i}" in taken:
                i += 1
            taken.add(f"{base} {i}")
            return f"{base} {i}"

        with self.edit("Duplicate"):
            mapping = self.model.duplicate(node_ids, label_for=label_for, frame_ids=frame_ids)
        self.scene.rebuild()
        self.scene.set_statuses(self.statuses)
        new_frames = [mapping[f] for f in frame_ids]
        if new_frames:
            # Select the copied frame(s) so the next drag moves the whole copy.
            self.scene.clearSelection()
            for frame_id in new_frames:
                self.scene.frame_items[frame_id].setSelected(True)
        else:
            self.scene.set_nodes_selected(list(mapping.values()), True, exclusive=True)
        return mapping

    def move_nodes(self, moved, frames=None):
        frames = frames or {}
        label = "Move frame" if frames and not moved else ("Move node" if len(moved) == 1 else "Move nodes")
        with self.edit(label):
            for node_id, (x, y) in moved.items():
                node = self.model.nodes.get(node_id)
                if node is not None:
                    node.position = [float(x), float(y)]
            for frame_id, rect in frames.items():
                frame = self.model.frames.get(frame_id)
                if frame is not None:
                    frame.rect = [float(v) for v in rect]

    # -- frames -------------------------------------------------------------

    def frame_selection(self, node_ids=None, label="Frame"):
        """Wrap the selected nodes in a new frame (title bar above them)."""
        from paramweave.gui.items import FRAME_HEADER_H

        node_ids = [n for n in (node_ids if node_ids is not None else self.scene.selected_node_ids()) if n in self.scene.node_items]
        if not node_ids:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "Select the nodes to frame first")
            return None
        box = QtCore.QRectF()
        for node_id in node_ids:
            box = box.united(self.scene.node_items[node_id].sceneBoundingRect())
        pad = 20.0
        rect = [box.left() - pad, box.top() - pad - FRAME_HEADER_H, box.width() + 2 * pad, box.height() + 2 * pad + FRAME_HEADER_H]
        with self.edit("Add frame", create_document=True):
            frame = self.model.create_frame(self._unique_frame_label(label), rect)
        self.scene.add_frame(frame)
        return frame

    def add_comment(self, position, text="Double-check this before cutting."):
        with self.edit("Add comment", create_document=True):
            frame = self.model.create_frame(
                self._unique_frame_label("Comment"), [position[0], position[1], 260.0, 110.0], "yellow", text
            )
        self.scene.add_frame(frame)
        return frame

    def _unique_frame_label(self, base):
        labels = {f.label for f in self.model.frames.values()}
        if base not in labels:
            return base
        i = 2
        while f"{base} {i}" in labels:
            i += 1
        return f"{base} {i}"

    def set_frame_field(self, frame_id, key, value):
        frame = self.model.frames.get(frame_id)
        if frame is None or key not in ("label", "color", "note") or getattr(frame, key) == value:
            return
        with self.edit(f"Edit frame {key}"):
            setattr(frame, key, str(value))
        self.scene.refresh_frame(frame_id)

    def delete(self, node_ids, edge_ids=(), frame_ids=()):
        node_ids = [n for n in node_ids if n in self.model.nodes]
        with self.edit("Delete") as doc:
            for frame_id in frame_ids:
                self.model.remove_frame(frame_id)  # the nodes inside stay
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

    # -- cut files ----------------------------------------------------------

    PREFS = "User parameter:BaseApp/Preferences/Mod/ParamWeave"

    def cut_panels(self, only_selected=False):
        """Evaluate, then return [(label, sketch geometry)] for the graph's Sketch nodes.

        With ``only_selected``, only selected Sketch nodes (or Sketch nodes
        inside selected frames) are used. Order is top-to-bottom, left-to-right
        in the graph, so panels keep a predictable order.
        """
        outputs = self.evaluate()
        sketch_ids = [n.id for n in self.model.nodes.values() if n.type_id == "sketch.sketch"]
        if only_selected:
            chosen = set(self.scene.selected_node_ids())
            for frame_id in self.scene.selected_frame_ids():
                chosen.update(self.model.frame_contents(frame_id)[0])
            sketch_ids = [n for n in sketch_ids if n in chosen]
        if not sketch_ids:
            raise ValueError("No Sketch nodes to export" + (" in the selection" if only_selected else " in this graph"))
        failed = [self.model.nodes[n].label for n in sketch_ids if "geometry" not in outputs.get(n, {})]
        if failed:
            raise ValueError("Cannot export; these sketches did not evaluate: " + ", ".join(sorted(failed)))
        sketch_ids.sort(key=lambda n: (self.model.nodes[n].position[1], self.model.nodes[n].position[0]))
        return [(self.model.nodes[n].label, outputs[n]["geometry"]) for n in sketch_ids]

    def export_cut_files(self, path, sheet_width=600.0, gap=5.0, only_selected=False):
        """Write the panels as a DXF or SVG (chosen by ``path``'s extension)."""
        from paramweave.app import cutfile

        panels = self.cut_panels(only_selected)
        text = cutfile.export(panels, os.path.splitext(path)[1], sheet_width, gap)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        self.status_label.setText(f"Exported {len(panels)} panel(s) to {os.path.basename(path)}")
        App.Console.PrintMessage(f"ParamWeave: exported {len(panels)} panel(s) to {path}\n")
        return len(panels)

    def export_cut_files_dialog(self):
        """Ask for layout options and a file name, then export."""
        prefs = App.ParamGet(self.PREFS)
        dialog = QtWidgets.QDialog(self.dock)
        dialog.setWindowTitle("Export Cut Files")
        form = QtWidgets.QFormLayout(dialog)
        width = QtWidgets.QDoubleSpinBox()
        width.setRange(10.0, 10000.0)
        width.setDecimals(1)
        width.setSuffix(" mm")
        width.setValue(prefs.GetFloat("CutSheetWidth", 600.0))
        gap = QtWidgets.QDoubleSpinBox()
        gap.setRange(0.0, 100.0)
        gap.setDecimals(1)
        gap.setSuffix(" mm")
        gap.setValue(prefs.GetFloat("CutGap", 5.0))
        selected = QtWidgets.QCheckBox("Only selected Sketch nodes / frames")
        has_selection = bool(self.scene.selected_node_ids() or self.scene.selected_frame_ids())
        selected.setEnabled(has_selection)
        form.addRow("Sheet width", width)
        form.addRow("Gap between panels", gap)
        form.addRow(selected)
        note = QtWidgets.QLabel(
            "Panels are laid flat in rows. Kerf is taken from each panel's kerf input; "
            "construction lines are not exported."
        )
        note.setWordWrap(True)
        form.addRow(note)
        buttons = QtWidgets.QDialogButtonBox(
            qenum(QtWidgets.QDialogButtonBox, "StandardButton", "Ok") | qenum(QtWidgets.QDialogButtonBox, "StandardButton", "Cancel")
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if not (dialog.exec() if hasattr(dialog, "exec") else dialog.exec_()):
            return None
        prefs.SetFloat("CutSheetWidth", width.value())
        prefs.SetFloat("CutGap", gap.value())
        doc = self.ensure_bound()
        start_dir = prefs.GetString("CutDir", os.path.dirname(doc.FileName) if doc.FileName else os.path.expanduser("~"))
        default = os.path.join(start_dir, f"{doc.Label}-panels.dxf")
        path, chosen = QtWidgets.QFileDialog.getSaveFileName(self.dock, "Export Cut Files", default, "DXF (*.dxf);;SVG (*.svg)")
        if not path:
            return None
        if os.path.splitext(path)[1].lower() not in (".dxf", ".svg"):
            path += ".svg" if chosen.startswith("SVG") else ".dxf"
        prefs.SetString("CutDir", os.path.dirname(path))
        return self.export_cut_files(path, width.value(), gap.value(), selected.isChecked())

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
        frames = self.scene.selected_frame_ids()
        if not node_ids and len(frames) == 1:
            self.properties.set_frame(frames[0])
        else:
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
