"""Explicit node registry and port metadata.

Pure Python: no FreeCAD or Qt imports, so it can be unit tested directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


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
    # Document type of the generated object. Specs that need something other
    # than a Part::Feature supply ``materialize(obj, values)``, which writes the
    # node's outputs into ``obj`` and may return extra outputs (e.g. the
    # recomputed "shape") plus an optional "_warning".
    generated_type: str = "Part::Feature"
    materialize: Optional[Callable[..., Optional[Dict[str, Any]]]] = None
    # Text parameters restricted to a fixed set of values, shown as a dropdown
    # in the property panel: ``{param key: (allowed, values)}``. Evaluation
    # still validates the value, since graph files are untrusted.
    choices: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
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
        # Every numeric parameter can be driven by an optional Number wire
        # (constant, expression, measured or referenced dimension). The port is
        # named after the parameter; see apply_driven_params().
        taken = {p.name for p in spec.inputs}
        for key, value in spec.default_params.items():
            if _is_number(value) and key not in taken:
                spec.inputs.append(PortSpec(key, "Number", required=False))
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
    if src in {"CAD.Solid", "CAD.Face", "CAD.Edge", "CAD.Vertex", "CAD.Wire"} and dst == "CAD.Shape":
        return True
    return False


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def driven_param_names(spec: NodeSpec, connected_ports) -> List[str]:
    """Parameters of ``spec`` currently overridden by a connected wire."""
    return [k for k, v in spec.default_params.items() if _is_number(v) and k in connected_ports]


def apply_driven_params(params: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``params`` with numeric entries replaced by same-named wired inputs.

    Integer parameters (e.g. polygon sides) only accept integral values.
    """
    out = dict(params)
    for key, old in params.items():
        if key not in inputs or not _is_number(old):
            continue
        value = inputs[key]
        if not _is_number(value):
            raise ValueError(f"input '{key}' must be a number, got {value!r}")
        if isinstance(old, int):
            if float(value) != int(value):
                raise ValueError(f"input '{key}' must be a whole number, got {value!r}")
            value = int(value)
        out[key] = value
    return out
