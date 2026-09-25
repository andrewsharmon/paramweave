"""UI-independent graph data model.

This module intentionally has no FreeCAD or Qt imports so it can be unit tested
with ordinary Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import uuid
from typing import Any, Dict, Iterable, List, Optional


SCHEMA_VERSION = 1


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class GraphNode:
    id: str
    type_id: str
    label: str
    position: List[float] = field(default_factory=lambda: [0.0, 0.0])
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        type_id: str,
        label: str,
        position: Iterable[float] = (0.0, 0.0),
        params: Optional[Dict[str, Any]] = None,
    ) -> "GraphNode":
        x, y = position
        return cls(new_id(), type_id, label, [float(x), float(y)], dict(params or {}))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type_id": self.type_id,
            "label": self.label,
            "position": [float(self.position[0]), float(self.position[1])],
            "params": self.params,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphNode":
        _require_mapping(data, "node")
        node_id = _require_str(data, "id", "node")
        type_id = _require_str(data, "type_id", f"node {node_id}")
        label = data.get("label", type_id)
        if not isinstance(label, str):
            raise GraphValidationError(f"node {node_id}: label must be a string")
        position = data.get("position", [0.0, 0.0])
        if not isinstance(position, (list, tuple)) or len(position) != 2:
            raise GraphValidationError(f"node {node_id}: position must be [x, y]")
        try:
            xy = [float(v) for v in position]
        except (TypeError, ValueError) as exc:
            raise GraphValidationError(f"node {node_id}: position must be numeric") from exc
        if not all(math.isfinite(v) for v in xy):
            raise GraphValidationError(f"node {node_id}: position must be finite")
        params = data.get("params", {})
        if not isinstance(params, dict):
            raise GraphValidationError(f"node {node_id}: params must be an object")
        return cls(id=node_id, type_id=type_id, label=label, position=xy, params=dict(params))


@dataclass
class GraphEdge:
    id: str
    src_node: str
    src_port: str
    dst_node: str
    dst_port: str

    @classmethod
    def create(cls, src_node: str, src_port: str, dst_node: str, dst_port: str) -> "GraphEdge":
        return cls(new_id(), src_node, src_port, dst_node, dst_port)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "src_node": self.src_node,
            "src_port": self.src_port,
            "dst_node": self.dst_node,
            "dst_port": self.dst_port,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphEdge":
        _require_mapping(data, "edge")
        edge_id = _require_str(data, "id", "edge")
        where = f"edge {edge_id}"
        return cls(
            id=edge_id,
            src_node=_require_str(data, "src_node", where),
            src_port=_require_str(data, "src_port", where),
            dst_node=_require_str(data, "dst_node", where),
            dst_port=_require_str(data, "dst_port", where),
        )


class GraphValidationError(ValueError):
    pass


def _require_mapping(data: Any, what: str) -> None:
    if not isinstance(data, dict):
        raise GraphValidationError(f"{what} must be a JSON object, got {type(data).__name__}")


def _require_str(data: Dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise GraphValidationError(f"{where}: '{key}' must be a non-empty string")
    return value


class GraphModel:
    def __init__(self) -> None:
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, GraphEdge] = {}

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()

    def add_node(self, node: GraphNode) -> GraphNode:
        if node.id in self.nodes:
            raise GraphValidationError(f"Duplicate node id: {node.id}")
        self.nodes[node.id] = node
        return node

    def create_node(
        self,
        type_id: str,
        label: str,
        position=(0.0, 0.0),
        params: Optional[Dict[str, Any]] = None,
    ) -> GraphNode:
        return self.add_node(GraphNode.create(type_id, label, position, params))

    def remove_node(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)
        doomed = [eid for eid, e in self.edges.items() if e.src_node == node_id or e.dst_node == node_id]
        for eid in doomed:
            self.edges.pop(eid, None)

    def connect(self, src_node: str, src_port: str, dst_node: str, dst_port: str) -> GraphEdge:
        if src_node not in self.nodes or dst_node not in self.nodes:
            raise GraphValidationError("Both edge endpoints must exist")
        if src_node == dst_node:
            raise GraphValidationError("Self edges are not supported")
        for edge in self.edges.values():
            if edge.dst_node == dst_node and edge.dst_port == dst_port:
                raise GraphValidationError(f"Input already connected: {dst_node}.{dst_port}")
            if (
                edge.src_node == src_node
                and edge.src_port == src_port
                and edge.dst_node == dst_node
                and edge.dst_port == dst_port
            ):
                raise GraphValidationError("Duplicate edge")
        edge = GraphEdge.create(src_node, src_port, dst_node, dst_port)
        self.edges[edge.id] = edge
        try:
            self.topological_order()
        except GraphValidationError:
            self.edges.pop(edge.id, None)
            raise
        return edge

    def remove_edge(self, edge_id: str) -> None:
        self.edges.pop(edge_id, None)

    def incoming(self, node_id: str) -> List[GraphEdge]:
        return [e for e in self.edges.values() if e.dst_node == node_id]

    def outgoing(self, node_id: str) -> List[GraphEdge]:
        return [e for e in self.edges.values() if e.src_node == node_id]

    def topological_order(self) -> List[str]:
        indegree = {nid: 0 for nid in self.nodes}
        outgoing: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges.values():
            if edge.src_node not in self.nodes or edge.dst_node not in self.nodes:
                raise GraphValidationError(f"Dangling edge: {edge.id}")
            indegree[edge.dst_node] += 1
            outgoing[edge.src_node].append(edge.dst_node)

        queue = [nid for nid, degree in indegree.items() if degree == 0]
        order: List[str] = []
        while queue:
            nid = queue.pop(0)
            order.append(nid)
            for dst in outgoing[nid]:
                indegree[dst] -= 1
                if indegree[dst] == 0:
                    queue.append(dst)

        if len(order) != len(self.nodes):
            raise GraphValidationError("Graph contains a dependency cycle")
        return order

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "nodes": [self.nodes[k].to_dict() for k in sorted(self.nodes)],
            "edges": [self.edges[k].to_dict() for k in sorted(self.edges)],
        }

    def to_json(self, *, pretty: bool = False) -> str:
        return json.dumps(
            self.to_dict(),
            indent=2 if pretty else None,
            sort_keys=True,
            separators=None if pretty else (",", ":"),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphModel":
        """Build a model from untrusted data, raising GraphValidationError on any defect."""
        _require_mapping(data, "graph")
        version = data.get("schema_version", 0)
        if isinstance(version, bool) or not isinstance(version, int) or version != SCHEMA_VERSION:
            raise GraphValidationError(f"Unsupported schema version: {version!r}")
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise GraphValidationError("'nodes' and 'edges' must be lists")
        model = cls()
        for raw in nodes:
            model.add_node(GraphNode.from_dict(raw))
        seen_inputs = set()
        for raw in edges:
            edge = GraphEdge.from_dict(raw)
            if edge.id in model.edges:
                raise GraphValidationError(f"Duplicate edge id: {edge.id}")
            if edge.src_node == edge.dst_node:
                raise GraphValidationError(f"Self edge: {edge.id}")
            key = (edge.dst_node, edge.dst_port)
            if key in seen_inputs:
                raise GraphValidationError(f"Input connected more than once: {edge.dst_node}.{edge.dst_port}")
            seen_inputs.add(key)
            model.edges[edge.id] = edge
        model.topological_order()
        return model

    @classmethod
    def from_json(cls, text: str) -> "GraphModel":
        if not text.strip():
            return cls()
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise GraphValidationError(f"Graph JSON is not valid JSON: {exc}") from exc
        return cls.from_dict(data)
