"""Direct, standalone MCP gateway with explicit observe/control authorization."""
import time

from .controls import PolicyError
from .server import Gateway

READ_NATIVE = frozenset(("concat_version", "project_list", "project_get",
    "timeline_read", "export_status", "media_probe", "effects_list",
    "template_list", "preview_frame"))
READ_CCER = frozenset(("ccer_preflight", "ccer_project_inspect",
    "ccer_timeline_validate", "ccer_asset_analyze", "ccer_audio_validate",
    "ccer_export_verify", "ccer_mission_status",
    "ccer_audit_report", "ccer_caption_validate", "ccer_visual_scan",
    "ccer_timecoded_review", "ccer_long_review_plan",
    "ccer_editorial_note_review", "ccer_timed_caption_context",
    "ccer_creative_plan", "ccer_storyboard", "ccer_tts_status",
    "ccer_asr_status", "ccer_transcript_read", "ccer_av_timeline",
    "ccer_audio_window", "ccer_av_events", "ccer_av_replay_poll",
    "ccer_shot_inspect", "ccer_scene_detect", "ccer_silence_map",
    "ccer_beat_candidates", "ccer_cut_plan", "ccer_caption_timing_hint",
    "ccer_color_report", "ccer_media_search", "ccer_media_match",
    "ccer_desktop_status", "ccer_desktop_capture"))

# User-mandated permanent GUI-FIRST policy. The direct ChatGPT connector may
# observe backend data, but MUST NEVER use invisible timeline/project writes.
# Native editing tools remain available to local developer tests only, through
# the separate Gateway (not this remote/direct client).
VISUAL_TOOLS = READ_NATIVE | READ_CCER | {"ccer_desktop_act"}
VIEW_MAX_AGE_SECONDS = 75


class DirectGateway(Gateway):
    def __init__(self, upstream, root, *, access="observe"):
        if access not in ("observe", "control"):
            raise PolicyError("Direct MCP access must be observe or control")
        super().__init__(upstream, root)
        self.access = access
        # Even an explicitly authorized control profile is GUI-only for writes.
        # `--access control` must never silently mean headless editing.
        self.allowed = VISUAL_TOOLS if access == "control" else READ_NATIVE | READ_CCER
        self.catalogue = [t for t in self.catalogue if t["name"] in self.allowed]
        self._last_visual_observation = None

    def invoke(self, name, args):
        if name not in self.allowed:
            raise PolicyError(
                "CCER VISUAL-ONLY: invisible project/timeline/edit/export calls "
                "are forbidden through ChatGPT. Observe and use Concat GUI "
                "with ccer_desktop_capture + ccer_desktop_act instead."
            )
        if name == "ccer_desktop_act":
            if not isinstance(args, dict):
                raise PolicyError("GUI action requires an argument object")
            recent = self._last_visual_observation
            # One dedicated BEFORE screenshot for every action, never a
            # scripted batch or an implicit headless fallback.
            if recent is None or time.monotonic() - recent["when"] > VIEW_MAX_AGE_SECONDS:
                raise PolicyError("Take a fresh Concat screenshot BEFORE every GUI action")
            if args.get("expectedWindowId") != recent["windowId"]:
                raise PolicyError("GUI target does not match the last screenshot")
            if args.get("withCapture", True) is not True:
                raise PolicyError("A screenshot AFTER every GUI action is mandatory")
            self._last_visual_observation = None   # fail closed on any error
        if name == "ccer_desktop_capture":
            # Any new capture invalidates a prior action receipt, including
            # errors and read-only fallbacks; fail closed on overloaded GUI.
            self._last_visual_observation = None
        outcome = super().invoke(name, args)
        if name in ("ccer_desktop_capture", "ccer_desktop_act"):
            metadata = outcome.get("structuredContent", {})
            has_image = any(part.get("type") == "image" for part in outcome.get("content", []))
            if not has_image or not metadata.get("sha256"):
                raise PolicyError("Visual verification missing: an actual Concat image is mandatory")
            if name == "ccer_desktop_capture":
                # Verified X11 fallback is a valid READ-ONLY image, never a
                # Slint BEFORE receipt authorizing mouse or keyboard input.
                if (metadata.get("safeForClickReceipt") is True
                        and metadata.get("captureSource") == "authenticated_native_slint"
                        and metadata.get("readOnly") is False
                        and type(metadata.get("frameNo")) is int
                        and metadata.get("window", {}).get("display") == "native-slint"):
                    self._last_visual_observation = {
                        "when": time.monotonic(),
                        "windowId": metadata["window"]["windowId"],
                    }
        return outcome

    def handle(self, message):
        if isinstance(message, dict) and message.get("method") == "tools/list":
            # Discover native read tools if Concat came online after the tunnel.
            # Reuse the existing Gateway catalogue, without exposing writes.
            discovered = self.upstream.tools()
            if discovered:
                names = {item["name"] for item in discovered}
                from .production import TOOLS
                if names & TOOLS.keys():
                    raise PolicyError("CCER/native tool catalogue collision")
                self.native = {item["name"]: item for item in discovered}
                self.catalogue = [
                    item for item in discovered if item["name"] in self.allowed
                ] + [item for item in self.catalogue
                     if item["name"] in READ_CCER
                      or (self.access == "control"
                          and item["name"] == "ccer_desktop_act")]
        response = super().handle(message)
        if (response and message.get("method") == "initialize"
                and "result" in response):
            response["result"]["instructions"] += (
                " Direct CCER profile: " + self.access
                + ". PERMANENT GUI-FIRST DIRECTIVE: All editing, imports, titles, "
                "timeline changes and exports MUST be performed by visually "
                "observable mouse/keyboard actions inside Concat Desktop. "
                "Never use native project_create/media_import/clip_update/"
                "title_add/export_start or other headless mutation tools. "
                "Before EVERY action call ccer_desktop_capture; after EVERY "
                "action inspect the returned screenshot. Interact one action "
                "at a time and allow human correction between steps. "
                "If a UI task is not feasible, stop and explain; NEVER fall "
                "back to headless. WCER is not in the operational path.")
        return response
