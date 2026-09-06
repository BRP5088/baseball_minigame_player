"""A caller that has just reset must not pay ~24s to rediscover the spawn.

WHAT THIS GUARDS
----------------
reset_environment() lands the character on SPAWN = office_corridor, and
office_corridor is in graph_walk.UNSEEDED — it has no appearance reference BY
DESIGN (CLAUDE.md 7: seeding office_door from a dark frame instantly created
false positives). So locate() can never name it. go_to_node_verified therefore
read `start is None`, called it lost, spent a 13.9s relocalise sweep with
nothing to find, and RESET A SECOND TIME to reach the spot it was standing on.

Measured 2026-09-05 over three complete archived runs — overnight/streak2.log
10 of 10 trials, failframes.log 8 of 8, newleg.log 8 of 8, **26 of 26** — every
trial opens with "not at portrait_room and cannot say where this is —
reloading to a known start", immediately after the harness's own reset. From
overnight/profile.json's own numbers that is 13.9s of sweep (its `turn_to 6
calls 11.41s` IS the sweep: 5 RELOCALISE_BEARINGS plus the turn back) plus a
8.96s reset plus 1.2s of sleep.

WHY THE TEST HAS TO CHECK THE SWEEP AND THE RESET, NOT THE OUTCOME
------------------------------------------------------------------
Both the old path and the new one end with follow() walking from
office_corridor. The runs are indistinguishable by result — the difference is
only the ~24s spent getting there, and the whole failure mode this project
keeps hitting is "the code did nothing and doing nothing looked exactly like
working". So the assertions are on the CALLS: the sweep and the reset must not
happen, and follow() must be handed the hint.

Offline. No game, no screen, no input.
"""

import os as _os
import sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
_os.environ["BASEBALL_TEST_RUN"] = "1"

import graph_walk as gw          # noqa: E402
import reset_env                 # noqa: E402

fails = []


def check(msg, ok):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


class Map:
    """Enough of a WorldMap to route, with every leg reachable."""

    landmarks = {"office_corridor": (0, 0), "portrait_room": (1, 0),
                 "bar_pool_room": (2, 0), "bar_jukebox": (3, 0)}
    confusable = []

    def __init__(self, reason="ok"):
        self._reason = reason

    def route_reason(self, a, b):
        return "same" if a == b else self._reason

    def route(self, a, b):
        return [a, b]

    def route_cost(self, path):
        return 1.0

    def steps_for(self, a, b):
        return [{"bearing": 0.0, "dur": 0.05, "speed": 0.2}]


def _run(node, hint, attempts=1, reason="ok", arrives=False, located=None):
    """Drive go_to_node_verified with everything expensive stubbed out.

    `located` is what locate() answers on its FIRST call. None (the default) is
    the spawn situation — the reference set deliberately has nothing to match.
    A node name instead is the case where the localiser DID answer, and the
    hint must then lose to it.
    """
    seen = {"sweep": 0, "reset": 0, "starts": []}

    real = (gw.locate, gw._look_around_for_a_node, gw.follow,
            reset_env.reset_environment)
    try:
        def _locate(m, img=None, capture=None, log=print):
            if not seen["starts"]:
                return ((located, f"{located} 500.000/3.000") if located
                        else (None, "unrecognised (78.000/1.100)"))
            return ((node, "arrived") if arrives
                    else (None, "unrecognised (78.000/1.100)"))

        gw.locate = _locate

        def sweep(m, capture, log=print):
            seen["sweep"] += 1
            return None

        def reset(log=print, progress_file=None):
            seen["reset"] += 1
            return 87.0

        def follow(m, start, goal=gw.GOAL, capture=None, read_heading=None,
                   log=print, shots=None):
            seen["starts"].append(start)
            return {"arrived": False, "reached": start, "reason": "ok",
                    "legs": [], "unverified": []}

        gw._look_around_for_a_node = sweep
        gw.follow = follow
        reset_env.reset_environment = reset
        gw.go_to_node_verified(Map(reason), node, capture=lambda: object(),
                               read_heading=lambda: 87.0,
                               log=lambda *a: None, attempts=attempts,
                               start_hint=hint)
    finally:
        (gw.locate, gw._look_around_for_a_node, gw.follow,
         reset_env.reset_environment) = real
    return seen


# --- 1. the hint replaces the sweep AND the second reset -------------------
with_hint = _run("portrait_room", gw.SPAWN)
check("with a start hint the relocalise sweep does not run",
      with_hint["sweep"] == 0)
check("with a start hint nothing is reloaded", with_hint["reset"] == 0)
check("and the route is walked from the hinted node",
      with_hint["starts"] == [gw.SPAWN])

# --- 2. the CONTROL: without one, both still happen ------------------------
# Without this the test would pass on a build where the sweep and the reset had
# simply been deleted, which is a different (and much worse) change.
without = _run("portrait_room", None)
check("CONTROL: with no hint the sweep still runs", without["sweep"] >= 1)
check("CONTROL: with no hint it still reloads", without["reset"] >= 1)
check("CONTROL: and then walks from the SPAWN",
      without["starts"] == [gw.SPAWN])

