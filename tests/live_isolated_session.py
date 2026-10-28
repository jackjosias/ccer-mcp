"""Private Concat UI validation: no physical mouse/focus input."""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from unittest.mock import patch
from ccer.isolated_session import read_session
from ccer.desktop_gui import status, capture, interact
from tests.live_isolation_probe import run


def main():
    loaded=read_session()
    if loaded is None:
        proc=subprocess.Popen([sys.executable,"-m","ccer.isolated_session","run"],
                              stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                              text=True,start_new_session=True)
        try:
            for _ in range(150):
                if proc.poll() is not None:
                    raise RuntimeError("Private Concat startup failed: "+proc.stdout.read()[-1200:])
                try:
                    loaded=read_session()
                except (OSError,Exception) as e:
                    raise RuntimeError("Private session manifest invalid: "+str(e))
                if loaded is not None:
                    break
                time.sleep(.2)
            else:
                raise RuntimeError("Private Concat did not become ready")
            main()
            return
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try: proc.wait(timeout=12)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            proc.stdout.close()
    state,env=loaded
    human_focus=run(["xdotool","getwindowfocus"])
    human_pointer=run(["xdotool","getmouselocation","--shell"])
    url=f"http://127.0.0.1:{state['viewerPort']}"
    code=state["viewerPass"]
    with urllib.request.urlopen(url+"/?pass="+code,timeout=7) as r:
        assert r.status==200 and b"Concat" in r.read(25000)
    with urllib.request.urlopen(url+"/image?pass="+code,timeout=30) as r:
        f=r.read(500000)
        assert r.status==200 and len(f)>800 and f.startswith(bytes.fromhex("ffd8"))
    try:
        urllib.request.urlopen(url+"/image?pass=invalid",timeout=5)
        raise RuntimeError("Private viewer authorization failed")
    except urllib.error.HTTPError as e:
        if e.code!=403: raise
    test_actions=[
      {"action":"key","key":"Escape"},{"action":"key","key":"Escape"},
      {"action":"click","x":50,"y":320},{"action":"click","x":60,"y":330},
      {"action":"scroll","x":100,"y":390,"scroll":1},
      {"action":"scroll","x":100,"y":390,"scroll":-1},
      {"action":"drag","x":40,"y":425,"target_x":120,"target_y":440,"duration":.5},
      {"action":"drag","x":120,"y":440,"target_x":40,"target_y":425,"duration":.5},
      {"action":"key","key":"Escape"},{"action":"key","key":"Escape"}]
    with patch.dict(os.environ,env):
        s=status()
        assert s["inputReady"] is True
        for step in test_actions:
            before=capture(max_width=640)
            outcome=interact(expected_window_id=before["window"]["windowId"],
                             confirm_action=True,**step)
            if not outcome.get("actionSent") or not outcome.get("sha256"):
                raise RuntimeError("Private GUI action did not return a frame")
    # Native Concat socket requires the private instance's own GUI opt-in.
    # Keep core visual input proof separate from native MCP permissions.
    native_checked = os.environ.get("CCER_TEST_NATIVE") == "1"
    if native_checked:
        bridge = subprocess.run([sys.executable, "-m", "tests.live_direct_control"],
                                capture_output=True, text=True, timeout=65)
        if bridge.returncode:
            raise RuntimeError("Private CCER Direct handshake failed: " +
                               (bridge.stdout + bridge.stderr)[-1400:])
        details = json.loads(bridge.stdout)
        if not details.get("visibleDragExecuted"):
            raise RuntimeError("CCER Direct did not control the private GUI")
    native_smoke = "--native-smoke" in sys.argv
    if native_smoke:
        # Reuse the attested private Xvfb; never start smoke on the human DISPLAY.
        smoke_args = [sys.executable, "-m", "tests.native_slint_smoke",
                      "--project", "--export"]
        if "--dialog-only" in sys.argv:
            smoke_args.append("--dialog-only")
        smoke = subprocess.run(
            smoke_args, env={**os.environ, **env},
            capture_output=True, text=True, timeout=300)
        print(smoke.stdout[-6000:], flush=True)
        if smoke.returncode:
            raise RuntimeError("Private native export smoke failed: " +
                               (smoke.stdout + smoke.stderr)[-2500:])
    if run(["xdotool","getwindowfocus"])!=human_focus:
        raise RuntimeError("Human focus changed")
    if run(["xdotool","getmouselocation","--shell"])!=human_pointer:
        raise RuntimeError("Human pointer moved")
    print(json.dumps({"isolatedDisplay":state["display"],
       "actionsWithBeforeAfter":len(test_actions),
       "viewerHTML":True,"viewerJPEG":True,"viewerUnauthorized403":True,
       "directMcpGuiControls":native_checked,
       "humanFocusUnchanged":True,"humanPointerUnchanged":True},indent=2))


if __name__=="__main__":main()
