"""Deterministic offline MCP discovery catalogue; never launch Concat."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "mcp-tools.json"
sys.path.insert(0, str(ROOT))

from ccer import __version__
from ccer.direct_gateway import DirectGateway, READ_CCER, READ_NATIVE
from ccer.production import TOOLS
from ccer.server import Gateway


class OfflineUpstream:
    """Only discovery is permitted; a tool invocation is a regression."""

    def tools(self):
        return []

    def tool(self, *args, **kwargs):
        raise AssertionError("Catalogue generation must not invoke tools")


def discover(gateway):
    response = gateway.handle({"jsonrpc": "2.0", "id": 1,
                               "method": "tools/list"})
    tools = response["result"]["tools"]
    names = [item["name"] for item in tools]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate tool in discovery response")
    return sorted(tools, key=lambda item: item["name"])


def build():
    with tempfile.TemporaryDirectory(prefix="ccer-catalogue-") as root:
        upstream = OfflineUpstream()
        standard = discover(Gateway(upstream, root))
        observe = discover(DirectGateway(upstream, root, access="observe"))
        control = discover(DirectGateway(upstream, root, access="control"))
    std = {item["name"]: item for item in standard}
    obs = {item["name"]: item for item in observe}
    ctl = {item["name"]: item for item in control}
    if set(std) != set(TOOLS) or set(obs) != set(READ_CCER):
        raise ValueError("Discovery and registry/observe policy differ")
    if set(ctl) != set(obs) | {"ccer_desktop_act"}:
        raise ValueError("Direct control must add only the GUI action")
    if any(std[name] != item for name, item in ctl.items()):
        raise ValueError("Tool schema differs between profiles")
    return {
        "formatVersion": 1,
        "server": {"name": "ccer-mcp", "version": __version__},
        "scope": "CCER-owned tools, offline tools/list discovery; upstream Concat tools are dynamic and excluded",
        "limitations": "Discovery is not proof of tool execution, runtime availability, or per-tool test coverage. Annotations are the runtime hints, not independent safety certifications.",
        "profiles": {
            "standard": sorted(std),
            "directObserve": sorted(obs),
            "directControl": sorted(ctl),
        },
        "directNativeAllowlist": sorted(READ_NATIVE),
        "counts": {"standard": len(std), "directObserve": len(obs),
                   "directControl": len(ctl)},
        "tools": standard,
    }


def render():
    return json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = render()
    if args.write:
        OUTPUT.write_text(content, encoding="utf-8")
    elif not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != content:
        print("MCP catalogue stale; run python3 docs/render_mcp_catalog.py --write")
        return 1
    print("MCP catalogue verified:", json.loads(content)["counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
