"""Opt-in isolated end-to-end render certification for CCER + Concat Desktop."""
import json
import time
from pathlib import Path

from ccer.server import Gateway
from ccer.transport import ConcatTransport, structured


def main():
    root = Path.home() / "Videos" / "CCER"
    binary = Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"
    transport = ConcatTransport(binary, mode="window", timeout=60)
    try:
        transport.start()
        gateway = Gateway(transport, root)
        name = "CCER-CERT-" + time.strftime("%Y%m%d-%H%M%S")
        project = root / name
        output = root / (name + ".mp4")
        print("CREATE", flush=True)
        created = gateway.invoke("project_create", {
            "location": str(root), "name": name,
            "video": {"width": 320, "height": 180, "rateNum": 24, "rateDen": 1},
        })
        if created.get("isError"):
            raise RuntimeError(created)
        print("TITLE", flush=True)
        title = gateway.invoke("title_add", {
            "path": str(project), "start": 0, "duration": 2.0,
            "style": {"content": "CCER / Concat MCP", "color": "#ffffff",
                      "fontSize": 0.09, "shadow": True},
        })
        if title.get("isError"):
            raise RuntimeError(title)
        print("TIMELINE", flush=True)
        qa = gateway.invoke("ccer_timeline_validate", {"path": str(project)})["structuredContent"]
        if not qa["valid"] or qa["clipCount"] < 1:
            raise RuntimeError("Failed timeline verification: " + str(qa))
        print("SAVE", flush=True)
        gateway.invoke("project_save", {"path": str(project)})
        print("EXPORT", flush=True)
        job = structured(gateway.invoke("export_start", {
            "path": str(project), "output": str(output), "preset": "ultrafast"}))
        job_id = job.get("job")
        if not job_id:
            raise RuntimeError("Export did not provide job ID: " + str(job))
        print("EXPORT_JOB", job_id, flush=True)
        status = structured(gateway.invoke("export_wait", {
            "job": job_id, "timeoutSeconds": 120}))
        print("EXPORT_STATUS", json.dumps(status)[:500], flush=True)
        if status.get("state") != "done":
            raise RuntimeError("Export not confirmed complete")
        verified = gateway.invoke("ccer_export_verify", {
            "file": str(output), "width": 320, "height": 180,
            "minDuration": 1.5, "maxDuration": 2.5})["structuredContent"]
        print("QUALIFICATION", json.dumps({
            "passed": verified["passed"], "errors": verified["errors"],
            "path": str(output), "bytes": Path(output).stat().st_size,
            "timeline": qa, "audit": gateway.invoke("ccer_audit_report", {})["structuredContent"]},
            ensure_ascii=False), flush=True)
        if not verified["passed"]:
            raise RuntimeError("Export QA failed")
    finally:
        transport.close()


if __name__ == "__main__":
    main()
