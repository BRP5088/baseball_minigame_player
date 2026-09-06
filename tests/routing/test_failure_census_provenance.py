"""A FAILURE CLASS IS ONLY EVIDENCE IF ITS FRAME CAME FROM THE LEG.

OPEN-1 exists because two runs collected failure frames that looked
authoritative and described something else:

  * eight frames captured AFTER recover_to_node read bearing 98.1-105.8 while
    the leg commanded 2.1 — the fan's signature, six of six;
  * four frames captured BEFORE the attempt identified as bar_pool_room at
    506-734 matches, i.e. photographs of the PREVIOUS node's arrival.

follow_verified now prefers the frame follow() published when the leg ended
(_LAST_LEG_END), which is the admissible one. But it still FALLS BACK to those
same two frames when no leg into the node ever completed — the reset raised,
the route was unreachable, or follow() stopped at an earlier leg on every
attempt. The fallback is logged, and a log line is not a number: every one of
those classes landed in `failures_by_kind` indistinguishably from a real one.

This file pins the split. `failures_by_kind` keeps counting everything, so no
denominator goes missing, and `failures_by_kind_leg_end` counts only the
frames that can support a claim about a leg.

MUTATION-TESTED: with `all_sources` extended anywhere but in lockstep, or the
filter comparing against a different string, the counts below stop separating.
"""
import os
import sys
import types

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import failure_kind as fk
import graph_walk as gw

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class Frame:
    """Identity is the whole point; nothing here looks at pixels."""

    def __init__(self, tag):
        self.tag = tag

    def convert(self, _m):
        return self

    def save(self, *a, **k):
        pass


ROUTE = ["portrait_room", "bar_pool_room", "bar_jukebox"]

# Stub the whole stack below follow_verified. `publish` decides whether a leg
# into the node completed — i.e. whether an admissible frame exists.
seen = []


def make_gtnv(publish):
    def fake(m, node, **kw):
        if publish:
            gw._LAST_LEG_END[node] = Frame("LEG-END")
        return False
    return fake


def fake_classify(img, node, route, live=True):
    seen.append(getattr(img, "tag", None))
    # The class is deliberately the SAME either way. If the fallback happened to
    # classify differently the split would be visible in `failures_by_kind`
    # alone, and this test would pass while measuring nothing.
    return "overshot", "stubbed"


_reset = types.ModuleType("reset_env")
_reset.reset_environment = lambda **k: None
_saved = sys.modules.get("reset_env")
sys.modules["reset_env"] = _reset

_orig = (fk.classify, gw.go_to_node_verified, gw.stream_is_live, gw.time.sleep)


def run(publish, trials=1):
    seen.clear()
    fk.classify = fake_classify
    gw.stream_is_live = lambda *a, **k: True
    gw.go_to_node_verified = make_gtnv(publish)
    gw.time.sleep = lambda *a: None
    try:
        return gw.consecutive_arrivals(
            None, ROUTE, trials, capture=lambda: Frame("FALLBACK"),
            read_heading=lambda: 0.0, log=lambda *a: None,
            reset_between=False, shots=None)
    finally:
        (fk.classify, gw.go_to_node_verified, gw.stream_is_live,
         gw.time.sleep) = _orig
        gw._LAST_LEG_END.clear()


