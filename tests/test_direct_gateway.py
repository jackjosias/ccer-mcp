import tempfile
import unittest
from ccer.controls import PolicyError
from ccer.direct_gateway import DirectGateway, READ_CCER
from ccer.server import Gateway


class FakeConcat:
    def __init__(self):
        self.calls = []

    def tools(self):
        return [{"name": t, "inputSchema": {"type": "object"}}
                for t in ("concat_version", "timeline_read", "project_create", "edit_apply")]

    def tool(self, name, args, timeout=None):
        self.calls.append(name)
        return {"structuredContent": {"concat": "0.2.8" if name == "concat_version" else "ok"},
                "isError": False}


class DirectGatewayTests(unittest.TestCase):
    def test_observe_filters_tool_discovery(self):
        with tempfile.TemporaryDirectory() as root:
            g = DirectGateway(FakeConcat(), root)
            names = {item["name"] for item in g.catalogue}
            self.assertEqual(names, READ_CCER | {"concat_version", "timeline_read"})
            self.assertNotIn("ccer_desktop_act", names)
            self.assertNotIn("project_create", names)

    def test_observe_refuses_writes_even_direct_calls(self):
        with tempfile.TemporaryDirectory() as root:
            backend = FakeConcat()
            g = DirectGateway(backend, root)
            with self.assertRaises(PolicyError):
                g.invoke("project_create", {})
            with self.assertRaises(PolicyError):
                g.invoke("ccer_desktop_act", {"confirm": True})
            reply = g.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                              "params": {"name": "project_create", "arguments": {}}})
            self.assertTrue(reply["result"]["isError"])
            self.assertFalse(backend.calls)

    def test_observe_can_read(self):
        with tempfile.TemporaryDirectory() as root:
            backend = FakeConcat()
            g = DirectGateway(backend, root)
            self.assertEqual(g.invoke("concat_version", {})["structuredContent"]["concat"], "0.2.8")
            self.assertEqual(backend.calls, ["concat_version"])

    def test_control_preserves_native_gateway(self):
        with tempfile.TemporaryDirectory() as root:
            backend = FakeConcat()
            g = DirectGateway(backend, root, access="control")
            self.assertEqual(len(g.catalogue), len(Gateway(FakeConcat(), root).catalogue))
            self.assertIn("ccer_desktop_act", {item["name"] for item in g.catalogue})
            g.invoke("project_create", {})
            self.assertEqual(backend.calls, ["project_create"])

    def test_modes_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(PolicyError):
                DirectGateway(FakeConcat(), root, access="unrestricted")
            result = DirectGateway(FakeConcat(), root).handle(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            self.assertIn("observe", result["result"]["instructions"])
