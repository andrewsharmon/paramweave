"""Graph evaluation and mapping of shape outputs to ordinary FreeCAD objects."""

from __future__ import annotations

from typing import Any, Dict

import FreeCAD as App

from paramweave.constants import GENERATED_GROUP_NAME
from paramweave.nodes.registry import registry


class EvaluationError(RuntimeError):
    pass


class GraphEvaluator:
    def __init__(self, document, model):
        self.document = document
        self.model = model
        self.outputs: Dict[str, Dict[str, Any]] = {}
        self.errors: Dict[str, str] = {}

    def _inputs_for(self, node_id: str) -> Dict[str, Any]:
        values: Dict[str, Any] = {}
        for edge in self.model.incoming(node_id):
            src_values = self.outputs.get(edge.src_node, {})
            if edge.src_port not in src_values:
                raise EvaluationError(
                    f"Missing upstream value {edge.src_node}.{edge.src_port} for {node_id}.{edge.dst_port}"
                )
            values[edge.dst_port] = src_values[edge.src_port]
        return values

    def evaluate_all(self) -> Dict[str, Dict[str, Any]]:
        self.outputs = {}
        self.errors = {}
        for node_id in self.model.topological_order():
            node = self.model.nodes[node_id]
            spec = registry.get(node.type_id)
            try:
                inputs = self._inputs_for(node_id)
                values = spec.evaluate(self.document, node, inputs)
                if not isinstance(values, dict):
                    raise EvaluationError(f"Node evaluator must return dict, got {type(values)!r}")
                self.outputs[node_id] = values
                if "shape" in values:
                    self._update_generated_shape(node, values["shape"])
            except Exception as exc:
                self.errors[node_id] = str(exc)
                App.Console.PrintError(f"ParamWeave node {node.label} ({node.id}) failed: {exc}\n")
                self.outputs[node_id] = {}
        self.document.recompute()
        return self.outputs

    def _generated_group(self):
        group = self.document.getObject(GENERATED_GROUP_NAME)
        if group is None:
            group = self.document.addObject("App::DocumentObjectGroup", GENERATED_GROUP_NAME)
            group.Label = "ParamWeave Generated"
        return group

    def _find_generated(self, node_id: str):
        for obj in self.document.Objects:
            if "ParamWeaveNodeId" in getattr(obj, "PropertiesList", []):
                if obj.ParamWeaveNodeId == node_id:
                    return obj
        return None

    def _update_generated_shape(self, node, shape):
        if shape is None:
            return
        obj = self._find_generated(node.id)
        if obj is None:
            safe_name = "ParamWeave_" + node.id.replace("-", "_")
            obj = self.document.addObject("Part::Feature", safe_name)
            obj.addProperty("App::PropertyString", "ParamWeaveNodeId", "ParamWeave", "Owning graph node UUID")
            obj.ParamWeaveNodeId = node.id
            self._generated_group().addObject(obj)
        obj.Label = node.label
        obj.Shape = shape
