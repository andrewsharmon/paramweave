"""Print the versions that matter for ParamWeave compatibility notes.

Run inside FreeCAD's Python console with exec(open(".../inspect_freecad_environment.py").read()),
or headless: freecadcmd tools/inspect_freecad_environment.py
"""

import platform
import sys

import FreeCAD as App

print("FreeCAD version:", ".".join(App.Version()[:3]), App.Version()[3:])
print("Platform:", platform.platform(), platform.machine())
print("Python:", sys.version.replace("\n", " "))
print("User app data:", App.getUserAppDataDir())
try:
    import Part

    print("OCC:", Part.OCC_VERSION)
except Exception as exc:
    print("Part import FAILED:", exc)
try:
    from PySide import QtCore

    print("Qt version:", QtCore.qVersion())
    print("PySide wrapper import: OK")
    try:
        import PySide6

        print("PySide6:", PySide6.__version__)
    except ImportError:
        import PySide2

        print("PySide2:", PySide2.__version__)
except Exception as exc:
    print("PySide wrapper import FAILED:", exc)
