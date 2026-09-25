from __future__ import annotations

from paramweave.gui.qt import QtCore, QtGui, QtWidgets


class GraphView(QtWidgets.QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing if hasattr(QtGui.QPainter, "RenderHint") else QtGui.QPainter.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag if hasattr(QtWidgets.QGraphicsView, "DragMode") else QtWidgets.QGraphicsView.RubberBandDrag)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#202328")))
        self.setMinimumWidth(320)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        self.scale(factor, factor)

    def keyPressEvent(self, event):
        key_enum = getattr(QtCore.Qt, "Key", QtCore.Qt)
        if event.key() == getattr(key_enum, "Key_Delete", getattr(QtCore.Qt, "Key_Delete", 0)):
            self.scene().delete_selected_nodes()
            event.accept()
            return
        if event.key() == getattr(key_enum, "Key_Escape", getattr(QtCore.Qt, "Key_Escape", 0)):
            self.scene().cancel_pending_connection()
            event.accept()
            return
        super().keyPressEvent(event)
