"""Live GUI bridge acceptance: Concat-only screenshot, menu click and Escape."""
import json
from pathlib import Path

from ccer.server import Gateway
from ccer.transport import ConcatTransport


def main():
    path = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    root = Path.home() / "Videos/CCER"
    transport = ConcatTransport(path, "window", timeout=45)
    try:
        transport.start()
        gateway = Gateway(transport, root)
        if len(gateway.catalogue) != 85:
            raise RuntimeError("Expected 85 native+CCER tools")
        status = gateway.invoke("ccer_desktop_status", {})["structuredContent"]
        if status["window"]["title"] != "Concat":
            raise RuntimeError("Wrong window detected")
        screen = gateway.invoke("ccer_desktop_capture", {"maxWidth": 840})
        if screen["content"][1]["type"] != "image":
            raise RuntimeError("Desktop screenshot not returned as an MCP image")
        before = screen["structuredContent"]
        # Click the harmless "Fichier" menu within Concat only, then close with Escape.
        click = gateway.invoke("ccer_desktop_act", {
            "expectedWindowId": before["window"]["windowId"],
            "action": "click", "x": 28, "y": 16,
            "button": 1, "confirm": True, "withCapture": True})
        if click["content"][1]["type"] != "image" or not click["structuredContent"]["actionSent"]:
            raise RuntimeError("Concat-only menu click did not complete")
        result = gateway.invoke("ccer_desktop_act", {
            "expectedWindowId": before["window"]["windowId"],
            "action": "key", "key": "Escape", "confirm": True,
            "withCapture": True})
        if result["content"][1]["type"] != "image":
            raise RuntimeError("No screenshot returned after GUI action")
        after = result["structuredContent"]
        if not (after["actionSent"] and after["verifiedTarget"] and
                after["windowId"] == before["window"]["windowId"]):
            raise RuntimeError("GUI action not verified as Concat-targeted")
        print(json.dumps({"toolCount": len(gateway.catalogue),
            "window": status["window"], "capture": {"sha256": before["sha256"],
                "width": before["imageWidth"]},
            "action": {"action": after["action"], "target": after["windowId"],
                       "clickSent": click["structuredContent"]["actionSent"],
                       "sent": after["actionSent"], "afterCapture": after["sha256"]},
            "audit": gateway.invoke("ccer_audit_report", {})["structuredContent"]["valid"]},
            indent=2, ensure_ascii=False), flush=True)
    finally:
        transport.close()


if __name__ == "__main__":
    main()
