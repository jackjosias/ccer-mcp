"""Frame-accurate editorial scene compositor built on FFmpeg.

Concat remains the editable native editor. This complementary renderer makes the
approved storyboard executable with exact per-scene timing, optional embedded SRT,
and narration/music stems. Never overwrites original media or existing output.
"""
from __future__ import annotations
import math
import os
import shutil
from .temp_lifecycle import managed_scratch, run_bounded_encoder

from .controls import PolicyError, media_probe
from .creative import to_srt
from .quality import captions_check


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def render(engine, plan: dict, output: str, *, audio: str | None = None,
           burn_captions: bool = True, preset: str = "veryfast") -> dict:
    if not isinstance(plan, dict):
        raise PolicyError("Creative plan required")
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 50:
        raise PolicyError("Storyboard must contain 1..50 scenes")
    video = plan.get("video")
    if not isinstance(video, dict):
        raise PolicyError("Storyboard missing video settings")
    try:
        width, height = int(video["width"]), int(video["height"])
        fps = float(video["rateNum"]) / float(video["rateDen"])
    except (KeyError, ValueError, TypeError, ZeroDivisionError) as err:
        raise PolicyError("Invalid video settings") from err
    if not (64 <= width <= 4096 and 64 <= height <= 4096 and
            math.isfinite(fps) and 1 <= fps <= 60):
        raise PolicyError("Unsupported output resolution or frame rate")
    target = engine.path(output)
    if target.suffix.lower() != ".mp4" or target.exists() or target.is_symlink():
        raise PolicyError("Output must be a new MP4 file")
    if not target.parent.is_dir():
        raise PolicyError("Output parent directory must exist")
    if preset not in ("ultrafast", "superfast", "veryfast", "fast", "medium", "slow"):
        raise PolicyError("Unsupported H.264 preset")
    if not shutil.which("ffmpeg"):
        raise PolicyError("FFmpeg unavailable")
    if shutil.disk_usage(engine.root).free < 1024 * 1024 * 1024:
        raise PolicyError("Insufficient space: require at least 1 GiB")
    sources = []
    total = 0.0
    for index, item in enumerate(scenes):
        if not isinstance(item, dict):
            raise PolicyError("Scene entries must be objects")
        duration = item.get("duration")
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or not 0.2 <= duration <= 600:
            raise PolicyError(f"Invalid scene duration at {index}")
        if not isinstance(item.get("source"), str):
            raise PolicyError(f"Missing approved media source for scene {index}")
        source = engine.path(item["source"], must_exist=True)
        if not source.is_file():
            raise PolicyError("Scene source is not a file")
        metadata = media_probe(source)
        if not any(s.get("codec_type") == "video" for s in metadata["streams"]):
            raise PolicyError("Scene source has no video stream")
        offset = item.get("mediaStart", 0)
        if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset) or offset < 0:
            raise PolicyError(f"Invalid mediaStart at scene {index}")
        if source.suffix.lower() in IMAGE_EXT:
            if offset != 0:
                raise PolicyError("Still images have no timecode seek")
        elif offset > 0:
            try:
                source_duration = float(metadata["format"]["duration"])
            except (ValueError, TypeError) as exc:
                raise PolicyError("Media duration unavailable for timecoded scene") from exc
            if not math.isfinite(source_duration) or offset + float(duration) > source_duration + .025:
                raise PolicyError(f"Scene {index} extends beyond source media")
        # A zero-offset video keeps the legacy loop behavior for short sources.
        sources.append(source)
        total += float(duration)
    if total > 1800:
        raise PolicyError("Maximum duration is 30 minutes per directed render")
    narration = engine.path(audio, must_exist=True) if audio else None
    if narration:
        m = media_probe(narration)
        if not any(s.get("codec_type") == "audio" for s in m["streams"]):
            raise PolicyError("Narration audio contains no audio stream")
    cues = plan.get("captions", [])
    if not isinstance(cues, list):
        raise PolicyError("Invalid captions")
    if cues and not captions_check(cues)["passed"]:
        raise PolicyError("Invalid subtitle timecodes")
    sidecar = target.with_suffix(".srt")
    if sidecar.exists() or sidecar.is_symlink():
        raise PolicyError("Subtitle sidecar already exists")
    mission = engine._mission("directed_render", {"output": str(target), "scenes": len(scenes)})
    try:
        with managed_scratch(engine.root, project=target.parent.name,
                             purpose="directed_render") as scratch:
            commands = []
            segments = []
            for i, (source, item) in enumerate(zip(sources, scenes)):
                if source.suffix.lower() in IMAGE_EXT:
                    commands.extend(["-loop", "1", "-i", str(source)])
                else:
                    offset = float(item.get("mediaStart", 0))
                    if offset > 0:
                        commands.extend(["-ss", f"{offset:.5f}", "-i", str(source)])
                    else:
                        commands.extend(["-stream_loop", "-1", "-i", str(source)])
                duration = float(item["duration"])
                # Output is constant-frame-rate. Videos shorter than a panel loop.
                segments.append(
                    f"[{i}:v]fps={fps:.6f},"
                    f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                    f"trim=duration={duration:.6f},setpts=PTS-STARTPTS[v{i}]")
            video_concat = "".join(f"[v{i}]" for i in range(len(scenes)))
            segments.append(f"{video_concat}concat=n={len(scenes)}:v=1:a=0[assembled]")
            if cues and burn_captions:
                (scratch / "captions.srt").write_text(to_srt(cues), encoding="utf-8")
                segments.append("[assembled]subtitles=filename=captions.srt,format=yuv420p[render]")
            else:
                segments.append("[assembled]format=yuv420p[render]")
            if narration:
                commands.extend(["-i", str(narration)])
            temp_mp4 = scratch / "output.mp4"
            command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                       "-y", *commands, "-filter_complex", ";".join(segments),
                       "-map", "[render]"]
            if narration:
                command.extend(["-map", f"{len(sources)}:a:0", "-c:a", "aac", "-b:a", "160k"])
            else:
                command.append("-an")
            command.extend(["-t", str(round(total, 3)), "-r", str(round(fps, 6)),
                            "-c:v", "libx264", "-preset", preset, "-crf", "22",
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                            str(temp_mp4)])
            run_bounded_encoder(command, scratch=scratch,
                                timeout=min(3600, max(120, int(total * 12))))
            metadata = media_probe(temp_mp4)
            image = next((s for s in metadata["streams"] if s.get("codec_type") == "video"), {})
            duration = float(metadata["format"]["duration"] or 0)
            if image.get("width") != width or image.get("height") != height:
                raise PolicyError("Rendered video dimensions mismatch")
            if not max(0.0, total - 0.5) <= duration <= total + 0.5:
                raise PolicyError(f"Rendered duration mismatch: {duration} != {total}")
            # Produce the optional editable sidecar without replacing an existing one.
            if cues:
                srt = to_srt(cues)
                (scratch / "delivery.srt").write_text(srt, encoding="utf-8")
                if sidecar.exists():
                    raise PolicyError("Subtitle output appeared during render")
                os.link(scratch / "delivery.srt", sidecar)
            if target.exists():
                if cues:
                    sidecar.unlink(missing_ok=True)
                raise PolicyError("Output appeared during render")
            try:
                os.link(temp_mp4, target)
            except BaseException:
                if cues:
                    sidecar.unlink(missing_ok=True)
                raise
            result = {"file": str(target), "subtitles": str(sidecar) if cues else None,
                      "width": width, "height": height, "fps": fps,
                      "duration": duration, "bytes": target.stat().st_size,
                      "narration": bool(narration), "captionsBurned": bool(cues and burn_captions),
                      "sceneCount": len(scenes), "verified": True, "missionId": mission["id"]}
        engine._finish(mission, "completed", output=str(target), bytes=result["bytes"])
        return result
    except BaseException as error:
        engine._finish(mission, "unknown", errorType=type(error).__name__)
        raise
