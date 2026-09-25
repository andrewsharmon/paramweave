"""Simple node parameter editor for the starter.

The panel never mutates the model. It emits edit requests which the workspace
applies inside a FreeCAD transaction.
"""

from __future__ import annotations

import json
import math

from paramweave.gui.qt import QtCore, QtWidgets


class PropertyPanel(QtWidgets.QScrollArea):
    # (node_id, param key, new value)
    parameterEdited = QtCore.Signal(str, str, object)
    # (node_id, new label)
    labelEdited = QtCore.Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.model = None
        self.node_id = None
        # The scroll area keeps one permanent container; only the body inside it
        # is swapped. (QScrollArea.takeWidget() on a widget holding keyboard
        # focus segfaults in Qt 6.8 while Qt looks for the next focus target.)
        self._container = QtWidgets.QWidget()
        self._container_layout = QtWidgets.QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.addStretch(1)
        self.setWidget(self._container)
        self._body = None
        self.set_node(None)

    def set_model(self, model):
        self.model = model
        self.set_node(None)

    def _new_form(self):
        # Replace the whole body widget rather than removing rows: an editor may
        # be mid-signal (editingFinished) when the panel is refreshed, so old
        # widgets are disposed of with deleteLater() instead of synchronously.
        old = self._body
        if old is not None:
            focus = QtWidgets.QApplication.focusWidget()
            if focus is not None and (focus is old or old.isAncestorOf(focus)):
                focus.clearFocus()
            self._container_layout.removeWidget(old)
            old.hide()
            old.deleteLater()
        self._body = QtWidgets.QWidget(self._container)
        form = QtWidgets.QFormLayout(self._body)
        form.setContentsMargins(6, 6, 6, 6)
        self._container_layout.insertWidget(0, self._body)
        return form

    def refresh(self):
        self.set_node(self.node_id)

    def set_node(self, node_id):
        form = self._new_form()
        self.node_id = node_id
        if self.model is None or node_id is None or node_id not in self.model.nodes:
            self.node_id = None
            form.addRow(QtWidgets.QLabel("Select a single graph node to edit its parameters."))
            return
        node = self.model.nodes[node_id]
        form.addRow("Type", QtWidgets.QLabel(node.type_id))
        label_edit = QtWidgets.QLineEdit(node.label)
        label_edit.setProperty("paramweave_key", "__label__")
        label_edit.editingFinished.connect(lambda nid=node_id, w=label_edit: self._label_finished(nid, w))
        form.addRow("Label", label_edit)
        for key, value in node.params.items():
            if isinstance(value, (dict, list)):
                # Structured values (e.g. captured references) are shown read-only;
                # hand-editing them as JSON is error-prone and bypasses capture.
                widget = QtWidgets.QPlainTextEdit(json.dumps(value, indent=2, sort_keys=True))
                widget.setReadOnly(True)
                widget.setMaximumHeight(120)
            elif isinstance(value, bool):
                widget = QtWidgets.QCheckBox()
                widget.setChecked(value)
                widget.toggled.connect(lambda checked, nid=node_id, k=key: self.parameterEdited.emit(nid, k, bool(checked)))
            else:
                widget = QtWidgets.QLineEdit(_format(value))
                widget.editingFinished.connect(lambda nid=node_id, k=key, w=widget: self._scalar_finished(nid, k, w))
            widget.setProperty("paramweave_key", key)
            form.addRow(key, widget)

    def _label_finished(self, node_id, widget):
        node = self.model.nodes.get(node_id) if self.model is not None else None
        text = widget.text().strip()
        if node is None:
            return
        if not text:
            widget.setText(node.label)
            return
        if text != node.label:
            self.labelEdited.emit(node_id, text)

    def _scalar_finished(self, node_id, key, widget):
        node = self.model.nodes.get(node_id) if self.model is not None else None
        if node is None or key not in node.params:
            return
        old = node.params[key]
        try:
            value = _parse_like(old, widget.text())
        except ValueError as exc:
            widget.setText(_format(old))
            QtWidgets.QToolTip.showText(widget.mapToGlobal(widget.rect().bottomLeft()), str(exc), widget)
            return
        if value != old or type(value) is not type(old):
            self.parameterEdited.emit(node_id, key, value)


def _format(value) -> str:
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _parse_like(old, text: str):
    """Parse text into the same JSON type as the current value."""
    text = text.strip()
    if isinstance(old, int) and not isinstance(old, bool):
        try:
            return int(text)
        except ValueError:
            raise ValueError(f"'{text}' is not an integer") from None
    if isinstance(old, float):
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f"'{text}' is not a number") from None
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        return value
    return text
