"""CCER high-level, guarded editing workflows built on Concat's native tools."""
import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from .controls import Journal, PolicyError, atomic_json, audio_analyze, confirm, inside, media_probe
from .transport import structured


def schema(description, properties=None, required=None):
    return {"type": "object", "description": description,
            "properties": properties or {}, "required": required or [],
            "additionalProperties": False}


STRING = {"type": "string"}
BOOL = {"type": "boolean"}
NUMBER = {"type": "number"}
PATH = {"type": "string", "description": "Absolute path inside CCER_ROOT"}
TOOLS = {
    "ccer_preflight": schema("Check editing runtime, media tools and available storage"),
    "ccer_project_inspect": schema("Full project inspection", {"path": PATH}, ["path"]),
    "ccer_checkpoint_create": schema("Save, then snapshot the open Concat project", {"path": PATH}, ["path"]),
    "ccer_checkpoint_restore": schema("Restore a snapshot OFFLINE (project must be closed); explicit approval required",
        {"checkpointId": STRING, "confirm": BOOL}, ["checkpointId", "confirm"]),
    "ccer_timeline_validate": schema("Find gaps, overlaps and invalid clips", {
        "path": PATH, "gapThresholdSeconds": NUMBER}, ["path"]),
    "ccer_batch_edit": schema("Single Concat atomic undoable batch with read-after-write validation", {
        "path": PATH, "commands": {"type": "array", "items": {"type": "object"}, "minItems": 1, "maxItems": 200},
        "save": BOOL, "expectedClipDelta": {"type": "integer"}},
        ["path", "commands"]),
    "ccer_asset_analyze": schema("Read video/audio metadata via FFprobe", {"file": PATH}, ["file"]),
    "ccer_audio_validate": schema("Scan sample for loudness and silence via FFmpeg", {
        "file": PATH, "seconds": {"type": "integer", "minimum": 1, "maximum": 300}}, ["file"]),
    "ccer_export_verify": schema("Inspect exported file and compare expected media properties", {
        "file": PATH, "width": {"type": "integer"}, "height": {"type": "integer"},
        "minDuration": NUMBER, "maxDuration": NUMBER}, ["file"]),
    "ccer_mission_status": schema("Find an operation's recorded state", {"missionId": STRING}, ["missionId"]),
    "ccer_mission_recover": schema("Get safe recovery guidance without blindly replaying edits", {
        "missionId": STRING}, ["missionId"]),
    "ccer_audit_report": schema("Verify the hash-linked audit journal"),
    "ccer_produce": schema("Create, assemble, title, caption and optionally export a complete video from a declarative plan", {"name": STRING, "profile": STRING, "shots": {"type": "array", "items": PATH}, "music": {"type": "array", "items": PATH}, "titles": {"type": "array", "items": {"type": "object"}}, "captions": {"type": "array", "items": {"type": "object"}}, "video": {"type": "object"}, "export": BOOL, "fast": BOOL}, ["name", "shots"]),
    "ccer_caption_validate": schema("Professional subtitle reading speed, safe layout, timing and overlaps", {"cues": {"type": "array", "items": {"type": "object"}}}, ["cues"]),
    "ccer_visual_scan": schema("FFmpeg detection of black frames and frozen scenes", {"file": PATH, "seconds": {"type": "integer", "minimum": 1, "maximum": 300}}, ["file"]),
    "ccer_delivery_transcode": schema("Safe verified video transcode to common platform aspect ratios", {"file": PATH, "output": PATH, "profile": STRING}, ["file", "output", "profile"]),
    "ccer_creative_plan": schema("Reviewable story structure built from user-supplied script", {"brief": {"type": "object"}}, ["brief"]),
    "ccer_storyboard": schema("Shot list and visual intent for planned scenes", {"plan": {"type": "object"}}, ["plan"]),
    "ccer_plan_save": schema("Write new creative plan JSON", {"plan": {"type": "object"}, "file": PATH}, ["plan", "file"]),
    "ccer_subtitles_write": schema("Write validated timed SRT subtitles", {"cues": {"type": "array", "items": {"type": "object"}}, "file": PATH}, ["cues", "file"]),
    "ccer_tts_status": schema("Check installed offline voice synthesis engines"),
    "ccer_voice_synthesize": schema("Offline narration via installed eSpeak", {"text": STRING, "file": PATH, "language": STRING, "rate": {"type": "integer"}, "engine": STRING}, ["text", "file"]),
    "ccer_audio_mix": schema("Normalize voice and duck background music with measured integrated loudness", {"voice": PATH, "music": PATH, "file": PATH, "musicGain": NUMBER, "targetLufs": NUMBER}, ["voice", "file"]),
    "ccer_shot_inspect": schema("Technical shot ranking from codec, resolution, duration", {"files": {"type": "array", "items": PATH}}, ["files"]),
    "ccer_scene_detect": schema("FFmpeg cut/scene change detection", {"file": PATH, "threshold": NUMBER, "seconds": {"type": "integer"}}, ["file"]),
    "ccer_contact_sheet": schema("Create 3x3 PNG shot overview", {"file": PATH, "output": PATH, "interval": NUMBER}, ["file", "output"]),
    "ccer_directed_render": schema("Frame-timed multi-scene FFmpeg composition with optional spoken audio and burned subtitles", {"plan": {"type": "object"}, "file": PATH, "audio": PATH, "burnCaptions": BOOL, "preset": STRING}, ["plan", "file"]),
    "ccer_voice_flite": schema("Generate local English speech WAV with optional FFmpeg libflite", {"text": STRING, "file": PATH, "language": STRING, "speaker": STRING}, ["text", "file"]),
    "ccer_studio_produce": schema("Produce full local editorial plan, narration, subtitles, music mix, directed video, export QA", {"name": STRING, "brief": {"type": "object"}, "video": {"type": "object"}, "narrationFile": PATH, "generateEnglishVoice": BOOL, "musicFile": PATH, "musicGain": NUMBER, "targetLufs": NUMBER, "burnCaptions": BOOL, "preset": STRING}, ["name", "brief"]),
    "ccer_silence_map": schema("Detect quiet and nonquiet intervals from a local audio or video file, not speech recognition", {"file": PATH, "seconds": NUMBER, "thresholdDb": NUMBER, "minSilence": NUMBER}, ["file"]),
    "ccer_beat_candidates": schema("Find candidate audio impulses and tentative tempo without promising accurate BPM", {"file": PATH, "seconds": NUMBER, "sensitivity": NUMBER}, ["file"]),
    "ccer_cut_plan": schema("Propose timeline cut times near supplied onsets; never change projects", {"duration": NUMBER, "onsets": {"type": "array", "items": NUMBER}, "targetShot": NUMBER, "minShot": NUMBER, "maxShot": NUMBER, "maxCuts": {"type": "integer"}}, ["duration"]),
    "ccer_caption_timing_hint": schema("Estimate phrase timing from nonquiet audio regions, not word-level forced alignment", {"cues": {"type": "array", "items": {"type": "object"}}, "silenceReport": {"type": "object"}}, ["cues", "silenceReport"]),
}


