"""CCER MCP stdio entry for supported OpenAI tunnel-client transport."""
import argparse
import os
import sys
from pathlib import Path
from .direct_gateway import DirectGateway
from .transport import ConcatTransport, TransportError


def main(argv=None):
    parser = argparse.ArgumentParser(description="CCER Direct MCP")
    parser.add_argument("--concat-bin", type=Path, default=Path(os.getenv(
        "CCER_CONCAT_BIN", str(Path.home() / "WORKSPACE-LOGICIEL/concat/Concat-0.2.8-x86_64.AppImage"))))
    parser.add_argument("--mode", choices=("window", "headless"),
                        default=os.getenv("CCER_MODE", "window"))
    parser.add_argument("--root", type=Path, default=Path(os.getenv(
        "CCER_ROOT", str(Path.home() / "Videos/CCER"))))
    parser.add_argument("--access", choices=("observe", "control"),
                        default=os.getenv("CCER_DIRECT_ACCESS", "observe"))
    args = parser.parse_args(argv)
    upstream = ConcatTransport(args.concat_bin, args.mode)
    try:
        upstream.start()
        DirectGateway(upstream, args.root, access=args.access).serve()
    except (TransportError, OSError, ValueError) as exc:
        print("CCER Direct startup failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        upstream.close()


if __name__ == "__main__":
    main()
