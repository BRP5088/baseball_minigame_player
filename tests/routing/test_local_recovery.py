"""go_to_node_verified must try a LOCAL search before resetting to the spawn.

A reset rewinds to the spawn and re-walks the whole route, discarding every
node already verified. At the measured ~55% arrival per node that is the
dominant cost of a trial — a 10-trial streak run took over 30 minutes, mostly
re-walking ground already walked correctly.
"""
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

import graph_walk as gw

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def run(local_first, recover_result, locate_seq):
    """Returns (result, calls) with reset/recover counted."""
    calls = {"reset": 0, "recover": 0, "follow": 0}
    seq = list(locate_seq)

    real = (gw.locate, gw.recover_to_node, gw.follow, gw.time.sleep)
    fake_reset = types.ModuleType("reset_env")

    def reset(log=None):
        calls["reset"] += 1
    fake_reset.reset_environment = reset
    saved = sys.modules.get("reset_env")
    sys.modules["reset_env"] = fake_reset
    gw.LOCAL_RECOVERY_FIRST = local_first
    # RELOCALISE_BY_TURNING runs BEFORE the local-recovery check and reaches the
    # REAL compass, which makes this offline test depend on a live game window.
    # An offline test that touches the console is not offline.
    old_reloc = gw.RELOCALISE_BY_TURNING
    gw.RELOCALISE_BY_TURNING = False
    try:
        gw.locate = lambda m, capture=None, log=None: (
            seq.pop(0) if seq else (None, "x"))

        def rec(m, node, capture=None, read_heading=None, log=None):
            calls["recover"] += 1
            return recover_result
        gw.recover_to_node = rec

        def fol(m, a, b, capture=None, read_heading=None, log=None, shots=None):
            calls["follow"] += 1
        gw.follow = fol
        gw.time.sleep = lambda *a: None
        out = gw.go_to_node_verified(None, "bar_pool_room",
                                     capture=lambda: None,
                                     log=lambda *a: None, attempts=2)
    finally:
        gw.locate, gw.recover_to_node, gw.follow, gw.time.sleep = real
        gw.LOCAL_RECOVERY_FIRST = True
        gw.RELOCALISE_BY_TURNING = old_reloc
        if saved is not None:
            sys.modules["reset_env"] = saved
        else:
            sys.modules.pop("reset_env", None)
    return out, calls


LOST = (None, "unrecognised")

# Local search finds it -> no reset at all.
ok, c = run(True, True, [LOST])
check("a successful local search avoids the reset entirely",
      ok and c["reset"] == 0)
check("and it did try the local search", c["recover"] == 1)
check("and it did not re-walk the route", c["follow"] == 0)

# Local search fails -> still resets, so a run cannot be lost by trying.
ok, c = run(True, False, [LOST, LOST, LOST])
check("a failed local search still falls back to the reset", c["reset"] >= 1)
check("the local search was attempted first", c["recover"] >= 1)

# Flag off -> old behaviour, straight to reset.
ok, c = run(False, True, [LOST, LOST, LOST])
check("with the flag off it never searches locally", c["recover"] == 0)
check("and goes straight to the reset", c["reset"] >= 1)

# Already there -> nothing happens at all.
ok, c = run(True, True, [("bar_pool_room", "ok")])
check("already at the node: no search, no reset",
      ok and c["recover"] == 0 and c["reset"] == 0)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