class Production:
    def __init__(self, upstream, root):
        self.upstream = upstream
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta = self.root / ".ccer"
        self.journal = Journal(self.root)
        self.lock = threading.RLock()

    def path(self, raw, *, must_exist=False):
        return inside(self.root, raw, must_exist=must_exist)

    def _mission(self, kind, data):
        ident = uuid.uuid4().hex
        value = {"id": ident, "kind": kind, "state": "running",
                 "started": time.time(), "data": data}
        atomic_json(self.meta / "missions" / (ident + ".json"), value)
        return value

    def _finish(self, mission, state, **fields):
        mission.update(state=state, ended=time.time(), **fields)
        atomic_json(self.meta / "missions" / (mission["id"] + ".json"), mission)
        self.journal.append("mission." + state, {"id": mission["id"], "kind": mission["kind"]})

    def _read(self, path):
        return structured(self.upstream.tool("timeline_read", {"path": str(path)}))

    def run(self, name, args):
        if name not in TOOLS:
            raise PolicyError("Unknown CCER tool")
        args = args or {}
        if not isinstance(args, dict):
            raise PolicyError("Arguments must be object")
        allowed = set(TOOLS[name]["properties"])
        if any(k not in allowed for k in args):
            raise PolicyError("Unexpected argument for " + name)
        for k in TOOLS[name]["required"]:
            if k not in args:
                raise PolicyError("Missing required argument: " + k)
        with self.lock:
            return self._dispatch(name, args)

    def _dispatch(self, name, a):
        if name == "ccer_silence_map":
            from .rhythm import silence_map
            return silence_map(self.path(a["file"], must_exist=True),
                               seconds=a.get("seconds", 90),
                               threshold_db=a.get("thresholdDb", -38),
                               min_silence=a.get("minSilence", .25))
        if name == "ccer_beat_candidates":
            from .rhythm import beat_candidates
            return beat_candidates(self.path(a["file"], must_exist=True),
                                   seconds=a.get("seconds", 90),
                                   sensitivity=a.get("sensitivity", 1.8))
        if name == "ccer_cut_plan":
            from .rhythm import cut_plan
            return cut_plan(duration=a["duration"], onsets=a.get("onsets"),
                            target_shot=a.get("targetShot", 2),
                            min_shot=a.get("minShot", .5),
                            max_shot=a.get("maxShot", 4),
                            max_cuts=a.get("maxCuts", 150))
        if name == "ccer_caption_timing_hint":
            from .rhythm import subtitle_timing_hint
            return subtitle_timing_hint(a["cues"], a["silenceReport"])
        if name == "ccer_voice_flite":
            from .voice_extensions import synthesize_flite
            return synthesize_flite(a["text"], self.path(a["file"]),
                                    language=a.get("language", "en"),
                                    speaker=a.get("speaker", "kal"))
        if name == "ccer_studio_produce":
            from .studio_pipeline import produce_studio
            return produce_studio(self, a)
        if name == "ccer_directed_render":
            from .director_render import render
            return render(self, a["plan"], a["file"], audio=a.get("audio"),
                          burn_captions=a.get("burnCaptions", True), preset=a.get("preset", "veryfast"))
        if name == "ccer_creative_plan":
            from .creative import plan
            return plan(a["brief"])
        if name == "ccer_storyboard":
            from .creative import storyboard
            return storyboard(a["plan"])
        if name == "ccer_plan_save":
            from .creative import save
            return save(self.root, a["file"], json.dumps(a["plan"], indent=2, ensure_ascii=False) + "\n")
        if name == "ccer_subtitles_write":
            from .creative import save, to_srt
            return save(self.root, a["file"], to_srt(a["cues"]))
        if name == "ccer_tts_status":
            from .audio_studio import engines
            from .voice_extensions import flite_available
            return {**engines(), "ffmpeg-flite": flite_available()}
        if name == "ccer_voice_synthesize":
            from .audio_studio import voice
            return voice(a["text"], self.path(a["file"]), language=a.get("language", "fr"),
                         rate=a.get("rate", 150), engine=a.get("engine", "auto"))
        if name == "ccer_audio_mix":
            from .audio_studio import mix
            return mix(self.path(a["voice"], must_exist=True),
                       self.path(a["music"], must_exist=True) if a.get("music") else None,
                       self.path(a["file"]), music_gain=a.get("musicGain", 0.18),
                       target_lufs=a.get("targetLufs", -16.0))
        if name == "ccer_shot_inspect":
            from .shot_intelligence import inspect_shots
            return inspect_shots([str(self.path(p, must_exist=True)) for p in a["files"]])
        if name == "ccer_scene_detect":
            from .shot_intelligence import scene_cuts
            return scene_cuts(self.path(a["file"], must_exist=True),
                              a.get("threshold", 0.32), a.get("seconds", 120))
        if name == "ccer_contact_sheet":
            from .shot_intelligence import contact_sheet
            return contact_sheet(self.path(a["file"], must_exist=True), self.path(a["output"]),
                                 interval=a.get("interval", 2))
        if name == "ccer_caption_validate":
            from .quality import captions_check
            return captions_check(a["cues"])
        if name == "ccer_visual_scan":
            from .quality import visual_scan
            return visual_scan(self.path(a["file"], must_exist=True), a.get("seconds", 60))
        if name == "ccer_delivery_transcode":
            from .quality import transcode
            source = self.path(a["file"], must_exist=True)
            dest = self.path(a["output"])
            mission = self._mission("delivery", {"source": str(source), "profile": a["profile"]})
            try:
                result = transcode(source, dest, a["profile"])
                self._finish(mission, "completed", output=str(dest))
                return {**result, "missionId": mission["id"]}
            except BaseException as error:
                self._finish(mission, "unknown", errorType=type(error).__name__)
                raise
        if name == "ccer_produce":
            from .recipes import produce
            return produce(self, a)
        if name == "ccer_preflight":
            return {
                "root": str(self.root), "rootWritable": os.access(self.root, os.W_OK),
                "concat": structured(self.upstream.tool("concat_version")),
                "ffmpeg": bool(shutil.which("ffmpeg")),
                "ffprobe": bool(shutil.which("ffprobe")),
                "diskFreeBytes": shutil.disk_usage(self.root).free,
                "audit": self.journal.verify(),
            }
        if name == "ccer_project_inspect":
            path = self.path(a["path"], must_exist=True)
            return structured(self.upstream.tool("project_get", {"path": str(path)}))
        if name == "ccer_checkpoint_create":
            path = self.path(a["path"], must_exist=True)
            if not (path / "concat.json").is_file():
                raise PolicyError("Not a saved Concat project directory")
            self.upstream.tool("project_save", {"path": str(path)})
            ident = uuid.uuid4().hex
            target = self.meta / "checkpoints" / ident / "project"
            target.parent.mkdir(parents=True, exist_ok=False)
            try:
                self._copy_project(path, target)
                checksum = hashlib.sha256((target / "concat.json").read_bytes()).hexdigest()
                record = {"id": ident, "project": str(path),
                          "created": time.time(), "sha256": checksum}
                atomic_json(target.parent / "metadata.json", record)
            except BaseException:
                shutil.rmtree(target.parent, ignore_errors=True)
                raise
            self.journal.append("checkpoint.created", {"id": ident, "project": str(path)})
            return record
        if name == "ccer_checkpoint_restore":
            confirm(a["confirm"])
            ident = a["checkpointId"]
            if not isinstance(ident, str) or not ident.isalnum() or len(ident) != 32:
                raise PolicyError("Invalid checkpoint ID")
            location = self.meta / "checkpoints" / ident
            record = json.loads((location / "metadata.json").read_text(encoding="utf-8"))
            destination = self.path(record["project"])
            if (destination / "concat.lock").exists():
                raise PolicyError("Project lock exists; close all Concat sessions first")
            saved = location / "project"
            if hashlib.sha256((saved / "concat.json").read_bytes()).hexdigest() != record["sha256"]:
                raise PolicyError("Checkpoint integrity mismatch")
            stage = destination.with_name(destination.name + ".ccer-restore-" + ident[:8])
            if stage.exists():
                raise PolicyError("Restore staging path already exists")
            self._copy_project(saved, stage)
            backup = self.meta / "restore-backups" / (ident + "-" + uuid.uuid4().hex[:6])
            backup.parent.mkdir(parents=True, exist_ok=True)
            moved = False
            try:
                if destination.exists():
                    destination.rename(backup)
                    moved = True
                stage.rename(destination)
            except BaseException:
                if moved and not destination.exists():
                    backup.rename(destination)
                if stage.exists():
                    shutil.rmtree(stage)
                raise
            self.journal.append("checkpoint.restored",
                                {"id": ident, "project": str(destination), "backup": str(backup) if moved else None})
            return {"restored": str(destination), "backup": str(backup) if moved else None}
        if name == "ccer_timeline_validate":
            timeline = self._read(self.path(a["path"], must_exist=True)).get("timeline", {})
            clips = timeline.get("clips", [])
            threshold = max(0.0, float(a.get("gapThresholdSeconds", 0.15)))
            issues, by_track = [], {}
            for clip in clips:
                start, duration = float(clip.get("start", 0)), float(clip.get("duration", 0))
                ident = clip.get("id")
                if start < 0 or duration <= 0:
                    issues.append({"kind": "invalid_clip", "id": ident})
                track = str(clip.get("trackId", clip.get("track", "unknown")))
                by_track.setdefault(track, []).append((start, start + duration, ident))
            for track, positions in by_track.items():
                positions.sort()
                for prev, cur in zip(positions, positions[1:]):
                    diff = cur[0] - prev[1]
                    if diff < -0.0001:
                        issues.append({"kind": "overlap", "track": track, "clips": [prev[2], cur[2]], "seconds": -diff})
                    elif diff > threshold:
                        issues.append({"kind": "gap", "track": track, "seconds": diff, "after": prev[2]})
            return {"valid": not any(i["kind"] in ("invalid_clip", "overlap") for i in issues),
                    "clipCount": len(clips), "issues": issues}
        if name == "ccer_batch_edit":
            path = self.path(a["path"], must_exist=True)
            commands = a["commands"]
            if not isinstance(commands, list) or not 1 <= len(commands) <= 200:
                raise PolicyError("commands must contain 1..200 operations")
            for cmd in commands:
                if not isinstance(cmd, dict) or "op" not in cmd:
                    raise PolicyError("Each command must specify op")
            mission = self._mission("batch_edit", {"project": str(path), "count": len(commands)})
            before = self._read(path)
            try:
                response = structured(self.upstream.tool("edit_apply",
                    {"path": str(path), "command": {"op": "batch", "commands": commands}}, timeout=120))
                after = self._read(path)
                old_n = len(before.get("timeline", {}).get("clips", []))
                new_n = len(after.get("timeline", {}).get("clips", []))
                delta = new_n - old_n
                verified = a.get("expectedClipDelta") is None or delta == a["expectedClipDelta"]
                if a.get("save", False) and verified:
                    self.upstream.tool("project_save", {"path": str(path)})
                self._finish(mission, "completed" if verified else "attention",
                    verification={"expectedDelta": a.get("expectedClipDelta"), "actualDelta": delta})
                return {"missionId": mission["id"], "verified": verified,
                        "clipDelta": delta, "saved": bool(a.get("save", False) and verified),
                        "editingResult": response}
            except BaseException as error:
                self._finish(mission, "unknown", reason=type(error).__name__)
                raise
        if name == "ccer_asset_analyze":
            return media_probe(self.path(a["file"], must_exist=True))
        if name == "ccer_audio_validate":
            return audio_analyze(self.path(a["file"], must_exist=True), a.get("seconds", 40))
        if name == "ccer_export_verify":
            report = media_probe(self.path(a["file"], must_exist=True))
            video = next((s for s in report["streams"] if s.get("codec_type") == "video"), {})
            errors = []
            for key in ("width", "height"):
                if key in a and video.get(key) != a[key]:
                    errors.append(f"{key} expected {a[key]}, got {video.get(key)}")
            try:
                duration = float(report["format"]["duration"])
            except (TypeError, ValueError):
                duration = None
                errors.append("Duration unavailable")
            if duration is not None:
                if duration < float(a.get("minDuration", 0)):
                    errors.append("Video shorter than expected")
                if duration > float(a.get("maxDuration", float("inf"))):
                    errors.append("Video longer than expected")
            result = {"passed": not errors, "errors": errors, "probe": report}
            self.journal.append("export.verified", {"file": str(report["file"]), "passed": result["passed"]})
            return result
        if name in ("ccer_mission_status", "ccer_mission_recover"):
            ident = a["missionId"]
            if not isinstance(ident, str) or len(ident) != 32 or not ident.isalnum():
                raise PolicyError("Invalid mission ID")
            file = self.meta / "missions" / (ident + ".json")
            value = json.loads(file.read_text(encoding="utf-8"))
            if name == "ccer_mission_recover":
                value["recovery"] = ("Inspect the Concat timeline and audit manually. "
                    "Do not automatically replay edits with unknown commit outcome.")
            return value
        if name == "ccer_audit_report":
            return self.journal.verify()
        raise PolicyError("Unknown tool")

    @staticmethod
    def _copy_project(src, dest):
        for path in src.rglob("*"):
            if path.is_symlink():
                raise PolicyError("Symlink in project snapshot refused")
        shutil.copytree(src, dest, symlinks=False,
                        ignore=shutil.ignore_patterns("concat.lock", ".ccer"))
