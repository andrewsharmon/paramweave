# Recorded design decisions

## 2026-09-25 initial handoff


### Project name
**Decision:** Use **ParamWeave** as the project/workbench name.

The earlier starter name `GraphCAD` was retired after collision screening. Public UI strings, Python package/module paths, FreeCAD object/property namespaces, command IDs, documentation, and packaging metadata should use `ParamWeave` / `paramweave`.

### UI host
**Decision:** Native FreeCAD workbench.

The user does not want a separate browser application for the initial project.

### Workspace layout
**Decision:** Graph pane beside the normal FreeCAD model/3D rendering.

The first implementation uses a docked pane because it gives a native resizable split without replacing FreeCAD's central viewer.

### Initial functionality
**Decision:** Reference nodes **and constructive nodes** in the first scope.

The prototype should already demonstrate that the graph can make exact FreeCAD geometry, not merely annotate existing objects.

### Platform
**Decision:** Verify first against current stable FreeCAD on macOS; keep code platform-agnostic.

No absolute macOS paths belong in runtime code.

### Persistence
**Decision:** Embed graph state inside `.FCStd`.

Use a FreeCAD document object/property to store versioned JSON. Do not directly rewrite the FCStd ZIP/XML format as the normal editing mechanism.

### Geometry authority
**Decision:** FreeCAD/OpenCascade owns exact geometry.

The graph stores node topology/parameters/references and maps shape-producing nodes to ordinary FreeCAD objects.

### License
**Decision:** Not selected yet.

Preference is maximally permissive while compatible. Avoid unnecessary copyleft/external dependencies until a deliberate choice is made.

### Graph UI dependency
**Decision:** Start with the Qt graphics primitives already available inside FreeCAD rather than depending on NodeGraphQt.

Rationale: fewer installation/version problems, especially during FreeCAD's Qt6 transition; the graph view remains replaceable.

## 2026-09-25 first hardening pass

### Repository
**Decision:** The project lives in `~/git/paramweave` (renamed from `freecad-paramweave-starter`) as its own git repository on `main`. No remote yet — publishing waits for a license decision.

### Undo/redo
**Decision:** Graph edits are FreeCAD document transactions, not a separate Qt undo stack.

Every mutation goes through `GraphWorkspace.edit()`, which opens a `ParamWeave: <action>` transaction (unless one is already active), mutates the model and writes `GraphJSON`. FreeCAD's Undo/Redo restores the property; the workspace reloads the model on `slotUndoDocument`/`slotRedoDocument`. Evaluation is its own transaction, so undoing it removes/restores generated objects. Node moves are persisted once on mouse release.

### Document binding
**Decision:** The workspace binds to exactly one document (by internal `Name`) and only writes there.

An App document observer schedules a rebind on create/activate/restore and drops the binding synchronously on delete. Loading never creates the store object; it is created on the first real edit. If embedded JSON fails validation, editing is disabled for that document and the data is left untouched.

### Scene is a view
**Decision:** `GraphScene` and `PropertyPanel` never mutate the model; they emit requests (connect, move, delete, edit parameter/label) that the workspace applies.

### Generated objects
**Decision:** Only nodes whose spec sets `generates_object=True` get a `Part::Feature`; reference nodes never copy referenced geometry.

A generated object is created visible only if its node is terminal (no generating consumer); intermediates are hidden on each evaluation, terminal outputs keep the user's visibility. Deleting a node deletes its generated object unless another document object depends on it, in which case it is kept and a warning is printed.

### Reference recovery
**Decision:** Geometric recovery must be unique: if more than one candidate is within `RECOVERY_TOLERANCE`, resolution fails as ambiguous.

A successful recovery never rewrites the stored reference; the node shows a `! check` warning naming the old and substituted sub-element. Exact-name resolution does not yet verify that the named sub-element is still the same geometry (topological naming problem; see M5).

### Unknown node types
**Decision:** Unregistered `type_id`s load as inert placeholder nodes (ports inferred from edges), are never evaluated, and are saved back unchanged.

## 2026-09-30 sketch nodes

### Sketch values flow as data; only the Sketch node makes an object
**Decision:** Sketch element and modifier nodes pass a plain JSON-like `Sketch.Geometry` value (`paramweave/app/sketch_model.py`, pure Python): sketch-local elements plus constraints that refer to elements by index (negative indices are the sketch axes). Modifiers never mutate their input. The **Sketch** node materializes the value into an ordinary `Sketcher::SketchObject` (rewritten, not duplicated, on each evaluation); solver failures and conflicting/redundant constraints are shown as a node warning.

To support this, `NodeSpec` gained `generated_type` and an optional `materialize(obj, values)` hook; nodes without one keep the `Part::Feature` behaviour.

### Existing sketches: read-only copy, or explicit driving
**Decision:** **Read Sketch** converts a document sketch into a `Sketch.Geometry` value and never changes it. Unsupported geometry (splines, ellipses…), external geometry and unknown constraint types raise an error instead of being dropped. **Drive Sketch Constraint** is the one node that writes into a user-owned object: it sets a *named* dimensional constraint, only when the value differs, inside the evaluation transaction (so it is undoable). It never matches constraints by index.

Angles are degrees in graph data and radians only at the Sketcher boundary.

## 2026-09-30 driven dimensions

### Every numeric parameter is drivable by a wire
**Decision:** At registration, each numeric default parameter gets an optional `Number` input port with the same name. When connected, the evaluator overrides the parameter for that evaluation only (`apply_driven_params`); the stored value is kept and shown as "driven by input" in the property panel. Integer parameters accept only whole numbers. No schema change: ports are derived from specs, not stored.

### Expressions are interpreted, never `eval()`ed
**Decision:** Expression nodes parse with `ast` and interpret a whitelist (numbers, the node's `a`–`d` inputs, `pi`/`e`, arithmetic, comparisons, conditional expressions, a fixed function table). Attributes, subscripts, strings, keywords and unknown names are rejected; length and exponent size are capped. Trig functions work in degrees, matching sketch angles.

### Variables are explicit wires
**Decision:** Expressions see only their wired inputs, not graph-wide names, so evaluation order stays visible in the graph. Document-level variables come from **Document Variable** (Spreadsheet alias / VarSet property), resolved by internal name first, then by a unique label; an ambiguous label is an error.
