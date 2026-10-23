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
            raise RuntimeError("CCER Direct stopped unexpectedly")
        message = json.loads(line)
        if message.get("id") != counter or message.get("error"):
            raise RuntimeError("MCP protocol failure: " + str(message)[:400])
        return message["result"]

    try:
        request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
        child.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        child.stdin.flush()
        tools = {item["name"] for item in request("tools/list")["tools"]}
        if len(tools) != 85 or "ccer_desktop_act" not in tools:
            raise RuntimeError("Control profile tools missing")
        info = request("tools/call", {"name": "ccer_desktop_status", "arguments": {}})
        if info.get("isError"):
            raise RuntimeError("Concat Desktop was not detected")
        window_id = info["structuredContent"]["window"]["windowId"]
        acted = request("tools/call", {"name": "ccer_desktop_act", "arguments": {
            "expectedWindowId": window_id, "action": "key",
            "key": "Escape", "confirm": True, "withCapture": True}})
        if acted.get("isError"):
            raise RuntimeError("Scoped Escape was not accepted")
        meta = acted["structuredContent"]
        if meta.get("windowId") != window_id or not meta.get("actionSent"):
            raise RuntimeError("GUI action window mismatch")
        if not any(block.get("type") == "image" for block in acted["content"]):
            raise RuntimeError("No screenshot returned after action")
        print(json.dumps({"tools": len(tools), "controlAllowed": True,
                          "concatWindow": window_id, "escapeSent": True,
                          "imageReceived": True, "wcerInExecution": False}, indent=2))
    finally:
        child.stdin.close()
        try:
            child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


if __name__ == "__main__":
    main()
