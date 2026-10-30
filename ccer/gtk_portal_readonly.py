"""Read-only GTK portal accessibility inventory; no pointer or file actions."""
from __future__ import annotations
import argparse
import importlib
import json
import sys
from pathlib import Path
from .controls import PolicyError


def snapshot(title="Exporter en SRT…", limit=120):
    if title != "Exporter en SRT…" or type(limit) is not int or not 1 <= limit <= 150:
        raise PolicyError("Unapproved GTK inspection target")
    # Ubuntu GI bindings may be outside a Conda environment.
    system_bindings = Path("/usr/lib/python3/dist-packages")
    if system_bindings.is_dir() and str(system_bindings) not in sys.path:
        sys.path.append(str(system_bindings))
    gi = importlib.import_module("gi")
    gi.require_version("Atspi", "2.0")
    atspi = importlib.import_module("gi.repository.Atspi")
    desktop = atspi.get_desktop(0)
    matches = []
    for i in range(min(desktop.get_child_count(), 150)):
        try:
            app = desktop.get_child_at_index(i)
            if "xdg-desktop-portal-gtk" not in str(app.get_name() or "").lower():
                continue
            pending = [(app, 0)]
            while pending and len(matches) < limit:
                node, depth = pending.pop(0)
                name = str(node.get_name() or "")[:160]
                role = str(node.get_role_name() or "")[:80]
                item = {"depth": depth, "name": name, "role": role}
                if role == "text":
                    try:
                        iface = node.get_text_iface()
                        if iface:
                            item["text"] = str(atspi.Text.get_text(iface, 0, -1))[:160]
                    except (AttributeError, RuntimeError, OSError):
                        pass
                if role == "push button" and name == "Save":
                    try:
                        action = node.get_action_iface()
                        if action:
                            item["actionCount"] = int(action.get_n_actions())
                            item["availableMethods"] = [name for name in dir(atspi.Action) if "action" in name or "name" in name][:30]
                            item["actionNames"] = [str(atspi.Action.get_name(action, i)) for i in range(min(4, action.get_n_actions()))]
                    except (AttributeError, RuntimeError, OSError):
                        pass
                matches.append(item)
                if depth < 7:
                    pending.extend((node.get_child_at_index(j), depth + 1)
                                   for j in range(min(node.get_child_count(), 70)))
        except (RuntimeError, OSError, AttributeError):
            continue
    return {"target": title, "nodes": matches, "readOnly": True,
            "savePerformed": False, "physicalPointerUsed": False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=120)
    args = ap.parse_args()
    print(json.dumps(snapshot(limit=args.limit), ensure_ascii=False))


if __name__ == "__main__":
    main()
