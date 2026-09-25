# ParamWeave

@AGENTS.md

## Quick reference

- Install into FreeCAD (symlink): `python3 tools/install_dev.py`, then restart FreeCAD.
- Pure tests: `python3 -m unittest discover -s tests -v`
- FreeCAD console tests: `python3 tools/run_freecad_tests.py`
- GUI smoke test (opens FreeCAD ~15 s): `python3 tools/run_freecad_tests.py --gui`
- Tested environments and FreeCAD quirks: `docs/COMPATIBILITY.md`; design decisions: `docs/DECISIONS.md`.
- `GraphWorkspace` (`ParamWeave/paramweave/gui/workspace.py`) is the only code that mutates the graph; scene and property panel emit requests.
