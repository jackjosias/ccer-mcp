"""MCP gateway: preserve Concat tools, expose governed CCER workflows."""
import json
import sys

from .controls import PolicyError
from .production import Production, TOOLS
from .transport import TransportError


class Gateway:
    def __init__(self, upstream, root):
        self.upstream = upstream
        self.production = Production(upstream, root)
        native = upstream.tools()
        self.native = {item["name"]: item for item in native}
        duplicates = self.native.keys() & TOOLS.keys()
        if duplicates:
            raise ValueError("CCER tool names collide with native tools")
        self.catalogue = native + [
            {"name": name, "description": config["description"],
             "inputSchema": {k: v for k,v in config.items() if k != "description"},
             "annotations": {"readOnlyHint": name in (
                "ccer_preflight", "ccer_project_inspect", "ccer_timeline_validate",
                "ccer_asset_analyze", "ccer_audio_validate", "ccer_export_verify",
                "ccer_mission_status", "ccer_mission_recover", "ccer_audit_report",
                  "ccer_timecoded_review", "ccer_long_review_plan",
                   "ccer_editorial_note_review", "ccer_timed_caption_context",
                 "ccer_desktop_status", "ccer_desktop_capture", "ccer_asr_status",
                  "ccer_transcript_read", "ccer_av_timeline", "ccer_audio_window",
                   "ccer_av_events", "ccer_av_replay_poll"),
                "destructiveHint": name == "ccer_checkpoint_restore"}}
            for name, config in TOOLS.items()
        ]

    def invoke(self, name, args):
        if not isinstance(args, dict):
            raise PolicyError("Arguments must be an object")
        if name in TOOLS:
            outcome = self.production.run(name, args)
            if name == "ccer_audio_window":
                audio = outcome.pop("audioBase64")
                metadata = dict(outcome)
                return {"content": [
                    {"type": "text", "text": json.dumps(metadata, ensure_ascii=False)},
                    {"type": "audio", "mimeType": outcome["mimeType"], "data": audio}],
                    "structuredContent": metadata, "isError": False}
            if (name in ("ccer_timecoded_review", "ccer_editorial_note_review",
                        "ccer_av_timeline") or
                    (name == "ccer_av_replay_poll" and "frames" in outcome)):
                # Preserve real images as MCP image content, not a multi-MB JSON
                # string. A vision-capable agent can inspect each sampled frame.
                frames = outcome.pop("frames")
                audio_evidence = outcome.pop("audioEvidence", None)
                summary = {**outcome, "frames": [
                    {"timeSeconds": frame["timeSeconds"], "mimeType": frame["mimeType"]}
                    for frame in frames]}
                content = [{"type": "text", "text": json.dumps(summary, ensure_ascii=False)}]
                for frame in frames:
                    content.append({"type": "text", "text":
                                    f"Video frame at {frame['timeSeconds']:.3f}s"})
                    content.append({"type": "image", "mimeType": "image/jpeg",
                                    "data": frame["imageBase64"]})
                if audio_evidence is not None:
                    summary["audioEvidence"] = {k: v for k, v in audio_evidence.items()
                                                if k != "audioBase64"}
                    content[0]["text"] = json.dumps(summary, ensure_ascii=False)
                    content.append({"type": "audio", "mimeType": audio_evidence["mimeType"],
                                    "data": audio_evidence["audioBase64"]})
                return {"content": content, "structuredContent": summary, "isError": False}
            if name in ("ccer_desktop_capture", "ccer_desktop_act") and "imageBase64" in outcome:
                metadata = {k: v for k, v in outcome.items() if k != "imageBase64"}
                return {"content": [
                    {"type": "text", "text": json.dumps(metadata, ensure_ascii=False)},
                    {"type": "image", "mimeType": outcome["mimeType"],
                     "data": outcome["imageBase64"]}],
                    "structuredContent": metadata, "isError": False}
            return {"content": [{"type": "text",
                     "text": json.dumps(outcome, ensure_ascii=False)}],
                    "structuredContent": outcome, "isError": False}
        if name not in self.native:
            raise PolicyError("Unknown tool: " + str(name))
        # Native writes stay inside the user's explicitly configured CCER_ROOT.
        for key in ("path", "location", "output"):
            if key in args and isinstance(args[key], str):
                self.production.path(args[key])
        result = self.upstream.tool(name, args, timeout=600 if name == "export_wait" else None)
        if name in ("project_create", "edit_apply", "export_start", "project_save"):
            self.production.journal.append("native." + name, {"tool": name})
        return result

    def handle(self, message):
        if not isinstance(message, dict):
            return None
        ident, method = message.get("id"), message.get("method")
        if ident is None:
            return None
        response = {"jsonrpc": "2.0", "id": ident}
        try:
            if method == "initialize":
                requested = message.get("params", {}).get("protocolVersion")
                response["result"] = {
                    "protocolVersion": requested if requested in (
                        "2025-11-25", "2025-06-18", "2025-03-26") else "2025-06-18",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "ccer-mcp", "version": "0.1.0"},
                    "instructions": "CCER controls Concat Desktop projects. Call ccer_preflight first; use project-specific locks and verify every export."}
            elif method == "ping":
                response["result"] = {}
            elif method == "tools/list":
                response["result"] = {"tools": self.catalogue}
            elif method == "tools/call":
                params = message.get("params") or {}
                try:
                    response["result"] = self.invoke(params.get("name"), params.get("arguments") or {})
                except (TransportError, PolicyError, OSError, ValueError, KeyError, TimeoutError) as error:
                    response["result"] = {"isError": True, "content": [
                        {"type": "text", "text": str(error)}]}
            else:
                response["error"] = {"code": -32601, "message": "Method not found"}
        except (ValueError, TypeError, KeyError) as error:
            response["error"] = {"code": -32602, "message": str(error)}
        return response

    def serve(self, reader=None, writer=None):
        reader = reader or sys.stdin
        writer = writer or sys.stdout
        for line in reader:
            if len(line) > 8_000_000:
                continue
            try:
                message = json.loads(line)
                reply = self.handle(message)
                if reply is not None:
                    writer.write(json.dumps(reply, ensure_ascii=False) + "\n")
                    writer.flush()
            except (ValueError, TypeError):
                continue
