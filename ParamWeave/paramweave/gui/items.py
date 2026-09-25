"""Minimal native Qt graph items.

The persistent graph model lives elsewhere. These classes are disposable views.
"""

from __future__ import annotations

from paramweave.gui.qt import QtCore, QtGui, QtWidgets, item_flag, pen_style, qenum


NODE_W = 180.0
HEADER_H = 28.0
ROW_H = 22.0
PORT_R = 5.0

PORT_COLOR = "#d0d0d0"
PORT_PENDING_COLOR = "#ffd166"

# status -> (outline color, outline width, dashed, badge text). The badge text
# carries the meaning so state is never communicated by color alone.
STATUS_STYLE = {
    "idle": ("#8a8f98", 1.0, False, ""),
    "ok": ("#8a8f98", 1.0, False, ""),
    "warning": ("#f2b233", 2.0, False, "! check"),
    "error": ("#ff5c5c", 2.5, False, "✕ error"),
    "blocked": ("#f28c33", 2.0, True, "… blocked"),
    "unknown": ("#b48cff", 2.0, True, "? unknown"),
}
SELECTED_COLOR = "#ffffff"


class PortItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, node_item, port_name: str, direction: str, type_name: str, y: float):
        super().__init__(-PORT_R, -PORT_R, PORT_R * 2, PORT_R * 2, node_item)
        self.node_item = node_item
        self.port_name = port_name
        self.direction = direction
        self.type_name = type_name
        x = 0.0 if direction == "in" else NODE_W
        self.setPos(x, y)
        self.set_pending(False)
        self.setPen(QtGui.QPen(QtGui.QColor("#303030"), 1.0))
        self.setToolTip(f"{'input' if direction == 'in' else 'output'}: {port_name} ({type_name})")

    def set_pending(self, pending: bool):
        self.setBrush(QtGui.QBrush(QtGui.QColor(PORT_PENDING_COLOR if pending else PORT_COLOR)))

    def mousePressEvent(self, event):
        scene = self.scene()
        if scene is not None and hasattr(scene, "handle_port_click"):
            scene.handle_port_click(self)
            event.accept()
            return
        super().mousePressEvent(event)


