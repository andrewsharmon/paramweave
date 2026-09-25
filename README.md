# ParamWeave — FreeCAD graph-workbench starter

> **Project name:** ParamWeave.

This folder is a coding-agent handoff package for a native FreeCAD workbench that places a patch/node graph beside the normal 3D view. Users can select FreeCAD objects, faces, edges, or vertices and create graph references to them; graph nodes can also construct and transform exact FreeCAD/OpenCascade geometry.

## Agreed project direction

- UI is **inside FreeCAD**, not a separate browser or Electron application.
- Target the **current stable FreeCAD 1.1.x line**, initially verified against **FreeCAD 1.1.3 on macOS**, while remaining platform-agnostic.
- The graph appears as a docked/split pane beside FreeCAD's existing 3D viewport.
- Initial scope includes both **reference nodes** and **constructive geometry nodes**.
- Graph state is **embedded in the `.FCStd` file**.
- FreeCAD remains authoritative for exact CAD geometry; the graph is authoritative for graph topology and graph-owned parameters.
- License is intentionally undecided. The desired eventual license is as permissive as practical while remaining compatible with FreeCAD and dependencies.
- Avoid hard dependencies on third-party node-editor libraries in the first prototype. The starter uses FreeCAD's bundled Qt/PySide graphics framework behind a replaceable UI layer.

## What is already scaffolded

The starter contains:

- a loadable external Python workbench layout (`Init.py`, `InitGui.py`);
- a Qt `QDockWidget` graph workspace intended to sit beside the normal FreeCAD 3D view;
- a serializable graph model with nodes, edges, schema versioning, validation, and topological ordering;
- embedded graph persistence in an `App::FeaturePython` document object;
- a node registry and typed ports;
- constructive nodes for Box, Cylinder, Translate, Fuse, and Cut;
- a FreeCAD reference node that can capture object/sub-element selection;
- measurement nodes for shape area/length/volume;
- generated `Part::Feature` output objects grouped under `ParamWeave Generated`;
- bidirectional selection synchronization hooks;
- a minimal native Qt graph scene/view with clickable input/output ports and wires;
- pure-Python unit tests for graph serialization and dependency ordering;
- design/architecture/roadmap documents intended for a coding agent.

The code is deliberately a **starter**, not a production-ready workbench. The first coding-agent task is to run and harden it inside FreeCAD 1.1.3 on macOS.

## Quick developer install on macOS

1. Start FreeCAD and open **View → Panels → Python console**.
2. Evaluate:

   ```python
   App.getUserAppDataDir()
   ```

3. Under that directory, create `Mod` if needed.
4. Copy or symlink the included `ParamWeave/` directory into:

   ```text
   <FreeCAD user app data>/Mod/ParamWeave
   ```

   On a typical macOS installation this is under:

   ```text
   ~/Library/Application Support/FreeCAD/Mod/ParamWeave
   ```

5. Restart FreeCAD.
6. Select **ParamWeave** from the workbench dropdown.
7. Open/create a document. The graph dock should appear on the right.

For Windows/Linux, do not hard-code paths. Use `App.getUserAppDataDir()` and place `ParamWeave` beneath its `Mod` directory.

## First manual smoke test

1. Create a new FreeCAD document.
2. Activate ParamWeave.
3. Add a **Box** graph node with the toolbar/menu command.
4. Add a **Cylinder** graph node.
5. Add a **Cut** graph node.
6. Connect `Box.shape → Cut.base` and `Cylinder.shape → Cut.tool` by clicking the output port and then the input port.
7. Select the Cut node and press **Evaluate Graph**.
8. Confirm ordinary `Part::Feature` objects appear under `ParamWeave Generated`.
9. Save, close, and reopen the `.FCStd`; verify graph nodes and connections return.
10. Select a face of any FreeCAD shape and invoke **Reference From Selection**; confirm a reference node appears and selecting that node re-highlights the referenced geometry.

## Repository layout

```text
freecad-paramweave-starter/
├── AGENTS.md
├── README.md
├── LICENSE_STATUS.md
├── docs/
├── tests/
├── tools/
└── ParamWeave/                 # copy/symlink this directory into FreeCAD's Mod directory
    ├── Init.py
    ├── InitGui.py
    ├── package.xml.template
    └── paramweave/
        ├── app/              # graph model, persistence, references, evaluator
        ├── gui/              # dock, graph scene, Qt items, selection sync
        ├── nodes/            # node specs/evaluators
        └── resources/
```

## Important implementation constraints

Read `AGENTS.md` and `docs/ARCHITECTURE.md` before modifying the design. In particular:

- do not make Qt graphics objects the persistent graph model;
- do not make `.FCStd` XML editing the API;
- do not duplicate OpenCascade geometry in graph JSON;
- do not put solver/CNC hardware logic in the graph UI layer;
- do not assume `Face12` is a permanently stable identity;
- do not require a pip-installed GUI framework for the first usable version.

## Current FreeCAD target

At package creation time, FreeCAD **1.1.3** is the current stable release. The starter uses the `from PySide import QtCore, QtGui, QtWidgets` compatibility path exposed by FreeCAD rather than importing a separately installed PySide package.
