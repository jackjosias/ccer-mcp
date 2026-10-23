"""Launch CCER gateway over MCP stdio on Linux, macOS or Windows."""
import argparse
import os
import sys
from pathlib import Path

from .server import Gateway
from .transport import ConcatTransport, TransportError


def main():
    parser = argparse.ArgumentParser(description="CCER MCP gateway")
    default_bin = (Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage")
    parser.add_argument("--concat-bin", type=Path,
                        default=Path(os.getenv("CCER_CONCAT_BIN", str(default_bin))))
    parser.add_argument("--mode", choices=("window", "headless"),
                        default=os.getenv("CCER_MODE", "window"))
    parser.add_argument("--root", type=Path,
                        default=Path(os.getenv("CCER_ROOT", str(Path.home() / "Videos/CCER"))))
    args = parser.parse_args()
    upstream = ConcatTransport(args.concat_bin, args.mode)
    try:
        upstream.start()
        Gateway(upstream, args.root).serve()
    except (TransportError, OSError, ValueError) as error:
        print("CCER startup failed: " + str(error), file=sys.stderr)
        raise SystemExit(1) from error
    finally:
        upstream.close()
