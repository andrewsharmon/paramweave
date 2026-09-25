"""Compile all Python files without importing FreeCAD."""

from pathlib import Path
import py_compile

root = Path(__file__).resolve().parents[1]
failures = []
for path in sorted(root.rglob("*.py")):
    try:
        py_compile.compile(str(path), doraise=True)
        print("OK", path.relative_to(root))
    except Exception as exc:
        failures.append((path, exc))
        print("FAIL", path.relative_to(root), exc)

if failures:
    raise SystemExit(1)
