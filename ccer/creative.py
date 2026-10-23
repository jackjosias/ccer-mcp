"""Deterministic, auditable storyboarding based solely on user-supplied claims."""
import json
import math
import re

from .controls import PolicyError, inside
from .quality import captions_check
from .recipes import FORMATS

WPM = {"shorts": 155, "reels": 155, "tiktok": 155, "tutorial": 125,
       "documentary": 135, "podcast": 140, "cinematic": 110,
       "youtube": 140, "advertisement": 145, "custom": 140}


def plan(brief):
    if not isinstance(brief, dict):
        raise PolicyError("Brief must be an object")
    topic, script = brief.get("topic"), brief.get("script")
    if not isinstance(topic, str) or not 0 < len(topic.strip()) <= 240:
        raise PolicyError("A topic is required")
    if not isinstance(script, str) or not 0 < len(script.strip()) <= 15000:
        raise PolicyError("Supply a verified narration script")
    profile = brief.get("profile", "shorts")
    if profile not in FORMATS:
        raise PolicyError("Unknown profile")
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+|\n+", script.strip()) if s.strip()]
    weight = [max(1, len(s.split())) for s in sentences]
    natural = sum(weight) / WPM[profile] * 60 + len(sentences) * 0.2
    target = brief.get("durationSeconds", max(5., natural))
    if not isinstance(target, (float, int)) or not math.isfinite(target) or not 3 <= target <= 3600:
        raise PolicyError("Invalid duration")
    if target < natural * 0.6:
        raise PolicyError("Insufficient duration for supplied script")
    assets = brief.get("assets", [])
    if not isinstance(assets, list) or len(assets) > 200 or any(not isinstance(p, str) for p in assets):
        raise PolicyError("assets must be a list of up to 200 paths")
    cursor = 0.
    roles = ("hook", "context", "development", "payoff", "closing")
    scenes, cues = [], []
    for index, sentence in enumerate(sentences):
        seconds = target - cursor if index == len(sentences)-1 else target * weight[index] / sum(weight)
        role = roles[min(4, index * 5 // len(sentences))]
        start = round(cursor, 3)
        source = assets[index] if index < len(assets) else None
        scenes.append({"id": f"s{index+1:03}", "role": role,
            "start": start, "duration": round(seconds, 3), "voiceText": sentence,
            "visualIntent": sentence[:180], "source": source, "requiresMedia": source is None})
        cues.append({"start": start, "duration": round(seconds, 3), "text": sentence})
        cursor += seconds
    width, height, fps = FORMATS[profile]
    return {"topic": topic, "profile": profile, "language": brief.get("language", "fr"),
        "durationSeconds": round(cursor, 3), "estimatedSpeechSeconds": round(natural, 2),
        "video": {"width": width, "height": height, "rateNum": fps, "rateDen": 1},
        "scenes": scenes, "captions": cues, "captionQA": captions_check(cues),
        "productionReady": all(s["source"] for s in scenes),
        "factsExternallyVerified": False, "timingVerifiedAgainstVoice": False}


def storyboard(value):
    if not isinstance(value, dict) or not isinstance(value.get("scenes"), list):
        raise PolicyError("Plan with scenes required")
    return {"topic": value.get("topic"), "profile": value.get("profile"),
            "panels": [{"sceneId": s["id"], "timeSeconds": s["start"],
                "durationSeconds": s["duration"], "narration": s["voiceText"],
                "source": s["source"], "visualIntent": s["visualIntent"],
                "camera": "push-in" if s["role"] in ("hook", "payoff") else "static",
                "subtitleSafeZone": True} for s in value["scenes"]]}


def srt_time(seconds):
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        raise PolicyError("Invalid cue time")
    ms = round(seconds * 1000)
    return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"


def to_srt(cues):
    qa = captions_check(cues)
    if not qa["passed"]:
        raise PolicyError("Invalid captions: " + json.dumps(qa["issues"]))
    return "\n\n".join(
        f"{i}\n{srt_time(float(c['start']))} --> {srt_time(float(c['start'])+float(c['duration']))}\n{c['text'].strip()}"
        for i,c in enumerate(sorted(cues, key=lambda c: float(c["start"])), 1)) + "\n"


def save(root, output, content):
    path = inside(root, output)
    if path.suffix.lower() not in (".json", ".srt", ".md"):
        raise PolicyError("Only editorial JSON/SRT/MD files allowed")
    if path.exists() or path.is_symlink():
        raise PolicyError("Refuse overwriting existing creative document")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"file": str(path), "bytes": path.stat().st_size}
