# Graph data model v1

## Node

Required:

```text
id       UUID string
 type_id registered node type string
 label    user-visible string
position [x, y] graph coordinates
params   JSON object
```

Optional additions must be backwards compatible within schema v1 or trigger schema v2.

## Edge

```text
id        UUID string
src_node  UUID
src_port  output port name
dst_node  UUID
dst_port  input port name
```

Rules:

- only one incoming edge per ordinary input port initially;
- fan-out from an output is allowed;
- self-edge is invalid;
- duplicate identical edges are invalid;
- cycles are invalid for ordinary constructive nodes;
- future explicit feedback/iteration nodes may introduce controlled cyclic semantics.

## Reference record v1

Stored in a reference node's `params.reference`:

```json
{
  "document_label": "optional-human-hint",
  "object_name": "Pad",
  "object_label": "Pad",
  "subelement": "Face12",
  "signature": {
    "shape_type": "Face",
    "area": 152.4,
    "length": 44.2,
    "volume": 0.0,
    "center": [1.0, 2.0, 3.0],
    "bbox": [0.0, 0.0, 0.0, 2.0, 4.0, 6.0]
  }
}
```

`object_name` is the FreeCAD internal object name, not its mutable display label.

## Embedded storage object

Preferred internal FreeCAD name:

```text
ParamWeaveGraph
```

Properties:

```text
GraphJSON      App::PropertyString
SchemaVersion App::PropertyInteger
```

The object may be hidden from normal tree presentation later through a custom view provider, but keep the implementation simple until stable.
