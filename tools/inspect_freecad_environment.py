"""Run from the FreeCAD Python console with exec(open(...).read()) or adapt as needed."""

import FreeCAD as App

print("FreeCAD version:", App.Version())
print("User app data:", App.getUserAppDataDir())
try:
    from PySide import QtCore
    print("Qt version:", QtCore.qVersion())
    print("PySide wrapper import: OK")
except Exception as exc:
    print("PySide wrapper import FAILED:", exc)
