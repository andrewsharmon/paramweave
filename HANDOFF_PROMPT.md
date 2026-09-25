# Prompt to give the coding agent

You are taking over development of **ParamWeave**, a native FreeCAD visual graph/patch workbench. Read `AGENTS.md`, `README.md`, and all files in `docs/` before changing architecture.

The agreed product direction is:

- run directly inside FreeCAD;
- target current stable FreeCAD, first verified on macOS, but remain platform-agnostic;
- present a resizable graph pane beside FreeCAD's ordinary 3D model viewport;
- allow users to select FreeCAD objects/faces/edges/vertices and create graph references to them;
- include constructive geometry nodes as well as reference/measurement nodes;
- embed graph state in the `.FCStd` document;
- keep exact geometry authoritative in FreeCAD/OpenCascade rather than serializing geometry into graph JSON;
- keep the project license undecided for now, with a preference for permissive-compatible licensing and dependencies.

The starter intentionally uses FreeCAD's bundled Qt/PySide `QGraphicsScene` rather than NodeGraphQt or another external graph GUI framework. Preserve the separation between graph core, FreeCAD adapter/runtime, and Qt view so the graph UI can be replaced later.

## Your first job

Run and harden the existing starter under **FreeCAD 1.1.3 stable on macOS**.

1. Install/symlink `ParamWeave/` into FreeCAD's user `Mod` directory.
2. Activate the workbench and resolve any API/Qt compatibility issues.
3. Record the exact FreeCAD/Python/Qt/PySide/OCC build tested.
4. Verify there is only one dock and one selection observer after repeated workbench activation.
5. Verify graph persistence through `.FCStd` save/close/reopen.
6. Verify Box and Cylinder nodes can wire into Cut/Fuse and evaluate to ordinary `Part::Feature` output objects.
7. Verify whole-object, face, edge, and vertex reference nodes can be created from FreeCAD selection and that graph/viewport selection synchronizes both directions.
8. Add automated or reproducible smoke tests for anything you fix.

Do not begin solver, CAM, or LinuxCNC/HAL integration until the base graph/CAD interaction is stable.

## Important known limitations in the starter

- Port connection is click-output then click-input, not drag-to-wire yet.
- Undo/redo is not integrated with FreeCAD transactions yet.
- Topological recovery is deliberately conservative and provisional.
- Graph changes are persisted frequently; movement persistence should eventually be debounced/transactional.
- Generated intermediate shapes are not yet intelligently hidden.
- Node parameters use basic text editing rather than FreeCAD quantity/unit widgets.
- No schema migration framework exists beyond rejecting unsupported versions.
- No document observer yet automatically rebinds the graph when the active document changes while the workbench stays open.

Treat these as planned work, not reasons to redesign the core boundaries.
