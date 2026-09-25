"""FreeCAD GUI initializer for the ParamWeave workbench."""

import FreeCAD as App
import FreeCADGui as Gui


class ParamWeaveWorkbench(Gui.Workbench):
    MenuText = "ParamWeave"
    ToolTip = "Patch-based CAD graph integrated with the FreeCAD 3D view"

    def Initialize(self):
        from paramweave import commands

        commands.register_commands()
        self.appendToolbar(
            "ParamWeave",
            [
                "ParamWeave_ToggleGraph",
                "ParamWeave_ReferenceSelection",
                "ParamWeave_AddBox",
                "ParamWeave_AddCylinder",
                "ParamWeave_AddCut",
                "ParamWeave_AddFuse",
                "ParamWeave_Evaluate",
            ],
        )
        self.appendMenu(
            "ParamWeave",
            [
                "ParamWeave_ToggleGraph",
                "ParamWeave_ReferenceSelection",
                "Separator",
                "ParamWeave_AddBox",
                "ParamWeave_AddCylinder",
                "ParamWeave_AddTranslate",
                "ParamWeave_AddCut",
                "ParamWeave_AddFuse",
                "ParamWeave_AddMeasure",
                "Separator",
                "ParamWeave_Evaluate",
            ],
        )

    def Activated(self):
        from paramweave.gui.workspace import workspace

        workspace().activate()

    def Deactivated(self):
        # Keep the dock alive so users can switch workbenches without losing UI state.
        # The dock remains toggleable and the singleton prevents duplicates.
        pass

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(ParamWeaveWorkbench())
