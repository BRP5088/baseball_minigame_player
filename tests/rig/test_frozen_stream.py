"""A frozen picture must be detected, not mistaken for dead input.

WHY THIS EXISTS
---------------
chiaki keeps heartbeating while its decoder stalls, so streaming() says yes and
every frame is identical. Measured twice on 2026-09-02 with chiaki logging
"pending_overflow_evict ... overflow queue full".

That state SATISFIES most checks in this project: nothing moves so nothing looks
blocked, and a reset probe measures delta 0.0 and reports "NO input is reaching
the game" — which is the opposite of the truth and sent two investigations at
the input path. A five-run measurement was lost to it.
"""
import os
import os as _os
import sys
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import numpy as np

import ensure_stream
# This file drives ensure_stream's ORCHESTRATION on purpose, against stubbed
# internals. The module refuses to run under BASEBALL_TEST_RUN since 2026-09-13 --
# the offline suite was reaching the LIVE rig, and one rung further is
# restart_chiaki.sh, i.e. kill -9 on the user's stream -- so opt in explicitly.
ensure_stream.RIG_DRIVER_IN_TESTS = True


fails = []


def check(c, m):
    if not c:
        fails.append(m)


class _Img:
    def __init__(self, v, shape=(16, 16)):
        self.v, self.shape = v, shape

    def convert(self, mode):
        return self

    def __array__(self, dtype=None):
        return np.full(self.shape, self.v, dtype=dtype or float)


def with_frames(frames):
    it = iter(frames)
    sys.modules["compass"] = types.SimpleNamespace(
        fast_capture=lambda: next(it))
    ensure_stream.time = types.SimpleNamespace(sleep=lambda s: None)


# Identical frames = frozen.
with_frames([_Img(50), _Img(50)])
check(ensure_stream.is_frozen() is True,
      "two identical captures were not called frozen; that state reports "
      "'NO input is reaching the game' from every reset probe while input is "
      "perfectly fine")

# A live picture must NOT be called frozen, or every run gets torn down.
with_frames([_Img(50), _Img(70)])
check(ensure_stream.is_frozen() is False,
      "a changing picture was called frozen — that would restart chiaki on a "
      "healthy stream")

# Barely-above-threshold change is live.
with_frames([_Img(50.0), _Img(51.0)])
check(ensure_stream.is_frozen() is False,
      "a 1.0 mean change was called frozen; the floor is "
      f"{ensure_stream.FROZEN_DELTA}")

# A capture that RAISES must not tear down a working stream.
def _boom():
    raise RuntimeError("grab failed")


sys.modules["compass"] = types.SimpleNamespace(fast_capture=_boom)
check(ensure_stream.is_frozen() is False,
      "a failed grab was reported as frozen; being unable to look is not "
      "evidence the picture stopped")

# Mismatched capture sizes must not crash — chiaki resizes its window while
# reconnecting, and a capture across that moment comes back a different shape.
with_frames([_Img(50, (1080, 1920)), _Img(50, (1084, 1927))])
try:
    r = ensure_stream.is_frozen()
    ok = r is True
except Exception as e:
    ok = False
    fails.append(f"is_frozen crashed on mismatched capture sizes: {e}")
check(ok, "identical frames of differing size were not called frozen")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  frozen stream: identical captures detected, live ones untouched, a "
      "failed grab is not 'frozen', and a mid-reconnect resize does not crash")
