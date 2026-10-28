"""One-purpose, user-confirmed AT-SPI GTK SRT Save bridge.

Runs only on existing Concat test project and exact visible GTK portal.
No pointer, keyboard, window activation, second editor, or overwrites.
"""
from __future__ import annotations
import argparse
import importlib
import json
import re
import subprocess
import time
from pathlib import Path
from .controls import PolicyError
from .gtk_portal_readonly import snapshot
from .project_caption_audit import inspect

PROJECT = Path.home() / "Desktop/Concat/Untitled project 8"
MEDIA_ROOT = Path.home() / "WORKSPACE-LOGICIEL/concat/ccer-mcp/.runtime/ccer-smoke"
SRT_NAME = "Untitled project 8.srt"
DIALOG = "Exporter en SRT…"


def preflight():
    target = PROJECT / SRT_NAME
    if PROJECT.is_symlink() or not PROJECT.is_dir() or target.exists() or target.is_symlink():
        raise PolicyError("Expected unused SRT destination in test project")
    audit = inspect(PROJECT, PROJECT / "concat.json", MEDIA_ROOT)
    if (not audit["captionQA"]["passed"] or audit["titleCount"] != 1
            or not audit["audioInSourceVideos"]):
        raise PolicyError("Actual Concat spoken project is not qualified")
    tree = subprocess.run(["xwininfo", "-root", "-tree"], capture_output=True,
                          text=True, timeout=12, check=True).stdout
    matches = [line for line in tree.splitlines()
               if re.search(r'0x[0-9a-f]+ "Exporter en SRT…": \("xdg-desktop-portal-gtk"', line)]
    if len(matches) != 1:
        raise PolicyError("Real GTK SRT chooser must be unique")
    nodes = snapshot(limit=140)["nodes"]
    if sum(x["role"] == "file chooser" and x["name"] == DIALOG for x in nodes) != 1:
        raise PolicyError("Expected unique accessible SRT chooser")
    if sum(x.get("text") == SRT_NAME for x in nodes) != 1:
        raise PolicyError("GTK filename differs from approved filename")
    save = [x for x in nodes if x["role"] == "push button" and x["name"] == "Save"]
    if len(save) != 1 or save[0].get("actionCount") != 1:
        raise PolicyError("GTK Save action is not unique")
    return {"project": str(PROJECT), "srtFile": str(target),
            "dialogVerified": True, "fileNameVerified": True,
            "buttonVerified": True, "savePerformed": False,
            "pointerMoved": False, "x11InputUsed": False}


def save_srt(*, confirm=False):
    if confirm is not True:
        raise PolicyError("Explicit confirm=true required")
    proof = preflight()
    atspi = importlib.import_module("gi.repository.Atspi")
    desktop = atspi.get_desktop(0)
    buttons = []
    found = 0
    for i in range(min(150, desktop.get_child_count())):
        app = desktop.get_child_at_index(i)
        if "xdg-desktop-portal-gtk" not in str(app.get_name() or "").lower():
            continue
        for j in range(min(100, app.get_child_count())):
            dialog = app.get_child_at_index(j)
            if str(dialog.get_name() or "") != DIALOG or str(dialog.get_role_name()) != "file chooser":
                continue
            found += 1
            pending = [(dialog, 0)]
            count = 0
            while pending and count < 140:
                node, depth = pending.pop(0)
                count += 1
                if str(node.get_name() or "") == "Save" and str(node.get_role_name()) == "push button":
                    buttons.append(node)
                if depth < 7:
                    pending.extend((node.get_child_at_index(k), depth+1)
                                   for k in range(min(node.get_child_count(), 60)))
    if found != 1 or len(buttons) != 1:
        raise PolicyError("GTK dialog changed before native Save")
    action = buttons[0].get_action_iface()
    if action is None or action.get_n_actions() != 1:
        raise PolicyError("GTK action changed before Save")
    # ONE AT-SPI accessibility action on the user-visible GTK button.
    # No X11 events, no retrial on an unknown native outcome.
    accepted = bool(atspi.Action.do_action(action, 0))
    target = Path(proof["srtFile"])
    for _ in range(15):
        if target.is_file() and not target.is_symlink():
            break
        time.sleep(0.2)
    written = target.is_file() and not target.is_symlink()
    return {"actionAccepted": accepted, "fileVerified": written,
            "srtFile": str(target), "bytes": target.stat().st_size if written else 0,
            "pointerMoved": False, "x11InputUsed": False,
            "success": accepted and written}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    result = save_srt(confirm=True) if args.confirm else preflight()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
