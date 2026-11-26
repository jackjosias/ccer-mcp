"""Tests for the evidence recorder without recursively running the suite."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("audit_mcp_tests", ROOT / "docs/audit_mcp_tests.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class McpEvidenceRecorderTests(unittest.TestCase):
    def test_records_only_known_tools_and_passing_tests(self):
        recorder = audit.Recorder({"ccer_example", "ccer_unused"})
        def original(instance, name, arguments):
            if arguments.get("fail"):
                raise ValueError("private argument never recorded")
            return {"isError": arguments.get("error", False)}
        observed = recorder.wrap(original, "dispatch")
        observed(None, "ccer_example", {})
        recorder.current = "test.good"
        observed(None, "ccer_example", {"error": True})
        with self.assertRaises(ValueError):
            observed(None, "ccer_example", {"fail": True})
        observed(None, "ccer_example", {})
        observed(None, "unknown", {})
        recorder.passed.add("test.good")
        recorder.current = "test.failed"
        observed(None, "ccer_example", {})
        rows = recorder.rows({})
        example = rows[0]
        self.assertEqual(example["name"], "ccer_example")
        self.assertEqual({x["outcome"] for x in example["observedInPassingTests"]},
                         {"returned", "returned:isError", "raised:ValueError"})
        self.assertEqual(len(example["observedInOtherTests"]), 1)
        self.assertFalse(rows[1]["observedInPassingTests"])
        self.assertNotIn("private argument", str(rows))

    def test_reference_inventory_covers_all_registry_names(self):
        refs = audit.literal_references(ROOT, audit.TOOLS)
        self.assertEqual(set(refs), set(audit.TOOLS))
        self.assertTrue(refs["ccer_desktop_act"])


if __name__ == "__main__":
    unittest.main()
