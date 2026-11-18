"""Read-only fast preview of the SAME attested Concat visible on the human desktop.

Reuse isolated_session.frame (FFmpeg X11 window capture); never supply its
JPEG as an action receipt. Real gestures remain guarded by native Slint.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import statistics
import time

if __package__ in (None, ""):
    import sys
    from pathlib import Path
    root=Path.cwd().resolve()
    if not (root/"ccer"/"visible_desktop.py").is_file():
        raise RuntimeError("CCER: start from attested CCER workspace")
    sys.path.insert(0,str(root))
    from ccer import visible_desktop as desktop
    from ccer.isolated_session import frame
    from ccer.controls import PolicyError
else:
    from . import visible_desktop as desktop
    from .isolated_session import frame
    from .controls import PolicyError

def preview():
    identity=desktop._file_state()
    if not desktop._live(identity):
        raise PolicyError("CCER: attested visible Concat required")
    display=desktop._desktop()
    if identity.get("display")!=display:
        raise PolicyError("CCER: display identity mismatch")
    windows=desktop._windows()
    if (len(windows)!=1 or windows[0]["pid"]!=identity["pid"]
            or windows[0]["title"]!="Concat"):
        raise PolicyError("CCER: exactly one attested Concat window required")
    window=windows[0]["windowId"]
    start=time.perf_counter()
    image=frame(dict(os.environ,DISPLAY=display),window)
    elapsed=round(1000*(time.perf_counter()-start),1)
    if desktop._windows()!=windows or not desktop._live(identity):
        raise PolicyError("CCER: window identity changed during capture")
    if (not isinstance(image,bytes) or not 400<=len(image)<=5_000_000
            or not image.startswith(bytes.fromhex("ffd8"))
            or not image.endswith(bytes.fromhex("ffd9"))):
        raise PolicyError("CCER: preview JPEG invalid")
    return {"jpeg":image,"pid":identity["pid"],"windowId":window,
            "sha256":hashlib.sha256(image).hexdigest(),
            "latencyMs":elapsed,"jpegBytes":len(image),
            "readOnly":True,"physicalInputUsed":False,
            "actionAuthority":False,"slintReceipt":False}

def benchmark(samples=3):
    if type(samples) is not int or not 1<=samples<=5:
        raise PolicyError("CCER: samples must be 1..5")
    data=[]
    for _ in range(samples):
        shot=preview()
        data.append({"latencyMs":shot["latencyMs"],"jpegBytes":shot["jpegBytes"]})
    return {"contract":"CCER_FAST_VISIBLE_PREVIEW_V1","captures":data,
            "medianMs":round(statistics.median(x["latencyMs"] for x in data),1),
            "source":"same attested human-visible Concat window",
            "readOnly":True,"slintReceipt":False,"actionAuthority":False,
            "physicalInputUsed":False,"savedFrames":0}

def main():
    p=argparse.ArgumentParser(description="CCER read-only visible preview benchmark")
    p.add_argument("--samples",type=int,default=3)
    print(json.dumps(benchmark(p.parse_args().samples)))

if __name__=="__main__":
    main()
