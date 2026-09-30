"""UI-independent graph data model.

This module intentionally has no FreeCAD or Qt imports so it can be unit tested
with ordinary Python.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import json
import math
import uuid
from typing import Any, Dict, Iterable, List, Optional


SCHEMA_VERSION = 2
# Versions from_dict() can read. v1 -> v2 added the optional "frames" list.
SUPPORTED_SCHEMA_VERSIONS = (1, 2)

FRAME_COLORS = ("gray", "blue", "green", "yellow", "orange", "red", "purple")
FRAME_MIN_SIZE = (80.0, 50.0)


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


@dataclass
class GraphFrame:
    """A labeled box that groups the nodes placed inside it.

    Membership is geometric: a node belongs to the frame when its position
    (top-left corner) lies inside ``rect``. Frames carry no graph semantics and
    are never evaluated; ``note`` makes a frame double as a comment.
    """

    id: str
    label: str
    rect: List[float]  # [x, y, width, height]
    color: str = "gray"
    note: str = ""

    @classmethod
    def create(cls, label: str, rect: Iterable[float], color: str = "gray", note: str = "") -> "GraphFrame":
        return cls(new_id(), label, _frame_rect(list(rect), "frame"), color if color in FRAME_COLORS else "gray", note)

    def contains(self, x: float, y: float) -> bool:
        fx, fy, fw, fh = self.rect
        return fx <= x <= fx + fw and fy <= y <= fy + fh

    def contains_rect(self, rect: List[float]) -> bool:
        x, y, w, h = rect
        return self.contains(x, y) and self.contains(x + w, y + h)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "label": self.label, "rect": [float(v) for v in self.rect], "color": self.color, "note": self.note}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphFrame":
        _require_mapping(data, "frame")
        frame_id = _require_str(data, "id", "frame")
        where = f"frame {frame_id}"
        label = data.get("label", "")
        note = data.get("note", "")
        color = data.get("color", "gray")
        if not isinstance(label, str) or not isinstance(note, str) or not isinstance(color, str):
            raise GraphValidationError(f"{where}: label, note and color must be strings")
        # Unknown color names (e.g. from a newer version) render as gray but
        # are kept so saving does not lose them.
        return cls(frame_id, label, _frame_rect(data.get("rect"), where), color, note)


def _frame_rect(rect: Any, where: str) -> List[float]:
    if not isinstance(rect, (list, tuple)) or len(rect) != 4:
        raise GraphValidationError(f"{where}: rect must be [x, y, width, height]")
    try:
        values = [float(v) for v in rect]
    except (TypeError, ValueError) as exc:
        raise GraphValidationError(f"{where}: rect must be numeric") from exc
    if any(isinstance(v, bool) for v in rect) or not all(math.isfinite(v) for v in values):
        raise GraphValidationError(f"{where}: rect must be finite numbers")
    values[2] = max(values[2], FRAME_MIN_SIZE[0])
    values[3] = max(values[3], FRAME_MIN_SIZE[1])
    return values


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
        self.frames: Dict[str, GraphFrame] = {}

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()
        self.frames.clear()

    # -- frames -------------------------------------------------------------

    def add_frame(self, frame: GraphFrame) -> GraphFrame:
        if frame.id in self.frames:
            raise GraphValidationError(f"Duplicate frame id: {frame.id}")
        self.frames[frame.id] = frame
        return frame

    def create_frame(self, label: str, rect, color: str = "gray", note: str = "") -> GraphFrame:
        return self.add_frame(GraphFrame.create(label, rect, color, note))

    def remove_frame(self, frame_id: str) -> None:
        """Remove only the frame; the nodes inside it stay."""
        self.frames.pop(frame_id, None)

    def frame_contents(self, frame_id: str):
        """(node ids, nested frame ids) inside a frame, including nested contents."""
        frame = self.frames[frame_id]
        nodes = [n.id for n in self.nodes.values() if frame.contains(*n.position)]
        frames = [f.id for f in self.frames.values() if f.id != frame_id and frame.contains_rect(f.rect)]
        return nodes, frames

    def move_frame(self, frame_id: str, dx: float, dy: float) -> None:
        """Move a frame together with everything inside it."""
        nodes, frames = self.frame_contents(frame_id)
        for node_id in nodes:
            pos = self.nodes[node_id].position
            self.nodes[node_id].position = [pos[0] + dx, pos[1] + dy]
        for fid in [frame_id, *frames]:
            r = self.frames[fid].rect
            self.frames[fid].rect = [r[0] + dx, r[1] + dy, r[2], r[3]]

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

    def connect(
        self, src_node: str, src_port: str, dst_node: str, dst_port: str, replace: bool = False
    ) -> GraphEdge:
        """Add an edge. With ``replace``, a wire already feeding the input is swapped out."""
        if src_node not in self.nodes or dst_node not in self.nodes:
            raise GraphValidationError("Both edge endpoints must exist")
        if src_node == dst_node:
            raise GraphValidationError("Self edges are not supported")
        replaced = None
        for edge in list(self.edges.values()):
            if edge.dst_node == dst_node and edge.dst_port == dst_port:
                if edge.src_node == src_node and edge.src_port == src_port:
                    raise GraphValidationError("Duplicate edge")
                if not replace:
                    raise GraphValidationError(f"Input already connected: {dst_node}.{dst_port}")
                replaced = self.edges.pop(edge.id)
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
            if replaced is not None:
                self.edges[replaced.id] = replaced
            raise
        return edge

    def duplicate(
        self, node_ids: Iterable[str], offset=(40.0, 40.0), label_for=None, frame_ids: Iterable[str] = ()
    ) -> Dict[str, str]:
        """Copy nodes, the wires among them, and the wires feeding them from outside.

        Keeping incoming wires means a copied sub-graph stays driven by the same
        constants/upstream nodes. ``frame_ids`` are copied with the same offset
        (callers pass the frames' contents in ``node_ids``). Returns
        ``{old_id: new_id}`` for nodes and frames.
        """
        mapping_frames: Dict[str, str] = {}
        for old_id in [f for f in frame_ids if f in self.frames]:
            old = self.frames[old_id]
            label = label_for(old.label) if label_for else old.label
            rect = [old.rect[0] + offset[0], old.rect[1] + offset[1], old.rect[2], old.rect[3]]
            mapping_frames[old_id] = self.create_frame(label, rect, old.color, old.note).id
        ids = [n for n in node_ids if n in self.nodes]
        mapping: Dict[str, str] = {}
        for old_id in ids:
            old = self.nodes[old_id]
            label = label_for(old.label) if label_for else old.label
            pos = (old.position[0] + offset[0], old.position[1] + offset[1])
            mapping[old_id] = self.create_node(old.type_id, label, pos, copy.deepcopy(old.params)).id
        for edge in list(self.edges.values()):
            if edge.dst_node in mapping:
                src = mapping.get(edge.src_node, edge.src_node)
                self.connect(src, edge.src_port, mapping[edge.dst_node], edge.dst_port)
        mapping.update(mapping_frames)
        return mapping

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
            "frames": [self.frames[k].to_dict() for k in sorted(self.frames)],
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
        if isinstance(version, bool) or not isinstance(version, int) or version not in SUPPORTED_SCHEMA_VERSIONS:
            raise GraphValidationError(f"Unsupported schema version: {version!r}")
        # v1 -> v2: frames were introduced; a v1 graph simply has none.
        frames = data.get("frames", []) if version >= 2 else []
        if not isinstance(frames, list):
            raise GraphValidationError("'frames' must be a list")
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
        for raw in frames:
            model.add_frame(GraphFrame.from_dict(raw))
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
