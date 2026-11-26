"""Evidence of MCP tools exercised by the offline unittest suite.

No live_* scripts, no Concat launch by this runner, no tool payloads recorded.
The report measures observed calls, not branch coverage or production safety.
"""
import argparse
import ast
from collections import defaultdict
from contextlib import ExitStack
import functools
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "mcp-test-evidence.json"
sys.path.insert(0, str(ROOT))

from ccer.direct_gateway import DirectGateway
from ccer.production import Production, TOOLS
from ccer.server import Gateway


def literal_references(root, names):
    refs = defaultdict(set)
    for path in sorted((root / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                for value in ast.walk(node):
                    if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value in names:
                        refs[value.value].add(path.name + "::" + node.name)
    return {name: sorted(refs[name]) for name in sorted(names)}


class Recorder:
    def __init__(self, names):
        self.names = set(names)
        self.current = None
        self.passed = set()
        self.events = defaultdict(set)

    def wrap(self, original, layer):
        @functools.wraps(original)
        def observed(instance, name, *args, **kwargs):
            test = self.current
            track = test is not None and isinstance(name, str) and name in self.names
            try:
                result = original(instance, name, *args, **kwargs)
            except Exception as exc:
                if track:
                    self.events[name].add((test, layer, "raised:" + type(exc).__name__))
                raise
            if track:
                outcome = "returned:isError" if isinstance(result, dict) and result.get("isError") is True else "returned"
                self.events[name].add((test, layer, outcome))
            return result
        return observed

    def rows(self, references):
        return [
            {
                "name": name,
                "literalTestReferences": references.get(name, []),
                "observedInPassingTests": [
                    {"test": test, "layer": layer, "outcome": outcome}
                    for test, layer, outcome in sorted(self.events[name])
                    if test in self.passed
                ],
                "observedInOtherTests": [
                    {"test": test, "layer": layer, "outcome": outcome}
                    for test, layer, outcome in sorted(self.events[name])
                    if test not in self.passed
                ],
            }
            for name in sorted(self.names)
        ]


def result_type(recorder):
    class EvidenceResult(unittest.TextTestResult):
        def startTest(self, test):
            recorder.current = test.id()
            super().startTest(test)

        def stopTest(self, test):
            try:
                super().stopTest(test)
            finally:
                recorder.current = None

        def addSuccess(self, test):
            recorder.passed.add(test.id())
            super().addSuccess(test)

    return EvidenceResult


def fingerprint(root):
    paths = sorted(list((root / "ccer").rglob("*.py"))
                   + list((root / "tests").glob("test_*.py"))
                   + [root / "docs/render_mcp_catalog.py", root / "docs/mcp-tools.json",
                      root / "docs/audit_mcp_tests.py"])
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def audit():
    recorder = Recorder(TOOLS)
    references = literal_references(ROOT, recorder.names)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")
    hooks = [(Gateway, "invoke", "gateway"), (DirectGateway, "invoke", "direct"),
             (Production, "run", "production"), (Production, "_dispatch", "dispatch")]
    with ExitStack() as stack:
        for cls, method, layer in hooks:
            stack.enter_context(patch.object(cls, method, recorder.wrap(getattr(cls, method), layer)))
        result = unittest.TextTestRunner(verbosity=1, resultclass=result_type(recorder)).run(suite)
    rows = recorder.rows(references)
    summary = {
        "tools": len(rows),
        "withLiteralTestReference": sum(bool(row["literalTestReferences"]) for row in rows),
        "observedInPassingTest": sum(bool(row["observedInPassingTests"]) for row in rows),
        "dispatchObservedInPassingTest": sum(any(e["layer"] == "dispatch" for e in row["observedInPassingTests"]) for row in rows),
        "dispatchReturnedInPassingTest": sum(any(e["layer"] == "dispatch" and e["outcome"] == "returned" for e in row["observedInPassingTests"]) for row in rows),
    }
    report = {
        "formatVersion": 1,
        "sourceAndTestFingerprintSha256": fingerprint(ROOT),
        "pythonVersion": platform.python_version(),
        "scope": "Offline in-process unittest discovery (test_*.py); no live_* or external Concat integration certification",
        "limitations": [
            "Literal references are not execution or assertions.",
            "Observed calls in passing tests may use mocks; exceptions may be expected.",
            "A return does not establish a correct edit or production safety.",
            "Subprocess calls, function-only tests and mocked-away methods are not captured by these hooks.",
            "Counts are not line, branch or exhaustive per-tool functional coverage.",
        ],
        "suite": {"run": result.testsRun, "passed": len(recorder.passed),
                  "skipped": len(result.skipped), "failures": len(result.failures),
                  "errors": len(result.errors), "expectedFailures": len(result.expectedFailures),
                  "unexpectedSuccesses": len(result.unexpectedSuccesses)},
        "summary": summary,
        "tools": rows,
    }
    return result.wasSuccessful(), report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write a successful evidence snapshot")
    args = parser.parse_args()
    os.chdir(ROOT)
    ok, report = audit()
    print(json.dumps({"suite": report["suite"], "summary": report["summary"]}, sort_keys=True))
    if not ok:
        return 1
    if args.write:
        OUTPUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
