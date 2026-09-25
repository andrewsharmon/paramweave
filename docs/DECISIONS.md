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
