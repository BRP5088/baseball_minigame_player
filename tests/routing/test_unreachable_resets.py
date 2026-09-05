"""A KNOWN but UNREACHABLE position must reset, exactly like a lost one.

Legs are one-way, so once the character is past a node there is no edge back.
When that happened locate() answered confidently, the reset was skipped because
position was "known", follow() found no route and returned without walking, and
the next attempt saw the same thing. Three attempts of doing nothing, silently.

MEASURED 2026-09-04: a re-record run reached its start node 0 of 20 times while
standing at bar_jukebox, one node PAST the bar_pool_room it wanted.
route_reason() said "unreachable" throughout.
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


class Map:
    def __init__(self, reason):
        self._r = reason

    def route_reason(self, a, b):
        return self._r


def run(here, reason):
    calls = {"reset": 0, "follow": []}
    fake = types.ModuleType("reset_env")
    fake.reset_environment = lambda log=None: calls.__setitem__("reset", calls["reset"] + 1)
    saved = sys.modules.get("reset_env")
    sys.modules["reset_env"] = fake
    real = (gw.locate, gw.follow, gw.time.sleep, gw.RELOCALISE_BY_TURNING)
    gw.RELOCALISE_BY_TURNING = False
    try:
        gw.locate = lambda m, capture=None, log=None: (here, "detail")
        gw.follow = lambda m, a, b, capture=None, read_heading=None, log=None, \
            shots=None: calls["follow"].append((a, b))
        gw.time.sleep = lambda *a: None
        gw.go_to_node_verified(Map(reason), "bar_pool_room",
                               capture=lambda: object(), log=lambda *a: None,
                               attempts=1)
    finally:
        gw.locate, gw.follow, gw.time.sleep, gw.RELOCALISE_BY_TURNING = real
        if saved is not None:
            sys.modules["reset_env"] = saved
        else:
            sys.modules.pop("reset_env", None)
    return calls


# Past the node, no way back: must reset, and must NOT try to walk a
# non-existent route.
c = run("bar_jukebox", "unreachable")
check("an unreachable known position triggers a reset", c["reset"] == 1)
check("and it walks from the SPAWN, not from where it was stuck",
      c["follow"] and c["follow"][0][0] == gw.SPAWN)

# A reachable known position must NOT reset — that would throw away progress.
c = run("portrait_room", "ok")
check("a reachable position does not reset", c["reset"] == 0)
check("and it routes from where it actually is",
      c["follow"] and c["follow"][0][0] == "portrait_room")

# Genuinely lost still resets.
c = run(None, "unknown_start")
check("a lost character still resets", c["reset"] == 1)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
