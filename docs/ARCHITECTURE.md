# Architecture

## System boundary

ParamWeave is a FreeCAD workbench, not a replacement CAD kernel.

```text
┌──────────────────────────── FreeCAD GUI ────────────────────────────┐
│                                                                     │
│  Model tree       3D view                     Graph dock             │
│      │                │                           │                  │
│      └──── FreeCAD selection API ────────────────┤                  │
│                                                  │                  │
└──────────────────────────────────────────────────┼──────────────────┘
                                                   │
                                            Graph GUI adapter
                                                   │
                              ┌────────────────────┴──────────────────┐
                              │       UI-independent graph model      │
                              │ nodes / edges / IDs / typed ports     │
                              └────────────────────┬──────────────────┘
                                                   │
                                   FreeCAD runtime/evaluator
                                                   │
                   ┌───────────────────────────────┼──────────────────┐
                   ▼                               ▼                  ▼
             FreeCAD document                  Part/OCC          future adapters
             persistence                       geometry          FEM/CAM/HAL
```

## Why the graph is a dock pane

The first implementation uses a docked Qt widget on the right. FreeCAD's existing 3D view stays in its normal central MDI area. Docking gives the desired resizable split-pane behavior without reparenting or replacing the native 3D viewer.

Later, if a true central split view proves necessary, keep the same graph widget/model and change only the mounting strategy.

## Persistence model

The graph is embedded in the FreeCAD document as a hidden-ish application object:

```text
App::FeaturePython  ParamWeaveGraph
├── SchemaVersion : integer
└── GraphJSON     : string
```

`GraphJSON` contains only graph/model data:

```json
{
  "schema_version": 1,
  "nodes": [
    {
      "id": "uuid",
      "type_id": "primitive.box",
      "label": "Box",
      "position": [120.0, 80.0],
      "params": {"length": 10.0, "width": 10.0, "height": 10.0}
    }
  ],
  "edges": []
}
```

Exact OpenCascade shapes stay in the FreeCAD document.

## Generated object mapping

Shape-producing nodes get/update a normal `Part::Feature` under an `App::DocumentObjectGroup` named `ParamWeave_Generated`.

Each generated object receives:

```text
ParamWeaveNodeId : App::PropertyString
```

This makes node-to-object lookup stable even if object labels change.

Recommended future behavior:

- non-terminal generated nodes default hidden;
- terminal shape outputs default visible;
- allow the user to pin/show intermediates;
- deleting a graph node should prompt/define what happens to its generated object;
- do not delete user-owned referenced objects.

## Node registry

Node types are explicitly registered in Python code. Serialized graph data contains a `type_id` but never code to execute.

Example node spec:

```text
primitive.box
 inputs:  none
 outputs: shape: CAD.Shape
 params:  length, width, height
```

The graph scene asks the registry what ports to draw. The evaluator asks the same registry which evaluation callback to run. This avoids duplicating node semantics in the GUI.

## Typed ports

Initial type vocabulary:

```text
Any
Number
Length
Vector
CAD.Shape
CAD.Solid
CAD.Face
CAD.Edge
CAD.Vertex
Reference
```

The starter only enforces exact type or `Any` compatibility. Expand later with subtype/coercion rules, e.g. `CAD.Solid -> CAD.Shape`.

Never use color alone to communicate type.

## Evaluation

Evaluation is demand-driven/topological at first:

1. validate graph;
2. topologically order acyclic dependency graph;
3. collect connected input values;
4. invoke evaluator callback for each node;
5. cache output dictionaries by node ID;
6. update generated FreeCAD objects for shape outputs;
7. report node-level errors without corrupting the graph.

Future improvements:

- dirty propagation;
- output hashing/caching;
- background jobs for non-FreeCAD compute;
- cancellation;
- cyclic/simulation nodes with explicit iteration semantics rather than accidental dependency cycles.

## Selection and references

A reference node stores a document-local reference record approximately like:

```json
{
  "object_name": "Pad",
  "subelement": "Face12",
  "signature": {
    "shape_type": "Face",
    "area": 100.0,
    "center": [5.0, 5.0, 0.0],
    "bbox": [0.0, 0.0, 0.0, 10.0, 10.0, 0.0]
  }
}
```

Resolution policy:

1. resolve exact object name;
2. resolve exact sub-element name if still present;
3. if missing, search candidates on the same object using geometric signature;
4. accept automatic recovery only above a strict confidence threshold and with a unique best match;
5. otherwise mark the node broken and require user repair.

The starter only implements a conservative approximation of steps 1–3. Improve this before depending on references for production designs.

## Undo/redo

This is an explicit early-design task. Graph changes should eventually participate in FreeCAD document transactions, but a Qt graphics command stack must not diverge from document state.

Preferred direction:

```text
user graph mutation
     ↓
FreeCAD transaction
     ↓
mutate GraphModel
     ↓
persist GraphJSON
     ↓
update GUI
```

Investigate `openTransaction`, `commitTransaction`, and document observers. Do not bolt an independent permanent undo history onto the graph UI without reconciling it with FreeCAD undo.

## Qt compatibility

Use FreeCAD's compatibility import:

```python
from PySide import QtCore, QtGui, QtWidgets
```

Do not install another PySide into FreeCAD's runtime. Keep Qt enum compatibility helpers centralized.

## Future extension boundaries

Once CAD graph interaction is stable, add adapters rather than monolithic nodes:

```text
Graph core
  ├── CAD adapter (FreeCAD/OCC)
  ├── Mesh adapter (Gmsh)
  ├── FEM adapter (Elmer)
  ├── CFD adapter (OpenFOAM)
  ├── CAM adapter (FreeCAD CAM)
  └── control adapter (LinuxCNC/HAL)
```

Real-time machine control must remain in LinuxCNC or another appropriate real-time controller. The graph can configure/supervise it but should not become the servo loop scheduler.
