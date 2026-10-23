"""End-to-end visual color/reframe/transition verification with isolated test clips."""
import json
import re
import subprocess
import time
from pathlib import Path

from ccer.server import Gateway
from ccer.transport import ConcatTransport


def make_solid(path, color):
    p = subprocess.run([
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=24:d=3",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        str(path)], text=True, capture_output=True, timeout=50)
    if p.returncode:
        raise RuntimeError("Color fixture render failed: " + p.stderr[-400:])


def sample_red_channel(path, second):
    # In YUV signalstats, VAVG distinguishes our synthetic red and blue scenes.
    p = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info",
        "-ss", f"{second:.3f}", "-i", str(path), "-frames:v", "1",
        "-vf", "signalstats,metadata=mode=print", "-an", "-f", "null", "-"],
        capture_output=True, text=True, timeout=35)
    if p.returncode:
        raise RuntimeError("Failed to sample transition frame: " + p.stderr[-300:])
    values = re.findall(r"lavfi\.signalstats\.VAVG=([0-9.]+)", p.stderr)
    if not values:
        raise RuntimeError("Missing VAVG frame telemetry")
    return float(values[-1])


def main():
    root = Path.home() / "Videos/CCER"
    folder = root / ("CCER-VISUAL-" + time.strftime("%Y%m%d-%H%M%S"))
    folder.mkdir(exist_ok=False)
    red, blue = folder / "red.mp4", folder / "blue.mp4"
    make_solid(red, "red")
    make_solid(blue, "blue")
    binary = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    client = ConcatTransport(binary, "window", timeout=45)
    try:
        client.start()
        gateway = Gateway(client, root)
        if len(gateway.catalogue) != 78:
            raise RuntimeError("Expected 78 MCP tools")
        color = gateway.invoke("ccer_color_report", {
            "file": str(red), "seconds": 2, "sampleInterval": .5})["structuredContent"]
        framed = gateway.invoke("ccer_reframe_export", {
            "file": str(red), "output": str(folder / "vertical.mp4"),
            "profile": "vertical-preview", "mode": "cover",
            "focusX": .5, "focusY": .5})["structuredContent"]
        transformed = gateway.invoke("ccer_transition_export", {
            "first": str(red), "second": str(blue),
            "output": str(folder / "crossfade.mp4"),
            "profile": "landscape-preview", "sceneSeconds": 1.5,
            "overlapSeconds": .5, "kind": "fade"})["structuredContent"]
        transition_v = [sample_red_channel(transformed["file"], t) for t in (.25, 1.25, 2.0)]
        if not transition_v[0] > transition_v[1] > transition_v[2]:
            raise RuntimeError("Crossfade not visually verifiable by red-to-blue chroma interpolation")
        qa = gateway.invoke("ccer_export_verify", {
            "file": transformed["file"], "width": 640, "height": 360,
            "minDuration": 2.3, "maxDuration": 2.7})["structuredContent"]
        out = {"color": color, "reframe": framed, "transition": transformed,
               "qualified": qa["passed"], "transitionVavg": transition_v, "audit": gateway.invoke(
                    "ccer_audit_report", {})["structuredContent"]["valid"]}
        print(json.dumps(out, ensure_ascii=False, indent=2), flush=True)
        if not (color["sampledFrames"] > 0 and framed["verified"] and
                transformed["verified"] and qa["passed"]):
            raise RuntimeError("Visual export qualification failed")
    finally:
        client.close()


if __name__ == "__main__":
    main()
