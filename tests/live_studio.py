"""Isolated live creative -> visual intelligence -> audio mix certification."""
import json
import subprocess
import time
from pathlib import Path

from ccer.server import Gateway
from ccer.transport import ConcatTransport


def audio_tone(path, hz, duration=2):
    task = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                           "-f", "lavfi", "-i", f"sine=frequency={hz}:duration={duration}",
                           "-c:a", "pcm_s16le", "-y", str(path)],
                          capture_output=True, text=True, timeout=45)
    if task.returncode:
        raise RuntimeError("Audio fixture failed: " + task.stderr[-300:])


def main():
    root = Path.home() / "Videos/CCER"
    source = sorted(root.glob("CCER-RECIPE-*.mp4"))[-1]
    run = "CCER-STUDIO-" + time.strftime("%Y%m%d-%H%M%S")
    folder = root / run
    folder.mkdir(exist_ok=False)
    binary = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    transport = ConcatTransport(binary, "window", timeout=45)
    try:
        transport.start()
        gateway = Gateway(transport, root)
        brief = {"topic": "Certification studio CCER", "profile": "shorts",
                 "durationSeconds": 6, "script": "Bonjour. Voici notre studio de montage.",
                 "assets": [str(source), str(source)]}
        plan = gateway.invoke("ccer_creative_plan", {"brief": brief})["structuredContent"]
        board = gateway.invoke("ccer_storyboard", {"plan": plan})["structuredContent"]
        saved = gateway.invoke("ccer_plan_save", {
            "plan": plan, "file": str(folder / "story.json")})["structuredContent"]
        subtitles = gateway.invoke("ccer_subtitles_write", {
            "cues": plan["captions"], "file": str(folder / "voice.srt")})["structuredContent"]
        sources = gateway.invoke("ccer_shot_inspect", {"files": [str(source)]})["structuredContent"]
        cuts = gateway.invoke("ccer_scene_detect", {
            "file": str(source), "seconds": 6})["structuredContent"]
        sheet = gateway.invoke("ccer_contact_sheet", {
            "file": str(source), "output": str(folder / "contact.png"), "interval": 0.5})["structuredContent"]
        voice = folder / "narration_fixture.wav"
        music = folder / "music_fixture.wav"
        audio_tone(voice, 220)
        audio_tone(music, 440)
        mixed = gateway.invoke("ccer_audio_mix", {
            "voice": str(voice), "music": str(music),
            "file": str(folder / "studio_mix.m4a"),
            "musicGain": 0.16, "targetLufs": -16})["structuredContent"]
        audio_qa = gateway.invoke("ccer_audio_validate", {
            "file": mixed["file"], "seconds": 3})["structuredContent"]
        print(json.dumps({"creativeScenes": len(plan["scenes"]),
            "storyboardPanels": len(board["panels"]), "srtFile": subtitles["file"],
            "planFile": saved["file"], "shotCount": len(sources["assets"]),
            "sceneCuts": cuts["count"], "contactSheet": sheet,
            "mix": mixed, "audioQA": audio_qa,
            "voiceEngines": gateway.invoke("ccer_tts_status", {})["structuredContent"]},
            ensure_ascii=False, indent=2), flush=True)
        assert len(plan["scenes"]) == 2 and len(board["panels"]) == 2
        assert sheet["bytes"] > 0 and mixed["verified"] and audio_qa["success"]
        assert mixed["loudnessWithin3Lufs"]
    finally:
        transport.close()


if __name__ == "__main__":
    main()
