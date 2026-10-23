"""Provision an independent CCER profile for installed OpenAI tunnel-client.

This creates a LOCAL profile only, after the operator supplies a real tunnel ID.
It never creates cloud resources, embeds credentials, starts a background
service, exposes a public port, or alters the WCER tunnel.
"""
import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .controls import PolicyError


TUNNEL_ID = re.compile(r"tunnel_[a-z0-9]{32}\Z")
PROFILE = re.compile(r"[a-z][a-z0-9-]{0,50}\Z")


def init_command(*, tunnel_id, access="observe", profile="ccer-direct", profile_dir=None):
    if not isinstance(tunnel_id, str) or not TUNNEL_ID.fullmatch(tunnel_id):
        raise PolicyError("Provide the real OpenAI tunnel ID: tunnel_ + 32 lowercase letters/digits")
    if access not in ("observe", "control"):
        raise PolicyError("Access must be observe or control")
    if not isinstance(profile, str) or not PROFILE.fullmatch(profile):
        raise PolicyError("Profile must be a lowercase ASCII name")
    launcher = Path(__file__).resolve().parents[1] / "ccer_direct_stdio.py"
    if not launcher.is_file():
        raise PolicyError("CCER Direct launcher not found")
    python = sys.executable
    if any(char.isspace() for char in str(python)) or any(char.isspace() for char in str(launcher)):
        raise PolicyError("Unsupported spaces in executable path for stdio profile")
    target = f"{python} {launcher} --access {access}"
    args = ["tunnel-client", "init", "--sample", "sample_mcp_stdio_local",
            "--profile", profile, "--tunnel-id", tunnel_id,
            "--mcp-command", target,
            "--control-plane-api-key-ref", "env:CONTROL_PLANE_API_KEY",
            "--health-listen-addr", "127.0.0.1:0"]
    if profile_dir is not None:
        directory = Path(profile_dir).expanduser().resolve()
        if not directory.is_dir():
            raise PolicyError("Profile directory must already exist")
        args.extend(["--profile-dir", str(directory)])
    return args


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create CCER Direct OpenAI tunnel profile")
    parser.add_argument("--tunnel-id", required=True)
    parser.add_argument("--access", choices=("observe", "control"), default="observe")
    parser.add_argument("--profile", default="ccer-direct")
    parser.add_argument("--profile-dir")
    options = parser.parse_args(argv)
    try:
        command = init_command(tunnel_id=options.tunnel_id,
                               access=options.access, profile=options.profile,
                               profile_dir=options.profile_dir)
    except PolicyError as exc:
        parser.error(str(exc))
    if not shutil.which("tunnel-client"):
        parser.error("tunnel-client is not installed")
    result = subprocess.run(command, text=True, capture_output=True, timeout=35)
    if result.returncode:
        print("Cannot initialize CCER tunnel profile: " + result.stderr[-500:], file=sys.stderr)
        return 1
    print(result.stdout.rstrip())
    print("CCER is not yet connected: set CONTROL_PLANE_API_KEY in your own Ubuntu "
          "environment, then run tunnel-client doctor --profile " + options.profile)
    print("After doctor succeeds, run tunnel-client run --profile " + options.profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