try:
    # --- the leg's own frame: admissible ------------------------------------
    r = run(publish=True, trials=3)
    check("a leg-end frame is counted in failures_by_kind",
          r["failures_by_kind"] == {"overshot": 3})
    check("...and in the leg-end census",
          r["failures_by_kind_leg_end"] == {"overshot": 3})
    check("...and nothing is marked as a fallback",
          r["failures_from_fallback_frame"] == 0)
    check("the classifier really saw the leg's frame", set(seen) == {"LEG-END"})

    # --- no leg ever completed: the fallback frame --------------------------
    # This is the fan / pre-attempt frame OPEN-1 was opened about. It is still
    # classified (a picture is better than nothing) and still counted in the
    # total, but it must NOT enter the census a leg conclusion is drawn from.
    r = run(publish=False, trials=3)
    check("a fallback frame is still counted in failures_by_kind",
          r["failures_by_kind"] == {"overshot": 3})
    check("...but is EXCLUDED from the leg-end census",
          r["failures_by_kind_leg_end"] == {})
    check("...and its count is stated, so no denominator goes missing",
          r["failures_from_fallback_frame"] == 3)
    check("the classifier really saw the fallback frame",
          set(seen) == {"FALLBACK"})

    # --- both in one run: the mixture the split exists for -------------------
    # A real run mixes them, and the mixture is the dangerous case: 3 of 6 is a
    # census over half the failures reported as though it covered all of them.
    seen.clear()
    fk.classify = fake_classify
    gw.stream_is_live = lambda *a, **k: True
    gw.time.sleep = lambda *a: None
    flip = {"n": 0}

    def alternating(m, node, **kw):
        flip["n"] += 1
        if flip["n"] % 2:
            gw._LAST_LEG_END[node] = Frame("LEG-END")
        return False

    gw.go_to_node_verified = alternating
    try:
        r = gw.consecutive_arrivals(
            None, ROUTE, 4, capture=lambda: Frame("FALLBACK"),
            read_heading=lambda: 0.0, log=lambda *a: None,
            reset_between=False, shots=None)
    finally:
        (fk.classify, gw.go_to_node_verified, gw.stream_is_live,
         gw.time.sleep) = _orig
        gw._LAST_LEG_END.clear()

    check("a mixed run counts every failure in the total",
          sum(r["failures_by_kind"].values()) == 4)
    check("...counts only the leg-end half in the leg-end census",
          sum(r["failures_by_kind_leg_end"].values()) == 2)
    check("...and reports the other half as fallback frames",
          r["failures_from_fallback_frame"] == 2)
    check("the two censuses do not silently agree on a mixed run",
          r["failures_by_kind"] != r["failures_by_kind_leg_end"])

    # --- the provenance list runs in LOCKSTEP with the kinds -----------------
    # If it ever drifts, zip() truncates and the leg-end census quietly shrinks
    # instead of failing. Length equality is the only thing that catches that.
    check("one source is recorded per class, always",
          len(gw._LAST_FAILURE_SOURCES) == len(gw._LAST_FAILURE_KINDS))

    # --- follow() must publish the PRE-FAN frame ----------------------------
    # This is the claim OPEN-1 rests on and it was pinned only at source level
    # ("_LAST_LEG_END[b] = img" appears in the file), which cannot catch a
    # SECOND assignment added after recover_to_node — exactly the shape that
    # produced the eight post-fan frames in the first place.
    class Map2:
        def route_reason(self, a, b): return "ok"
        def route(self, a, b): return [a, b]
        def route_cost(self, p): return 1.0
        def steps_for(self, a, b): return [{"bearing": 1.0, "dur": 0.1,
                                            "speed": 0.3}]

    frames = iter([Frame("LEG-END"), Frame("POST-FAN"), Frame("POST-FAN2")])
    fan_ran = {"n": 0}

    def fan(m, node, capture=None, read_heading=None, log=print):
        # The fan MOVES the character — that is the whole problem — so anything
        # captured after it describes the fan.
        fan_ran["n"] += 1
        return True

    saved_g = (gw.stream_is_live, gw.confirm, gw.confirmable,
               gw.recover_to_node, gw.walk_link, gw.ALIGN_AT_NODES,
               gw.RECOVER_MISSED, gw.time.sleep)
    gw._LAST_LEG_END.clear()
    try:
        gw.stream_is_live = lambda *a, **k: True
        gw.walk_link = lambda *a, **k: {"a": "x", "b": "y", "steps": 1,
                                        "travelled": 0.1, "hazards": []}
        gw.confirmable = lambda m, node: True
        # Abstain the first time (which is what fires the fan), confirm after.
        seq = iter([(None, "abstained"), (True, "confirmed")])
        gw.confirm = lambda m, node, img, log=print: next(seq)
        gw.recover_to_node = fan
        gw.ALIGN_AT_NODES = False
        gw.RECOVER_MISSED = True
        gw.time.sleep = lambda *a: None
        gw.follow(Map2(), "bar_pool_room", "bar_jukebox",
                  capture=lambda: next(frames), read_heading=lambda: 0.0,
                  log=lambda *a: None)
    finally:
        (gw.stream_is_live, gw.confirm, gw.confirmable, gw.recover_to_node,
         gw.walk_link, gw.ALIGN_AT_NODES, gw.RECOVER_MISSED,
         gw.time.sleep) = saved_g

    check("the recovery fan actually ran in this scenario", fan_ran["n"] == 1)
    published = getattr(gw._LAST_LEG_END.get("bar_jukebox"), "tag", None)
    check("follow() publishes the frame taken BEFORE the fan, not after "
          f"(got {published!r})", published == "LEG-END")
    gw._LAST_LEG_END.clear()

    # --- the admissible label is a NAMED constant, not a repeated sentence ---
    src = open(os.path.join(_ROOT, "graph_walk.py"), encoding="utf-8").read()
    check("the leg-end label is defined once", src.count('LEG_END_SOURCE = ') == 1)
    check("...and the filter compares against that same constant",
          "if src == LEG_END_SOURCE" in src)
finally:
    if _saved is not None:
        sys.modules["reset_env"] = _saved
    else:
        sys.modules.pop("reset_env", None)

print()
if FAILS:
    raise SystemExit(f"{len(FAILS)} FAILED")
print("OK: the leg-end census counts only frames that came from a leg")
