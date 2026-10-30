"""Declarative, restart-auditable, A-to-Z Concat timeline production recipe.

Uses original Concat media/edit/export tools instead of duplicating its video engine.
"""
import hashlib
import json
import re
import shutil
from .controls import PolicyError
from .transport import structured


FORMATS = {
    "shorts": (1080, 1920, 30),
    "reels": (1080, 1920, 30),
    "tiktok": (1080, 1920, 30),
    "youtube": (1920, 1080, 30),
    "tutorial": (1920, 1080, 30),
    "documentary": (1920, 1080, 25),
    "podcast": (1920, 1080, 30),
    "advertisement": (1920, 1080, 30),
    "cinematic": (1920, 1080, 24),
    "custom": (1920, 1080, 30),
}


def produce(engine, spec):
    name = spec["name"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9 _-]{0,63}", name):
        raise PolicyError("Invalid production name")
    shots = spec["shots"]
    if not isinstance(shots, list) or not 1 <= len(shots) <= 200 or not all(isinstance(s, str) for s in shots):
        raise PolicyError("shots must be 1..200 local media paths")
    profile = spec.get("profile", "custom")
    if profile not in FORMATS:
        raise PolicyError("Unknown production profile")
    w, h, fps = FORMATS[profile]
    video = spec.get("video") or {"width": w, "height": h, "rateNum": fps, "rateDen": 1}
    if not isinstance(video, dict) or any(not isinstance(video.get(k), int) for k in
                                       ("width", "height", "rateNum", "rateDen")):
        raise PolicyError("Invalid video settings")
    if not (64 <= video["width"] <= 8192 and 64 <= video["height"] <= 8192
            and 1 <= video["rateNum"] <= 240000 and 1 <= video["rateDen"] <= 1001):
        raise PolicyError("Video settings outside supported range")
    captions = spec.get("captions", [])
    titles = spec.get("titles", [])
    music = spec.get("music", [])
    if not isinstance(captions, list) or len(captions) > 1000:
        raise PolicyError("Max 1000 caption cues")
    if not isinstance(titles, list) or len(titles) > 100:
        raise PolicyError("Max 100 titles")
    if not isinstance(music, list) or len(music) > 8:
        raise PolicyError("Max 8 soundtrack files")
    if any(not isinstance(entry, dict) for entry in captions + titles):
        raise PolicyError("Caption and title cues must be objects")
    if any(not isinstance(item, str) for item in music):
        raise PolicyError("Music paths must be strings")
    sources = [engine.path(p, must_exist=True) for p in shots + music]
    if any(not p.is_file() for p in sources):
        raise PolicyError("Every source must be a file")
    folder = engine.path(str(engine.root / name))
    exported = engine.path(str(engine.root / (name + ".mp4")))
    if folder.exists() or exported.exists():
        raise PolicyError("Production already exists: choose a unique name")
    if shutil.disk_usage(engine.root).free < 1024 * 1024 * 1024:
        raise PolicyError("Less than 1 GiB free; refuse automated production")
    mission = engine._mission("production", {
        "name": name, "profile": profile, "sourceCount": len(sources),
        "sourceManifestSha256": hashlib.sha256(json.dumps(
            [str(p) for p in sources], sort_keys=True).encode()).hexdigest()})
    try:
        engine.upstream.tool("project_create", {
            "location": str(engine.root), "name": name, "video": video})
        media_ids = {}
        def obtain(p):
            key = str(p)
            if key not in media_ids:
                record = structured(engine.upstream.tool("media_import",
                    {"path": str(folder), "file": key}))
                ident = record.get("createdId")
                if not ident:
                    raise PolicyError("Concat import returned no media ID: " + key)
                media_ids[key] = ident
            return media_ids[key]
        shot_ids = [obtain(engine.path(p, must_exist=True)) for p in shots]
        engine.upstream.tool("clips_add_sequence", {
            "path": str(folder), "mediaIds": shot_ids, "start": 0})
        for source in music:
            music_id = obtain(source)
            engine.upstream.tool("clips_add_sequence", {
                "path": str(folder), "mediaIds": [music_id], "start": 0})
        for cue in titles + captions:
            text = cue.get("text")
            if not isinstance(text, str) or not text.strip():
                raise PolicyError("Empty title/caption")
            start, duration = float(cue.get("start", 0)), float(cue.get("duration", 2))
            if start < 0 or duration <= 0:
                raise PolicyError("Invalid cue timing")
            engine.upstream.tool("title_add", {
                "path": str(folder), "start": start, "duration": duration,
                "above": True, "style": {"content": text,
                    **(cue.get("style") if isinstance(cue.get("style"), dict) else {})}})
        qa = engine._dispatch("ccer_timeline_validate", {
            "path": str(folder)})
        engine.upstream.tool("project_save", {"path": str(folder)})
        output = {"missionId": mission["id"], "project": str(folder),
                  "profile": profile, "shots": len(shots), "music": len(music),
                  "titles": len(titles), "captions": len(captions), "timelineQA": qa,
                  "exported": False}
        if spec.get("export", True):
            export = structured(engine.upstream.tool("export_start", {
                "path": str(folder), "output": str(exported),
                "preset": "ultrafast" if spec.get("fast", False) else "medium"}))
            job = export.get("job")
            if not job:
                raise PolicyError("Concat export returned no job")
            wait = structured(engine.upstream.tool("export_wait",
                {"job": job, "timeoutSeconds": 600}, timeout=650))
            if wait.get("state") != "done":
                raise PolicyError("Export did not finish: " + str(wait.get("state")))
            output["exportQA"] = engine._dispatch("ccer_export_verify", {
                "file": str(exported), "width": video["width"], "height": video["height"]})
            output["exported"] = output["exportQA"]["passed"]
            output["videoFile"] = str(exported)
            if not output["exported"]:
                raise PolicyError("Export failed QA")
        engine._finish(mission, "completed", project=str(folder),
                       exported=output["exported"])
        return output
    except BaseException as err:
        engine._finish(mission, "unknown", errorType=type(err).__name__,
                       project=str(folder))
        raise
