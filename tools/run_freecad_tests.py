"""Run ParamWeave tests that need FreeCAD, using an isolated FreeCAD user home.

Usage (ordinary Python 3, no FreeCAD import needed):

    python3 tools/run_freecad_tests.py            # console (freecadcmd) tests
    python3 tools/run_freecad_tests.py --gui      # full GUI smoke test (opens a window)
    python3 tools/run_freecad_tests.py --all

The FreeCAD executables are located from ``--freecad-bin`` / ``$FREECAD_BIN``
(a directory containing ``freecadcmd`` and ``freecad``), falling back to common
install locations. Each run creates a throwaway ``FREECAD_USER_HOME`` so the
developer's real FreeCAD preferences and Mod directory are never touched.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "ParamWeave"

CANDIDATE_BIN_DIRS = [
    "/Applications/FreeCAD.app/Contents/Resources/bin",
    "/usr/bin",
    "/usr/local/bin",
    r"C:\Program Files\FreeCAD 1.1\bin",
]


def _exe(bin_dir: Path, name: str) -> Path | None:
    for candidate in (name, name + ".exe", name.capitalize(), name.capitalize() + ".exe"):
        path = bin_dir / candidate
        if path.exists():
            return path
    return None


def find_bin_dir(explicit: str | None) -> Path:
    options = [explicit, os.environ.get("FREECAD_BIN")] + CANDIDATE_BIN_DIRS
    for option in options:
        if option and _exe(Path(option), "freecadcmd"):
            return Path(option)
    found = shutil.which("freecadcmd") or shutil.which("FreeCADCmd")
    if found:
        return Path(found).parent
    raise SystemExit("Could not find freecadcmd; pass --freecad-bin or set FREECAD_BIN")


def gui_executable(bin_dir: Path) -> Path:
    if platform.system() == "Darwin":
        # Launch through the bundle's MacOS stub so the environment matches a normal start.
        bundle_exe = bin_dir.parents[1] / "MacOS" / "FreeCAD"
        if bundle_exe.exists():
            return bundle_exe
    exe = _exe(bin_dir, "freecad")
    if exe is None:
        raise SystemExit(f"Could not find the FreeCAD GUI executable in {bin_dir}")
    return exe


def make_user_home(tmp: Path) -> Path:
    home = tmp / "fchome"
    mod = home / "Mod"
    mod.mkdir(parents=True)
    target = mod / "ParamWeave"
    try:
        target.symlink_to(WORKBENCH, target_is_directory=True)
    except OSError:  # e.g. Windows without symlink privilege
        shutil.copytree(WORKBENCH, target)
    return home


def _env(home: Path, out: Path, work: Path) -> dict:
    env = dict(os.environ)
    env.update(
        FREECAD_USER_HOME=str(home),
        PARAMWEAVE_TEST_OUT=str(out),
        PARAMWEAVE_TEST_WORKDIR=str(work),
        PARAMWEAVE_ROOT=str(ROOT),
    )
    return env


def _report(out: Path, label: str) -> bool:
    if not out.exists():
        print(f"[{label}] no result file written")
        return False
    ok = True
    summary_seen = False
    for line in out.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        name = entry["check"]
        if name == "__summary__":
            summary_seen = True
            ok = ok and entry["ok"]
            continue
        status = "PASS" if entry["ok"] else "FAIL"
        print(f"[{label}] {status} {name}")
        if not entry["ok"]:
            ok = False
            for detail_line in entry["detail"].rstrip().splitlines():
                print(f"          {detail_line}")
    if not summary_seen:
        print(f"[{label}] run ended before the summary (crash or timeout?)")
        ok = False
    return ok


def run_console(bin_dir: Path, tmp: Path, verbose: bool) -> bool:
    home = make_user_home(tmp / "console")
    out = tmp / "console_results.jsonl"
    cmd = [str(_exe(bin_dir, "freecadcmd")), str(ROOT / "tests" / "freecad" / "run_console_tests.py")]
    proc = subprocess.run(cmd, env=_env(home, out, tmp), capture_output=True, text=True, timeout=600)
    if verbose or proc.returncode not in (0, 1):
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:])
    return _report(out, "console") and proc.returncode == 0


def run_gui(bin_dir: Path, tmp: Path, verbose: bool, script: Path | None = None) -> bool:
    home = make_user_home(tmp / "gui")
    out = tmp / "gui_results.jsonl"
    cmd = [str(gui_executable(bin_dir)), str(script or ROOT / "tests" / "gui" / "gui_smoke.py")]
    proc = subprocess.run(cmd, env=_env(home, out, tmp), capture_output=True, text=True, timeout=600)
    if verbose or proc.returncode not in (0, 1):
        print(f"[gui] FreeCAD exit code {proc.returncode}")
        print(proc.stdout[-6000:])
        print(proc.stderr[-6000:])
    return _report(out, "gui") and proc.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gui", action="store_true", help="run only the GUI smoke test")
    parser.add_argument("--all", action="store_true", help="run console tests and the GUI smoke test")
    parser.add_argument("--gui-script", type=Path, help="run this GUI script instead of the smoke test (implies --gui)")
    parser.add_argument("--freecad-bin", help="directory containing freecadcmd/freecad")
    parser.add_argument("--keep", action="store_true", help="keep the temporary directory")
    parser.add_argument("-v", "--verbose", action="store_true", help="print FreeCAD stdout/stderr")
    args = parser.parse_args()
    if args.gui_script:
        args.gui = True

    bin_dir = find_bin_dir(args.freecad_bin)
    tmp = Path(tempfile.mkdtemp(prefix="paramweave_tests_"))
    ok = True
    try:
        if not args.gui or args.all:
            ok = run_console(bin_dir, tmp, args.verbose) and ok
        if args.gui or args.all:
            ok = run_gui(bin_dir, tmp, args.verbose, args.gui_script and args.gui_script.resolve()) and ok
    finally:
        if args.keep:
            print(f"kept {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    print("OK" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
