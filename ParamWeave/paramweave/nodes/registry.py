"""Explicit node registry and port metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List


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

    def all(self) -> List[NodeSpec]:
        return list(self._specs.values())


registry = NodeRegistry()


def types_compatible(src: str, dst: str) -> bool:
    if src == "Any" or dst == "Any":
        return True
    if src == dst:
        return True
    # Minimal starter covariance. Expand into a proper type lattice later.
    if src in {"CAD.Solid", "CAD.Face", "CAD.Edge", "CAD.Vertex"} and dst == "CAD.Shape":
        return True
    return False
