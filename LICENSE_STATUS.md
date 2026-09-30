# License status — decision intentionally pending

No project license has been selected yet. Do **not** publish this starter as though it grants reuse rights until a license is chosen.

The stated preference is: **as permissive as practical while remaining compatible with FreeCAD and selected dependencies**.

Likely choices to evaluate:

- **MIT** — shortest/permissive; very easy downstream reuse.
- **BSD-3-Clause** — similarly permissive with a non-endorsement clause.
- **Apache-2.0** — permissive plus explicit patent terms; longer text.
- **LGPL-3.0-or-later** — stronger reciprocal requirements than desired, but may be considered if future integration choices warrant it.

The initial scaffold intentionally avoids vendoring or requiring NodeGraphQt/QtNodes. It uses Qt/PySide through FreeCAD's own runtime APIs.

FreeCAD itself has LGPL licensing, while individual optional backends/add-ons can have other licenses. Before distribution through FreeCAD's Addon Manager, choose a project license and replace `ParamWeave/package.xml.template` with a real `package.xml` that identifies that license.

## Dependency policy during prototype

1. Prefer FreeCAD/Python standard-library capabilities first.
2. Prefer MIT/BSD/Apache external Python dependencies where they materially reduce work.
3. Do not vendor third-party code without retaining its license/notice files.
4. Record every non-standard dependency here before merging.
5. Keep future GPL solver integrations (Gmsh/Elmer/OpenFOAM, etc.) behind clear adapters/process boundaries where technically appropriate; get legal review before making licensing claims.

This is project-planning information, not legal advice.

## Recorded dependencies

| Dependency | License | Used by | Kind |
|---|---|---|---|
| reportlab | BSD-3-Clause | `tools/build_tutorial_pdf.py` | Documentation tooling only; not imported by the workbench and not shipped. Install in a throwaway virtualenv. |
| Pillow | MIT-CMU (HPND) | `tools/build_tutorial_pdf.py` | Same as above. |
