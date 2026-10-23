"""Direct, standalone MCP gateway with explicit observe/control authorization."""
from .controls import PolicyError
from .server import Gateway

READ_NATIVE = frozenset(("concat_version", "project_list", "project_get",
    "timeline_read", "export_status", "media_probe", "effects_list",
    "template_list", "preview_frame"))
READ_CCER = frozenset(("ccer_preflight", "ccer_project_inspect",
    "ccer_timeline_validate", "ccer_asset_analyze", "ccer_audio_validate",
    "ccer_export_verify", "ccer_mission_status", "ccer_mission_recover",
    "ccer_audit_report", "ccer_caption_validate", "ccer_visual_scan",
    "ccer_creative_plan", "ccer_storyboard", "ccer_tts_status",
    "ccer_shot_inspect", "ccer_scene_detect", "ccer_silence_map",
    "ccer_beat_candidates", "ccer_cut_plan", "ccer_caption_timing_hint",
    "ccer_color_report", "ccer_media_search", "ccer_media_match",
    "ccer_desktop_status", "ccer_desktop_capture"))


class DirectGateway(Gateway):
    def __init__(self, upstream, root, *, access="observe"):
        if access not in ("observe", "control"):
            raise PolicyError("Direct MCP access must be observe or control")
        super().__init__(upstream, root)
        self.access = access
        self.allowed = (frozenset(t["name"] for t in self.catalogue)
                        if access == "control" else READ_NATIVE | READ_CCER)
        self.catalogue = [t for t in self.catalogue if t["name"] in self.allowed]

    def invoke(self, name, args):
        if name not in self.allowed:
            raise PolicyError("Direct MCP profile refuses this operation. "
                              "Explicitly enable control on the Ubuntu host.")
        return super().invoke(name, args)

    def handle(self, message):
        response = super().handle(message)
        if (response and message.get("method") == "initialize"
                and "result" in response):
            response["result"]["instructions"] += (
                " Direct CCER profile: " + self.access
                + ". WCER is not required in the operational path.")
        return response
