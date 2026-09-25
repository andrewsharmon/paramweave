"""Graph evaluation and mapping of shape outputs to ordinary FreeCAD objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import FreeCAD as App

from paramweave.constants import GENERATED_GROUP_NAME, NODE_ID_PROPERTY
from paramweave.nodes.registry import registry

# Node statuses reported to the UI. Keep in sync with gui/items.py.
OK = "ok"
WARNING = "warning"  # evaluated, but something needs the user's attention
ERROR = "error"  # this node failed
BLOCKED = "blocked"  # an upstream node failed, so this one was not run


class EvaluationError(RuntimeError):
    pass


@dataclass
class NodeResult:
    status: str
    message: str = ""


class GraphEvaluator:
    def __init__(self, document, model):
        self.document = document
        self.model = model
        self.outputs: Dict[str, Dict[str, Any]] = {}
        self.results: Dict[str, NodeResult] = {}

    @property
    def errors(self) -> Dict[str, str]:
        return {nid: r.message for nid, r in self.results.items() if r.status == ERROR}

    def _blocking_upstream(self, node_id: str) -> Optional[str]:
        for edge in self.model.incoming(node_id):
            upstream = self.results.get(edge.src_node)
            if upstream is not None and upstream.status in (ERROR, BLOCKED):
                return edge.src_node
        return None

    def _inputs_for(self, node_id: str) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for edge in self.model.incoming(node_id):
            src_values = self.outputs.get(edge.src_node, {})
            if edge.src_port not in src_values:
                src = self.model.nodes[edge.src_node]
                raise EvaluationError(f"Upstream node '{src.label}' produced no '{edge.src_port}' output")
            values[edge.dst_port] = src_values[edge.src_port]
        return values

    def evaluate_all(self) -> Dict[str, Dict[str, Any]]:
        self.outputs = {}
        self.results = {}
        for node_id in self.model.topological_order():
            node = self.model.nodes[node_id]
            blocker = self._blocking_upstream(node_id)
            if blocker is not None:
                label = self.model.nodes[blocker].label
                self.results[node_id] = NodeResult(BLOCKED, f"Blocked: upstream node '{label}' failed")
                self.outputs[node_id] = {}
                continue
            try:
                spec = registry.find(node.type_id)
                if spec is None:
                    raise EvaluationError(f"Unknown node type '{node.type_id}' (not evaluated)")
                inputs = self._inputs_for(node_id)
                values = spec.evaluate(self.document, node, inputs)
                if not isinstance(values, dict):
                    raise EvaluationError(f"Node evaluator must return dict, got {type(values)!r}")
                warning = values.pop("_warning", "")
                self.outputs[node_id] = values
                if spec.generates_object and values.get("shape") is not None:
                    self._update_generated_shape(node, values["shape"])
                self.results[node_id] = NodeResult(WARNING, warning) if warning else NodeResult(OK)
                if warning:
                    App.Console.PrintWarning(f"ParamWeave node {node.label}: {warning}\n")
            except Exception as exc:
                self.results[node_id] = NodeResult(ERROR, str(exc))
                App.Console.PrintError(f"ParamWeave node {node.label} ({node.id}) failed: {exc}\n")
                self.outputs[node_id] = {}
        self._update_visibility()
        self.document.recompute()
        return self.outputs

    def _generated_group(self):
        group = self.document.getObject(GENERATED_GROUP_NAME)
        if group is None:
            group = self.document.addObject("App::DocumentObjectGroup", GENERATED_GROUP_NAME)
            group.Label = "ParamWeave Generated"
        return group

    def _update_generated_shape(self, node, shape):
        obj = find_generated(self.document, node.id)
        if obj is None:
            safe_name = "ParamWeave_" + node.id.replace("-", "_")
            obj = self.document.addObject("Part::Feature", safe_name)
            obj.addProperty("App::PropertyString", NODE_ID_PROPERTY, "ParamWeave", "Owning graph node UUID")
            setattr(obj, NODE_ID_PROPERTY, node.id)
            obj.setEditorMode(NODE_ID_PROPERTY, 1)
            self._generated_group().addObject(obj)
            obj.Visibility = self._is_terminal(node.id)
        if obj.Label != node.label:
            obj.Label = node.label
        obj.Shape = shape

    def _is_terminal(self, node_id: str) -> bool:
        """True if no generating node consumes this node's output."""
        for edge in self.model.outgoing(node_id):
            spec = registry.find(self.model.nodes[edge.dst_node].type_id)
            if spec is not None and spec.generates_object:
                return False
        return True

    def _update_visibility(self) -> None:
        # Intermediate results are hidden so the terminal shape is visible.
        # Terminal outputs keep whatever visibility the user chose.
        for node_id in self.model.nodes:
            obj = find_generated(self.document, node_id)
            if obj is not None and not self._is_terminal(node_id) and obj.Visibility:
                obj.Visibility = False


def find_generated(document, node_id: str):
    for obj in document.Objects:
        if NODE_ID_PROPERTY in obj.PropertiesList and getattr(obj, NODE_ID_PROPERTY) == node_id:
            return obj
    return None


def remove_generated(document, node_ids: Iterable[str]) -> list:
    """Delete generated objects owned by removed nodes.

    Objects that other document objects depend on are kept (and reported) so
    deleting a graph node never breaks user-authored features.
    """
    kept = []
    group = document.getObject(GENERATED_GROUP_NAME)
    for node_id in node_ids:
        obj = find_generated(document, node_id)
        if obj is None:
            continue
        dependents = [o for o in obj.InList if group is None or o.Name != group.Name]
        if dependents:
            kept.append(obj.Name)
            App.Console.PrintWarning(
                f"ParamWeave: kept {obj.Label} ({obj.Name}); it is used by "
                + ", ".join(o.Label for o in dependents)
                + "\n"
            )
            continue
        document.removeObject(obj.Name)
    return kept
