# Roadmap and acceptance criteria

## Phase A — prove native integration

### A1 Workbench lifecycle
Acceptance:
- FreeCAD 1.1.3 macOS starts with workbench installed.
- Activating ParamWeave creates exactly one graph dock.
- Deactivating/reactivating does not duplicate selection observers or widgets.
- No third-party Python package is required.

### A2 Persistence
Acceptance:
- Create two nodes and one edge.
- Save `.FCStd`.
- Close/reopen document.
- Graph layout, parameters, IDs, and edge reappear unchanged.

### A3 Constructive geometry
Acceptance:
- Box and Cylinder evaluate to valid FreeCAD shapes.
- Cut/Fuse consume connected shapes.
- Re-evaluation updates existing generated objects rather than creating duplicates.
- Invalid dimensions produce a node error, not a corrupted document.

### A4 References
Acceptance:
- Whole object, face, edge, and vertex references can be captured.
- Graph → viewport selection works.
- Viewport → graph selection works.
- Deleting referenced geometry marks the node broken.
- No silent rebinding to an ambiguous sub-element.

## Phase B — make the graph editor practical

- Drag-to-wire.
- Type-aware connection highlighting.
- Node search.
- Copy/paste/duplicate/delete.
- Group/frame/comment nodes.
- FreeCAD-integrated undo/redo.
- Quantity editors and units.
- Multi-selection/reference-set node.
- Better topology reference strategy.
- Graph schema migration test suite.

## Phase C — deeper CAD integration

- Sketch/reference geometry nodes.
- Datum plane/axis/point nodes.
- Revolve, loft, sweep, fillet, chamfer, array/pattern.
- Placement/orientation nodes.
- FreeCAD expression/property reference nodes.
- Drag FreeCAD tree objects/properties into graph.
- Viewport manipulators linked to graph parameters.
- Subgraphs/macros with typed public ports.

## Phase D — engineering dataflow

After the CAD core is stable:

- Gmsh mesh node adapter.
- Elmer study nodes.
- OpenFOAM study nodes.
- VTK result/field nodes.
- FreeCAD CAM job/toolpath nodes.
- LinuxCNC/HAL configuration nodes.

Keep heavy solver data out of the JSON document property; store durable result references/metadata and use external files or FreeCAD-native objects as appropriate.

## Phase E — procedural/control representation

Do not force sequential logic into the dataflow graph. Evaluate a complementary block/state-machine surface for:

- probing routines;
- tool-change procedures;
- event logic;
- machine startup/shutdown;
- error recovery.

The dataflow graph remains best for continuous dependencies, geometry, signals, and solver coupling.
