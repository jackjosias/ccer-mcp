"""End-to-end format delivery certification against a CCER-produced MP4."""
import json
import time
from pathlib import Path
from ccer.server import Gateway
from ccer.transport import ConcatTransport


def main():
    root = Path.home() / "Videos/CCER"
    videos = sorted(root.glob("CCER-RECIPE-*.mp4"))
    if not videos:
        raise RuntimeError("First run tests.live_recipe")
    source = videos[-1]
    output = root / ("CCER-DELIVERY-" + time.strftime("%Y%m%d-%H%M%S") + ".mp4")
    binary = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    c = ConcatTransport(binary, "window", timeout=60)
    try:
        c.start()
        g = Gateway(c, root)
        report = g.invoke("ccer_delivery_transcode", {
            "file": str(source), "output": str(output),
            "profile": "square-preview"})["structuredContent"]
        checked = g.invoke("ccer_export_verify", {
            "file": str(output), "width": 320, "height": 320})["structuredContent"]
        visuals = g.invoke("ccer_visual_scan", {
            "file": str(output), "seconds": 5})["structuredContent"]
        print(json.dumps({
            "transcode": report, "exportPassed": checked["passed"],
            "visualScan": visuals, "audit": g.invoke("ccer_audit_report", {})["structuredContent"]},
            ensure_ascii=False, indent=2), flush=True)
        if not (report["verified"] and checked["passed"]):
            raise RuntimeError("Delivery verification failed")
    finally:
        c.close()


if __name__ == "__main__":
    main()
