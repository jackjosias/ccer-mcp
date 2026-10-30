"""CCER MCP stdio entry for supported OpenAI tunnel-client transport."""
import argparse
import os
import sys
from pathlib import Path
from .concat_setup import default_binary
from .direct_gateway import DirectGateway
from .isolated_session import bind_direct_process
from .controls import PolicyError
from .transport import DeferredConcatTransport, TransportError


def main(argv=None):
    parser = argparse.ArgumentParser(description="CCER Direct MCP")
    parser.add_argument("--concat-bin", type=Path, default=default_binary())
    parser.add_argument("--mode", choices=("window", "headless"),
                        default=os.getenv("CCER_MODE", "window"))
    parser.add_argument("--isolated-session", action="store_true",
                        help="Opt in to a private test DISPLAY; default uses the real desktop")
    parser.add_argument("--root", type=Path, default=Path(os.getenv(
        "CCER_ROOT", str(Path.home() / "Videos/CCER"))))
    parser.add_argument("--access", choices=("observe", "control"),
                        default=os.getenv("CCER_DIRECT_ACCESS", "observe"))
    args = parser.parse_args(argv)
    if args.mode != "window":
        parser.error("CCER Direct is GUI-FIRST only; headless mode is forbidden")
    try:
        # GUI-FIRST defaults to the user-visible desktop. A private Xvfb
        # session may be selected only by an explicit command-line opt-in.
        private = bind_direct_process() if args.isolated_session else False
        if private:
            print("CCER Direct: attached to private Concat GUI", file=sys.stderr)
        # Direct GUI-FIRST must control the existing native window, never spawn
        # another editor just to populate native read-tool discovery.
        # Native backend spawning remains available to other local workflows.
        upstream = DeferredConcatTransport(
            args.concat_bin, "window", permit_launch=False)
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
