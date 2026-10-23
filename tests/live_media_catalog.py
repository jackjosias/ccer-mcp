"""Live CCER Media Intelligence: user annotations -> matching -> verified visual MP4."""
import json
import re
import subprocess
import time
from pathlib import Path

from ccer.server import Gateway
from ccer.transport import ConcatTransport


def solid(path, color):
    p = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=24:d=3",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt",
                        "yuv420p", str(path)], capture_output=True, text=True, timeout=50)
    if p.returncode:
        raise RuntimeError("Could not create synthetic clip: " + p.stderr[-300:])


def chroma(path, moment):
    p = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info",
                        "-ss", str(moment), "-i", str(path), "-frames:v", "1",
                        "-vf", "signalstats,metadata=mode=print",
                        "-an", "-f", "null", "-"],
                       capture_output=True, text=True, timeout=45)
    values = re.findall(r"lavfi\.signalstats\.VAVG=([\d.]+)", p.stderr)
    if p.returncode or not values:
        raise RuntimeError("FFmpeg chroma analysis failed")
    return float(values[-1])


def main():
    root = Path.home() / "Videos" / "CCER"
    folder = root / ("CCER-MEDIA-" + time.strftime("%Y%m%d-%H%M%S"))
    folder.mkdir(exist_ok=False)
    red, blue = folder / "red.mp4", folder / "blue.mp4"
    solid(red, "red")
    solid(blue, "blue")
    binary = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    upstream = ConcatTransport(binary, "window", timeout=50)
    try:
        upstream.start()
        gateway = Gateway(upstream, root)
        if len(gateway.catalogue) != 82:
            raise RuntimeError("Expected 82 MCP tools")
        catalog = folder / "catalog.json"
        indexed = gateway.invoke("ccer_media_index", {
            "items": [
                {"file": str(red), "tags": ["rouge", "eclatant"],
                 "description": "Rouge éclatant, fond uniforme"},
                {"file": str(blue), "tags": ["bleu", "profond"],
                 "description": "Bleu profond, fond uniforme"}],
            "output": str(catalog)})["structuredContent"]
        found = gateway.invoke("ccer_media_search", {
            "catalog": str(catalog), "text": "rouge éclatant"})["structuredContent"]
        planned = gateway.invoke("ccer_creative_plan", {"brief": {
            "topic": "Plans annotés",
            "script": "Rouge éclatant. Bleu profond.",
            "profile": "custom", "durationSeconds": 4,
            "language": "fr"}})["structuredContent"]
        planned["video"] = {"width": 320, "height": 180, "rateNum": 24, "rateDen": 1}
        match = gateway.invoke("ccer_media_match", {
            "catalog": str(catalog), "plan": planned,
            "allowReuse": False})["structuredContent"]
        if not match["ready"] or [s["source"] for s in match["plan"]["scenes"]] != [str(red), str(blue)]:
            raise RuntimeError("Wrong source selections: " + str(match))
        produced = gateway.invoke("ccer_media_match_render", {
            "catalog": str(catalog), "plan": planned,
            "output": str(folder / "final.mp4"), "confirm": True,
            "burnCaptions": False, "preset": "ultrafast",
            "allowReuse": False})["structuredContent"]
        first = chroma(produced["render"]["file"], .5)
        last = chroma(produced["render"]["file"], 3.5)
        if first < last + 70:
            raise RuntimeError("Real output did not show red shot followed by blue shot")

        # Media-inpoint test: a joined red-blue source, seek into blue half.
        joined = folder / "joined.mp4"
        p = subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", str(red), "-i", str(blue),
            "-filter_complex", "[0:v]trim=duration=2,setpts=PTS-STARTPTS[v0];"
                               "[1:v]trim=duration=2,setpts=PTS-STARTPTS[v1];"
                               "[v0][v1]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-c:v", "libx264", "-preset", "ultrafast", str(joined)],
            capture_output=True, text=True, timeout=60)
        if p.returncode:
            raise RuntimeError("Combined clip could not render: " + p.stderr[-300:])
        offset_plan = {"video": planned["video"], "scenes": [
            {"id": "offset", "source": str(joined), "mediaStart": 2.3, "duration": 1.0}],
            "captions": []}
        offset_result = gateway.invoke("ccer_directed_render", {
            "plan": offset_plan, "file": str(folder / "from_offset.mp4"),
            "burnCaptions": False, "preset": "ultrafast"})["structuredContent"]
        offset_color = chroma(offset_result["file"], .3)
        if offset_color > 150:
            raise RuntimeError("Inpoint seek did not select blue part of joined video")

        # Regression protection: still PNGs and short-video looping still work.
        image = folder / "still.png"
        frame = subprocess.run([
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-ss", "0.5", "-i", str(red), "-frames:v", "1", str(image)],
            capture_output=True, text=True, timeout=35)
        if frame.returncode:
            raise RuntimeError("Could not extract PNG regression fixture")
        still = gateway.invoke("ccer_directed_render", {
            "plan": {"video": planned["video"],
                     "scenes": [{"id": "still", "source": str(image), "duration": 1.0}],
                     "captions": []},
            "file": str(folder / "still.mp4"), "burnCaptions": False,
            "preset": "ultrafast"})["structuredContent"]
        loop = gateway.invoke("ccer_directed_render", {
            "plan": {"video": planned["video"],
                     "scenes": [{"id": "loop", "source": str(red), "duration": 4.0}],
                     "captions": []},
            "file": str(folder / "loop.mp4"), "burnCaptions": False,
            "preset": "ultrafast"})["structuredContent"]
        if not (still["verified"] and loop["verified"]):
            raise RuntimeError("Regressed still-image or zero-offset looping video")

        result = {"indexed": indexed["indexedCount"],
                  "queryMatches": found["totalMatches"], "matched": len(match["matched"]),
                  "renderQualified": produced["technicalQA"],
                  "video": produced["render"]["file"],
                  "beginEndVavg": [first, last], "offsetVavg": offset_color,
                  "stillImageVerified": still["verified"], "loopVerified": loop["verified"],
                  "auditValid": gateway.invoke("ccer_audit_report", {})["structuredContent"]["valid"]}
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    finally:
        upstream.close()


if __name__ == "__main__":
    main()
