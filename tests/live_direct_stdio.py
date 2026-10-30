"""Real external MCP client -> CCER Direct stdio -> Concat, no WCER dependency."""
import json
import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path.home() / "Videos/CCER"
    script = Path(__file__).resolve().parents[1] / "ccer_direct_stdio.py"
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "ccer_desktop_capture", "arguments": {"maxWidth": 480}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "ccer_desktop_act", "arguments": {
             "action": "key", "key": "Escape", "confirm": True}}},
    ]
    env = dict(os.environ, CCER_DIRECT_ACCESS="observe", CCER_ROOT=str(root))
    # An absolute Python script path resolves imports without installed packages.
    process = subprocess.run(
        [sys.executable, str(script)], cwd="/tmp",
        input="\n".join(json.dumps(x) for x in requests) + "\n",
        capture_output=True, text=True, timeout=80, env=env)
    if process.returncode:
        raise RuntimeError("CCER Direct failed: " + process.stderr[-500:])
    replies = {m["id"]: m for line in process.stdout.splitlines()
               if (m := json.loads(line)).get("id") is not None}
    if len(replies) != 4:
        raise RuntimeError("Missing MCP responses")
    tools = {item["name"] for item in replies[2]["result"]["tools"]}
    capture = replies[3]["result"]
    if "ccer_desktop_capture" not in tools or "ccer_desktop_act" in tools:
        raise RuntimeError("Unsafe tool discovery in observe mode")
    if capture.get("isError") or not any(c.get("type") == "image" for c in capture["content"]):
        raise RuntimeError("No MCP image received")
    if not replies[4]["result"].get("isError"):
        raise RuntimeError("Desktop writes unexpectedly permitted")
    print(json.dumps({"server": "ccer-mcp", "mode": "observe", "tools": len(tools),
                      "imageReceived": True, "guiWritesDenied": True,
                      "wcerRequired": False}, indent=2))


if __name__ == "__main__":
    main()
