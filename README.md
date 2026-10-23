# CCER — Creative Engineering Runtime

A guarded, **local-first** MCP gateway for **Concat Desktop** on Linux, macOS and Windows.

## Implemented

- Dynamically exposes every native Concat MCP tool (42 in the tested Concat 0.2.8).
- Adds 29 CCER tools: governed editing, creative planning, local audio/video inspection, subtitle preparation, offline English speech, directed rendering, and complete studio production: preflight, project inspection, checkpoints, rollback, timeline QA, transactional batch editing, media probe, audio QA, export QA, mission status, safe recovery and tamper-evident audit.
- Uses the **same native Concat engine** over MCP stdio; does not attempt to edit Concat's open on-screen project (upstream v0.2.8 constraint).
- Explicit `window` or `headless` mode, no silent fallback, sandboxed write paths, bounded subprocess waits.
- No Python runtime dependencies beyond the standard library. FFmpeg and FFprobe are optional for media QA.

## Install on Ubuntu

From this directory:

    python3 -m pip install --user --no-build-isolation -e .

Or directly, without installing:

    python3 -m ccer --concat-bin /home/jack-josias/WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage --mode window

Concat Desktop must be open with Settings → Automation → Scripts and apps **enabled**.
The Concat MCP subprocess obtains its loopback token from the local owner-only `automation.json`. Never paste it into configurations or logs.

## Client configuration

Place this in the MCP client's local configuration (adjust paths):

    {
      "mcpServers": {
        "ccer": {
          "command": "/usr/bin/python3",
          "args": [
            "-m", "ccer",
            "--concat-bin", "/home/jack-josias/WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage",
            "--mode", "window",
            "--root", "/home/jack-josias/Videos/CCER"
          ],
          "env": {
            "PYTHONPATH": "/home/jack-josias/WORKSPACE-LOGICIEL/concat/ccer-mcp"
          }
        }
      }
    }

`--root` scopes project creation, editing and export to a dedicated folder. Keep production source clips in that folder or explicitly import them into it first. The gateway creates the root if absent. No public network listener is opened.

## Production workflow

1. Call `ccer_preflight` and inspect versions and disk capacity.
2. Use `project_create` then `timeline_read` on a **CCER-owned** project.
3. Use `media_probe`, `media_import`, `clip_add`, `title_add`, `captions_add`, effects/keyframes and `edit_apply`.
4. `ccer_checkpoint_create` before disruptive edits; `ccer_batch_edit` wraps commands into Concat's native atomic batch.
5. `ccer_timeline_validate`; inspect `preview_frame`.
6. `project_save`, `export_start`, `export_wait`, `ccer_export_verify`. For a complete recipe, call `ccer_produce` with `name`, `shots`, `profile`, optional `captions`, `titles`, `music`, and `export`.
7. Call `ccer_caption_validate` for readability, `ccer_visual_scan` for black/frozen frames and `ccer_delivery_transcode` for verified square, vertical or landscape deliveries.
8. Use `ccer_audit_report` to check the local journal chain.

### Safety contract

- `ccer_checkpoint_restore` requires `confirm=true`, validates checkpoint SHA, and **refuses any existing concat.lock**. Close the project in every window and API session first. The displaced project stays in an explicit restore-backup folder.
- Timeouts report **UNKNOWN outcome**, never automatically replay potentially destructive edits.
- `ccer_mission_recover` provides guidance, not an unsafe blind retry.
- Native tool argument fields `path`, `location` and `output` must remain under CCER_ROOT. A read-only `file` media input is not currently sandboxed; it may be outside the root.
- The SHA-linked audit detects accidental or partial edits but is **not a cryptographically authenticated record**: an attacker with filesystem write access could replace the entire journal.
- Media QA is diagnostic, not proof of artistic quality; human creative review remains valuable.

## Testing

    python3 -m compileall -q ccer
    python3 -m unittest discover -s tests -v

## Creative studio V2

Documentation détaillée : [CCER V2 Studio](docs/CCER_V2_STUDIO.md).

New MCP tools: `ccer_voice_flite` (English-only offline FFmpeg speech) and
`ccer_studio_produce` (reviewable script/storyboard, optional real narration,
music ducking, frame-timed rendering, SRT subtitles and technical QA).
Start with `ccer_tts_status` to verify whether `ffmpeg-flite` is available.

For French, use a prerecorded French narration through `narrationFile`.
Do not pretend English `flite` can narrate French naturally. Audio/text alignment
is currently estimated, not forced-aligned to speech. The studio renderer uses
FFmpeg as a complementary engine; Concat Desktop stays accessible through MCP.

## Scope and roadmap

This is **v0.1.0 foundation**, not an end-to-end self-directed production agent. Live on-screen editing, full color-grading intelligence, LLM-based creative direction, b-roll discovery, automatic beat synchronization, speech forced-alignment, visual continuity understanding and distributed rendering remain subsequent features. Deterministic storyboarding, English flite voice and studio orchestration are implemented. Upstream Concat also limits what's currently possible. No claim of complete CapCut functional parity is made.

## License

This CCER gateway is original code. Concat is a separate upstream project under AGPL-3.0-or-later; its license applies to modifications or redistribution of that upstream as required by the license.
