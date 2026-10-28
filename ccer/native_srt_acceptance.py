"""Read-only acceptance of Concat-exported SRT against genuine source A/V.

Existing SRT parser and FFmpeg frame review are the single source of truth;
temporary decoded JPEGs remain in memory and never enter JSON output.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from .controls import inside, PolicyError
from .av_timeline import read_srt, audiovisual_review


def verify(media_root, project_root, video, srt, *, timeline_offset_seconds=0,
           frame_count=2):
    if type(frame_count) is not int or not 1 <= frame_count <= 4:
        raise PolicyError("frameCount must be 1..4")
    source = inside(media_root, video, must_exist=True)
    raw = Path(srt)
    if raw.is_symlink():
        raise PolicyError("Unsafe SRT symlink")
    captions = inside(project_root, raw, must_exist=True)
    validated = read_srt(source, captions,
                         timeline_offset_seconds=timeline_offset_seconds)
    review = audiovisual_review(source, captions, start_seconds=0,
                                seconds=min(4, validated["durationSeconds"]),
                                frame_count=frame_count,
                                timeline_offset_seconds=timeline_offset_seconds)
    associations = review["frameSpeechAssociations"]
    if not associations or not any(a["cueIndices"] for a in associations):
        raise PolicyError("Real decoded frames do not align with SRT cues")
    return {
        "media": str(source), "srt": str(captions),
        "durationSeconds": validated["durationSeconds"],
        "timebase": validated["timebase"],
        "timelineOffsetSeconds": validated["timelineOffsetSeconds"],
        "cues": validated["cues"], "captionQA": validated["captionQA"],
        "decodedFrameCount": review["frameCount"],
        "frameSpeechAssociations": associations,
        "audioPresent": validated["audioPresent"],
        "sourceProvenance": "external_srt_read_from_disk",
        "transcriptionPerformed": False,
        "speechAccuracyVerified": False,
        "semanticUnderstandingPerformed": False,
        "readOnly": True, "mediaArtifactsCreated": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--media-root", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--srt", required=True)
    parser.add_argument("--timeline-offset", type=float, default=0.)
    args = parser.parse_args()
    print(json.dumps(verify(args.media_root, args.project_root, args.video, args.srt,
                            timeline_offset_seconds=args.timeline_offset),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
