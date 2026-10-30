"""Real isolated A-Z acceptance test: English narration, directed scenes, subtitles and QA."""
import json
import time
from pathlib import Path
from ccer.server import Gateway
from ccer.transport import ConcatTransport


def main():
    root = Path.home() / "Videos/CCER"
    sources = sorted(root.glob("CCER-RECIPE-*.mp4"))
    if not sources:
        raise RuntimeError("First run tests.live_recipe to create an approved source")
    source = str(sources[-1])
    concat = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    upstream = ConcatTransport(concat, "window", timeout=45)
    try:
        upstream.start()
        gateway = Gateway(upstream, root)
        if len(gateway.catalogue) != 71:
            raise RuntimeError("Expected 71 MCP tools; catalogue mismatch")
        result = gateway.invoke("ccer_studio_produce", {
            "name": "CCER-FLITE-" + time.strftime("%Y%m%d-%H%M%S"),
            "brief": {"topic": "CCER offline narrated editing",
                      "script": "Hello. Welcome to the CCER studio.",
                      "language": "en", "profile": "custom",
                      "durationSeconds": 8.0,
                      "assets": [source, source]},
            "generateEnglishVoice": True,
            "video": {"width": 320, "height": 180, "rateNum": 24, "rateDen": 1},
            "burnCaptions": True, "preset": "ultrafast"})["structuredContent"]
        print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
        if not result["passed"] or not Path(result["render"]["file"]).is_file():
            raise RuntimeError("Final MP4 was not verified")
    finally:
        upstream.close()


if __name__ == "__main__":
    main()
