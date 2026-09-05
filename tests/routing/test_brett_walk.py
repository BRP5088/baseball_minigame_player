"""Offline check for the brett_walk primitives.

Every module that touches the console is faked, so this never drives the PS5.
"""
import json
import os
import os as _os
import sys
import types

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

SENT = []


def _fake(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


_fake("analog_replay",
      send=lambda lines: SENT.append(list(lines)),
      clear=lambda: SENT.append(["clear"]),
      to_axis=lambda v: round(v, 3))
_fake("walk_steps",
      SETTLE=0.0,
      TURN_TOLERANCE=3.5,
      _grey=lambda: 0,
      _view_change=lambda a, b: 1.0,
      turn_to=lambda t, log=None: t)
_fake("compass", fast_capture=lambda: "IMG", read_bearing=lambda img: 90.0)
_fake("table_prompt", at_table=lambda img: False)
_fake("places",
      identify=lambda img: ("portrait_room", 640, 2.0),
      keypoints=lambda img, cache_key=None: (None, [0] * 500),
      add=lambda room, img: f"places/{room}.jpg")
_fake("input_controller", press=lambda a, hold_seconds=0.05: SENT.append([f"btn {a}"]))

import brett_walk  # noqa: E402

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def axis(kind):
    """Value of the LAST write of this axis."""
    return next((float(ln.split()[1]) for lines in reversed(SENT)
                 for ln in lines if ln.startswith(kind + " ")), None)


def held(kind):
    """Value of the FIRST write of this axis — what was actually held.

    The last write is the recentre-to-zero, so `axis` would report 0 for a
    stick that was pushed hard and then released.
    """
    return next((float(ln.split()[1]) for lines in SENT
                 for ln in lines if ln.startswith(kind + " ")), None)


notes = []
w = brett_walk.Walk("t", recorder=types.SimpleNamespace(
    note=lambda action, **f: notes.append(dict(action=action, **f))),
    log=lambda *a: None)

SENT.clear()
w.forward(0.5)
fwd = axis("left_y")
SENT.clear()
w.back(0.5)
back = axis("left_y")
check("forward and back push the stick opposite ways",
      fwd is not None and back is not None and fwd * back < 0)

SENT.clear()
w.right(0.4)
check("strafe moves left_x, not left_y",
      axis("left_x") not in (None, 0.0) and axis("left_y") == 0.0)
check("strafe right and left are opposite signs",
      (lambda r: (SENT.clear(), w.left(0.4), r * axis("left_x") < 0)[-1])(axis("left_x")))

# A 2.0s push must be split: chiaki drops injected input after 5s, and an
# unchunked leg silently caps at ~4.5s.
SENT.clear()
w.forward(2.0)
pushes = sum(1 for lines in SENT for ln in lines if ln.startswith("left_y"))
check("a long push is chunked (<=0.8s each)", pushes >= 3)

check("moves are recorded", [n for n in notes if n["action"] == "forward"])
check("recorded note carries the duration",
      any(n.get("seconds") == 2.0 for n in notes))

brett_walk.CHIAKI_TIMES_THE_HOLD = True
SENT.clear()
w.camera(0.5, x=0.3)
check("a timed hold is ONE write, with the duration in ms",
      sum(1 for ls in SENT for l in ls if l.startswith("right_x")) == 1
      and any(l == "right_x 0.3 500" for ls in SENT for l in ls))
check("and it does NOT write a separate release",
      not any(l == "right_x 0" for ls in SENT for l in ls))

brett_walk.CHIAKI_TIMES_THE_HOLD = False
SENT.clear()
w.camera(0.5, x=0.3)
check("camera moves right_x, and does NOT move the character",
      held("right_x") == 0.3 and held("left_x") == 0.0
      and held("left_y") == 0.0)
SENT.clear()
w.camera(2.0, y=-0.4)
check("camera pitch goes to right_y", held("right_y") == -0.4)
check("a long camera push is chunked",
      sum(1 for ls in SENT for l in ls if l.startswith("right_x")) >= 3)
check("camera recentres the stick when done",
      SENT[-1] == ["right_x 0", "right_y 0"])

# to_axis clamps to int16, so an out-of-range magnitude is silently full
# stick. Obeying something the caller did not mean, quietly, is the failure
# shape this project keeps getting bitten by.
warned = []
w2 = brett_walk.Walk("t", recorder=None, log=lambda m: warned.append(m))
SENT.clear()
w2.camera(0.2, x=10.0)
check("an out-of-range magnitude is clamped to the stick's range",
      held("right_x") == 1.0)
check("and the clamp is REPORTED, not silent",
      any("clamp" in m for m in warned))

# Full stick measured 4.8x worse than 0.9. Saying nothing about that is how a
# caller lands on the worst point of the response curve without knowing.
warned.clear()
w2.camera(0.2, x=0.95)
check("a magnitude above the usable band is flagged",
      any("usable band" in m for m in warned))
warned.clear()
w2.camera(0.2, x=0.9)
check("and 0.9 itself is NOT flagged",
      not any("usable band" in m for m in warned))

sys.modules["walk_steps"].turn_to = lambda t, log=None: 359.7
notes.clear()
lines = []
w3 = brett_walk.Walk("t", recorder=types.SimpleNamespace(
    note=lambda action, **f: notes.append(dict(action=action, **f))),
    log=lambda m: lines.append(m))
w3.turn(2)
check("a turn across 0/360 is reported as a SMALL error, not a huge one",
      notes and abs(notes[-1]["error"]) < 5)
check("and the printed line says so",
      any("+" in m or "-" in m for m in lines) and "off by" in " ".join(lines))

sys.modules["walk_steps"].turn_to = lambda t, log=None: None
notes.clear(); lines.clear()
crash = None
try:
    w3.turn(90)
except Exception as e:                 # a dead compass must not kill the walk
    crash = e
check("a failed compass read does not raise", crash is None)
check("a failed compass read is reported as FAILED, not as a number",
      crash is None and "FAILED" in " ".join(lines)
      and notes and notes[-1]["got"] is None)
sys.modules["walk_steps"].turn_to = lambda t, log=None: t

brett_walk.CHIAKI_TIMES_THE_HOLD = True
w.jump()
check("jump is cross", any(l == ["btn cross"] for l in SENT))

notes.clear()
w.mark("somewhere")
check("mark saves a rich frame", notes and notes[-1]["action"] == "mark")

sys.modules["places"].keypoints = lambda img, cache_key=None: (None, [0] * 12)
notes.clear()
check("mark REFUSES a featureless frame", w.mark("dark") is None)
check("the refusal is recorded",
      notes and notes[-1]["action"] == "mark_refused")

# walk() must not start without a live picture: with no game window, capture
# returns the desktop and every reading is of the wrong window.
_fake("ensure_stream", ensure_live=lambda log=None: False)
_fake("world_log", Recorder=lambda *a, **k: types.SimpleNamespace(
    dir="/tmp/x", stop=lambda: "/tmp/x",
    note=lambda action, **f: None,
    start=lambda: sys.modules["world_log"].Recorder()))
refused = False
try:
    with brett_walk.walk("nope", log=lambda *a: None):
        pass
except RuntimeError:
    refused = True
check("walk() refuses a dead stream", refused)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
