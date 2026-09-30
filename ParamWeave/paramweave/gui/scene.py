"""Graph scene that projects GraphModel into QGraphicsItems.

The scene is a view: it never mutates the model. User edits (connect, move,
delete) are emitted as requests which the workspace applies to the model,
persists inside a FreeCAD transaction, and then reflects back here.
"""

from __future__ import annotations

from paramweave.gui.qt import QtCore, QtGui, QtWidgets
from paramweave.gui.items import ConnectionItem, FrameItem, NodeItem, PortItem
from paramweave.nodes.registry import placeholder_spec, registry, types_compatible


class GraphScene(QtWidgets.QGraphicsScene):
    # (selected node ids, user_driven). user_driven is False when the change
    # mirrors FreeCAD's selection or a rebuild, so it must not be echoed back.
    nodeSelectionChanged = QtCore.Signal(object, bool)
    connectRequested = QtCore.Signal(str, str, str, str)
    # ({node_id: (x, y)}, {frame_id: [x, y, w, h]}) after a drag/resize ends
    nodesMoved = QtCore.Signal(object, object)
    deleteRequested = QtCore.Signal(object, object, object)  # node, edge, frame ids

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.node_items = {}
        self.edge_items = {}
        self.frame_items = {}
        self.pending_port = None
        self._statuses = {}
        self._moved = set()
        self._moved_frames = set()
        self._quiet = 0
        self._has_rect = False
        self.selectionChanged.connect(self._emit_node_selection)

    # -- model projection -------------------------------------------------

    def set_model(self, model):
        self.model = model
        self._statuses = {}
        self.rebuild()

    def rebuild(self):
        selected = set(self.selected_node_ids()) | set(self.selected_frame_ids())
        with self.quiet():
            self.clear()
            self._has_rect = False
            self.node_items = {}
            self.edge_items = {}
            self.frame_items = {}
            self.pending_port = None
            self._moved = set()
            self._moved_frames = set()
            if self.model is not None:
                for frame in self.model.frames.values():
                    self._add_frame_item(frame)
                for frame_id in selected & set(self.frame_items):
                    self.frame_items[frame_id].setSelected(True)
                for node in self.model.nodes.values():
                    self._add_node_item(node)
                for edge in self.model.edges.values():
                    self._add_edge_item(edge)
                for node_id in selected & set(self.node_items):
                    self.node_items[node_id].setSelected(True)
            self.grow_scene_rect()
        self.nodeSelectionChanged.emit(self.selected_node_ids(), False)

    def grow_scene_rect(self):
        """Keep a pan margin around all items; grow (never shrink) as nodes are added/moved."""
        padded = self.itemsBoundingRect().adjusted(-400, -400, 400, 400)
        current = self.sceneRect() if self._has_rect else QtCore.QRectF()
        self.setSceneRect(padded if current.isNull() else current.united(padded))
        self._has_rect = True

    def _add_node_item(self, node):
        spec = registry.find(node.type_id) or placeholder_spec(node.id, node.type_id, self.model)
        item = NodeItem(node, spec)
        status = self._statuses.get(node.id)
        if status is not None:
            item.set_status(*status)
        self.addItem(item)
        self.node_items[node.id] = item
        return item

    def _add_frame_item(self, frame):
        item = FrameItem(frame)
        self.addItem(item)
        self.frame_items[frame.id] = item
        return item

    def add_frame(self, frame):
        item = self._add_frame_item(frame)
        self.grow_scene_rect()
        self.clearSelection()
        item.setSelected(True)
        return item

    def refresh_frame(self, frame_id: str):
        item = self.frame_items.get(frame_id)
        if item is not None:
            item.refresh()

    def add_node(self, node):
        item = self._add_node_item(node)
        self.grow_scene_rect()
        self.clearSelection()
        item.setSelected(True)
        return item

    def _add_edge_item(self, edge):
        src_node = self.node_items.get(edge.src_node)
        dst_node = self.node_items.get(edge.dst_node)
        if src_node is None or dst_node is None:
            return None
        src = src_node.port("out", edge.src_port)
        dst = dst_node.port("in", edge.dst_port)
        if src is None or dst is None:
            return None
        item = ConnectionItem(edge.id, src, dst)
        self.addItem(item)
        self.edge_items[edge.id] = item
        return item

    def add_edge(self, edge):
        return self._add_edge_item(edge)

    def refresh_node(self, node_id: str):
        item = self.node_items.get(node_id)
        if item is not None:
            item.refresh()
        for edge_item in self.edge_items.values():
            if node_id in (edge_item.src_port.node_item.node_id, edge_item.dst_port.node_item.node_id):
                edge_item.update_path()

    def set_statuses(self, statuses):
        """statuses: {node_id: (status, message)}; replaces all previous statuses."""
        self._statuses = dict(statuses)
        for node_id, item in self.node_items.items():
            item.set_status(*self._statuses.get(node_id, ("idle", "")))

    def status_of(self, node_id: str):
        item = self.node_items.get(node_id)
        return None if item is None else item.status

    # -- moving -----------------------------------------------------------

    def node_item_moved(self, item):
        if self._quiet:
            return
        self._moved.add(item.node_id)
        for edge_item in self.edge_items.values():
            if item in (edge_item.src_port.node_item, edge_item.dst_port.node_item):
                edge_item.update_path()

    def frame_item_moved(self, item):
        if self._quiet:
            return
        self._moved_frames.add(item.frame_id)

    def prepare_frame_drag(self, pressed):
        """Work out what a frame drag carries: everything inside the selected frames.

        Selected items are moved by Qt already, so only unselected contents are
        carried, and all of them by the pressed frame so nothing moves twice.
        """
        if self.model is None:
            return
        selected = set(self.selectedItems())
        carried = []
        for item in list(self.frame_items.values()):
            item.carry = []
            if not item.isSelected():
                continue
            nodes, frames = self.model.frame_contents(item.frame_id)
            for other in [self.node_items.get(n) for n in nodes] + [self.frame_items.get(f) for f in frames]:
                if other is not None and other not in selected and other not in carried:
                    carried.append(other)
        pressed.carry = carried

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.flush_moves()

    def flush_moves(self):
        if not self._moved and not self._moved_frames:
            return
        moved = {}
        for node_id in self._moved:
            item = self.node_items.get(node_id)
            if item is not None:
                moved[node_id] = (float(item.pos().x()), float(item.pos().y()))
        frames = {}
        for frame_id in self._moved_frames:
            item = self.frame_items.get(frame_id)
            if item is not None:
                frames[frame_id] = item.geometry()
        self._moved = set()
        self._moved_frames = set()
        if moved or frames:
            self.grow_scene_rect()
            self.nodesMoved.emit(moved, frames)

    # -- wiring -----------------------------------------------------------

    def mousePressEvent(self, event):
        if self.pending_port is not None:
            under = self.itemAt(event.scenePos(), QtGui.QTransform())
            if not isinstance(under, PortItem):
                self.cancel_pending_connection()
        super().mousePressEvent(event)

    def handle_port_click(self, port):
        if self.pending_port is None:
            if port.direction != "out":
                self._tip("Start a connection from an output port (then click an input)")
                return
            self.pending_port = port
            port.set_pending(True)
            return

        first = self.pending_port
        self.cancel_pending_connection()
        if port is first:
            return
        if port.direction != "in":
            self._tip("Connections go from an output port to an input port")
            return
        if first.node_item.node_id == port.node_item.node_id:
            self._tip("A node cannot be connected to itself")
            return
        if not types_compatible(first.type_name, port.type_name):
            self._tip(f"Incompatible ports: {first.type_name} → {port.type_name}")
            return
        self.connectRequested.emit(
            first.node_item.node_id, first.port_name, port.node_item.node_id, port.port_name
        )

    def cancel_pending_connection(self):
        if self.pending_port is not None:
            self.pending_port.set_pending(False)
        self.pending_port = None

    def _tip(self, text: str):
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), text)

    # -- selection --------------------------------------------------------

    class _Quiet:
        def __init__(self, scene):
            self.scene = scene

        def __enter__(self):
            self.scene._quiet += 1

        def __exit__(self, *_exc):
            self.scene._quiet -= 1

    def quiet(self):
        """Suppress selection/move notifications for programmatic changes."""
        return self._Quiet(self)

    def selected_node_ids(self):
        return [i.node_id for i in self.selectedItems() if isinstance(i, NodeItem)]

    def selected_frame_ids(self):
        return [i.frame_id for i in self.selectedItems() if isinstance(i, FrameItem)]

    def _emit_node_selection(self):
        if self._quiet:
            return
        self.nodeSelectionChanged.emit(self.selected_node_ids(), True)

    def select_node(self, node_id: str):
        """Select exactly one node, as if the user clicked it."""
        self.clearSelection()
        item = self.node_items.get(node_id)
        if item:
            item.setSelected(True)
            for view in self.views():
                view.ensureVisible(item)

    def set_nodes_selected(self, node_ids, selected: bool = True, exclusive: bool = False):
        """Mirror an external (FreeCAD) selection change without echoing it back."""
        with self.quiet():
            if exclusive:
                self.clearSelection()
            for node_id in node_ids:
                item = self.node_items.get(node_id)
                if item is not None:
                    item.setSelected(selected)
                    if selected:
                        for view in self.views():
                            view.ensureVisible(item)
        self.nodeSelectionChanged.emit(self.selected_node_ids(), False)

    def request_delete_selected(self):
        nodes = [i.node_id for i in self.selectedItems() if isinstance(i, NodeItem)]
        edges = [i.edge_id for i in self.selectedItems() if isinstance(i, ConnectionItem)]
        frames = self.selected_frame_ids()
        if nodes or edges or frames:
            self.deleteRequested.emit(nodes, edges, frames)
