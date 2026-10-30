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

    def test_control_is_visually_scoped_and_blocks_backend_writes(self):
        with tempfile.TemporaryDirectory() as root:
            backend = FakeConcat()
            g = DirectGateway(backend, root, access="control")
            full = Gateway(FakeConcat(), root)
            names = {item["name"] for item in g.catalogue}
            self.assertLess(len(names), len(full.catalogue))
            self.assertIn("ccer_desktop_act", names)
            self.assertIn("ccer_desktop_capture", names)
            self.assertNotIn("project_create", names)
            self.assertNotIn("ccer_produce", names)
            self.assertNotIn("ccer_media_match_render", names)
            for mutation in ("project_create", "edit_apply", "ccer_produce",
                             "export_start", "title_add", "ccer_media_match_render"):
                with self.subTest(mutation=mutation):
                    with self.assertRaises(PolicyError):
                        g.invoke(mutation, {})
            result = g.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                               "params": {"name": "project_create", "arguments": {}}})
            self.assertTrue(result["result"]["isError"])
            self.assertEqual(backend.calls, [])

    def test_capture_gate_requires_new_before_image_for_every_action(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            g = DirectGateway(FakeConcat(), root, access="control")
            fake = {
                "window": {"windowId": "0xabc", "display": "native-slint"},
                "sha256": "valid-image", "mimeType": "image/jpeg",
                "imageBase64": "aGVsbG8=", "imageWidth": 640,
                "captureSource": "authenticated_native_slint",
                "safeForClickReceipt": True, "readOnly": False,
                "frameNo": 42,
            }
            arguments = {"expectedWindowId": "0xabc", "action": "key",
                         "key": "Escape", "confirm": True}
            with patch.object(g.production, "run", return_value=fake) as process:
                with self.assertRaises(PolicyError):
                    g.invoke("ccer_desktop_act", arguments)
                first = g.invoke("ccer_desktop_capture", {})
                self.assertTrue(any(c["type"] == "image" for c in first["content"]))
                with self.assertRaises(PolicyError):
                    g.invoke("ccer_desktop_act", dict(arguments, withCapture=False))
                with self.assertRaises(PolicyError):
                    g.invoke("ccer_desktop_act", dict(arguments, expectedWindowId="0xdef"))
                result = g.invoke("ccer_desktop_act", arguments)
                self.assertTrue(any(c["type"] == "image" for c in result["content"]))
                with self.assertRaises(PolicyError):
                    g.invoke("ccer_desktop_act", arguments)
                g.invoke("ccer_desktop_capture", {})
                g._last_visual_observation["when"] -= 3600
                with self.assertRaises(PolicyError):
                    g.invoke("ccer_desktop_act", arguments)
                self.assertEqual(process.call_count, 3)


    def test_x11_fallback_is_viewable_but_never_authorizes_a_click(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            g = DirectGateway(FakeConcat(), root, access="control")
            fallback = {
                "window": {"windowId": "0xabc", "display": ":1", "pid": 598971},
                "sha256": "verified-x11-image", "mimeType": "image/jpeg",
                "imageBase64": "aGVsbG8=", "imageWidth": 640,
                "captureSource": "verified_x11_read_only",
                "safeForClickReceipt": False, "readOnly": True,
            }
            args = {"expectedWindowId": "0xabc", "action": "click",
                    "x": 200, "y": 150, "confirm": True}
            with patch.object(g.production, "run", return_value=fallback) as run:
                result = g.invoke("ccer_desktop_capture", {})
                self.assertTrue(any(c["type"] == "image" for c in result["content"]))
                self.assertIsNone(g._last_visual_observation)
                with self.assertRaisesRegex(PolicyError, "fresh Concat screenshot"):
                    g.invoke("ccer_desktop_act", args)
                self.assertEqual(1, run.call_count)

    def test_readonly_fallback_revokes_earlier_native_authorization(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            g = DirectGateway(FakeConcat(), root, access="control")
            native = {
                "window": {"windowId": "0xabc", "display": "native-slint"},
                "sha256": "native", "mimeType": "image/jpeg",
                "imageBase64": "aGVsbG8=", "frameNo": 16,
                "captureSource": "authenticated_native_slint",
                "safeForClickReceipt": True, "readOnly": False,
            }
            fallback = {
                "window": {"windowId": "0xabc", "display": ":1"},
                "sha256": "fallback", "mimeType": "image/jpeg",
                "imageBase64": "aGVsbG8=",
                "captureSource": "verified_x11_read_only",
                "safeForClickReceipt": False, "readOnly": True,
            }
            with patch.object(g.production, "run", side_effect=[native, fallback]) as run:
                g.invoke("ccer_desktop_capture", {})
                self.assertIsNotNone(g._last_visual_observation)
                g.invoke("ccer_desktop_capture", {})
                self.assertIsNone(g._last_visual_observation)
                with self.assertRaisesRegex(PolicyError, "fresh Concat screenshot"):
                    g.invoke("ccer_desktop_act", {
                        "expectedWindowId": "0xabc", "action": "click",
                        "confirm": True, "x": 200, "y": 150})
                self.assertEqual(2, run.call_count)


    def test_jsonrpc_capture_fallback_is_never_click_authorization(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            g = DirectGateway(FakeConcat(), root, access="control")
            handshake = g.handle({"jsonrpc": "2.0", "id": 1,
                                  "method": "initialize", "params": {}})
            self.assertEqual("ccer-mcp", handshake["result"]["serverInfo"]["name"])
            listing = g.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            self.assertIn("ccer_desktop_act",
                          {t["name"] for t in listing["result"]["tools"]})
            fallback = {
                "window": {"windowId": "0xabc", "pid": 598971, "display": ":1"},
                "sha256": "valid-image", "imageBase64": "aGVsbG8=",
                "mimeType": "image/jpeg", "captureSource": "verified_x11_read_only",
                "safeForClickReceipt": False, "readOnly": True,
            }
            with patch.object(g.production, "run", return_value=fallback) as process:
                read = g.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                 "params": {"name": "ccer_desktop_capture",
                                            "arguments": {}}})
                self.assertFalse(read["result"]["isError"])
                self.assertTrue(any(p["type"] == "image"
                                    for p in read["result"]["content"]))
                blocked = g.handle({"jsonrpc": "2.0", "id": 4,
                                    "method": "tools/call",
                                    "params": {"name": "ccer_desktop_act",
                                               "arguments": {
                                                   "expectedWindowId": "0xabc",
                                                   "action": "click",
                                                   "x": 250, "y": 100,
                                                   "confirm": True}}})
                self.assertTrue(blocked["result"]["isError"])
                self.assertIn("fresh Concat screenshot",
                              blocked["result"]["content"][0]["text"])
                self.assertEqual(1, process.call_count)

    def test_failed_capture_revokes_existing_native_authorization(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            g = DirectGateway(FakeConcat(), root, access="control")
            native = {
                "window": {"windowId": "0xabc", "display": "native-slint"},
                "sha256": "native", "mimeType": "image/jpeg",
                "imageBase64": "aGVsbG8=", "frameNo": 7,
                "captureSource": "authenticated_native_slint",
                "safeForClickReceipt": True, "readOnly": False,
            }
            with patch.object(g.production, "run",
                              side_effect=[native, PolicyError("CCER: UI timeout")]) as run:
                g.invoke("ccer_desktop_capture", {})
                self.assertIsNotNone(g._last_visual_observation)
                with self.assertRaisesRegex(PolicyError, "UI timeout"):
                    g.invoke("ccer_desktop_capture", {})
                self.assertIsNone(g._last_visual_observation)
                with self.assertRaisesRegex(PolicyError, "fresh Concat screenshot"):
                    g.invoke("ccer_desktop_act", {
                        "expectedWindowId": "0xabc", "action": "click",
                        "x": 250, "y": 100, "confirm": True})
                self.assertEqual(2, run.call_count)


    def test_offline_then_online_mcp_catalogue_keeps_gui_only_control(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as root:
            backend = FakeConcat()
            g = DirectGateway(backend, root, access="control")
            # A disconnected Concat backend must not erase safe CCER tools.
            with patch.object(backend, "tools", side_effect=[[], backend.tools()]):
                first = g.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
                second = g.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            for response in (first, second):
                names = {t["name"] for t in response["result"]["tools"]}
                self.assertIn("ccer_desktop_status", names)
                self.assertIn("ccer_desktop_capture", names)
                self.assertIn("ccer_desktop_act", names)
                self.assertNotIn("project_create", names)
                self.assertNotIn("edit_apply", names)
            # A control profile still cannot click without an authenticated
            # fresh Slint BEFORE screenshot, even after backend reconnects.
            blocked = g.handle({"jsonrpc": "2.0", "id": 3,
                                "method": "tools/call",
                                "params": {"name": "ccer_desktop_act",
                                           "arguments": {"expectedWindowId": "0xabc",
                                                         "action": "click",
                                                         "x": 70, "y": 90,
                                                         "confirm": True}}})
            self.assertTrue(blocked["result"]["isError"])
            self.assertIn("fresh Concat screenshot",
                          blocked["result"]["content"][0]["text"])

    def test_direct_cli_uses_passive_backend_and_never_starts_second_concat(self):
        from unittest.mock import ANY, patch
        from ccer.direct_cli import main
        with tempfile.TemporaryDirectory() as root:
            with (patch("ccer.direct_cli.bind_direct_process", return_value=False) as binding,
                  patch("ccer.direct_cli.DeferredConcatTransport") as backend,
                  patch("ccer.direct_cli.DirectGateway") as gateway):
                main(["--mode", "window", "--access", "control", "--root", root])
                binding.assert_not_called()
                backend.assert_called_once_with(ANY, "window", permit_launch=False)
                backend.return_value.start.assert_called_once_with()
                backend.return_value.close.assert_called_once_with()
                gateway.return_value.serve.assert_called_once_with()

    def test_private_session_is_explicit_opt_in_only(self):
        from unittest.mock import patch
        from ccer.direct_cli import main
        with tempfile.TemporaryDirectory() as root:
            with (patch("ccer.direct_cli.bind_direct_process", return_value=True) as binding,
                  patch("ccer.direct_cli.DeferredConcatTransport"),
                  patch("ccer.direct_cli.DirectGateway")):
                main(["--isolated-session", "--mode", "window", "--root", root])
                binding.assert_called_once_with()

    def test_direct_cli_rejects_headless_even_with_control_access(self):
        from unittest.mock import patch
        from ccer.direct_cli import main
        with patch("sys.argv", ["ccer-direct", "--mode", "headless",
                                "--access", "control"]):
            with self.assertRaises(SystemExit) as caught:
                main()
            self.assertNotEqual(caught.exception.code, 0)

    def test_modes_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(PolicyError):
                DirectGateway(FakeConcat(), root, access="unrestricted")
            result = DirectGateway(FakeConcat(), root).handle(
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            self.assertIn("observe", result["result"]["instructions"])
