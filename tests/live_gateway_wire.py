"""Full stdio MCP wire test: external client -> CCER -> Concat Desktop."""
import json
import subprocess
import sys
from pathlib import Path


def main():
    binary = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    root = Path.home() / "Videos/CCER"
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "ccer-e2e", "version": "0.1.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "ccer_preflight", "arguments": {}}},
    ]
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    command = [sys.executable, "-m", "ccer", "--concat-bin", str(binary),
               "--mode", "window", "--root", str(root)]
    process = subprocess.run(command, input=payload, text=True,
                             capture_output=True, timeout=50)
    if process.returncode:
        raise RuntimeError("MCP process returned failure: " + process.stderr[-500:])
    responses = {item["id"]: item for line in process.stdout.splitlines()
                 if (item := json.loads(line)).get("id") is not None}
    if len(responses) != 3:
        raise RuntimeError("Expected initialize, tools/list, tools/call responses")
    tools = responses[2]["result"]["tools"]
    before = responses[3]["result"]["structuredContent"]
    report = {"server": responses[1]["result"]["serverInfo"]["name"],
              "toolCount": len(tools),
              "concatMode": before["concat"]["mcp"]["mode"],
              "ffprobe": before["ffprobe"],
              "auditValid": before["audit"]["valid"]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["server"] != "ccer-mcp" or report["toolCount"] != 85:
        raise RuntimeError("MCP gateway tools mismatch")
    if report["concatMode"] != "window":
        raise RuntimeError("MCP gateway did not use Concat Desktop window")


if __name__ == "__main__":
    main()
