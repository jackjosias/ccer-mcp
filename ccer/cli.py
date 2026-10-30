"""Launch CCER gateway over MCP stdio on Linux, macOS or Windows."""
import argparse
import os
import sys
from pathlib import Path

from .concat_setup import default_binary
from .server import Gateway
from .transport import ConcatTransport, TransportError


def main():
    parser = argparse.ArgumentParser(description="CCER MCP gateway")
    parser.add_argument("--concat-bin", type=Path, default=default_binary())
    parser.add_argument("--mode", choices=("window", "headless"),
                        default=os.getenv("CCER_MODE", "window"))
    parser.add_argument("--root", type=Path,
                        default=Path(os.getenv("CCER_ROOT", str(Path.home() / "Videos/CCER"))))
    args = parser.parse_args()
    if not args.concat_bin.is_file():
        parser.error("Concat not found. Run 'ccer-concat --install' on Linux, or set CCER_CONCAT_BIN to an installed executable.")
    upstream = ConcatTransport(args.concat_bin, args.mode)
    try:
        upstream.start()
        Gateway(upstream, args.root).serve()
    except (TransportError, OSError, ValueError) as error:
        print("CCER startup failed: " + str(error), file=sys.stderr)
        raise SystemExit(1) from error
    finally:
        upstream.close()
