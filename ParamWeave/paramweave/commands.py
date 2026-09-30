"""FreeCAD command registration for ParamWeave."""

from __future__ import annotations

import FreeCAD as App
import FreeCADGui as Gui


_REGISTERED = False


class _Command:
    def __init__(self, text, tooltip, callback, icon=""):
        self.text = text
        self.tooltip = tooltip
        self.callback = callback
        self.icon = icon

    def GetResources(self):
        data = {"MenuText": self.text, "ToolTip": self.tooltip}
        if self.icon:
            data["Pixmap"] = self.icon
        return data

    def Activated(self):
        try:
            self.callback()
        except Exception as exc:
            App.Console.PrintError(f"ParamWeave: {exc}\n")

    def IsActive(self):
        return True


def _ws():
    from paramweave.gui.workspace import workspace
    return workspace()


def _insert_finger_box():
    from paramweave.examples import finger_box

    _ws().insert_example(finger_box.build, "Finger-jointed box")


def register_commands():
    global _REGISTERED
    if _REGISTERED:
        return
    commands = {
        "ParamWeave_ToggleGraph": _Command("Toggle Graph", "Show or hide the ParamWeave pane", lambda: _ws().toggle()),
        "ParamWeave_ReferenceSelection": _Command(
            "Reference From Selection",
            "Create a graph reference to the selected FreeCAD object/face/edge/vertex",
            lambda: _ws().add_reference_from_selection(),
        ),
        "ParamWeave_AddBox": _Command("Add Box Node", "Add a constructive Box node", lambda: _ws().add_node("primitive.box")),
        "ParamWeave_AddCylinder": _Command(
            "Add Cylinder Node", "Add a constructive Cylinder node", lambda: _ws().add_node("primitive.cylinder")
        ),
        "ParamWeave_AddTranslate": _Command(
            "Add Translate Node", "Add a shape translation node", lambda: _ws().add_node("transform.translate")
        ),
        "ParamWeave_AddCut": _Command("Add Cut Node", "Add a Boolean Cut node", lambda: _ws().add_node("boolean.cut")),
        "ParamWeave_AddFuse": _Command("Add Fuse Node", "Add a Boolean Fuse node", lambda: _ws().add_node("boolean.fuse")),
        "ParamWeave_AddMeasure": _Command(
            "Add Measure Node", "Add a shape measurement node", lambda: _ws().add_node("measure.shape")
        ),
        "ParamWeave_ExportCutFiles": _Command(
            "Export Cut Files…",
            "Export the graph's Sketch nodes laid flat as a DXF or SVG for laser cutting",
            lambda: _ws().export_cut_files_dialog(),
        ),
        "ParamWeave_ExampleFingerBox": _Command(
            "Example: Finger-Jointed Box",
            "Insert a fully parameterized finger-jointed box graph (edit the constants, then Evaluate)",
            _insert_finger_box,
        ),
        "ParamWeave_Evaluate": _Command("Evaluate Graph", "Evaluate all graph dependencies", lambda: _ws().evaluate()),
    }
    for name, command in commands.items():
        Gui.addCommand(name, command)
    _REGISTERED = True
