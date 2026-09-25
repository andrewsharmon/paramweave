# Coding-agent handoff: ParamWeave

## Mission

Build a robust native FreeCAD workbench that combines the normal FreeCAD 3D modeling viewport with a visual patch/dataflow graph. The key user interaction is:

1. select an object, face, edge, vertex, or suitable property in FreeCAD;
2. create/reference it in the graph;
3. wire it into constructive, measurement, analysis, CAM, or eventually machine-control nodes;
4. have graph-created geometry remain ordinary FreeCAD document objects whenever practical.

This repository is a starter, not a frozen design. Preserve the architectural boundaries below while iterating quickly.

## Decisions already made

- Native FreeCAD workbench.
- Current stable FreeCAD on macOS is the first verification platform; code must remain platform-agnostic.
- Graph state embedded in the `.FCStd` document.
- Initial node set includes constructive nodes, not only references.
- License not selected yet; prefer permissive-compatible dependencies and avoid introducing restrictive dependencies without an explicit decision.
- FreeCAD document/OpenCascade objects are authoritative for exact CAD geometry.
- Graph model must be UI-independent and serializable.

## Non-negotiable architecture

### 1. Three layers

Keep these separate:

- **Graph core**: nodes, edges, IDs, types, serialization, dependency ordering. Must be testable without FreeCAD or Qt.
- **FreeCAD adapter/runtime**: reads/writes document objects, resolves references, evaluates geometry nodes, persists JSON.
- **Qt GUI**: displays graph and sends user actions to the core/runtime. It must never become the only source of graph truth.

### 2. Exact geometry stays in FreeCAD

Graph JSON stores identifiers, parameters, graph topology, and references. It must not serialize B-rep geometry blobs.

### 3. Reference stability is a first-class problem

`ObjectName + Face12` is only the first lookup. Preserve room for stable topology naming and semantic/geometric recovery. Never silently rebind an ambiguous broken reference.

### 4. Generated geometry should be inspectable without the plugin

When a graph node outputs a shape, create/update an ordinary `Part::Feature` (or a more appropriate native feature later). Store the graph node UUID on that document object.

### 5. The graph view is replaceable

The starter uses `QGraphicsScene/QGraphicsView` to avoid dependency and Qt-version problems. Keep the graph core clean enough that a future QtNodes/NodeGraphQt/web view can replace it.

## First task: run/harden the starter

Before extending functionality:

1. Install the `ParamWeave/` folder into the FreeCAD user `Mod` directory.
2. Run on FreeCAD 1.1.3 macOS ARM64 if available.
3. Fix import/runtime issues without adding a large dependency.
4. Verify graph dock creation/removal is idempotent.
5. Verify a graph survives save/reopen.
6. Verify Box → Cut and reference selection workflows.
7. Add a short compatibility note containing FreeCAD/Python/Qt/PySide/OCC versions actually tested.

## Milestone order

### M0 — Workbench shell
- Loads on FreeCAD 1.1.3.
- Graph dock appears to the right of 3D view.
- Toggle command works.
- No duplicate docks/observers after workbench reactivation.

### M1 — Persistent graph core
- Graph model serializes to stable JSON schema.
- Embedded in document.
- Save/reopen round-trip works.
- Mutations participate sensibly in FreeCAD undo/redo or are clearly documented if not yet supported.

### M2 — Selection/reference bridge
- Create reference node from whole object, face, edge, vertex.
- Selecting graph reference highlights FreeCAD geometry.
- Selecting referenced geometry highlights corresponding graph nodes.
- Broken reference is visibly marked and never silently rebound if ambiguous.

### M3 — Constructive nodes
- Box, Cylinder, Translate, Fuse, Cut.
- Typed ports prevent clearly invalid connections.
- Evaluation is topological and deterministic.
- Dirty propagation avoids recomputing unrelated branches.
- Generated FreeCAD objects are updated, not duplicated every evaluation.

### M4 — Usable node editing
- Parameter/property editor.
- Node creation search/context menu.
- Delete/duplicate.
- Undo/redo.
- Copy/paste.
- Frame/group/comment nodes.
- Zoom/pan ergonomics.

### M5 — Better FreeCAD integration
- Drag tree/object/subelement to graph if practical.
- Drag FreeCAD properties to graph.
- Native quantity/unit editing.
- Better persistent references using FreeCAD topology facilities.
- Viewport handles for graph nodes such as point/vector/plane.

Do not start solver/CAM/HAL integration until M0–M4 are reliable.

## Coding style

- Python 3.11+ syntax only if compatible with the FreeCAD target.
- Type hints are encouraged in graph-core modules.
- Keep imports of `FreeCAD`, `FreeCADGui`, and `Part` out of pure graph-core files.
- Prefer small adapters over global state.
- IDs stored in graph files must be UUID strings and never depend on display labels.
- User-facing labels may change without breaking references.
- Every schema change must increment/migrate schema version.

## Testing

Pure graph tests must run with ordinary Python:

```bash
python -m unittest discover -s tests -v
```

FreeCAD integration tests should eventually be runnable using FreeCAD's console executable where supported. Do not make ordinary unit tests require a GUI.

## Security / trust boundary

Treat embedded graph JSON as untrusted input when opening files from others. Never `eval()` expressions or import arbitrary modules named by graph data. Node `type_id` values must resolve only through an explicit registry.

## License rule until decided

Do not add a project LICENSE file or copyright header claiming a license until the owner chooses one. Record dependency licenses in `LICENSE_STATUS.md`. Prefer MIT/BSD/Apache-style dependencies. If adding LGPL/GPL dependencies, document whether they are linked/imported or invoked out-of-process and why the dependency is needed.
