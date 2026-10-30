"""Certifies a genuinely timed multi-shot video with subtitles and narration."""
import json
import time
from pathlib import Path

from ccer.server import Gateway
from ccer.transport import ConcatTransport


def main():
    root = Path.home() / "Videos" / "CCER"
    source = sorted(root.glob("CCER-RECIPE-*.mp4"))[-1]
    mixes = sorted(root.glob("CCER-STUDIO-*/studio_mix.m4a"))
    if not mixes:
        raise RuntimeError("First run tests.live_studio")
    audio = mixes[-1]
    binpath = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    driver = ConcatTransport(binpath, "window", timeout=45)
    try:
        driver.start()
        gateway = Gateway(driver, root)
        plan = gateway.invoke("ccer_creative_plan", {"brief": {
            "topic": "Chaîne de production audiovisuelle CCER",
            "script": "Bienvenue au studio. Notre montage est automatisé.",
            "durationSeconds": 4.0, "profile": "shorts",
            "assets": [str(source), str(source)]}})["structuredContent"]
        plan["video"] = {"width": 320, "height": 180, "rateNum": 24, "rateDen": 1}
        output = root / ("CCER-DIRECTED-" + time.strftime("%Y%m%d-%H%M%S") + ".mp4")
        result = gateway.invoke("ccer_directed_render", {
            "plan": plan, "file": str(output), "audio": str(audio),
            "burnCaptions": True, "preset": "ultrafast"})["structuredContent"]
        qa = gateway.invoke("ccer_export_verify", {
            "file": str(output), "width": 320, "height": 180,
            "minDuration": 3.5, "maxDuration": 4.5})["structuredContent"]
        print(json.dumps({"render": result, "verified": qa["passed"],
            "audit": gateway.invoke("ccer_audit_report", {})["structuredContent"]},
            indent=2, ensure_ascii=False), flush=True)
        if not (result["verified"] and qa["passed"]):
            raise RuntimeError("Directed export has not qualified")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
