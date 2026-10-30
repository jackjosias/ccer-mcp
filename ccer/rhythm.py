"""Bounded, reviewable FFmpeg rhythm analysis and subtitle timing hints.

This module deliberately does NOT claim musical source separation, verified BPM,
speech recognition or word-level forced alignment. It provides editorial candidates
to verify before applying an edit.
"""
from __future__ import annotations

import math
import re
import shutil
import statistics
import subprocess
import sys
from array import array
from pathlib import Path

from .controls import PolicyError, media_probe
from .quality import captions_check
from .temporal_seek import start_args, absolute


def _duration(report):
    try:
        duration = float(report["format"]["duration"])
    except (TypeError, ValueError, KeyError) as exc:
        raise PolicyError("Media duration unavailable") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise PolicyError("Media duration must be positive and finite")
    return duration


def _audio(path, requested_seconds):
    if not shutil.which("ffmpeg"):
        raise PolicyError("FFmpeg unavailable")
    if isinstance(requested_seconds, bool) or not isinstance(requested_seconds, (int, float)):
        raise PolicyError("seconds must be numeric")
    if not math.isfinite(requested_seconds) or not 1 <= requested_seconds <= 300:
        raise PolicyError("seconds must be between 1 and 300")
    source = Path(path)
    meta = media_probe(source)
    if not any(s.get("codec_type") == "audio" for s in meta["streams"]):
        raise PolicyError("Media has no audio stream")
    length = min(float(requested_seconds), _duration(meta))
    return source, length


def silence_map(path, *, seconds=90, threshold_db=-38.0, min_silence=0.25, start_seconds=0):
    """Detect silent intervals and complement speaking/music-active intervals."""
    source, length = _audio(path, seconds)
    seek, offset = start_args(start_seconds)
    length = min(length, _duration(media_probe(source)) - offset)
    if length <= 0:
        raise PolicyError("Requested audio window starts beyond media duration")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
           for v in (threshold_db, min_silence)):
        raise PolicyError("Silence thresholds must be finite numbers")
    if not -90 <= threshold_db <= -15 or not 0.05 <= min_silence <= 3:
        raise PolicyError("Invalid silence detection threshold/duration")
    p = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", *seek, "-i", str(source),
         "-t", f"{length:.6f}", "-af",
         f"asetpts=PTS-STARTPTS,silencedetect=noise={threshold_db:.2f}dB:d={min_silence:.3f}",
         "-vn", "-f", "null", "-"],
        capture_output=True, text=True, timeout=min(930, max(35, int(length * 4))))
    if p.returncode:
        raise PolicyError("FFmpeg silencedetect failed: " + p.stderr[-400:])
    starts = [float(t) for t in re.findall(r"silence_start:\s*(-?[0-9.]+)", p.stderr)]
    ends = [float(t) for t in re.findall(r"silence_end:\s*(-?[0-9.]+)", p.stderr)]
    # FFmpeg reports end for complete intervals and may leave a trailing open one.
    silent = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else length
        start = min(length, max(0., start))
        end = min(length, max(0., end))
        if end > start:
            silent.append([round(start, 3), round(end, 3)])
    silent.sort()
    merged = []
    for start, end in silent:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    active, cursor = [], 0.
    for start, end in merged:
        if start > cursor + 0.001:
            active.append([round(cursor, 3), round(start, 3)])
        cursor = max(cursor, end)
    if length > cursor + 0.001:
        active.append([round(cursor, 3), round(length, 3)])
    return {"file": str(source), "analyzedSeconds": round(length, 3), "startSeconds": offset,
            "thresholdDb": threshold_db, "minimumSilenceSeconds": min_silence,
            "silences": [{"start": absolute(a, offset), "end": absolute(b, offset), "duration": round(b-a, 3)} for a, b in merged],
            "activeRegions": [{"start": absolute(a, offset), "end": absolute(b, offset), "duration": round(b-a, 3)} for a, b in active],
            "method": "FFmpeg silencedetect, not speech recognition"}


