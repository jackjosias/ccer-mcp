"""One-call CCER studio: reviewed plan, narration, mix, directed edit, export and QA."""
from __future__ import annotations
import json
import math
import re
import shutil
from pathlib import Path

from .audio_studio import mix
from .controls import PolicyError, atomic_json, media_probe
from .creative import plan as creative_plan, save as save_document
from .director_render import render as directed_render
from .quality import captions_check, visual_scan
from .voice_extensions import synthesize_flite


def _duration(path):
    meta = media_probe(path)
    if not any(s.get("codec_type") == "audio" for s in meta["streams"]):
        raise PolicyError("Narration contains no audio stream")
    try:
        seconds = float(meta["format"]["duration"])
    except (ValueError, TypeError) as exc:
        raise PolicyError("Narration duration unavailable") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise PolicyError("Invalid narration duration")
    return seconds


def produce_studio(engine, spec):
    if not isinstance(spec, dict):
        raise PolicyError("Studio specification must be a JSON object")
    name = spec.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,60}", name):
        raise PolicyError("Name must be 1..61 ASCII characters: alphanumerics, _ and -")
    if not isinstance(spec.get("brief"), dict):
        raise PolicyError("Supply brief with topic, script and assets")
    recorded = spec.get("narrationFile")
    generate = spec.get("generateEnglishVoice", False)
    music = spec.get("musicFile")
    if not isinstance(generate, bool) or (generate and recorded):
        raise PolicyError("Use either recorded narration or generated English speech")
    if recorded is not None and not isinstance(recorded, str):
        raise PolicyError("narrationFile must be a string")
    if music is not None and not isinstance(music, str):
        raise PolicyError("musicFile must be a string")
    if music and not (recorded or generate):
        raise PolicyError("Music mixing requires narration")
    if not isinstance(spec.get("burnCaptions", True), bool):
        raise PolicyError("burnCaptions must be boolean")
    if shutil.disk_usage(engine.root).free < 1024 * 1024 * 1024:
        raise PolicyError("Less than 1 GiB free; production refused")
    planned = creative_plan(spec["brief"])
    if len(planned["scenes"]) > 50 or not planned["productionReady"]:
        raise PolicyError("At most 50 approved scenes with real local media required")
    for scene in planned["scenes"]:
        scene["source"] = str(engine.path(scene["source"], must_exist=True))
        if not Path(scene["source"]).is_file():
            raise PolicyError("Scene source is not a file")
    if "video" in spec:
        planned["video"] = spec["video"]
    if not captions_check(planned["captions"])["passed"]:
        raise PolicyError("Caption timing invalid")
    voice_file = engine.path(recorded, must_exist=True) if recorded else None
    music_file = engine.path(music, must_exist=True) if music else None
    if voice_file:
        _duration(voice_file)
    if music_file and not music_file.is_file():
        raise PolicyError("Music source missing")
    folder = engine.path(str(engine.root / name))
    if folder.exists() or folder.is_symlink():
        raise PolicyError("Production name exists; no overwrite or blind retry")
    mission = engine._mission("studio_pipeline", {
        "name": name, "sceneCount": len(planned["scenes"])})
    try:
        folder.mkdir(mode=0o700)
        save_document(engine.root, str(folder / "plan.json"),
                      json.dumps(planned, ensure_ascii=False, indent=2) + "\n")
        if generate:
            if planned["language"] not in ("en", "en-US", "en-GB"):
                raise PolicyError("FFmpeg flite supports English only; supply French recording")
            result = synthesize_flite(spec["brief"]["script"], folder / "narration.wav",
                                      language=planned["language"])
            voice_file = engine.path(result["file"], must_exist=True)
        if voice_file and music_file:
            mixed = mix(voice_file, music_file, folder / "master.m4a",
                        music_gain=float(spec.get("musicGain", 0.18)),
                        target_lufs=float(spec.get("targetLufs", -16.0)))
            voice_file = engine.path(mixed["file"], must_exist=True)
        voice_seconds = _duration(voice_file) if voice_file else None
        expected = float(planned["durationSeconds"])
        if voice_seconds and voice_seconds > expected + 0.25:
            raise PolicyError("Narration exceeds video duration; increase durationSeconds")
        result = directed_render(engine, planned, str(folder / "final.mp4"),
                                 audio=str(voice_file) if voice_file else None,
                                 burn_captions=spec.get("burnCaptions", True),
                                 preset=spec.get("preset", "veryfast"))
        verified = engine._dispatch("ccer_export_verify", {
            "file": result["file"], "width": result["width"],
            "height": result["height"], "minDuration": expected - 0.6,
            "maxDuration": expected + 0.6})
        if not verified["passed"]:
            raise PolicyError("Export failed technical verification")
        visual = visual_scan(Path(result["file"]), seconds=min(30, max(1, int(expected))))
        report = {"missionId": mission["id"], "name": name, "render": result,
            "storyboard": str(folder / "plan.json"), "captionFile": result.get("subtitles"),
            "voiceFile": str(voice_file) if voice_file else None,
            "voiceSeconds": voice_seconds, "expectedRuntime": expected,
            "technicalQA": verified["passed"], "visualQA": visual,
            "needsVisualReview": bool(visual["needsHumanReview"]),
            "timingAlignedToSpeech": False, "researchVerified": False, "passed": True}
        atomic_json(folder / "report.json", report)
        engine._finish(mission, "completed", output=result["file"], inspected=True)
        return report
    except BaseException as exc:
        engine._finish(mission, "unknown", errorType=type(exc).__name__, directory=str(folder))
        raise
