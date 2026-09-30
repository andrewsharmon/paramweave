"""Simple node parameter editor for the starter.

The panel never mutates the model. It emits edit requests which the workspace
applies inside a FreeCAD transaction.
"""

from __future__ import annotations

import json
import math

from paramweave.gui.qt import QtCore, QtWidgets
from paramweave.nodes.registry import registry


class _NoteEdit(QtWidgets.QPlainTextEdit):
    """Multi-line editor that reports its text when it loses focus."""

    editingFinished = QtCore.Signal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()


class PropertyPanel(QtWidgets.QScrollArea):
    # (node_id, param key, new value)
    parameterEdited = QtCore.Signal(str, str, object)
    # (node_id, new label)
    labelEdited = QtCore.Signal(str, str)
    # (frame_id, "label" | "color" | "note", new value)
    frameEdited = QtCore.Signal(str, str, object)

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
        if getattr(self, "frame_id", None) is not None:
            self.set_frame(self.frame_id)
        else:
            self.set_node(self.node_id)

    def set_frame(self, frame_id):
        """Edit a frame's label, color and note."""
        from paramweave.app.model import FRAME_COLORS

        form = self._new_form()
        self.node_id = None
        self.frame_id = frame_id
        frame = self.model.frames.get(frame_id) if self.model is not None else None
        if frame is None:
            self.frame_id = None
            form.addRow(QtWidgets.QLabel("Select a single graph node to edit its parameters."))
            return
        form.addRow("Type", QtWidgets.QLabel("frame"))
        label = QtWidgets.QLineEdit(frame.label)
        label.setProperty("paramweave_key", "__label__")
        label.editingFinished.connect(lambda fid=frame_id, w=label: self._frame_text(fid, "label", w.text().strip()))
        form.addRow("Label", label)
        color = QtWidgets.QComboBox()
        color.addItems(list(FRAME_COLORS))
        if frame.color in FRAME_COLORS:
            color.setCurrentText(frame.color)
        color.setProperty("paramweave_key", "color")
        color.currentTextChanged.connect(lambda text, fid=frame_id: self.frameEdited.emit(fid, "color", text))
        form.addRow("Color", color)
        note = _NoteEdit(frame.note)
        note.setProperty("paramweave_key", "note")
        note.setPlaceholderText("Optional comment shown inside the frame")
        note.setMaximumHeight(110)
        note.editingFinished.connect(lambda fid=frame_id, w=note: self._frame_text(fid, "note", w.toPlainText()))
        form.addRow("Note", note)
        hint = QtWidgets.QLabel("Nodes placed inside the frame move with it. Delete removes only the frame.")
        hint.setWordWrap(True)
        form.addRow(hint)

    def _frame_text(self, frame_id, key, text):
        frame = self.model.frames.get(frame_id) if self.model is not None else None
        if frame is None or (key == "label" and not text):
            return
        if getattr(frame, key) != text:
            self.frameEdited.emit(frame_id, key, text)

    def set_node(self, node_id):
        form = self._new_form()
        self.frame_id = None
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
        wired = {e.dst_port for e in self.model.incoming(node_id)}
        spec = registry.find(node.type_id)
        choices = spec.choices if spec is not None else {}
        for key, value in node.params.items():
            if key in wired and isinstance(value, (int, float)) and not isinstance(value, bool):
                # The wire overrides the stored value at evaluation time.
                widget = QtWidgets.QLineEdit("driven by input")
                widget.setReadOnly(True)
                widget.setEnabled(False)
                widget.setToolTip(f"'{key}' comes from the connected '{key}' input; disconnect it to edit ({_format(value)} is kept)")
            elif isinstance(value, (dict, list)):
                # Structured values (e.g. captured references) are shown read-only;
                # hand-editing them as JSON is error-prone and bypasses capture.
                widget = QtWidgets.QPlainTextEdit(json.dumps(value, indent=2, sort_keys=True))
                widget.setReadOnly(True)
                widget.setMaximumHeight(120)
            elif key in choices and isinstance(value, str):
                widget = QtWidgets.QComboBox()
                widget.addItems(list(choices[key]))
                if value not in choices[key]:
                    # Keep an unknown stored value visible rather than silently replacing it.
                    widget.addItem(value)
                widget.setCurrentText(value)
                widget.currentTextChanged.connect(
                    lambda text, nid=node_id, k=key: self._choice_changed(nid, k, text)
                )
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

    def _choice_changed(self, node_id, key, text):
        node = self.model.nodes.get(node_id) if self.model is not None else None
        if node is not None and node.params.get(key) != text:
            self.parameterEdited.emit(node_id, key, text)

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
