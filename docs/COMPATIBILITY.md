# Compatibility

## Verified environments

| Date | Platform | FreeCAD | Python | Qt | PySide | OCC | Result |
|---|---|---|---|---|---|---|---|
| 2026-09-25 | macOS 15.2 (Darwin 24.2.0), Apple Silicon (arm64) | 1.1.3 (build 20260725, git `145529fe`) | 3.11.14 (conda-forge) | 6.8.3 | PySide6 6.8.3 via FreeCAD's `PySide` shim | 7.8.1 | Console suite 22/22, GUI smoke 23/23 (3 consecutive runs) |

Versions were read from the running FreeCAD (`App.Version()`, `sys.version`,
`QtCore.qVersion()`, `PySide6.__version__`, `Part.OCC_VERSION`). Reproduce with
`tools/inspect_freecad_environment.py` or **Help → About FreeCAD → Copy to clipboard**.

Pure graph-core tests (`python -m unittest discover -s tests`) also pass on the
system Python 3.9.6, so the graph core stays importable on older interpreters.

Not yet tested: macOS x86_64, Windows, Linux (AppImage/Flatpak), FreeCAD 1.0.x,
Qt5-based builds. The Qt enum helpers in `paramweave/gui/qt.py` are written to
support Qt5 and Qt6 but have only run on Qt6.

## Platform notes discovered while testing

- **User Mod directory is versioned in FreeCAD 1.x.** On macOS it is
  `~/Library/Application Support/FreeCAD/v1-1/Mod`, not `.../FreeCAD/Mod`.
  `tools/install_dev.py` uses this default; `App.getUserAppDataDir()` is authoritative.
- **Python commands get no automatic undo transaction.** `Gui.runCommand` on a
  Python command leaves `App.getActiveTransaction()` as `None`, so ParamWeave
  opens its own `ParamWeave: …` transactions (see `app/persistence.py`).
- **Selection observers receive resolved names.** Selecting `NestedCyl.Face1`
  inside an `App::Part` calls `addSelection(doc, "NestedCyl", "Face1", …)`.
  `references.selection_target()` still resolves dotted subnames defensively.
- **`QScrollArea.takeWidget()` segfaults (Qt 6.8.3)** when the taken widget
  contains the keyboard focus widget. The property panel swaps an inner body
  widget instead.
- **Property status survives save/reopen.** `Output` + `NoRecompute` on the
  embedded `GraphJSON` keeps graph edits from marking the document for recompute.
- **Synthetic mouse events and FreeCAD's event filters.** Shortly after a 3D
  view is created, a synthetic press sent to the graph viewport can be
  re-dispatched to the 3D viewer. Real pointer input is unaffected; the GUI
  smoke test verifies delivery and retries (see `tests/gui/gui_smoke.py`).

## How to run the verification

```bash
python3 -m unittest discover -s tests -v          # pure graph core, no FreeCAD
python3 tools/run_freecad_tests.py                # freecadcmd console suite
python3 tools/run_freecad_tests.py --gui          # full GUI smoke test (opens a window ~15 s)
```

Both FreeCAD runners use a throwaway `FREECAD_USER_HOME`, so your real
preferences, recent files and Mod directory are untouched. Set `FREECAD_BIN`
(or pass `--freecad-bin`) to the directory containing `freecadcmd` on
non-macOS systems.
