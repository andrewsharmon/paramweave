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

## 2026-09-30 finger-jointed box example

### Finger joints are a sketch element, not a solid feature
**Decision:** `Finger Joint Panel` produces one closed sketch outline per panel (edge modes `out`/`in`/`flat`/`recessed`, odd finger counts so edges are symmetric). Joints are made by giving mating edges opposite modes and the same count, so panels stay flat 2D profiles that can be exported for cutting. Kerf is handled by the panel's `kerf` parameter (see below).

### Extrude follows the sketch plane
**Decision:** Extrude now orients its direction by the input shape's placement +Z (the sketch normal) rather than the wire winding, so profiles extrude predictably to the side the sketch offset implies.

### Examples are pure graph builders
**Decision:** Example graphs live in `paramweave/examples/` as functions that add nodes/edges to a `GraphModel` (no FreeCAD import), exposed through menu commands and `GraphWorkspace.insert_example`. Their tests check real geometry: the finger box's panels must tile the box shell exactly (sum of volumes equals the shell and equals the fused volume).

## 2026-09-30 GUI editing and tutorials

### Duplicate and re-wiring
**Decision:** Ctrl+D (⌘D) / "Duplicate Selected" copies the selected nodes, the wires among them, and the wires feeding them from outside, so a copied chain stays driven by the same constants. Wiring into an occupied input replaces the old wire in one undoable step (a failed replacement, e.g. a cycle, restores the old wire).

### The graph view claims its own shortcuts
**Decision:** `GraphView` accepts its keys (Ctrl/⌘+D, Delete, Backspace, F, Esc) in Qt's ShortcutOverride phase. Without this, FreeCAD's application shortcuts intermittently swallowed Ctrl+D while the graph had focus (found while scripting the tutorial).

### Tutorials are executable
**Decision:** Each tutorial has a GUI script (`tests/gui/tutorial_*.py`) that performs every step through GUI interactions (context-menu add signal, port clicks, typing in the property panel, Ctrl-click, Ctrl+D, Delete, dragging, the Evaluate button), verifies the resulting geometry, and regenerates the tutorial's screenshots. The Markdown source is rendered to PDF by `tools/build_tutorial_pdf.py`, so text, pictures and the verified workflow stay in sync.

## 2026-09-30 kerf allowance

### Kerf grows the cut outline, not the model
**Decision:** `Finger Joint Panel` takes `kerf` (default 0) and offsets its whole outline outward by `kerf / 2` (exact for right-angled outlines: each vertex moves by the sum of its edges' outward normals). Fingers get `kerf` wider and slots `kerf` narrower, so parts fit tight after cutting. The sketch is the cutting outline, so the 3D assembly overlaps by the kerf; nominal geometry is kerf 0. Kerf must be >= 0 and smaller than the narrowest finger/slot and the thickness. Loose-fit clearance (a negative allowance) is not supported yet.

### Parameters added later still work in old graphs
**Decision:** The evaluator fills parameters missing from a saved node with the node type's current defaults before applying wired overrides, so a parameter introduced after a graph was saved (like `kerf`) evaluates with its default and can be driven by a wire. Stored node params are not rewritten.

## 2026-09-30 frames

### Frames are layout data with geometric membership (schema v2)
**Decision:** Frames are a separate top-level `frames` list (id, label, rect, color, note), not nodes, so they never enter evaluation or dependency ordering. A node belongs to a frame when its position is inside the frame's rect; nested frames are frames wholly inside another. No member IDs are stored, so deleting or duplicating nodes cannot leave dangling references, and dropping a node into a frame is enough to add it. Schema bumped to v2; v1 graphs migrate with no frames.

### Interaction
**Decision:** Only a frame's title bar grabs it; presses in the body fall through so rubber-band selection works inside frames. Dragging a frame carries its unselected contents (computed from the model at press time, so nothing moves twice) and records node and frame moves as one undo step. Deleting a frame keeps its nodes. Duplicating a frame copies its contents with it. Comments are frames with a note.

## 2026-09-30 cut file export

### Export is an explicit command, never a graph node
**Decision:** DXF/SVG export runs only from the **Export Cut Files…** command with a user-chosen path. There is no export node: graph files are untrusted input, and a node carrying a file path would let a shared graph write files on Evaluate.

### Own minimal writers, no new dependency
**Decision:** `paramweave/app/cutfile.py` (pure Python) writes AutoCAD R12 ASCII DXF (LINE/ARC/CIRCLE, `$INSUNITS` mm, one layer per panel) and SVG (mm-sized, red 0.01 mm hairline strokes, one titled group per panel) directly from `Sketch.Geometry` values, so no Draft/ezdxf dependency is needed. Panels are placed in sketch-local coordinates and shelf-packed (tallest first) within a sheet width with a gap. Construction elements and points are skipped; kerf is already in the outlines. SVG keeps DXF's y-up orientation so both files show the same layout. A FreeCAD console test reads the DXF back with FreeCAD's own importer and checks edge count and total length.

## 2026-09-30 license

### Project license: Apache-2.0
**Decision:** ParamWeave is licensed Apache-2.0 (`LICENSE`, `NOTICE`, `package.xml`). It is permissive, widely approved for use inside organizations, carries an explicit patent grant, and is compatible with FreeCAD (LGPL-2.1+), PySide/Qt and the FreeCAD Addon Index. Extension packages that build on ParamWeave live in their own repositories under their own licenses and register node types through the explicit registry; graph files that use an extension's nodes must still open without it, with those nodes marked missing. Contributions are accepted under Apache-2.0 (inbound = outbound).

## 2026-09-30 kerf fit test and corner relief

### The kerf test is built from Finger Joint Panels, one node per orientation
**Decision:** `Kerf Fit Test` (`sketch.kerf_test`, pure logic in `paramweave/app/fit_test.py`) builds its coupons with the same `finger_panel` code as real parts, so the test measures exactly the kerf compensation the box uses. One node makes one orientation. The example graph has three nodes (0°, 90°, 45°) so each orientation is its own sketch and cut group. The angle matters because a finger's width comes from cuts perpendicular to the joint edge, and lasers often have direction-dependent kerf (elliptical spot, polarisation, per-axis mechanics). Pairs are marked with index holes rather than engraved text, so any cutter that can cut the outline can cut the marks.

### Pairs are turned in place and packed as strips
**Decision:** Each pair is rotated about its own centre and the pairs are laid in one row along X. The pitch is the smallest separation (bounding box, or either axis of the turned pair rectangle grown by the largest kerf) that keeps a `gap` between pairs, so 45° pairs nest. Every orientation is therefore a short, wide strip, and the strips stack into one rectangular sheet. Rotating a whole set as a block was dropped: the 45° set's bounding box wasted most of the sheet.

### Corner relief is part of the outline, chosen by a dropdown
**Decision:** `relieved_outline` in `sketch_model` replaces each reflex (inside) corner of a right-angled outline with a circular arc of the tool radius that passes through the sharp corner: `dogbone` (centre on the bisector) or T-bones (centre on one edge). `finger_panel` records which edges are finger/slot walls, so `tbone_depth` notches the slot bottom (relief goes deeper, walls stay straight) and `tbone_side` notches the wall. Relief is applied after the kerf offset. A tool too large for an edge is an error, never a silently clipped relief. Style values live in `NodeSpec.choices`, which the property panel shows as a dropdown (also used for edge modes and sketch planes). Evaluation still validates the value, because graph files are untrusted, and an unknown stored value is shown rather than silently replaced.
