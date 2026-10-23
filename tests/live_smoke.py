"""Read-only live qualification of the CCER -> Concat Desktop MCP chain."""
import argparse
import json
from pathlib import Path

from ccer.server import Gateway
from ccer.transport import ConcatTransport


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--concat-bin", type=Path, default=Path.home() /
        "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage")
    parser.add_argument("--root", type=Path, default=Path.home() / "Videos/CCER")
    parser.add_argument("--mode", choices=("window", "headless"), default="window")
    parser.add_argument("--schemas", action="store_true")
    args = parser.parse_args()
    transport = ConcatTransport(args.concat_bin, args.mode, timeout=15)
    try:
        transport.start()
        gateway = Gateway(transport, args.root)
        result = gateway.invoke("ccer_preflight", {})["structuredContent"]
        report = {"nativeTools": len(gateway.native), "ccerTools": len(gateway.catalogue) - len(gateway.native),
                  "totalTools": len(gateway.catalogue),
                  "concatVersion": result["concat"].get("concat"),
                  "mcpMode": result["concat"].get("mcp", {}).get("mode"),
                  "rootWritable": result["rootWritable"],
                  "ffprobe": result["ffprobe"], "ffmpeg": result["ffmpeg"],
                  "auditValid": result["audit"]["valid"]}
        if args.schemas:
            report["schemas"] = {
                name: gateway.native[name].get("inputSchema") for name in
                ("project_create", "title_add", "export_start", "export_wait")
                if name in gateway.native}
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if result["concat"].get("mcp", {}).get("mode") != args.mode:
            raise RuntimeError("Unexpected downstream MCP mode")
        if len(gateway.native) < 42:
            raise RuntimeError("Expected at least 42 Concat tools")
    finally:
        transport.close()


if __name__ == "__main__":
    main()
