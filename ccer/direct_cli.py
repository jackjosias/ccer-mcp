"""CCER MCP stdio entry for supported OpenAI tunnel-client transport."""
import argparse
import os
import sys
from pathlib import Path
from .direct_gateway import DirectGateway
from .isolated_session import bind_direct_process
from .controls import PolicyError
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
    if args.mode != "window":
        parser.error("CCER Direct is GUI-FIRST only; headless mode is forbidden")
    try:
        private = bind_direct_process()
        # Both the backend transport and GUI actions use a single verified
        # isolated X display, never the user's foreground session.
        if private:
            print("CCER Direct: attached to private Concat GUI", file=sys.stderr)
        upstream = ConcatTransport(args.concat_bin, "window")
        upstream.start()
        DirectGateway(upstream, args.root, access=args.access).serve()
    except (TransportError, PolicyError, OSError, ValueError) as exc:
        print("CCER Direct startup failed: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        if "upstream" in locals():
            upstream.close()


if __name__ == "__main__":
    main()
