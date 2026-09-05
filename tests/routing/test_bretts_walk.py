"""The driver must not corrupt the map, and must not move on a bad picture.

WHY THIS EXISTS
---------------
record-leg WRITES to world_map.json. A leg saved without confirming the
destination is worse than no leg at all: routing plans through it forever, and
nothing downstream can tell it was never actually walked.

Measured 2026-09-02, this is not hypothetical — a bearing that provably reached
bar_jukebox from one pose failed from another 157px away, so "it worked once"
is not evidence a leg is real.
"""
import json
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

import Bretts_walk as bw

fails = []


def check(c, m):
    if not c:
        fails.append(m)


# Every command must be reachable from the CLI, or a launch profile silently
# does nothing.
parser = bw.build_parser()
for name in ("where", "doctor", "connect", "reset", "walk", "last-mile",
             "label", "sweep", "record-leg"):
    check(name in bw.COMMANDS, f"{name!r} is missing from COMMANDS")
    try:
        parser.parse_args([name] + (["x"] if name == "label" else [])
                          + (["a", "b", "--bearing", "1", "--duration", "1"]
                             if name == "record-leg" else []))
    except SystemExit:
        fails.append(f"the CLI cannot parse the {name!r} subcommand")

# --- record-leg must REFUSE to save an unconfirmed arrival ----------------
saved = []


def _fake_modules(arrived):
    sys.modules["walk_steps"] = types.SimpleNamespace(
        turn_to=lambda t, log=print, **k: None,
        walk_forward=lambda sp, sec, strafe=0.0: 20.0,
        read_heading=lambda: 90.0)
    sys.modules["compass"] = types.SimpleNamespace(
        fast_capture=lambda: object(), read_bearing=lambda img: 90.0)
    sys.modules["places"] = types.SimpleNamespace(
        identify=lambda img, **k: (("bar_jukebox", 800, 4.0) if arrived
                                   else (None, 20, 1.1)),
        keypoints=lambda img, **k: (None, [0] * 900),
        add=lambda room, img, **k: "places/x/y.jpg")
    sys.modules["table_prompt"] = types.SimpleNamespace(
        at_table=lambda img: arrived, ink=lambda img: 0.05)

    class _Map:
        landmarks = {"bar_pool_room": (0, 0, 0), "bar_jukebox": (0, 1, 0)}

        def mark(self, n):
            self.landmarks[n] = (0, 0, 0)

        def connect(self, a, b, steps, **k):
            saved.append((a, b, steps))

        def save(self, path=None):
            saved.append("SAVED")

    sys.modules["worldmap"] = types.SimpleNamespace(
        WorldMap=types.SimpleNamespace(load=lambda *a, **k: _Map()))


args = types.SimpleNamespace(start="bar_pool_room", end="bar_jukebox",
                             bearing=337.1, duration=0.8, speed=0.25)

# Arrival NOT confirmed -> must not write anything.
saved.clear()
_fake_modules(arrived=False)
bw._live = lambda log=print: True
bw._to_node = lambda node, log=print, allow_reset=True: True
rc = bw.cmd_record_leg(args)
check(rc != 0, "record-leg reported success without confirming the destination")
check(saved == [],
      f"record-leg WROTE to the map without confirming arrival ({saved}). A leg "
      f"the router plans through must be one that was actually walked.")

# Arrival confirmed -> saves exactly one leg, with the walk that produced it.
saved.clear()
_fake_modules(arrived=True)
rc = bw.cmd_record_leg(args)
check(rc == 0, "record-leg failed on a confirmed arrival")
legs = [s for s in saved if s != "SAVED"]
check(len(legs) == 1, f"expected one leg saved, got {legs}")
check("SAVED" in saved, "the map was never written")
if legs:
    a, b, steps = legs[0]
    check((a, b) == ("bar_pool_room", "bar_jukebox"), f"saved {a}->{b}")
    check(len(steps) == 1 and abs(steps[0]["dur"] - 0.8) < 1e-6
          and abs(steps[0]["bearing"] - 337.1) < 0.05,
          f"the saved leg {steps} does not match the walk that was verified")

# --- refusing to walk at all without a live picture -----------------------
bw._live = lambda log=print: False
saved.clear()
check(bw.cmd_record_leg(args) == 2,
      "record-leg walked without a live picture; with no game window capture "
      "used to return the DESKTOP and every reading was of the wrong window")
check(saved == [], "it wrote to the map with no live picture")
check(bw.cmd_sweep(types.SimpleNamespace(
    corner=[1.0], jukebox=[1.0], table=[1.0], start="portrait_room",
    out=None)) == 2, "sweep ran without a live picture")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  Bretts_walk: every subcommand parses; record-leg refuses to write an "
      "unconfirmed leg, saves the exact walk it verified, and neither it nor "
      "sweep moves without a live picture")
