# Test plan

## Pure Python tests

Run outside FreeCAD:

```bash
python -m unittest discover -s tests -v
```

Coverage target for graph core:

- empty graph round-trip;
- node/edge round-trip;
- stable IDs;
- invalid edge detection;
- one-input rule;
- cycle detection;
- topological ordering;
- node deletion removes incident edges;
- unknown JSON keys tolerated only where explicitly intended.

## Manual FreeCAD smoke tests

Record exact environment from **Help → About FreeCAD → Copy to clipboard**.

### Workbench lifecycle
- Activate/deactivate 10 times.
- Confirm one dock.
- Confirm one selection observer.
- Close document while dock is open.
- Open another document.

### Persistence
- Create graph.
- Save/reopen.
- Save As.
- Undo/redo document operations around graph changes once transaction support exists.

### Geometry
- Box dimensions positive, zero, negative.
- Cylinder radius/height boundary cases.
- Fuse overlapping/non-overlapping shapes.
- Cut intersecting/non-intersecting shapes.
- Translate.
- Change primitive parameter and re-evaluate; object identity should remain stable.

### References
- Whole Part::Feature.
- Face.
- Edge.
- Vertex.
- Rename Label (should survive).
- Upstream edit that preserves sub-element.
- Upstream edit that renumbers sub-elements.
- Delete referenced object.
- Two geometrically similar candidate faces: must not silently choose a wrong face.

### Platform checks
- macOS ARM64 stable build first.
- macOS x86_64 if available.
- Windows stable.
- Linux AppImage stable.

## Security tests

- Malformed embedded JSON.
- Unknown `type_id`.
- Very large node counts.
- Strings that look like Python expressions must remain inert.
- No `eval`, `exec`, or graph-directed module imports.