# --- 3. the hint is spent on the FIRST attempt only ------------------------
# By the second attempt the character has walked a leg, so "the caller reset
# onto SPAWN" is no longer true. A hint that survived would be the stale cached
# handle from CLAUDE.md's catalogue, one leg later.
two = _run("bar_jukebox", "bar_pool_room", attempts=2)
check("attempt 1 uses the hint, attempt 2 does not",
      two["starts"] == ["bar_pool_room", gw.SPAWN])
check("so exactly one sweep and one reset happen across two attempts",
      (two["sweep"], two["reset"]) == (1, 1))

# --- 4. an unroutable hint is refused, not believed ------------------------
# The hint is the caller's claim about POSITION; whether a route exists from
# there is the map's business, and legs are one-way.
bad = _run("portrait_room", gw.SPAWN, reason="unreachable")
check("an unroutable hint is ignored and recovery runs normally",
      bad["sweep"] >= 1 and bad["reset"] >= 1)

# --- 4b. THE LOCALISER OUTRANKS THE CALLER --------------------------------
# The hint is a claim; locate() is evidence. If locate() names a node the map
# can route from, the hint must not be substituted for it — believing the
# caller over the screen is how a run walks a route from a place it is not
# standing in. This case is here because a mutant that simply dropped the
# `start is None` guard passed all 13 checks above on 2026-09-05.
seen_loc = _run("bar_jukebox", gw.SPAWN, located="bar_pool_room")
check("a hint does NOT override a locate() that named a routable node",
      seen_loc["starts"] == ["bar_pool_room"])
check("and when locate() answered, no sweep and no reload were needed",
      (seen_loc["sweep"], seen_loc["reset"]) == (0, 0))

# --- 4c. AND THE HINT IS SPENT EVEN WHEN IT WAS NOT USED -------------------
# Attempt 1 located a node and WALKED A LEG. By attempt 2 the caller's "I just
# reset onto SPAWN" is a lie one leg old, so the hint must be gone — the stale
# cached handle from CLAUDE.md 10's catalogue. This is the case the original
# consumption site (inside the `start is None` branch) could not cover.
# The hint here is deliberately NOT gw.SPAWN: after a reset the code routes
# from SPAWN anyway, so a hint equal to SPAWN makes the two outcomes identical
# and this check would be vacuous. "portrait_room" is distinguishable.
two_loc = _run("bar_jukebox", "portrait_room", attempts=2,
               located="bar_pool_room")
check("a hint not used on attempt 1 is still gone by attempt 2",
      two_loc["starts"] == ["bar_pool_room", gw.SPAWN])
check("so attempt 2 swept and reloaded like any other lost attempt",
      (two_loc["sweep"], two_loc["reset"]) == (1, 1))

# --- 5. follow_verified hands it to the FIRST node only --------------------
seen_hints = []
_real_gtnv = gw.go_to_node_verified
try:
    def spy(m, node, capture=None, read_heading=None, log=None, attempts=3,
            shots=None, start_hint=None):
        seen_hints.append(start_hint)
        return True

    gw.go_to_node_verified = spy
    gw.follow_verified(Map(), ["portrait_room", "bar_pool_room", "bar_jukebox"],
                       capture=lambda: object(), read_heading=lambda: 87.0,
                       log=lambda *a: None, start_hint=gw.SPAWN)
finally:
    gw.go_to_node_verified = _real_gtnv
check("follow_verified hints only the first node",
      seen_hints == [gw.SPAWN, None, None])

# --- 6. consecutive_arrivals sends it, and the flag turns it off -----------
def _hints_from_consecutive(flag, reset_between=True):
    got = []
    real = (gw.go_to_node_verified, gw.stream_is_live, gw.TRUST_RESET_SPAWN,
            reset_env.reset_environment)
    try:
        gw.TRUST_RESET_SPAWN = flag
        gw.stream_is_live = lambda *a, **k: True
        reset_env.reset_environment = lambda log=print, progress_file=None: 87.0

        def spy(m, node, capture=None, read_heading=None, log=None, attempts=3,
                shots=None, start_hint=None):
            got.append(start_hint)
            return True

        gw.go_to_node_verified = spy
        gw.consecutive_arrivals(Map(), ["portrait_room"], 1,
                                capture=lambda: object(),
                                read_heading=lambda: 87.0,
                                log=lambda *a: None,
                                reset_between=reset_between)
    finally:
        (gw.go_to_node_verified, gw.stream_is_live, gw.TRUST_RESET_SPAWN,
         reset_env.reset_environment) = real
    return got


check("consecutive_arrivals passes SPAWN after its own reset",
      _hints_from_consecutive(True) == [gw.SPAWN])
check("TRUST_RESET_SPAWN=False restores the old behaviour (the A/B control)",
      _hints_from_consecutive(False) == [None])
check("no hint when it did not reset — the character is wherever it was left",
      _hints_from_consecutive(True, reset_between=False) == [None])

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f in fails:
        print("  " + f)
    raise SystemExit(1)
print("all green")
