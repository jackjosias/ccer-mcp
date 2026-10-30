"""External client -> CCER Direct control -> Concat X11 without a WCER call."""
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    script = Path(__file__).resolve().parents[1] / "ccer_direct_stdio.py"
    env = dict(os.environ, CCER_DIRECT_ACCESS="control")
    child = subprocess.Popen([sys.executable, str(script)], cwd="/tmp", env=env,
                             text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, bufsize=1)
    counter = 0

    def request(method, params=None):
        nonlocal counter
        counter += 1
        child.stdin.write(json.dumps({"jsonrpc": "2.0", "id": counter,
                                       "method": method, "params": params or {}}) + "\n")
        child.stdin.flush()
        line = child.stdout.readline()
        if not line:
            try:
                child.wait(timeout=4)
            except subprocess.TimeoutExpired:
                pass
            details = child.stderr.read()[-2500:] if child.poll() is not None else "process hung with closed stdout"
            raise RuntimeError("CCER Direct stopped unexpectedly: " + details)
        message = json.loads(line)
        if message.get("id") != counter or message.get("error"):
            raise RuntimeError("MCP protocol failure: " + str(message)[:400])
        return message["result"]

    try:
        request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
        child.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        child.stdin.flush()
        tools = {item["name"] for item in request("tools/list")["tools"]}
        if ("ccer_desktop_act" not in tools or "ccer_desktop_capture" not in tools
                or "project_create" in tools or "export_start" in tools
                or "ccer_produce" in tools):
            raise RuntimeError("GUI-first policy missing from direct MCP catalogue")
        refused = request("tools/call", {"name": "project_create",
                                        "arguments": {"name": "FORBIDDEN"}})
        if not refused.get("isError"):
            raise RuntimeError("Headless project creation was not blocked")
        info = request("tools/call", {"name": "ccer_desktop_status", "arguments": {}})
        if info.get("isError"):
            raise RuntimeError("Concat Desktop was not detected")
        state = info["structuredContent"]
        window_id = state["window"]["windowId"]
        before = request("tools/call", {"name": "ccer_desktop_capture",
                                        "arguments": {"maxWidth": 640}})
        if before.get("isError") or not any(b.get("type") == "image" for b in before["content"]):
            raise RuntimeError("Missing mandatory pre-action screenshot")
        if not state.get("inputReady", False):
            refused_key = request("tools/call", {"name": "ccer_desktop_act",
                "arguments": {"expectedWindowId": window_id, "action": "key",
                              "key": "Escape", "confirm": True, "withCapture": True}})
            if not refused_key.get("isError"):
                raise RuntimeError("A shared-desktop keyboard command was accepted!")
            reason = str(refused_key.get("content", []))
            if "FOCUS_ISOLATION_REQUIRED" not in reason:
                raise RuntimeError("Unexpected focus isolation failure: " + reason[:400])
            print(json.dumps({"tools": len(tools), "guiFirstEnforced": True,
                  "headlessProjectCreationDenied": True,
                  "sharedDisplayInputDenied": True,
                  "readOnlyCaptureSucceeded": True,
                  "isolatedConcatControl": "NOT_YET_AVAILABLE",
                  "wcerInExecution": False}, indent=2))
            return
        acted = request("tools/call", {"name": "ccer_desktop_act", "arguments": {
            "expectedWindowId": window_id, "action": "key",
            "key": "Escape", "confirm": True, "withCapture": True}})
        if acted.get("isError"):
            raise RuntimeError("Scoped Escape was not accepted: " + str(acted.get("content", []))[:900])
        meta = acted["structuredContent"]
        if meta.get("windowId") != window_id or not meta.get("actionSent"):
            raise RuntimeError("GUI action window mismatch")
        if not any(block.get("type") == "image" for block in acted["content"]):
            raise RuntimeError("No screenshot returned after action")
        no_repeat = request("tools/call", {"name": "ccer_desktop_act", "arguments": {
            "expectedWindowId": window_id, "action": "key",
            "key": "Escape", "confirm": True}})
        if not no_repeat.get("isError"):
            raise RuntimeError("Another GUI action was allowed without a new screenshot")
        # Demonstrate actual pointer movement on an EMPTY panel area.
        # No clip, timeline or existing project content is touched.
        next_before = request("tools/call", {"name": "ccer_desktop_capture",
                                             "arguments": {"maxWidth": 640}})
        if next_before.get("isError"):
            raise RuntimeError("Fresh screenshot missing before visible drag")
        drag = request("tools/call", {"name": "ccer_desktop_act", "arguments": {
            "expectedWindowId": window_id, "action": "drag",
            "x": 55, "y": 295, "targetX": 140, "targetY": 315,
            "duration": .65, "confirm": True, "withCapture": True}})
        if drag.get("isError") or not any(b.get("type") == "image" for b in drag["content"]):
            raise RuntimeError("Visible GUI drag was not completed")
        if not drag["structuredContent"].get("actionSent"):
            raise RuntimeError("X11 pointer drag did not reach Concat")
        print(json.dumps({"tools": len(tools), "guiFirstEnforced": True,
                          "headlessProjectCreationDenied": True,
                          "concatWindow": window_id, "escapeSent": True,
                          "beforeAndAfterImages": True,
                          "unobservedRepeatDenied": True,
                          "visibleDragExecuted": True,
                          "wcerInExecution": False}, indent=2))
    finally:
        child.stdin.close()
        try:
            child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


if __name__ == "__main__":
    main()
