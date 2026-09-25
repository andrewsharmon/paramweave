"""Run ParamWeave's FreeCAD console tests inside ``freecadcmd``.

Invoked by ``tools/run_freecad_tests.py``; not meant for ordinary Python.
Results are written as JSON lines to ``$PARAMWEAVE_TEST_OUT``.
"""

import json
import os
import sys
import tempfile
import traceback
import unittest

HERE = os.path.dirname(os.path.abspath(globals().get("__file__") or os.path.join(os.environ["PARAMWEAVE_ROOT"], "tests", "freecad", "x")))
ROOT = os.path.dirname(os.path.dirname(HERE))
for path in (os.path.join(ROOT, "ParamWeave"), HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

OUT_PATH = os.environ.get("PARAMWEAVE_TEST_OUT") or os.path.join(tempfile.gettempdir(), "paramweave_console.jsonl")


class JsonLinesResult(unittest.TestResult):
    def __init__(self, stream):
        super().__init__()
        self.stream = stream

    def _write(self, test, ok, detail=""):
        self.stream.write(json.dumps({"check": test.id(), "ok": ok, "detail": detail}) + "\n")
        self.stream.flush()

    def addSuccess(self, test):
        super().addSuccess(test)
        self._write(test, True)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._write(test, False, self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._write(test, False, self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._write(test, True, f"skipped: {reason}")


def main():
    with open(OUT_PATH, "w") as out:
        try:
            suite = unittest.defaultTestLoader.discover(HERE, pattern="fc_test_*.py", top_level_dir=HERE)
            result = JsonLinesResult(out)
            suite.run(result)
            ok = result.wasSuccessful()
            out.write(json.dumps({"check": "__summary__", "ok": ok, "detail": f"ran {result.testsRun}"}) + "\n")
        except Exception:
            ok = False
            out.write(json.dumps({"check": "__runner__", "ok": False, "detail": traceback.format_exc()}) + "\n")
    os._exit(0 if ok else 1)


main()
