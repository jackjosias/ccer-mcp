"""Shared validated seek offsets for long-form CCER technical analysis."""
import math
from .controls import PolicyError

def start_args(start_seconds=0):
    if (isinstance(start_seconds, bool) or
            not isinstance(start_seconds, (int, float)) or
            not math.isfinite(start_seconds) or
            not 0 <= start_seconds <= 86400):
        raise PolicyError("startSeconds must be between 0 and 86400")
    start = float(start_seconds)
    return (["-ss", f"{start:.6f}"] if start else []), start

def absolute(relative, start):
    return round(float(relative) + start, 3)
