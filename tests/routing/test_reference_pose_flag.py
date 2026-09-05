"""align_at_node must correct toward the pose the flag selects — and the two
must actually be different files, or the flag is decorative.

The bug this guards: places/<node>/route_*.jpg was overwritten with the BOT's
arrival frames while world_map.json still holds the HUMAN's legs. Correction
then pulls onto pose A and walks a leg recorded from pose B, 71-212px away.
"""
import os
import os as _os
import sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
ROOT = _ROOT
sys.path.insert(0, ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import graph_walk as gw

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


NODES = ("portrait_room", "bar_pool_room", "bar_jukebox")
orig = gw.REFERENCE_POSE
try:
    for node in NODES:
        gw.REFERENCE_POSE = "bot"
        b = gw._recorded_reference(node)
        gw.REFERENCE_POSE = "human"
        h = gw._recorded_reference(node)
        check(f"{node}: both poses resolve to a file",
              b is not None and h is not None)
        check(f"{node}: the flag actually selects a DIFFERENT file", b != h)
        check(f"{node}: the human reference is the preserved backup",
              h is not None and gw.HUMAN_REFERENCE_DIR in h)
        # They must also differ in CONTENT — a backup that was overwritten with
        # the same frame would make the flag silently meaningless.
        if b and h and os.path.exists(b) and os.path.exists(h):
            check(f"{node}: the two references differ in content",
                  open(b, "rb").read() != open(h, "rb").read())
finally:
    gw.REFERENCE_POSE = orig

check("default is recorded explicitly", gw.REFERENCE_POSE in ("bot", "human"))

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
