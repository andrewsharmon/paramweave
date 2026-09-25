"""Explicit node registry and port metadata.

Pure Python: no FreeCAD or Qt imports, so it can be unit tested directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class PortSpec:
    name: str
    type_name: str
    required: bool = True


@dataclass
class NodeSpec:
    type_id: str
    title: str
    category: str
    inputs: List[PortSpec] = field(default_factory=list)
    outputs: List[PortSpec] = field(default_factory=list)
    default_params: Dict[str, Any] = field(default_factory=dict)
    evaluate: Callable[..., Dict[str, Any]] = lambda *_args, **_kwargs: {}
    # When True, the node's "shape" output is mirrored into an ordinary
    # Part::Feature so the result is inspectable without the plugin. Reference
    # nodes leave this False: their shape already lives in the document.
    generates_object: bool = False
    # Placeholder specs stand in for unregistered type_ids found in a file.
    placeholder: bool = False

    def input(self, name: str) -> Optional[PortSpec]:
        return next((p for p in self.inputs if p.name == name), None)

    def output(self, name: str) -> Optional[PortSpec]:
        return next((p for p in self.outputs if p.name == name), None)


class NodeRegistry:
    def __init__(self):
        self._specs: Dict[str, NodeSpec] = {}

    def register(self, spec: NodeSpec) -> NodeSpec:
        if spec.type_id in self._specs:
            raise ValueError(f"Node type already registered: {spec.type_id}")
        self._specs[spec.type_id] = spec
        return spec

    def get(self, type_id: str) -> NodeSpec:
        try:
            return self._specs[type_id]
        except KeyError as exc:
            raise KeyError(f"Unknown ParamWeave node type: {type_id}") from exc

    def find(self, type_id: str) -> Optional[NodeSpec]:
        return self._specs.get(type_id)

    def all(self) -> List[NodeSpec]:
        return list(self._specs.values())


registry = NodeRegistry()


def placeholder_spec(node_id: str, type_id: str, model) -> NodeSpec:
    """Describe an unregistered node well enough to draw it and its wires.

    Graph files may come from newer plugin versions or other people. Rather
    than refusing to display the graph, show an inert node whose ports are
    inferred from the edges that touch it. It is never evaluated.
    """
    inputs = sorted({e.dst_port for e in model.edges.values() if e.dst_node == node_id})
    outputs = sorted({e.src_port for e in model.edges.values() if e.src_node == node_id})
    return NodeSpec(
        type_id=type_id,
        title=f"Unknown: {type_id}",
        category="Unknown",
        inputs=[PortSpec(name, "Any") for name in inputs],
        outputs=[PortSpec(name, "Any") for name in outputs],
        placeholder=True,
    )


def types_compatible(src: str, dst: str) -> bool:
    if src == "Any" or dst == "Any":
        return True
    if src == dst:
        return True
    # Minimal starter covariance. Expand into a proper type lattice later.
    if src in {"CAD.Solid", "CAD.Face", "CAD.Edge", "CAD.Vertex"} and dst == "CAD.Shape":
        return True
    return False
