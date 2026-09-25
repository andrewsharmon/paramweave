"""Link (or copy) the ParamWeave workbench into FreeCAD's user Mod directory.

    python3 tools/install_dev.py                 # symlink into the default Mod dir
    python3 tools/install_dev.py --copy          # copy instead (e.g. Windows without symlink rights)
    python3 tools/install_dev.py --uninstall
    python3 tools/install_dev.py --mod-dir PATH  # explicit Mod directory

FreeCAD 1.x keeps user data in a versioned folder (for 1.1: ``.../FreeCAD/v1-1``).
The authoritative location is whatever ``App.getUserAppDataDir()`` prints in
FreeCAD's Python console; pass ``--mod-dir <that>/Mod`` if the default differs.
Restart FreeCAD after installing.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "ParamWeave"
FREECAD_DATA_VERSION = "v1-1"


def default_mod_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "FreeCAD"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "FreeCAD"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "FreeCAD"
    return base / FREECAD_DATA_VERSION / "Mod"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mod-dir", type=Path, default=None)
    parser.add_argument("--copy", action="store_true", help="copy files instead of symlinking")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()

    mod_dir = args.mod_dir or default_mod_dir()
    target = mod_dir / "ParamWeave"

    if target.is_symlink() or target.exists():
        if target.is_symlink() and target.resolve() == WORKBENCH.resolve() and not args.uninstall and not args.copy:
            print(f"Already linked: {target} -> {WORKBENCH}")
            return 0
        if not args.uninstall and not target.is_symlink():
            print(f"{target} exists and is not a symlink; remove it first or use --uninstall", file=sys.stderr)
            return 1
        if target.is_symlink():
            target.unlink()
        else:
            shutil.rmtree(target)
        print(f"Removed {target}")
    if args.uninstall:
        return 0

    mod_dir.mkdir(parents=True, exist_ok=True)
    if args.copy:
        shutil.copytree(WORKBENCH, target, ignore=shutil.ignore_patterns("__pycache__"))
        print(f"Copied {WORKBENCH} -> {target}")
    else:
        target.symlink_to(WORKBENCH, target_is_directory=True)
        print(f"Linked {target} -> {WORKBENCH}")
    print("Restart FreeCAD, then pick ParamWeave from the workbench selector.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
