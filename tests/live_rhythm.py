"""Live rhythm test: synthetic 120 BPM music -> MCP analysis -> CCER directed export."""
import json
import math
import time
import wave
from array import array
from pathlib import Path

from ccer.server import Gateway
from ccer.transport import ConcatTransport


def make_click_track(path):
    rate = 8000
    audio = array("h")
    for idx in range(rate * 4):
        t = idx / rate
        active = idx % (rate // 2) < int(rate * 0.07)
        audio.append(int(22000 * math.sin(2 * math.pi * 440 * t)) if active else 0)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(audio.tobytes())


def main():
    root = Path.home() / "Videos/CCER"
    media = sorted(root.glob("CCER-RECIPE-*.mp4"))
    if not media:
        raise RuntimeError("Missing CCER media fixture: run tests.live_recipe first")
    folder = root / ("CCER-RHYTHM-" + time.strftime("%Y%m%d-%H%M%S"))
    folder.mkdir(exist_ok=False)
    audio = folder / "music_120bpm.wav"
    make_click_track(audio)
    binary = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    upstream = ConcatTransport(binary, "window", timeout=45)
    try:
        upstream.start()
        gateway = Gateway(upstream, root)
        if len(gateway.catalogue) != 75:
            raise RuntimeError("MCP catalog must expose 75 tools")
        silences = gateway.invoke("ccer_silence_map", {
            "file": str(audio), "seconds": 4, "minSilence": 0.15})["structuredContent"]
        beats = gateway.invoke("ccer_beat_candidates", {
            "file": str(audio), "seconds": 4})["structuredContent"]
        cuts = gateway.invoke("ccer_cut_plan", {
            "duration": 4, "onsets": beats["onsetsSeconds"],
            "targetShot": 1., "minShot": .3, "maxShot": 1.5})["structuredContent"]
        captions = gateway.invoke("ccer_caption_timing_hint", {
            "cues": [{"text": "Intro musique"}, {"text": "Montage CCER"}],
            "silenceReport": silences})["structuredContent"]
        if len(beats["onsetsSeconds"]) < 4 or len(cuts["shots"]) < 3:
            raise RuntimeError("Insufficient detected musical events / shot candidates")
        timeline = {
            "topic": "CCER beat montage",
            "video": {"width": 320, "height": 180, "rateNum": 24, "rateDen": 1},
            "scenes": [{
                "id": "cut-" + str(index + 1),
                "start": clip["start"], "duration": clip["duration"],
                "source": str(media[-1])
            } for index, clip in enumerate(cuts["shots"])],
            "captions": []
        }
        output = folder / "montage_rythme.mp4"
        result = gateway.invoke("ccer_directed_render", {
            "plan": timeline, "file": str(output),
            "audio": str(audio), "burnCaptions": False,
            "preset": "ultrafast"})["structuredContent"]
        verified = gateway.invoke("ccer_export_verify", {
            "file": str(output), "width": 320, "height": 180,
            "minDuration": 3.5, "maxDuration": 4.5})["structuredContent"]
        result_summary = {
            "estimatedBpm": beats["estimatedBpm"],
            "tempoConfidence": beats["tempoConfidence"],
            "onsetsCount": len(beats["onsetsSeconds"]),
            "silencesCount": len(silences["silences"]),
            "cutCount": len(cuts["cutPointsSeconds"]),
            "captionTimingMethod": captions["method"],
            "render": result, "verified": verified["passed"]
        }
        print(json.dumps(result_summary, indent=2, ensure_ascii=False), flush=True)
        if not verified["passed"]:
            raise RuntimeError("Music montage did not qualify")
    finally:
        upstream.close()


if __name__ == "__main__":
    main()
