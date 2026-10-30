# CCER — Creative Engineering Runtime

**RÈGLE PERMANENTE POUR CHATGPT : montage visuel manuel obligatoire.**
Chaque action modifiant Concat exige une capture avant, un geste réel souris/clavier,
puis une capture après. Aucune mutation headless n'est permise via le connecteur.
Voir [CCER GUI-FIRST](docs/CCER_GUI_FIRST_CONTRACT.md) et
[isolation focus/souris](docs/CCER_FOCUS_ISOLATION.md).
**Aucune action CCER n'est autorisée sur le focus ou le pointeur du bureau
humain.** Le rendu Concat dans un Xvfb isolé reste bloqué par Vulkan/DRI3.

A guarded, **local-first** MCP gateway for **Concat Desktop** on Linux, macOS and Windows.

## Implemented

- Dynamically exposes every native Concat MCP tool (42 in the tested Concat 0.2.8).
- Adds 43 CCER tools: governed editing, creative planning, local audio/video inspection, subtitle preparation, offline English speech, directed rendering, and complete studio production: preflight, project inspection, checkpoints, rollback, timeline QA, transactional batch editing, media probe, audio QA, export QA, mission status, safe recovery and tamper-evident audit.
- Uses the **same native Concat engine** over MCP stdio; does not attempt to edit Concat's open on-screen project (upstream v0.2.8 constraint).
- Explicit `window` or `headless` mode, no silent fallback, sandboxed write paths, bounded subprocess waits.
- No Python runtime dependencies beyond the standard library. FFmpeg and FFprobe are optional for media QA.

## Install on Ubuntu

From this directory:

    python3 -m pip install --user --no-build-isolation -e .

Or directly, without installing:

    python3 -m ccer --concat-bin /home/your-user/WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage --mode window

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
            "--concat-bin", "/home/your-user/WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage",
            "--mode", "window",
            "--root", "/home/your-user/Videos/CCER"
          ],
          "env": {
            "PYTHONPATH": "/home/your-user/WORKSPACE-LOGICIEL/concat/ccer-mcp"
          }
        }
      }
    }

`--root` scopes project creation, editing and export to a dedicated folder. Keep production source clips in that folder or explicitly import them into it first. The gateway creates the root if absent. No public network listener is opened.

## Production workflow — developer-only native Gateway

Ces appels automatiques sont conservés pour les tests internes. Ils sont
**interdits dans le connecteur ChatGPT Direct**, même en mode control. Toute
mission vidéo de l'utilisateur doit passer par la fenêtre Concat visible.


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

## Rhythm and subtitle timing (75 MCP tools total)

- `ccer_silence_map`: find quiet/nonquiet passages with FFmpeg.
- `ccer_beat_candidates`: identify rhythmic audio impulses, tentative BPM and confidence.
- `ccer_cut_plan`: propose shot boundaries near supplied impulses. This changes **no project**.
- `ccer_caption_timing_hint`: allocate supplied phrases to nonsilent intervals. This is
  **not** a transcript, word-level alignment, or a substitute for listening review.

The tested workflow uses `ccer_cut_plan` to construct a reviewed storyboard,
then reuses `ccer_directed_render` to output an isolated MP4.

`python3 -m tests.live_rhythm` certifies these steps on a synthetic 120 BPM audio
track under `~/Videos/CCER`, never on a user's existing production project.

## Visual editing and verification (78 MCP tools total)

- `ccer_color_report`: sampled FFmpeg signalstats luminance, saturation and U/V metrics.
- `ccer_reframe_export`: padded "contain" or non-distorting "cover" crop with focus.
- `ccer_transition_export`: new two-clip MP4 with a fade, wipe or slide.
  Original source audio is **not** mixed by this function; optional external soundtrack only.
- `python3 -m tests.live_visual` generates two isolated colored videos, exports
  a vertical crop and a crossfade, and verifies the resulting MP4 files.
- Every rendering tool rejects output overwrites and verifies delivered duration
  and frame dimensions. These controls are not a substitute for artistic review.

## Media intelligence (82 MCP tools total)

- Human-annotated footage catalog with optional existing FFmpeg scene cuts.
- Keyword search across editor-provided descriptions and tags, with provenance.
- Match script storyboard scenes to annotated source clips (including mediaStart).
- Execute approved matching via existing CCER renderer and export QA.

This is metadata/annotation-based retrieval, NOT trained automatic visual recognition.
Detailed guide: docs/CCER_MEDIA_INTELLIGENCE.md.
Reproducible live test: python3 -m tests.live_media_catalog

## Direct Concat Desktop GUI control (85 MCP tools)

ChatGPT GPT-6 can orchestrate the existing CCER editor plus a Concat-specific
X11 visual bridge without any local LLM. Three tools are implemented:
`ccer_desktop_status`, `ccer_desktop_capture` (MCP JPEG image content), and
`ccer_desktop_act` (approved scoped click/key/type/scroll and post-action screenshot).
The window must be verified by exact class/PID, all actions must carry a fresh
window ID and `confirm=true`; this integration is **X11-only**.
Detailed instructions and safeguards: [CCER Desktop Control](docs/CCER_DESKTOP_CONTROL.md).
Live acceptance: `python3 -m tests.live_direct_control`.
Le glisser-déposer est limité au pointeur d'un Xvfb privé attesté ;
il ne doit jamais déplacer la souris physique de l'utilisateur.
Le dialogue GTK « Importer des médias » est pris en charge après vérification
stricte de sa classe, de son titre et de son processus (aucune autre fenêtre).

## Direct ChatGPT MCP connectivity (independent of WCER)

The standalone entrypoint `ccer_direct_stdio.py` serves the existing CCER
MCP gateway over stdio for the official OpenAI `tunnel-client`.

- `observe` (default) exposes 34 review and inspection tools, including
  real Concat screenshots. Writing commands are rejected server-side.
- `control` : l'accès direct ChatGPT est **GUI-FIRST** : outils de lecture
  et `ccer_desktop_act` seulement. Toutes les mutations MCP invisibles sont
  refusées au niveau du serveur. Une capture avant/après chaque geste est
  obligatoire. Le moteur natif conserve ses 85 outils pour les tests internes.
- `python3 -m ccer.tunnel_setup --tunnel-id <real-tunnel-id>` creates a
  separate CCER profile with **no API credentials in Git**.
- `tunnel-client doctor --profile ccer-direct` and
  `tunnel-client run --profile ccer-direct` authenticate that profile.

For an **existing** observe tunnel, use `python3 -m ccer.profile_access --access control --apply`, then restart only the `ccer-direct` process in its original terminal and refresh ChatGPT's connector. Do not recreate the tunnel or disclose secrets.

See [CCER Direct setup](docs/CCER_DIRECT_TUNNEL.md). Verify locally with
`python3 -m tests.live_direct_stdio` (observe) and
`python3 -m tests.live_direct_control` (full control).
The remote ChatGPT app must still be registered and authorized before any
claim of direct ChatGPT operation.

## Scope and roadmap

This is **v0.1.0 foundation**, not an end-to-end self-directed production agent. Automatic understanding of all desktop UI states, full color-grading intelligence, LLM-based creative direction, b-roll discovery, robust beat tracking for varied real-world music, speech forced-alignment, visual continuity understanding and distributed rendering remain subsequent features. Deterministic storyboarding, English flite voice and studio orchestration are implemented. Upstream Concat also limits what's currently possible. No claim of complete CapCut functional parity is made.

## License

This CCER gateway is original code. Concat is a separate upstream project under AGPL-3.0-or-later; its license applies to modifications or redistribution of that upstream as required by the license.
