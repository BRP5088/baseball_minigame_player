"""Before resetting, go_to_node_verified must look around — by TURNING only.

Why: "lost" triggers a reset, which rewinds to the spawn and re-walks the whole
route (~75s of a 338s trial). Some of those are not lost. Measured 2026-09-03,
the character stood in a known room facing a blown-out white wall, locate()
abstained on a near-featureless frame, and turning recovered it.

This is NOT the recovery fan, which MOVES and measured worse (155s vs 75s,
arriving less often). The property that makes turning safe — it cannot change
position — is what this test pins.

IT ALSO PINS WHERE THE BEHAVIOUR LIVES. locate() is a QUERY and must stay free
of side effects: `Bretts_walk.py where` is documented as "MOVES NOTHING".
Putting the turn inside locate() broke test_graph_walk's reset guard, which was
right to complain.
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


def run(look_results, turning=True):
    """look_results: what _look_around_for_a_node returns on each call."""
    seq = list(look_results)
    calls = {"reset": 0, "look": 0, "walk": 0, "follow": 0}

    fake_reset = types.ModuleType("reset_env")
    fake_reset.reset_environment = lambda log=None: calls.__setitem__(
        "reset", calls["reset"] + 1)
    saved = sys.modules.get("reset_env")
    sys.modules["reset_env"] = fake_reset

    real = (gw.locate, gw._look_around_for_a_node, gw.follow, gw.time.sleep)
    old_flag, old_local = gw.RELOCALISE_BY_TURNING, gw.LOCAL_RECOVERY_FIRST
    gw.RELOCALISE_BY_TURNING = turning
    gw.LOCAL_RECOVERY_FIRST = False
    try:
        gw.locate = lambda m, capture=None, log=None: (None, "unrecognised")

        # mirrors the real signature: graph_walk threads the caller's heading seam
        # into the sweep, the way `fol` below already takes it
        def look(m, capture, read_heading=None, log=None):
            calls["look"] += 1
            return seq.pop(0) if seq else None
        gw._look_around_for_a_node = look

        def fol(m, a, b, capture=None, read_heading=None, log=None, shots=None):
            calls["follow"] += 1
        gw.follow = fol
        gw.time.sleep = lambda *a: None
        out = gw.go_to_node_verified(None, "bar_pool_room",
                                     capture=lambda: object(),
                                     log=lambda *a: None, attempts=1)
    finally:
        gw.locate, gw._look_around_for_a_node, gw.follow, gw.time.sleep = real
        gw.RELOCALISE_BY_TURNING, gw.LOCAL_RECOVERY_FIRST = old_flag, old_local
        if saved is not None:
            sys.modules["reset_env"] = saved
        else:
            sys.modules.pop("reset_env", None)
    return out, calls


# Turning finds the node itself -> no reset at all.
ok, c = run([("bar_pool_room", "found")])
check("turning to the node avoids the reset entirely", ok and c["reset"] == 0)
check("and it did look", c["look"] == 1)

# Turning finds a DIFFERENT known node -> route from there, still no reset.
ok, c = run([("portrait_room", "found")])
check("recognising somewhere else routes from there instead of resetting",
      c["reset"] == 0 and c["follow"] >= 1)

# Turning finds nothing -> genuinely lost, reset still happens.
ok, c = run([None])
check("a genuinely lost character still resets", c["reset"] >= 1)
check("and it tried looking first", c["look"] == 1)

# Flag off -> never looks.
ok, c = run([("bar_pool_room", "found")], turning=False)
check("with the flag off it never looks around", c["look"] == 0)
check("and goes straight to the reset", c["reset"] >= 1)

# locate() MUST remain a pure query — no turning parameter, no side effect.
import inspect
sig = inspect.signature(gw.locate)
check("locate() takes no look-around flag (it is a query)",
      "_looking" not in sig.parameters)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
