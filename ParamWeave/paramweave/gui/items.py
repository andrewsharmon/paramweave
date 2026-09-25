"""Minimal native Qt graph items.

The persistent graph model lives elsewhere. These classes are disposable views.
"""

from __future__ import annotations

from paramweave.gui.qt import QtCore, QtGui, QtWidgets, item_flag


NODE_W = 180.0
HEADER_H = 28.0
ROW_H = 22.0
PORT_R = 5.0


class PortItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, node_item, port_name: str, direction: str, type_name: str, y: float):
        super().__init__(-PORT_R, -PORT_R, PORT_R * 2, PORT_R * 2, node_item)
        self.node_item = node_item
        self.port_name = port_name
        self.direction = direction
        self.type_name = type_name
        x = 0.0 if direction == "in" else NODE_W
        self.setPos(x, y)
        self.setBrush(QtGui.QBrush(QtGui.QColor("#d0d0d0")))
        self.setPen(QtGui.QPen(QtGui.QColor("#303030"), 1.0))
        self.setToolTip(f"{direction}: {port_name} ({type_name})")
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.LeftButton if hasattr(QtCore.Qt, "MouseButton") else QtCore.Qt.LeftButton)

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
        self.setBrush(QtGui.QBrush(QtGui.QColor("#3b3f45")))
        self.setPen(QtGui.QPen(QtGui.QColor("#8a8f98"), 1.0))
        self.setFlag(item_flag("ItemIsMovable"), True)
        self.setFlag(item_flag("ItemIsSelectable"), True)
        self.setFlag(item_flag("ItemSendsGeometryChanges"), True)
        self.setPos(float(graph_node.position[0]), float(graph_node.position[1]))

        title = QtWidgets.QGraphicsTextItem(graph_node.label, self)
        title.setDefaultTextColor(QtGui.QColor("white"))
        title.setPos(8.0, 2.0)

        for i, port in enumerate(spec.inputs):
            y = HEADER_H + 12.0 + i * ROW_H
            p = PortItem(self, port.name, "in", port.type_name, y)
            self.ports[("in", port.name)] = p
            text = QtWidgets.QGraphicsTextItem(port.name, self)
            text.setDefaultTextColor(QtGui.QColor("#e0e0e0"))
            text.setPos(9.0, y - 11.0)

        for i, port in enumerate(spec.outputs):
            y = HEADER_H + 12.0 + i * ROW_H
            p = PortItem(self, port.name, "out", port.type_name, y)
            self.ports[("out", port.name)] = p
            text = QtWidgets.QGraphicsTextItem(port.name, self)
            text.setDefaultTextColor(QtGui.QColor("#e0e0e0"))
            width = text.boundingRect().width()
            text.setPos(NODE_W - width - 9.0, y - 11.0)

    @property
    def node_id(self):
        return self.graph_node.id

    def port(self, direction: str, name: str):
        return self.ports.get((direction, name))

    def itemChange(self, change, value):
        position_change = getattr(
            getattr(QtWidgets.QGraphicsItem, "GraphicsItemChange", QtWidgets.QGraphicsItem),
            "ItemPositionHasChanged",
            getattr(QtWidgets.QGraphicsItem, "ItemPositionHasChanged", None),
        )
        if position_change is not None and change == position_change:
            scene = self.scene()
            if scene is not None and hasattr(scene, "node_item_moved"):
                scene.node_item_moved(self)
        return super().itemChange(change, value)


class ConnectionItem(QtWidgets.QGraphicsPathItem):
    def __init__(self, edge_id: str, src_port: PortItem, dst_port: PortItem):
        super().__init__()
        self.edge_id = edge_id
        self.src_port = src_port
        self.dst_port = dst_port
        self.setZValue(-10.0)
        self.setPen(QtGui.QPen(QtGui.QColor("#b8c7ff"), 2.0))
        self.update_path()

    def update_path(self):
        a = self.src_port.scenePos()
        b = self.dst_port.scenePos()
        dx = max(abs(b.x() - a.x()) * 0.5, 40.0)
        path = QtGui.QPainterPath(a)
        path.cubicTo(a.x() + dx, a.y(), b.x() - dx, b.y(), b.x(), b.y())
        self.setPath(path)
