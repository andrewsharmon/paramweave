"""Simple node parameter editor for the starter."""

from __future__ import annotations

import json

from paramweave.gui.qt import QtCore, QtWidgets


class PropertyPanel(QtWidgets.QWidget):
    parameterChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = None
        self.node_id = None
        self.form = QtWidgets.QFormLayout(self)
        self.form.setContentsMargins(6, 6, 6, 6)

    def set_model(self, model):
        self.model = model
        self.set_node(None)

    def _clear(self):
        while self.form.rowCount():
            self.form.removeRow(0)

    def set_node(self, node_id):
        self._clear()
        self.node_id = node_id
        if self.model is None or node_id is None or node_id not in self.model.nodes:
            self.form.addRow(QtWidgets.QLabel("Select a graph node to edit parameters."))
            return
        node = self.model.nodes[node_id]
        self.form.addRow("Type", QtWidgets.QLabel(node.type_id))
        label_edit = QtWidgets.QLineEdit(node.label)
        label_edit.editingFinished.connect(lambda: self._set_label(label_edit.text()))
        self.form.addRow("Label", label_edit)
        for key, value in node.params.items():
            if isinstance(value, (dict, list)):
                widget = QtWidgets.QPlainTextEdit(json.dumps(value, indent=2, sort_keys=True))
                widget.setMaximumHeight(100)
                widget.textChanged.connect(lambda k=key, w=widget: self._set_json(k, w.toPlainText()))
            else:
                widget = QtWidgets.QLineEdit(str(value))
                widget.editingFinished.connect(lambda k=key, w=widget: self._set_scalar(k, w.text()))
            self.form.addRow(key, widget)

    def _node(self):
        if self.model is None or self.node_id is None:
            return None
        return self.model.nodes.get(self.node_id)

    def _set_label(self, text: str):
        node = self._node()
        if node is not None and text:
            node.label = text
            self.parameterChanged.emit()

    def _set_scalar(self, key: str, text: str):
        node = self._node()
        if node is None:
            return
        old = node.params.get(key)
        try:
            if isinstance(old, bool):
                value = text.strip().lower() in {"1", "true", "yes", "on"}
            elif isinstance(old, int) and not isinstance(old, bool):
                value = int(text)
            elif isinstance(old, float):
                value = float(text)
            else:
                value = text
        except ValueError:
            return
        node.params[key] = value
        self.parameterChanged.emit()

    def _set_json(self, key: str, text: str):
        node = self._node()
        if node is None:
            return
        try:
            value = json.loads(text)
        except Exception:
            return
        node.params[key] = value
        self.parameterChanged.emit()
