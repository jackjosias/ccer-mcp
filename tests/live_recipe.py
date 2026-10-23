"""Real CCER declarative recipe smoke: isolated short from an earlier certified MP4."""
import json
import time
from pathlib import Path

from ccer.server import Gateway
from ccer.transport import ConcatTransport


def main():
    root = Path.home() / "Videos/CCER"
    sources = sorted(root.glob("CCER-CERT-*.mp4"))
    if not sources:
        raise RuntimeError("No previous CCER certified test video; run live_render first")
    source = sources[-1]
    binary = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    upstream = ConcatTransport(binary, "window", timeout=45)
    try:
        upstream.start()
        gateway = Gateway(upstream, root)
        name = "CCER-RECIPE-" + time.strftime("%Y%m%d-%H%M%S")
        production = gateway.invoke("ccer_produce", {
            "name": name, "profile": "custom", "fast": True,
            "video": {"width": 320, "height": 180, "rateNum": 24, "rateDen": 1},
            "shots": [str(source)],
            "titles": [{"start": 0.0, "duration": 1.0,
                        "text": "MONTAGE CCER AUTOMATISE"}],
            "captions": [{"start": 1.0, "duration": 0.7,
                          "text": "Concat MCP + Creative Runtime"}],
            "export": True})["structuredContent"]
        print(json.dumps({
            "missionId": production["missionId"],
            "project": production["project"],
            "videoFile": production.get("videoFile"),
            "exported": production["exported"],
            "clipCount": production["timelineQA"]["clipCount"],
            "exportQA": production.get("exportQA", {}).get("passed"),
            "audit": gateway.invoke("ccer_audit_report", {})["structuredContent"]},
            ensure_ascii=False, indent=2), flush=True)
        if not production["exported"]:
            raise RuntimeError("Recipe export did not qualify")
    finally:
        upstream.close()


if __name__ == "__main__":
    main()
