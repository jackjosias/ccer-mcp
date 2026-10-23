"""Immutable, provenance-aware footage catalog and annotated storyboard matching.

No inferred object recognition: semantic terms come from user-provided
descriptions/tags. Timing and encoding come from FFprobe and optional FFmpeg cuts.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
import unicodedata
import uuid

from .controls import PolicyError, inside, media_probe
from .shot_intelligence import scene_cuts

_WORDS = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a au aux de des du dans et en est la le les l un une sur pour par qui que qu ce ces son sa se ses nos notre votre vos our the and with from this that is are an of to in".split())


def _words(value):
    if not isinstance(value, str):
        raise PolicyError("Search text must be a string")
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return [token for token in _WORDS.findall(normalized) if len(token) > 1 and token not in _STOP]


def _number(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PolicyError(f"{label} must be a finite number")
    if not low <= value <= high:
        raise PolicyError(f"{label} out of supported range")
    return float(value)


def _source(root, raw):
    if not isinstance(raw, str) or not raw:
        raise PolicyError('Media source path must be a nonempty string')
    p = inside(root, raw, must_exist=True)
    if not p.is_file():
        raise PolicyError("Catalog source must be a real file")
    return p


def build(root, items, output, *, detect_scenes=False, threshold=.32, analyze_seconds=120):
    """Write a new immutable indexed catalog from explicit, annotated media files."""
    if not isinstance(items, list) or not 1 <= len(items) <= 40:
        raise PolicyError("Provide 1..40 media objects")
    if type(detect_scenes) is not bool:
        raise PolicyError("detectScenes must be boolean")
    _number(threshold, "threshold", .05, .95)
    limit = int(_number(analyze_seconds, "analyzeSeconds", 1, 120))
    destination = inside(root, output)
    if destination.suffix.lower() != ".json" or not destination.parent.is_dir():
        raise PolicyError("Catalog destination must be JSON in existing directory")
    if destination.exists() or destination.is_symlink():
        raise PolicyError("Catalog already exists; use a unique name")
    records, seen = [], set()
    for i, item in enumerate(items):
        if not isinstance(item, dict) or set(item).difference({"file", "description", "tags", "licenseNote"}):
            raise PolicyError("Asset must provide file, optional description, tags, licenseNote")
        source = _source(root, item.get("file"))
        if str(source) in seen:
            raise PolicyError("Duplicate media path in catalog")
        seen.add(str(source))
        description = item.get("description", "")
        tags = item.get("tags", [])
        license_note = item.get("licenseNote", "")
        if not isinstance(description, str) or len(description) > 1500:
            raise PolicyError("Description too long or not string")
        if not isinstance(tags, list) or len(tags) > 40 or any(not isinstance(t, str) or len(t) > 70 for t in tags):
            raise PolicyError("Invalid tags")
        if not isinstance(license_note, str) or len(license_note) > 300:
            raise PolicyError("Invalid licenseNote")
        info = media_probe(source)
        stream = next((s for s in info["streams"] if s.get("codec_type") == "video"), None)
        if stream is None:
            raise PolicyError(f"Media {source} does not contain video")
        seconds = _number(float(info["format"]["duration"]), "media duration", .2, 14400)
        boundaries = []
        if detect_scenes:
            # Existing scene_cuts uses FFmpeg; do not add a duplicate detector.
            detected = scene_cuts(str(source), threshold=threshold, seconds=min(limit, max(1, math.ceil(seconds))))
            boundaries = sorted(set(float(t) for t in detected["cutsSeconds"] if .2 <= t <= seconds-.2))
        end = min(float(limit), seconds) if detect_scenes else seconds
        starts = [0.] + [t for t in boundaries if t < end]
        ends = starts[1:] + [end]
        for start, stop in zip(starts, ends):
            length = round(stop-start, 3)
            if length < .2:
                continue
            records.append({
                "id": f"media-{i+1:03}-shot-{len(records)+1:04}",
                "file": str(source),
                "mediaStart": round(start, 3),
                "duration": length,
                "description": description,
                "tags": tags,
                "licenseNote": license_note,
                "provenance": {"semantics": "user_annotation", "cuts": "ffmpeg_scene_metric" if detect_scenes else "whole_asset"},
                "technical": {"width": stream.get("width"), "height": stream.get("height"),
                              "codec": stream.get("codec_name")},
                "sourceVersion": {"size": source.stat().st_size,
                                  "mtimeNs": source.stat().st_mtime_ns},
            })
    if not records:
        raise PolicyError("No usable video segments")
    data = {"schemaVersion": 1, "createdAt": time.time(), "catalogId": uuid.uuid4().hex,
            "items": records, "indexedCount": len(records), "sourceCount": len(seen),
            "semanticModel": None, "annotationsVerified": False,
            "note": "Only user-supplied tags/descriptions, no visual semantic inference"}
    # Exclusive creation ensures no concurrent run overwrites another catalog.
    with destination.open("x", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    return {"catalog": str(destination), "sourceCount": len(seen),
            "indexedCount": len(records), "semanticModel": None,
            "annotationsVerified": False}


def load(root, catalog):
    path = inside(root, catalog, must_exist=True)
    if path.suffix.lower() != ".json" or path.stat().st_size > 3_000_000:
        raise PolicyError("Invalid or oversized catalog")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schemaVersion") != 1 or not isinstance(value.get("items"), list):
        raise PolicyError("Unsupported catalog schema")
    if len(value["items"]) > 3000:
        raise PolicyError("Catalog too large")
    for item in value["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("file"), str):
            raise PolicyError("Invalid indexed media entry")
        source = _source(root, item["file"])
        version = item.get("sourceVersion")
        if not isinstance(version, dict):
            raise PolicyError("Source version missing; rebuild catalog")
        stat = source.stat()
        if version.get("size") != stat.st_size or version.get("mtimeNs") != stat.st_mtime_ns:
            raise PolicyError("Source media changed since indexing; rebuild catalog")
    return value


def query(root, catalog, text, *, limit=12):
    value = load(root, catalog)
    terms = set(_words(text))
    if not terms:
        raise PolicyError("Query must contain meaningful words")
    if type(limit) is not int or not 1 <= limit <= 50:
        raise PolicyError("limit must be 1..50")
    matches = []
    for item in value["items"]:
        if not isinstance(item, dict):
            raise PolicyError("Malformed catalog item")
        # Never index filenames as semantic evidence.
        tags = set(_words(" ".join(item.get("tags", []))))
        description = set(_words(item.get("description", "")))
        weighted = sum(3 if token in tags else 1 if token in description else 0 for token in terms)
        if weighted <= 0:
            continue
        coverage = sum(token in tags or token in description for token in terms) / len(terms)
        matches.append({"id": item["id"], "file": item["file"],
                        "mediaStart": item["mediaStart"], "duration": item["duration"],
                        "score": round(weighted / (3*len(terms)) + .25*coverage, 4),
                        "matchedTerms": sorted(t for t in terms if t in tags or t in description),
                        "annotation": {"description": item.get("description"), "tags": item.get("tags")},
                        "provenance": item.get("provenance")})
    matches.sort(key=lambda x: (-x["score"], x["file"], x["mediaStart"]))
    return {"query": text, "matches": matches[:limit], "totalMatches": len(matches),
            "ranking": "exact normalized annotation tokens, weighted tags; no embedding model",
            "needsEditorialReview": True}


def match_storyboard(root, catalog, plan, *, allow_reuse=True):
    """Attach annotated source segments to existing creative plan; never guess."""
    if not isinstance(plan, dict) or not isinstance(plan.get("scenes"), list):
        raise PolicyError("Storyboard plan with scenes required")
    if not 1 <= len(plan["scenes"]) <= 50:
        raise PolicyError("Expected 1..50 storyboard scenes")
    if type(allow_reuse) is not bool:
        raise PolicyError("allowReuse must be boolean")
    matched = json.loads(json.dumps(plan))
    chosen, missing, used = [], [], set()
    for index, scene in enumerate(matched["scenes"]):
        if not isinstance(scene, dict):
            raise PolicyError("Scene must be object")
        request = str(scene.get("visualIntent") or scene.get("voiceText") or "").strip()
        if not request:
            raise PolicyError("Each scene needs a visual intent or voiceText")
        result = query(root, catalog, request, limit=50)
        required = _number(scene.get("duration", 0), "scene duration", .2, 600)
        candidates = [x for x in result["matches"]
                      if x["duration"] + 0.02 >= required and (allow_reuse or x["id"] not in used)]
        if not candidates:
            scene["source"] = None
            scene["requiresMedia"] = True
            missing.append({"index": index, "query": request})
            continue
        best = candidates[0]
        used.add(best["id"])
        scene["source"] = best["file"]
        scene["mediaStart"] = best["mediaStart"]
        scene["sourceClipId"] = best["id"]
        scene["annotationMatchScore"] = best["score"]
        scene["requiresMedia"] = False
        chosen.append({"index": index, "catalogClipId": best["id"],
                       "mediaStart": best["mediaStart"], "score": best["score"]})
    matched["productionReady"] = not missing
    matched["mediaMatchProvenance"] = "user_annotations_not_model_inference"
    return {"plan": matched, "matched": chosen, "missing": missing,
            "ready": not missing, "requiresEditorialReview": True}
