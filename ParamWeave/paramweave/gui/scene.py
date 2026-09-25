"""Graph scene that projects GraphModel into QGraphicsItems."""

from __future__ import annotations

from paramweave.gui.qt import QtCore, QtGui, QtWidgets
from paramweave.gui.items import ConnectionItem, NodeItem
from paramweave.nodes.registry import registry, types_compatible


class GraphScene(QtWidgets.QGraphicsScene):
    modelChanged = QtCore.Signal()
    nodeSelectionChanged = QtCore.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.node_items = {}
        self.edge_items = {}
        self.pending_port = None
        self.selectionChanged.connect(self._emit_node_selection)

    def set_model(self, model):
        self.model = model
        self.rebuild()

    def rebuild(self):
        self.clear()
        self.node_items = {}
        self.edge_items = {}
        self.pending_port = None
        if self.model is None:
            return
        for node in self.model.nodes.values():
            self._add_node_item(node)
        for edge in self.model.edges.values():
            self._add_edge_item(edge)
        self.setSceneRect(self.itemsBoundingRect().adjusted(-100, -100, 100, 100))

    def _add_node_item(self, node):
        spec = registry.get(node.type_id)
        item = NodeItem(node, spec)
        self.addItem(item)
        self.node_items[node.id] = item
        return item

    def add_node(self, node):
        item = self._add_node_item(node)
        item.setSelected(True)
        self.modelChanged.emit()
        return item

    def _add_edge_item(self, edge):
        src = self.node_items[edge.src_node].port("out", edge.src_port)
        dst = self.node_items[edge.dst_node].port("in", edge.dst_port)
        if src is None or dst is None:
            return
        item = ConnectionItem(edge.id, src, dst)
        self.addItem(item)
        self.edge_items[edge.id] = item

    def node_item_moved(self, item):
        if self.model is None:
            return
        node = self.model.nodes.get(item.node_id)
        if node is not None:
            p = item.pos()
            node.position = [float(p.x()), float(p.y())]
        self.update_connections_for_node(item.node_id)
        self.modelChanged.emit()

    def update_connections_for_node(self, node_id: str):
        if self.model is None:
            return
        for edge in self.model.edges.values():
            if edge.src_node == node_id or edge.dst_node == node_id:
                item = self.edge_items.get(edge.id)
                if item:
                    item.update_path()

    def handle_port_click(self, port):
        if self.pending_port is None:
            if port.direction != "out":
                return
            self.pending_port = port
            port.setBrush(QtGui.QBrush(QtGui.QColor("#ffd166")))
            return

        first = self.pending_port
        self.pending_port = None
        first.setBrush(QtGui.QBrush(QtGui.QColor("#d0d0d0")))
        if port.direction != "in" or first.node_item.node_id == port.node_item.node_id:
            return
        if not types_compatible(first.type_name, port.type_name):
            QtWidgets.QToolTip.showText(
                QtGui.QCursor.pos(),
                f"Incompatible ports: {first.type_name} → {port.type_name}",
            )
            return
        try:
            edge = self.model.connect(
                first.node_item.node_id,
                first.port_name,
                port.node_item.node_id,
                port.port_name,
            )
        except Exception as exc:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), str(exc))
            return
        self._add_edge_item(edge)
        self.modelChanged.emit()

    def cancel_pending_connection(self):
        if self.pending_port is not None:
            self.pending_port.setBrush(QtGui.QBrush(QtGui.QColor("#d0d0d0")))
        self.pending_port = None

    def _emit_node_selection(self):
        selected = [i for i in self.selectedItems() if isinstance(i, NodeItem)]
        self.nodeSelectionChanged.emit(selected[0].node_id if len(selected) == 1 else None)

    def select_node(self, node_id: str):
        self.clearSelection()
        item = self.node_items.get(node_id)
        if item:
            item.setSelected(True)
            self.views()[0].ensureVisible(item) if self.views() else None

    def delete_selected_nodes(self):
        selected = [i for i in self.selectedItems() if isinstance(i, NodeItem)]
        if not selected or self.model is None:
            return
        for item in selected:
            self.model.remove_node(item.node_id)
        self.rebuild()
        self.modelChanged.emit()
