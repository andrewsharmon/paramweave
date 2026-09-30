# License status

ParamWeave's core is licensed under the **Apache License 2.0** (`LICENSE`, `NOTICE`), decided 2026-09-30. See `docs/DECISIONS.md` ("Project license") for the rationale.

- Apache-2.0 is compatible with FreeCAD (LGPL-2.1+) and PySide/Qt (LGPL): the workbench only imports them at runtime and bundles no FreeCAD or Qt code.
- Extension packages that build on ParamWeave are separate packages with their own licenses; they are not committed to this repository.
- Contributions to the core are accepted under Apache-2.0 (inbound = outbound).

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
