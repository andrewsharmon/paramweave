# UX specification

## Default workspace

Use FreeCAD's ordinary main window and 3D view. The ParamWeave dock opens on the right at roughly 40–45% width when the workbench activates.

```text
┌───────────────────────────────────────────────────────────────┐
│ FreeCAD                                                       │
├──────────────┬────────────────────────┬───────────────────────┤
│ Model tree   │  native 3D viewport    │ ParamWeave              │
│              │                        │                       │
│ Body         │       █████            │ [Box] ───────┐       │
│ ├ Sketch     │     █████████          │              ▼       │
│ ├ Pad        │       █████            │ [Cylinder]→[Cut]      │
│ └ Pocket     │                        │                       │
│              │                        │ node properties       │
├──────────────┴────────────────────────┴───────────────────────┤
│ report/status/property panels as normal                       │
└───────────────────────────────────────────────────────────────┘
```

The user can resize/hide the dock normally.

## Core interaction: reference from selection

1. User selects one object/sub-element in the normal FreeCAD viewport or tree.
2. User invokes **Reference From Selection**.
3. A graph reference node appears at the current graph insertion point.
4. Selecting the graph node highlights the referenced FreeCAD object/sub-element.
5. Selecting that geometry in FreeCAD selects/highlights matching reference node(s) in the graph.

Multiple-selection support is a later feature and should likely create an explicit `Reference Set` node rather than silently selecting only one item.

## Graph wiring

Starter interaction:

- click an output port;
- click a compatible input port;
- a wire is created;
- click empty canvas or press Esc to cancel pending wire.

Future interaction should additionally support conventional drag-to-connect.

## Node creation

Starter:

- toolbar/menu commands for common nodes;
- context menu on empty graph canvas.

Later:

- press Tab / double-click empty canvas to search node palette;
- recently used nodes;
- categories;
- favorites;
- drag object/property from FreeCAD tree/property editor.

## Node property editing

The dock contains a simple property panel below the graph. Selecting a node shows editable parameters. The first version accepts numeric/string values; later replace numeric text fields with FreeCAD quantity-aware editors so units work correctly.

## Error representation

Do not fail silently. A node with an evaluation or reference error should show:

- visible error state/badge;
- concise tooltip/message;
- detailed traceback only in report/debug output;
- downstream nodes marked blocked rather than independently failing with misleading errors.

## Geometry visibility

Generated graph objects should be clearly grouped. Future UI should provide node-level controls:

- eye/show output;
- pin intermediate;
- select generated object;
- frame selected object in 3D view.

## Accessibility

- Port type is communicated by text/tooltip as well as visual styling.
- Keyboard navigation and delete/copy/paste are milestone requirements.
- Do not rely on red/green alone for valid/invalid states.
