"""Safety certification: GUI actions can never steal the human X11 session.

Read-only snapshots before and after a deliberate denied key request.
The target is the already open Concat window, which is NOT focused or changed.
"""
from ccer.controls import PolicyError
from ccer.desktop_gui import status, interact
from tests.live_isolation_probe import run


def main():
    focus = run(["xdotool", "getwindowfocus"])
    pointer = run(["xdotool", "getmouselocation", "--shell"])
    state = status()
    if state["inputReady"]:
        raise RuntimeError("Shared human display was incorrectly authorized")
    try:
        interact(expected_window_id=state["window"]["windowId"],
                 action="key", key="Escape", confirm_action=True,
                 with_capture=False)
    except PolicyError as error:
        if "FOCUS_ISOLATION_REQUIRED" not in str(error):
            raise
    else:
        raise RuntimeError("CCER allowed input on the human display")
    if run(["xdotool", "getwindowfocus"]) != focus:
        raise RuntimeError("Host focus changed during denied operation")
    if run(["xdotool", "getmouselocation", "--shell"]) != pointer:
        raise RuntimeError("Host pointer moved during denied operation")
    print({"sharedInputDenied": True, "focusPreserved": True,
           "mousePreserved": True, "readOnlyStatusAvailable": True})


if __name__ == "__main__":
    main()
