"""Contract tests for an offline-safe direct Concat backend."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ccer.transport import DeferredConcatTransport, TransportError


class DeferredTransportTests(unittest.TestCase):
    def test_offline_boot_then_reconnect_on_fresh_request(self):
        state = {"ready": False, "starts": 0, "calls": 0, "closes": 0}

        class Process:
            def poll(self):
                return None

        class FakeBackend:
            def __init__(self, binary, mode):
                self.process = Process()

            def start(self):
                state["starts"] += 1
                if not state["ready"]:
                    raise TransportError("Concat disconnected")

            def tools(self):
                return [{"name": "concat_version", "inputSchema": {"type": "object"}}]

            def tool(self, name, arguments=None, timeout=None):
                state["calls"] += 1
                return {"structuredContent": {"concat": "0.2.8"}}

            def close(self):
                state["closes"] += 1

        with patch("ccer.transport.ConcatTransport", FakeBackend):
            bridge = DeferredConcatTransport(Path("/unused"), retry_seconds=0)
            bridge.start()
            self.assertEqual(1, state["starts"])
            self.assertEqual([], bridge.tools())
            self.assertEqual(2, state["starts"])
            state["ready"] = True
            self.assertEqual("concat_version", bridge.tools()[0]["name"])
            self.assertEqual("0.2.8", bridge.tool("concat_version")["structuredContent"]["concat"])
            self.assertEqual(1, state["calls"])
            bridge.close()
            self.assertEqual(3, state["closes"])

    def test_failed_dispatched_request_is_not_replayed(self):
        state = {"calls": 0, "starts": 0}

        class Process:
            def poll(self):
                return None

        class FakeBackend:
            def __init__(self, binary, mode):
                self.process = Process()

            def start(self):
                state["starts"] += 1

            def tools(self):
                return []

            def tool(self, name, arguments=None, timeout=None):
                state["calls"] += 1
                raise TransportError("Timeout; operation outcome UNKNOWN")

            def close(self):
                pass

        with patch("ccer.transport.ConcatTransport", FakeBackend):
            bridge = DeferredConcatTransport(Path("/unused"), retry_seconds=0)
            with self.assertRaisesRegex(TransportError, "UNKNOWN"):
                bridge.tool("concat_version")
            self.assertEqual(1, state["calls"])
            self.assertEqual(1, state["starts"])
            bridge.close()


if __name__ == "__main__":
    unittest.main()
