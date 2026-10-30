"""Audit saved Concat title captions relative to approved source video.

Read-only; a Concat title alone never proves Whisper provenance or accuracy.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from .controls import PolicyError, inside, media_probe
from .quality import captions_check


def _seconds(value, name, allow_zero=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise PolicyError(f"{name} must be finite")
    if not (0 <= value <= 86400) or (value == 0 and not allow_zero):
        raise PolicyError(f"{name} out of bounds")
    return float(value)


def inspect(project_root, project_file, media_root):
    raw = Path(project_file)
    if raw.is_symlink():
        raise PolicyError("Project file symlink denied")
    path = inside(project_root, raw, must_exist=True)
    if path.name != "concat.json" or path.stat().st_size > 4_000_000:
        raise PolicyError("Expected bounded Concat project JSON")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise PolicyError("Unreadable Concat project") from exc
    if not isinstance(data, dict):
        raise PolicyError("Invalid project object")
    all_timelines = data.get("timelines")
    if not isinstance(all_timelines, list) or len(all_timelines) > 100:
        raise PolicyError("Invalid timeline list")
    matches = [t for t in all_timelines if isinstance(t, dict)
               and t.get("id") == data.get("activeTimelineId")]
    if len(matches) != 1 or not isinstance(matches[0].get("clips"), list):
        raise PolicyError("Active timeline not unique")
    clips = matches[0]["clips"]
    if len(clips) > 5000:
        raise PolicyError("Too many clips")
    media = data.get("media")
    if not isinstance(media, list):
        raise PolicyError("Invalid media catalogue")
    by_id = {m.get("id"): m for m in media if isinstance(m, dict) and m.get("id")}
    cached, videos, cues = {}, [], []
    for clip in clips:
        if not isinstance(clip, dict):
            raise PolicyError("Invalid clip entry")
        kind = clip.get("kind")
        if kind not in ("video", "text"):
            continue
        start = _seconds(clip.get("start"), "start", allow_zero=True)
        duration = _seconds(clip.get("duration"), "duration")
        if start + duration > 86400:
            raise PolicyError("Clip exceeds timeline limit")
        if kind == "text":
            meta = clip.get("text")
            words = meta.get("content") if isinstance(meta, dict) else None
            if not isinstance(words, str) or not 0 < len(words.strip()) <= 800:
                raise PolicyError("Invalid Concat title content")
            cues.append({"start": start, "duration": duration, "text": words.strip()})
            continue
        m = by_id.get(clip.get("mediaId"))
        if not m or not isinstance(m.get("path"), str):
            raise PolicyError("Video source missing from catalogue")
        source = inside(media_root, m["path"], must_exist=True)
        if source not in cached:
            cached[source] = media_probe(source)
        probe = cached[source]
        if not any(s.get("codec_type") == "video" for s in probe["streams"]):
            raise PolicyError("Media has no video stream")
        try:
            real_duration = float(probe["format"]["duration"])
        except (ValueError, TypeError, KeyError) as exc:
            raise PolicyError("Media duration unavailable") from exc
        source_start = _seconds(clip.get("sourceStart", 0), "source start", allow_zero=True)
        speed = _seconds(clip.get("speed", 1), "speed")
        if (not math.isfinite(real_duration) or
                source_start + duration * speed > real_duration + .06):
            raise PolicyError("Clip exceeds physical media duration")
        videos.append({"start": start, "end": start + duration,
                       "hasAudio": any(s.get("codec_type") == "audio"
                                       for s in probe["streams"])})
    if not videos or len(cues) > 2000:
        raise PolicyError("Video or caption count invalid")
    qa = captions_check(cues)
    issues = list(qa["issues"])
    for idx, cue in enumerate(cues):
        end = cue["start"] + cue["duration"]
        if not any(v["start"] <= cue["start"] + .001 and
                   end <= v["end"] + .001 for v in videos):
            issues.append({"level": "error", "cue": idx, "issue": "outside_video"})
    return {
        "project": data.get("name", path.parent.name),
        "activeTimelineId": data["activeTimelineId"],
        "videoCount": len(videos), "titleCount": len(cues),
        "titles": [{"startSeconds": round(c["start"], 3),
                    "endSeconds": round(c["start"] + c["duration"], 3),
                    "text": c["text"]} for c in cues],
        "captionQA": {"passed": not any(i["level"] == "error" for i in issues),
                      "count": len(cues), "issues": issues},
        "audioInSourceVideos": any(v["hasAudio"] for v in videos),
        "provenance": "concat_saved_project_title_only",
        "whisperOriginVerified": False, "speechAccuracyVerified": False,
        "transcriptionPerformed": False, "nativeSrtExportPerformed": False,
        "readOnly": True, "mediaArtifactsCreated": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Read-only Concat subtitle QA")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument("--media-root", required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.project_root, args.file, args.media_root),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
