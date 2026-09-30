from __future__ import annotations

from paramweave.gui.qt import QtCore, QtGui, QtWidgets, key, mouse_button, qenum


class GraphView(QtWidgets.QGraphicsView):
    # (type_id, scene position) chosen from the canvas context menu.
    addNodeRequested = QtCore.Signal(str, object)
    referenceRequested = QtCore.Signal(object)
    duplicateRequested = QtCore.Signal()

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(qenum(QtGui.QPainter, "RenderHint", "Antialiasing"))
        self.setDragMode(qenum(QtWidgets.QGraphicsView, "DragMode", "RubberBandDrag"))
        self.setTransformationAnchor(qenum(QtWidgets.QGraphicsView, "ViewportAnchor", "AnchorUnderMouse"))
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#202328")))
        self.setMinimumWidth(320)
        self.setFocusPolicy(qenum(QtCore.Qt, "FocusPolicy", "StrongFocus"))
        self._pan_origin = None
        self.node_menu_entries = []  # [(category, title, type_id)] provided by the workspace

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        current = self.transform().m11()
        if 0.1 < current * factor < 5.0:
            self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == mouse_button("MiddleButton"):
            self._pan_origin = event.position() if hasattr(event, "position") else event.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_origin is not None:
            pos = event.position() if hasattr(event, "position") else event.pos()
            delta = pos - self._pan_origin
            self._pan_origin = pos
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == mouse_button("MiddleButton") and self._pan_origin is not None:
            self._pan_origin = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _is_own_shortcut(self, event) -> bool:
        k = event.key()
        ctrl = bool(event.modifiers() & qenum(QtCore.Qt, "KeyboardModifier", "ControlModifier"))
        if k == key("Key_D"):
            return ctrl
        return k in (key("Key_Delete"), key("Key_Backspace"), key("Key_Escape"), key("Key_F")) and not ctrl

    def event(self, event):
        # FreeCAD registers application-wide shortcuts (and other docked
        # widgets may hold them too). Claiming the graph's own keys in the
        # ShortcutOverride phase makes Qt deliver them to keyPressEvent while
        # the graph has focus instead of to a global action.
        if event.type() == qenum(QtCore.QEvent, "Type", "ShortcutOverride") and self._is_own_shortcut(event):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        k = event.key()
        if k in (key("Key_Delete"), key("Key_Backspace")):
            self.scene().request_delete_selected()
            event.accept()
            return
        if k == key("Key_Escape"):
            self.scene().cancel_pending_connection()
            event.accept()
            return
        if k == key("Key_D") and event.modifiers() & qenum(QtCore.Qt, "KeyboardModifier", "ControlModifier"):
            # Ctrl+D (Cmd+D on macOS, where Qt maps Cmd to Control).
            self.duplicateRequested.emit()
            event.accept()
            return
        if k == key("Key_F"):
            self.frame_all()
            event.accept()
            return
        super().keyPressEvent(event)

    def frame_all(self):
        scene = self.scene()
        rect = scene.itemsBoundingRect()
        if rect.isNull():
            return
        self.fitInView(rect.adjusted(-40, -40, 40, 40), qenum(QtCore.Qt, "AspectRatioMode", "KeepAspectRatio"))
        if self.transform().m11() > 1.5:
            self.resetTransform()
            self.centerOn(rect.center())

    def contextMenuEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        if self.scene().itemAt(scene_pos, QtGui.QTransform()) is not None:
            super().contextMenuEvent(event)
            return
        menu = QtWidgets.QMenu(self)
        ref_action = menu.addAction("Reference From Selection")
        ref_action.triggered.connect(lambda: self.referenceRequested.emit(scene_pos))
        menu.addSeparator()
        submenus = {}
        for category, title, type_id in self.node_menu_entries:
            sub = submenus.get(category)
            if sub is None:
                sub = submenus[category] = menu.addMenu(category)
            action = sub.addAction(title)
            action.triggered.connect(lambda _checked=False, t=type_id: self.addNodeRequested.emit(t, scene_pos))
        menu.addSeparator()
        if self.scene().selected_node_ids():
            menu.addAction("Duplicate Selected (Ctrl+D)").triggered.connect(self.duplicateRequested.emit)
        menu.addAction("Frame All (F)").triggered.connect(self.frame_all)
        menu.exec(event.globalPos()) if hasattr(menu, "exec") else menu.exec_(event.globalPos())