class NodeItem(QtWidgets.QGraphicsRectItem):
    def __init__(self, graph_node, spec):
        rows = max(len(spec.inputs), len(spec.outputs), 1)
        h = HEADER_H + rows * ROW_H + 8.0
        super().__init__(0.0, 0.0, NODE_W, h)
        self.graph_node = graph_node
        self.spec = spec
        self.ports = {}
        self.status = "unknown" if spec.placeholder else "idle"
        self.status_message = "Node type is not registered; it is preserved but not evaluated" if spec.placeholder else ""
        self.setBrush(QtGui.QBrush(QtGui.QColor("#3b3f45")))
        self.setFlag(item_flag("ItemIsMovable"), True)
        self.setFlag(item_flag("ItemIsSelectable"), True)
        self.setFlag(item_flag("ItemSendsGeometryChanges"), True)
        self.setPos(float(graph_node.position[0]), float(graph_node.position[1]))

        self.title = QtWidgets.QGraphicsSimpleTextItem("", self)
        self.title.setBrush(QtGui.QBrush(QtGui.QColor("white")))
        self.title.setPos(8.0, 6.0)
        self.badge = QtWidgets.QGraphicsSimpleTextItem("", self)
        self.badge.setPos(NODE_W - 8.0, 6.0)

        for i, port in enumerate(spec.inputs):
            y = HEADER_H + 12.0 + i * ROW_H
            self.ports[("in", port.name)] = PortItem(self, port.name, "in", port.type_name, y)
            text = QtWidgets.QGraphicsSimpleTextItem(port.name, self)
            text.setBrush(QtGui.QBrush(QtGui.QColor("#e0e0e0")))
            text.setPos(10.0, y - text.boundingRect().height() / 2)

        for i, port in enumerate(spec.outputs):
            y = HEADER_H + 12.0 + i * ROW_H
            self.ports[("out", port.name)] = PortItem(self, port.name, "out", port.type_name, y)
            text = QtWidgets.QGraphicsSimpleTextItem(port.name, self)
            text.setBrush(QtGui.QBrush(QtGui.QColor("#e0e0e0")))
            width = text.boundingRect().width()
            text.setPos(NODE_W - width - 10.0, y - text.boundingRect().height() / 2)

        self.refresh()

    @property
    def node_id(self):
        return self.graph_node.id

    def port(self, direction: str, name: str):
        return self.ports.get((direction, name))

    def refresh(self):
        """Re-read label and status; cheap enough to call after any edit."""
        title = self.graph_node.label
        metrics = QtGui.QFontMetricsF(self.title.font())
        badge_text = STATUS_STYLE.get(self.status, STATUS_STYLE["idle"])[3]
        room = NODE_W - 16.0 - (metrics.horizontalAdvance(badge_text) + 8.0 if badge_text else 0.0)
        self.title.setText(metrics.elidedText(title, qenum(QtCore.Qt, "TextElideMode", "ElideRight"), room))
        color, width, dashed, badge = STATUS_STYLE.get(self.status, STATUS_STYLE["idle"])
        self.badge.setText(badge)
        self.badge.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        self.badge.setPos(NODE_W - 8.0 - self.badge.boundingRect().width(), 6.0)
        pen = QtGui.QPen(QtGui.QColor(SELECTED_COLOR if self.isSelected() else color), width + (1.0 if self.isSelected() else 0.0))
        if dashed:
            pen.setStyle(pen_style("DashLine"))
        self.setPen(pen)
        tip = [f"{self.graph_node.label} ({self.graph_node.type_id})"]
        if self.status_message:
            tip.append(self.status_message)
        self.setToolTip("\n".join(tip))

    def set_status(self, status: str, message: str = ""):
        if self.spec.placeholder:
            return
        self.status = status
        self.status_message = message
        self.refresh()

    def itemChange(self, change, value):
        changes = getattr(QtWidgets.QGraphicsItem, "GraphicsItemChange", QtWidgets.QGraphicsItem)
        result = super().itemChange(change, value)
        if change == getattr(changes, "ItemPositionHasChanged", None):
            scene = self.scene()
            if scene is not None and hasattr(scene, "node_item_moved"):
                scene.node_item_moved(self)
        elif change == getattr(changes, "ItemSelectedHasChanged", None):
            self.refresh()
        return result


class ConnectionItem(QtWidgets.QGraphicsPathItem):
    def __init__(self, edge_id: str, src_port: PortItem, dst_port: PortItem):
        super().__init__()
        self.edge_id = edge_id
        self.src_port = src_port
        self.dst_port = dst_port
        self.setZValue(-10.0)
        self.setFlag(item_flag("ItemIsSelectable"), True)
        self.setToolTip(
            f"{src_port.node_item.graph_node.label}.{src_port.port_name} → "
            f"{dst_port.node_item.graph_node.label}.{dst_port.port_name} (Delete removes)"
        )
        self._apply_pen()
        self.update_path()

    def _apply_pen(self):
        selected = self.isSelected()
        self.setPen(QtGui.QPen(QtGui.QColor("#ffffff" if selected else "#b8c7ff"), 3.0 if selected else 2.0))

    def shape(self):
        # Widen the clickable area so thin wires are easy to select.
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(10.0)
        return stroker.createStroke(self.path())

    def itemChange(self, change, value):
        changes = getattr(QtWidgets.QGraphicsItem, "GraphicsItemChange", QtWidgets.QGraphicsItem)
        result = super().itemChange(change, value)
        if change == getattr(changes, "ItemSelectedHasChanged", None):
            self._apply_pen()
        return result

    def update_path(self):
        a = self.src_port.scenePos()
        b = self.dst_port.scenePos()
        dx = max(abs(b.x() - a.x()) * 0.5, 40.0)
        path = QtGui.QPainterPath(a)
        path.cubicTo(a.x() + dx, a.y(), b.x() - dx, b.y(), b.x(), b.y())
        self.setPath(path)