def beat_candidates(path, *, seconds=90, sensitivity=1.8):
    """Find strong audio transients using mono PCM energy novelty.

    The estimated tempo assumes reasonably periodic onsets. For speech or
    non-percussive music, return candidates but do not imply a reliable beat.
    """
    source, length = _audio(path, seconds)
    if isinstance(sensitivity, bool) or not isinstance(sensitivity, (int, float)) or not math.isfinite(sensitivity):
        raise PolicyError("sensitivity must be finite")
    if not 1.2 <= sensitivity <= 4:
        raise PolicyError("sensitivity must be in [1.2, 4]")
    sample_rate, hop = 8000, 160
    p = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-i", str(source), "-map", "0:a:0", "-t", f"{length:.6f}",
         "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"],
        capture_output=True, timeout=min(930, max(35, int(length * 4))))
    if p.returncode:
        raise PolicyError("FFmpeg PCM decode failed: " + p.stderr[-400:].decode(errors="replace"))
    if len(p.stdout) > 300 * sample_rate * 2 + 1000:
        raise PolicyError("Decoded PCM unexpectedly large")
    values = array("h")
    values.frombytes(p.stdout[:len(p.stdout) // 2 * 2])
    if sys.byteorder != "little":
        values.byteswap()
    energies = []
    for pos in range(0, len(values) - hop + 1, hop):
        block = values[pos:pos + hop]
        energies.append(sum(abs(value) for value in block) / (hop * 32768.))
    peak = max(energies, default=0.)
    if peak < 0.0005:
        return {"file": str(source), "analyzedSeconds": round(length, 3),
                "onsetsSeconds": [], "estimatedBpm": None, "tempoConfidence": 0.,
                "method": "PCM 20ms amplitude novelty; silence or weak signal"}
    raw = []
    for index in range(4, len(energies)):
        before = energies[max(0, index-12):index]
        baseline = sum(before) / len(before)
        if energies[index] < max(peak * 0.11, 0.004):
            continue
        if energies[index] < baseline * sensitivity:
            continue
        if energies[index] - energies[index-1] < peak * 0.06:
            continue
        timecode = index * hop / sample_rate
        if not raw or timecode - raw[-1] >= .18:
            raw.append(timecode)
    intervals = [y-x for x, y in zip(raw, raw[1:]) if .28 <= y-x <= 1.5]
    bpm = None
    confidence = 0.
    if len(intervals) >= 2:
        median_gap = statistics.median(intervals)
        stable = [d for d in intervals if abs(d-median_gap) <= max(.06, median_gap*.12)]
        confidence = round(len(stable) / len(intervals), 3)
        if len(stable) >= 2 and confidence >= .55:
            bpm = round(60 / statistics.median(stable), 1)
    return {"file": str(source), "analyzedSeconds": round(length, 3),
            "onsetsSeconds": [round(t, 3) for t in raw[:1000]],
            "estimatedBpm": bpm, "tempoConfidence": confidence,
            "method": "energy-onset heuristic (not verified beat tracking)",
            "requiresListeningReview": True}


def cut_plan(*, duration, onsets=None, target_shot=2.0, min_shot=.5, max_shot=4., max_cuts=150):
    """Propose frame-independent cuts near strong onsets; never mutates a timeline."""
    fields = (duration, target_shot, min_shot, max_shot)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in fields):
        raise PolicyError("Timing values must be finite numbers")
    if not .5 <= duration <= 1800 or not .2 <= min_shot <= target_shot <= max_shot <= 30:
        raise PolicyError("Invalid duration / shot constraints")
    if isinstance(max_cuts, bool) or not isinstance(max_cuts, int) or not 1 <= max_cuts <= 150:
        raise PolicyError("maxCuts must be 1..150")
    if onsets is None:
        onsets = []
    if not isinstance(onsets, list) or len(onsets) > 1500:
        raise PolicyError("onsets must be a list <= 1500")
    if any(isinstance(t, bool) or not isinstance(t, (int,float)) or not math.isfinite(t) for t in onsets):
        raise PolicyError("Onset positions must be finite numeric seconds")
    valid = sorted(set(float(t) for t in onsets if 0 < t < duration))
    points = [0.]
    while (duration - points[-1] > max_shot + 0.00001 or
           duration - points[-1] > target_shot + min_shot + 0.00001):
        left = points[-1]
        desired = left + target_shot
        choices = [t for t in valid if left+min_shot <= t <= left+max_shot
                   and duration-t >= min_shot]
        candidate = min(choices, key=lambda t: abs(t-desired)) if choices else min(duration-min_shot, desired)
        if candidate <= left+0.0001:
            raise PolicyError("Unable to generate valid cut positions")
        points.append(round(candidate, 3))
        if len(points) - 1 >= max_cuts:
            raise PolicyError("Cut limit reached; increase average shot duration")
    if duration-points[-1] < min_shot and len(points)>1:
        points.pop()
    points.append(round(duration, 3))
    shots = [{"start": points[i], "end": points[i+1],
              "duration": round(points[i+1]-points[i], 3),
              "onBeat": any(abs(points[i]-t) <= .03 for t in valid) if i else False}
             for i in range(len(points)-1)]
    return {"duration": float(duration), "cutPointsSeconds": points[1:-1],
            "shots": shots, "mutated": False, "requiresEditorialApproval": True}


def subtitle_timing_hint(cues, silent_report):
    """Distribute supplied text over detected non-silent intervals.

    This is an estimate NOT phoneme/word forced alignment or transcription.
    """
    if not isinstance(cues, list) or not 1 <= len(cues) <= 200:
        raise PolicyError("Supply 1..200 cue objects")
    if any(not isinstance(c, dict) or not isinstance(c.get("text"), str) or not c["text"].strip()
           for c in cues):
        raise PolicyError("Every cue must contain text")
    active = silent_report.get("activeRegions")
    if not isinstance(active, list) or not active:
        raise PolicyError("No detected active audio regions")
    regions = []
    for r in active:
        if not isinstance(r, dict):
            raise PolicyError("Invalid audio region")
        a, b = r.get("start"), r.get("end")
        if any(not isinstance(v, (float,int)) or not math.isfinite(v) for v in (a,b)):
            raise PolicyError("Audio region times must be finite")
        if a < 0 or b <= a or (regions and a < regions[-1][1]):
            raise PolicyError("Audio regions must be sorted, non-overlapping")
        regions.append((float(a),float(b)))
    weights = [max(1,len(c["text"].split())) for c in cues]
    total_weight = sum(weights)
    total_speech = sum(b-a for a,b in regions)
    if total_speech < .2*len(cues):
        raise PolicyError("Not enough detected active audio for the captions")
    def locate(active_seconds):
        left = max(0., active_seconds)
        for index, (a,b) in enumerate(regions):
            interval = b-a
            if left <= interval or index == len(regions)-1:
                return min(b,a+left)
            left -= interval
        return regions[-1][1]
    result = []
    used = 0
    for cue, weight in zip(cues, weights):
        start = locate(total_speech*used/total_weight)
        used += weight
        end = locate(total_speech*used/total_weight)
        result.append({"start": round(start, 3),
                       "duration": round(max(0.,end-start), 3),
                       "text": cue["text"]})
    qa = captions_check(result)
    return {"cues": result, "captionQA": qa,
            "method": "proportional word-count allocation over nonsilent regions",
            "forcedAligned": False, "transcribed": False,
            "requiresListeningReview": True}
