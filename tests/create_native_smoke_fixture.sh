#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime="$repo/.upstream-concat/.ccer-ffmpeg7"
export LD_LIBRARY_PATH="$runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
output="$repo/.runtime/ccer-smoke/source.mp4"
mkdir -p "$(dirname "$output")"
"$runtime/bin/ffmpeg" -hide_banner -loglevel error -nostdin -y \
    -f lavfi -i 'testsrc2=size=640x360:rate=24' \
    -f lavfi -i 'sine=frequency=440:sample_rate=48000' \
    -t 2 -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
    -c:a aac -shortest "$output"
"$runtime/bin/ffprobe" -v error \
    -show_entries format=duration,size \
    -show_entries stream=index,codec_type,codec_name \
    -of default=noprint_wrappers=1 "$output"
