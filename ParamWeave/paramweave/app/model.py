"""UI-independent graph data model.

This module intentionally has no FreeCAD or Qt imports so it can be unit tested
with ordinary Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
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
        return cls(
            id=str(data["id"]),
            type_id=str(data["type_id"]),
            label=str(data.get("label", data["type_id"])),
            position=[float(v) for v in data.get("position", [0.0, 0.0])],
            params=dict(data.get("params", {})),
        )


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
        return cls(
            id=str(data["id"]),
            src_node=str(data["src_node"]),
            src_port=str(data["src_port"]),
            dst_node=str(data["dst_node"]),
            dst_port=str(data["dst_port"]),
        )


class GraphValidationError(ValueError):
    pass


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
        version = int(data.get("schema_version", 0))
        if version != SCHEMA_VERSION:
            raise GraphValidationError(f"Unsupported schema version: {version}")
        model = cls()
        for raw in data.get("nodes", []):
            model.add_node(GraphNode.from_dict(raw))
        for raw in data.get("edges", []):
            edge = GraphEdge.from_dict(raw)
            if edge.id in model.edges:
                raise GraphValidationError(f"Duplicate edge id: {edge.id}")
            model.edges[edge.id] = edge
        model.topological_order()
        return model

    @classmethod
    def from_json(cls, text: str) -> "GraphModel":
        if not text.strip():
            return cls()
        return cls.from_dict(json.loads(text))
