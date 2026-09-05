"""The executor must walk real legs and STOP when it cannot confirm where it is.

WHY THIS EXISTS
---------------
Nothing consumed WorldMap.route() before 2026-09-01, so this module is entirely
new and load-bearing: it is what turns a graph into movement on a live console.
Its failure modes are the expensive ones —

  - a leg with no steps "walked" successfully while standing still;
  - carrying on past a leg that did not land, so every later leg is walked from
    an unknown position (four earlier attempts ended jammed in geometry that
    way);
  - confirming arrival at the table with places.identify(), whose confidence
    there IS the prompt text — the same pixels table_prompt already reads;
  - walking backwards, because forward is left_y NEGATIVE.
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

import graph_walk
import worldmap

fails = []


def check(c, m):
    if not c:
        fails.append(m)


def a_map():
    m = worldmap.WorldMap()
    for n in ("start", "middle", "dealer_table"):
        m.mark(n)
    # 90 and 200 are far apart on purpose: these assertions are about walking
    # each recorded bearing, and near-identical bearings now MERGE into one
    # push (see the merge_steps block).
    m.connect("start", "middle",
              [{"bearing": 90.0, "dur": 1.0, "speed": 0.25},
               {"bearing": 200.0, "dur": 0.5, "speed": 0.30}])
    m.connect("middle", "dealer_table", [{"bearing": 180.0, "dur": 2.0, "speed": 0.2}])
    return m


class Rig:
    """Records what the executor asked the stick and the compass to do."""

    def __init__(self):
        self.turns = []
        self.walks = []
        self.faced = []
        self.hazard_on = None

    def turn_to(self, target, read_heading, capture, log=print, **kw):
        self.turns.append(target)
        return target, []

    def walk_leg(self, lx, ly, seconds, capture, read_heading, label="", log=print,
                 step_sec=None):
        self.walks.append({"lx": lx, "ly": ly, "seconds": seconds, "label": label,
                           "step_sec": step_sec})
        if self.hazard_on and self.hazard_on in label:
            h = types.SimpleNamespace(kind="STUCK", t=0.1, heading=90.0, note="wedged")
            return 0.1, 0.2, [h]
        return seconds, 40.0, []


def install(rig):
    sys.modules["slow_traverse"] = types.SimpleNamespace(
        turn_to=rig.turn_to, walk_leg=rig.walk_leg)
    # face_the_table() sweeps the camera looking for the prompt, so it needs a
    # compass and a turn primitive as well. Recording the sweep lets the tests
    # below assert it actually happened.
    rig.faced = []
    sys.modules["compass"] = types.SimpleNamespace(
        read_bearing=lambda img: 90.0, fast_capture=lambda: object())
    rig.forwards = 0

    def _fwd(sp, sec, strafe=0.0):
        rig.forwards += 1

    sys.modules["walk_steps"] = types.SimpleNamespace(
        turn_to=lambda t, log=print, **kw: rig.faced.append(t),
        read_heading=lambda: 90.0, walk_forward=_fwd)


# --- a leg with no steps must RAISE, not report success -------------------
m = a_map()
m.mark("orphan_dest")
m.connect("start", "orphan_dest", 4.0)        # priced, but no steps
rig = Rig(); install(rig)
raised = False
try:
    graph_walk.walk_link(m, "start", "orphan_dest", lambda: object(), lambda: 90.0,
                         log=lambda *a: None)
except ValueError:
    raised = True
check(raised,
      "walk_link accepted a leg with no steps. It would report a completed "
      "route while the character never moved")
check(not rig.walks, "it sent stick input for a leg it could not walk")

# --- a normal leg: turns to each bearing, walks FORWARD --------------------
rig = Rig(); install(rig)
leg = graph_walk.walk_link(m, "start", "middle", lambda: object(), lambda: 90.0,
                           log=lambda *a: None)
check(rig.turns == [90.0, 200.0], f"turned to {rig.turns}, expected both bearings")
check(len(rig.walks) == 2, f"made {len(rig.walks)} walk calls, expected 2")
check(all(w["ly"] < 0 for w in rig.walks),
      f"left_y came out {[w['ly'] for w in rig.walks]}; forward is NEGATIVE "
      "(walk_steps.walk_forward), so a positive value walks the route backwards")
check(all(w["lx"] == 0.0 for w in rig.walks),
      "the executor strafed; recorded legs are walked straight")
# The MAGNITUDE, not just the sign. Only `ly < 0` was asserted until
# 2026-09-03, so mutation-testing `s.get("speed", 0.25)` to
# `s.get("speed", 0.25) * 0.1` — every leg walked at a tenth of its recorded
# speed, i.e. a tenth of its distance — left the whole file green.
check([round(-w["ly"], 6) for w in rig.walks] == [0.25, 0.30],
      f"pushed at {[-w['ly'] for w in rig.walks]} against the recorded speeds "
      f"[0.25, 0.30] from the map above")
check([w["seconds"] for w in rig.walks] == [1.0, 0.5],
      f"durations {[w['seconds'] for w in rig.walks]} do not match the recording")
check(abs(leg["travelled"] - 1.5) < 1e-6, f"travelled {leg['travelled']}")
# Each recorded step must be ONE continuous push, not chunked. Replaying a
# 0.79s step as four 0.25s pushes with a stop between each makes the character
# re-accelerate every time and walk the route short — measured 2026-09-01, it
# ended two rooms adrift from the destination.
check([w["step_sec"] for w in rig.walks] == [w["seconds"] for w in rig.walks],
      f"step_sec came out {[w['step_sec'] for w in rig.walks]} against durations "
      f"{[w['seconds'] for w in rig.walks]} — each step must be pushed in one go")

# Merging is OFF by default: A/B tested 2026-09-02 on VERIFIED positions it
# scored 1.3 of 5 against 3.0 unmerged. merge_steps() itself is still tested
# below, because the function is correct even though enabling it is not.
check(graph_walk.MERGE_STEPS is False,
      "step merging is enabled. Measured on verified positions it walks the "
      "route SHORTER (1.3 vs 3.0 of 5), most likely by overshooting into "
      "furniture — turn it back on only with an A/B that says otherwise")

# ...and the SWITCH ITSELF, exercised with merging ON. Everything else in this
# file runs with MERGE_STEPS False, so walk_link's `if MERGE_STEPS: steps =
# merge_steps(steps)` was never entered by any test: mutation-tested
# 2026-09-03, replacing that condition with `if False` left the whole file
# green. merge_steps() is tested to death below and would have gone on being
# tested to death while nothing called it — the switch would simply be dead the
# day a better A/B turns it back on.
m_merge = worldmap.WorldMap()
for _n in ("ms", "me"):
    m_merge.mark(_n)
# Four 0.5s steps on one bearing: 2.0s total, well under MERGE_MAX_SEC, so a
# wired-up walk_link must issue exactly one 2.0s push.
m_merge.connect("ms", "me", [{"bearing": 90.0, "dur": 0.5, "speed": 0.25}
                             for _ in range(4)])
_merge_rig = Rig(); install(_merge_rig)
_was_merging = graph_walk.MERGE_STEPS
try:
    graph_walk.MERGE_STEPS = True
    graph_walk.walk_link(m_merge, "ms", "me", lambda: object(), lambda: 90.0,
                         log=lambda *a: None)
finally:
    graph_walk.MERGE_STEPS = _was_merging
check([w["seconds"] for w in _merge_rig.walks] == [2.0],
      f"with MERGE_STEPS on, four 0.5s steps came out as "
      f"{[w['seconds'] for w in _merge_rig.walks]} rather than one 2.0s push — "
      f"walk_link is not calling merge_steps at all")
check(graph_walk.MERGE_STEPS is False,
      "the wiring check above left step merging switched on for every test "
      "after it")

# --- a BLOCKED leg (no view change) stops, even with one push per step ----
# slow_traverse's own STUCK detector needs two quiet CHUNKS inside one call, and
# each step is now a SINGLE chunk, so it can never fire. Without a check at this
# level a blocked character is ground into a wall in silence — measured
# 2026-09-01: movement fell to 3.1, 3.0, 1.9 while every step reported "walked".
class WallRig(Rig):
    def walk_leg(self, lx, ly, seconds, capture, read_heading, label="", log=print,
                 step_sec=None):
        self.walks.append({"lx": lx, "ly": ly, "seconds": seconds, "label": label,
                           "step_sec": step_sec})
        return seconds, 2.0, []      # pushed, but the view barely changed


m_long = worldmap.WorldMap()
for n in ("s", "e"):
    m_long.mark(n)
# Six 0.5s pushes on one bearing. NOTE these are SHORT steps: merging is off,
# so walk_link replays all six separately and every one of them is under
# LONG_PUSH_SEC. The long-push rule is covered separately below.
m_long.connect("s", "e", [{"bearing": 0.0, "dur": 0.5, "speed": 0.25}] * 6)
rig = WallRig(); install(rig)
# The escape now runs on EVERY blockage (the wall/NPC test was removed), so this
# block needs its collaborators stubbed too. None of them make progress here —
# the point is that a wall still ends the leg.
sys.modules["input_controller"] = types.SimpleNamespace(press=lambda a, **kw: None)
sys.modules["pose"] = types.SimpleNamespace(displacement=lambda a, b: 1.0)
leg = graph_walk.walk_link(m_long, "s", "e", lambda: object(), lambda: 90.0,
                           log=lambda *a: None)
check(len(rig.walks) <= 3,
      f"pushed {len(rig.walks)} times into a wall before giving up; a long push "
      f"with no view change is a wall on its own evidence, and grinding on "
      f"wastes the leg")
check(any(h.kind == "BLOCKED" for h in leg["hazards"]),
      f"a leg that never moved reported hazards {[h.kind for h in leg['hazards']]} "
      f"— it must say BLOCKED, or the caller cannot tell it from a clean walk")

# ...and a leg that IS moving must not be cut short.
rig = Rig(); install(rig)
sys.modules["pose"] = types.SimpleNamespace(displacement=lambda a, b: 1.0)
leg = graph_walk.walk_link(m_long, "s", "e", lambda: object(), lambda: 90.0,
                           log=lambda *a: None)
check(len(rig.walks) >= 1 and not any(h.kind == "BLOCKED" for h in leg["hazards"]),
      f"a clean leg was cut short or reported BLOCKED ({len(rig.walks)} pushes)")
check(not any(h.kind == "BLOCKED" for h in leg["hazards"]),
      "a clean leg was reported BLOCKED")

# --- ONE long push that moved nothing is a wall on its own evidence -------
# It must not need a second step to confirm: `stalled += 2 if dur >=
# LONG_PUSH_SEC else 1`. Every fixture above uses 0.5s steps and merging is
# off, so that branch was never reached — mutation-tested 2026-09-03,
# flattening it to `stalled += 1` AND raising LONG_PUSH_SEC to 100.0 both left
# the whole file green. Grinding a 1.5s push into a wall a second time is 1.5s
# of a live console spent making the jam worse.
m_one = worldmap.WorldMap()
for _n in ("s1", "e1"):
    m_one.mark(_n)
m_one.connect("s1", "e1", [{"bearing": 0.0, "dur": 1.5, "speed": 0.25}
                           for _ in range(3)])
rig = WallRig(); install(rig)
sys.modules["input_controller"] = types.SimpleNamespace(press=lambda a, **kw: None)
sys.modules["pose"] = types.SimpleNamespace(displacement=lambda a, b: 1.0)
leg = graph_walk.walk_link(m_one, "s1", "e1", lambda: object(), lambda: 90.0,
                           log=lambda *a: None)
check(len(rig.walks) == 1,
      f"pushed {len(rig.walks)} times; one 1.5s push that moved nothing is "
      f"already a wall, and a second costs another 1.5s of pushing into it")
check(any(h.kind == "BLOCKED" for h in leg["hazards"]),
      f"a single long push that moved nothing reported "
      f"{[h.kind for h in leg['hazards']]} instead of BLOCKED")

# --- STUCK abandons the rest of the leg -----------------------------------
rig = Rig(); rig.hazard_on = "step 1/2"; install(rig)
leg = graph_walk.walk_link(m, "start", "middle", lambda: object(), lambda: 90.0,
                           log=lambda *a: None)
check(len(rig.walks) == 1,
      f"kept walking after STUCK ({len(rig.walks)} steps) — pushing harder into "
      "whatever is in the way is how runs wedged on doorframes")

# --- follow() stops at the first leg that does not check out --------------
class Places:
    def __init__(self, answers):
        self.answers = answers
        self.i = 0

    def identify(self, img, **kw):
        a = self.answers[min(self.i, len(self.answers) - 1)]
        self.i += 1
        return a


def run_follow(identify_answers, at_table=True):
    rig = Rig(); install(rig)
    sys.modules["places"] = Places(identify_answers)
    sys.modules["table_prompt"] = types.SimpleNamespace(
        at_table=lambda img: at_table, ink=lambda img: 0.04 if at_table else 0.01)
    return rig, graph_walk.follow(m, "start", "dealer_table",
                                  capture=lambda: object(),
                                  read_heading=lambda: 90.0,
                                  log=lambda *a: None)

rig, res = run_follow([("middle", 0.8, 0.2)])
check(res["arrived"] is True, f"clean route did not arrive: {res}")
check(res["reached"] == "dealer_table", f"reached {res['reached']!r}")

rig, res = run_follow([("somewhere_else", 0.8, 0.2)])
check(res["arrived"] is False, "a wrong first leg still reported arrival")
check(res.get("failed_leg") == ("start", "middle"),
      f"blamed {res.get('failed_leg')}, expected the first leg")
check(len(rig.walks) == 2,
      f"walked {len(rig.walks)} step(s) after the mismatch — it must stop, "
      "because every later leg would start from an unknown position")

# Abstaining is ADVISORY, not fatal — and this was measured, not assumed.
# Over every live run on 2026-09-01, 10 mid-route confirmations failed and ALL
# TEN were abstentions; identify() never once named a different room. Each
# frame I opened showed the character standing in the right place, with the
# reference set simply not covering that pose or that arrangement of NPCs.
# Stopping on "I am not sure" ended runs at node 1 of 5 with nothing wrong.
rig, res = run_follow([(None, 0.4, 0.01)])
check(res["arrived"] is True,
      "an unrecognised mid-route node stopped the run. Abstaining means the "
      "reference set has a hole, not that the character is lost — and the "
      "goal's own prompt is the authoritative check either way")
check(res.get("unverified") == ["middle"],
      f"the unconfirmed node was not reported ({res.get('unverified')!r}); a "
      f"silent 'arrived' would hide exactly which reference set needs frames")

# Seeing a DIFFERENT room is still fatal — that IS positive evidence of being
# somewhere unplanned, and every later leg would start from it.
rig, res = run_follow([("somewhere_else", 0.8, 0.2)])
check(res["arrived"] is False and res.get("reason") == "wrong_room",
      f"a positively wrong room did not stop the run: {res.get('reason')!r}")

# --- the GOAL is confirmed by the prompt, never by appearance -------------
sys.modules["places"] = Places([("dealer_table", 0.99, 0.9)])
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: False, ink=lambda img: 0.01)
verdict, detail = graph_walk.confirm(m, "dealer_table", object(), log=lambda *a: None)
check(verdict is False,
      "confirm() called the table ARRIVED on places.identify() while the prompt "
      "was absent. identify()'s confidence there IS the prompt text, so that is "
      "one detector reading the same pixels twice")
check("at_table" in detail, f"detail {detail!r} does not name the instrument used")

# --- unverifiable nodes report None, not a confident answer ---------------
m.confusable = [["office_corridor", "office_door"]]
m.mark("office_door")
for node in ("office_door", "office_corridor"):
    v, d = graph_walk.confirm(m, node, object(), log=lambda *a: None)
    check(v is None,
          f"confirm({node!r}) returned {v!r}. It has no usable appearance "
          f"reference, so a True/False here would be invented")

# --- "reached" is a routing claim, not evidence of position ---------------
# follow() treats an unrecognised node as advisory on purpose. The cost is that
# its "reached" cannot be trusted to mean "standing there": on 2026-09-02 it
# reported reaching bar_jukebox while the character was in a stairwell, and a
# scouting pass photographed the wrong room. Anything that must actually BE
# somewhere uses go_to_node_verified, which believes only locate().
_seen = {"n": 0}
rig = Rig(); install(rig)
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: False, ink=lambda img: 0.01)


def _identify_wrong_then_right(img, **kw):
    _seen["n"] += 1
    return ("middle", 0.9, 0.4) if _seen["n"] > 2 else ("start", 0.9, 0.4)


sys.modules["places"] = types.SimpleNamespace(identify=_identify_wrong_then_right)
ok = graph_walk.go_to_node_verified(m, "middle", capture=lambda: object(),
                                    read_heading=lambda: 90.0,
                                    log=lambda *a: None)
check(ok is True, "go_to_node_verified gave up while the node was reachable")

# It must NOT claim success when the localiser never agrees.
_seen["n"] = 0
sys.modules["places"] = types.SimpleNamespace(
    identify=lambda img, **kw: ("start", 0.9, 0.4))
rig = Rig(); install(rig)
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: False, ink=lambda img: 0.01)
ok = graph_walk.go_to_node_verified(m, "middle", capture=lambda: object(),
                                    read_heading=lambda: 90.0,
                                    log=lambda *a: None, attempts=2)
check(ok is False,
      "go_to_node_verified reported standing at a node the localiser never "
      "confirmed — that is exactly the stairwell mistake it exists to prevent")

# --- a FROZEN stream must stop the run, not sail through it ---------------
# Identical frames satisfy almost every check here: nothing moves so nothing
# looks blocked, nothing changes so a confirmation that passed once passes
# forever. Measured 2026-09-02: follow() reported arrived=True having walked a
# whole route into a picture that had not updated in minutes, because chiaki's
# decode queue had overflowed ("pending_overflow_evict ... overflow queue full").
class _Frame:
    def __init__(self, v): self.v = v

    def convert(self, mode):
        import numpy as np

        class _A:
            def __init__(self, v): self.v = v

            def __array__(self, dtype=None):
                return np.full((8, 8), self.v, dtype=dtype or float)

        return _A(self.v)


rig = Rig(); install(rig)
sys.modules["places"] = Places([("middle", 0.9, 0.4)])
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: True, ink=lambda img: 0.05)
res = graph_walk.follow(m, "start", "dealer_table",
                        capture=lambda: _Frame(50),      # never changes
                        read_heading=lambda: 90.0, log=lambda *a: None)
check(res["arrived"] is False and res.get("reason") == "stream_frozen",
      f"a frozen stream produced reason {res.get('reason')!r}, arrived="
      f"{res.get('arrived')}. Walking a route into a still picture must be "
      f"refused, not reported as success")
check(not rig.walks, "it sent stick input into a frozen stream")

# A live stream must NOT be mistaken for frozen, or every run is blocked.
_tick = {"n": 0}


def _moving():
    _tick["n"] += 1
    return _Frame(50 + (_tick["n"] % 7) * 5)


rig = Rig(); install(rig)
sys.modules["places"] = Places([("middle", 0.9, 0.4)])
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: True, ink=lambda img: 0.05)
res = graph_walk.follow(m, "start", "dealer_table", capture=_moving,
                        read_heading=lambda: 90.0, log=lambda *a: None)
check(res.get("reason") != "stream_frozen",
      "a live, changing stream was called frozen")

# --- a missed node gets a BOUNDED hunt, not a wander -----------------------
# The localiser is not the weak part: over 11 routed passes portrait_room was
# recognised with ~1500 keypoints every time, and rooms score 400-1500 whenever
# the character is genuinely in them. What loses runs is walking blind past a
# node missed by a metre. But every movement-based recovery tried so far made
# things WORSE by wandering, so this one is small and walks back.
_walks = {"n": 0}
_found_after = {"n": 3}


def _install_recover(found_after):
    _walks["n"] = 0
    _found_after["n"] = found_after
    rig = Rig(); install(rig)
    sys.modules["walk_steps"] = types.SimpleNamespace(
        turn_to=lambda t, log=print, **kw: rig.faced.append(t),
        read_heading=lambda: 90.0,
        walk_forward=lambda sp, sec, strafe=0.0: _walks.__setitem__("n", _walks["n"] + 1))
    sys.modules["table_prompt"] = types.SimpleNamespace(
        at_table=lambda img: False, ink=lambda img: 0.01)
    sys.modules["places"] = types.SimpleNamespace(
        identify=lambda img, **kw: (("middle", 900, 4.0)
                                    if _walks["n"] >= _found_after["n"]
                                    else (None, 40, 1.1)))
    return rig


# Already there: no walking at all.
_install_recover(0)
ok = graph_walk.recover_to_node(m, "middle", capture=lambda: object(),
                                read_heading=lambda: 90.0, log=lambda *a: None)
check(ok is True and _walks["n"] == 0,
      f"walked {_walks['n']} step(s) while already at the node")

# Found a few probes in: stops immediately.
_install_recover(3)
ok = graph_walk.recover_to_node(m, "middle", capture=lambda: object(),
                                read_heading=lambda: 90.0, log=lambda *a: None)
check(ok is True, "the recovery fan missed a node it walked onto")
# The counter includes walk-BACK steps, so allow the probe that found it plus
# the walk-back of the probe before.
check(_walks["n"] <= _found_after["n"] + 2,
      f"took {_walks['n']} steps for a node found at step {_found_after['n']} — "
      f"it must stop the moment the localiser agrees")

# Never found: bounded, and it walks BACK after each failed probe so the
# character does not end up further away than it started.
rig = _install_recover(10 ** 6)
ok = graph_walk.recover_to_node(m, "middle", capture=lambda: object(),
                                read_heading=lambda: 90.0, log=lambda *a: None)
check(ok is False, "recover_to_node claimed success without the localiser")
_max = len(graph_walk.RECOVER_FAN) * graph_walk.RECOVER_STEPS * 2
check(_walks["n"] <= _max,
      f"walked {_walks['n']} steps against a bound of {_max}; an unbounded "
      f"recovery is how earlier attempts turned a miss into a new failure")
# Every outward probe must be walked BACK, or the recovery accumulates the very
# drift it exists to fix. Parity cannot show this (7 bearings x 2 steps is
# already even), so check that the reverse bearings were actually turned to.
_rig_faced = rig.faced
_reverse_turns = sum(1 for b in _rig_faced
                     if any(abs(((b - ((90.0 + off) % 360.0) - 180.0) % 360.0)) < 1.0
                            for off in graph_walk.RECOVER_FAN))
check(_reverse_turns >= len(graph_walk.RECOVER_FAN),
      f"only {_reverse_turns} reverse turns for {len(graph_walk.RECOVER_FAN)} "
      f"probes — failed probes must be walked back, or a recovery that finds "
      f"nothing leaves the character further away than it started")

# ...and follow() must actually CALL it. A recovery nothing invokes is the
# "code did nothing and doing nothing looked like working" shape exactly.
_probe = {"walks": 0}
rig = Rig(); install(rig)
sys.modules["walk_steps"] = types.SimpleNamespace(
    turn_to=lambda t, log=print, **kw: rig.faced.append(t),
    read_heading=lambda: 90.0,
    walk_forward=lambda sp, sec, strafe=0.0: _probe.__setitem__("walks", _probe["walks"] + 1))
# at_table must be FALSE while the mid-route recovery runs, or locate() short-
# circuits to the goal and the fan can never find `middle`. It becomes true once
# enough walking has happened for the final approach.
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: _probe["walks"] >= 2, ink=lambda img: 0.05)
# Abstains until the recovery has taken a step, then agrees.
sys.modules["places"] = types.SimpleNamespace(
    identify=lambda img, **kw: (("middle", 900, 4.0) if _probe["walks"] >= 1
                                else (None, 40, 1.1)))
res = graph_walk.follow(m, "start", "dealer_table", capture=lambda: object(),
                        read_heading=lambda: 90.0, log=lambda *a: None)
check(_probe["walks"] >= 1,
      "follow() never ran the recovery on an unconfirmed node — the hunt "
      "exists precisely so the next leg does not start from an unknown spot")
check(res["arrived"] is True, f"the run did not complete: {res.get('reason')}")
check(res.get("unverified") == [],
      f"a node recovered by the fan is still listed unverified "
      f"({res.get('unverified')}) — the re-check after recovery did not happen")

# --- legs stop SHORT where the localiser can close the gap -----------------
# The recorded distance is right for the pose the human started from. The
# executor starts differently each run, so walking it in full overshoots into
# furniture — measured, arrivals 6-10 keypoints deep in a wall. Walking ~60%
# and letting recover_to_node() finish trades a guess for a measurement.
rig = Rig(); install(rig)
sys.modules["places"] = Places([("middle", 900, 4.0)])
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: True, ink=lambda img: 0.05)
graph_walk.follow(m, "start", "dealer_table", capture=lambda: object(),
                  read_heading=lambda: 90.0, log=lambda *a: None)
_mid = [w for w in rig.walks if "start->middle" in w["label"]]
_goal = [w for w in rig.walks if "->dealer_table" in w["label"]]
# SHORT_WALK is OFF by default: A/B tested 2026-09-02 it scored 2.0 of 5
# against 3.0 for full legs, and the short-leg arrivals at bar_jukebox still
# identified as PORTRAIT_ROOM — the character never left the first room.
# walk_link still honours `fraction`, so the mechanism is kept and tested.
check(graph_walk.SHORT_WALK is False,
      "SHORT_WALK is enabled; measured, it walks the route two rooms short "
      "because a localiser search cannot substitute for distance")
# `fraction` on its own rig, so what it did to the PUSHES can be read back.
# The step COUNT was the only thing asserted here until 2026-09-03, and
# mutation-testing showed that is not a test of anything: dropping the
# `* fraction` outright, and applying it to the speed instead of the duration,
# BOTH left the whole file green. SHORT_WALK is off, but the mechanism is kept
# on purpose, so it has to still work when it is turned back on.
_frac_rig = Rig(); install(_frac_rig)
_frac = graph_walk.walk_link(m, "start", "middle", lambda: object(),
                             lambda: 90.0, log=lambda *a: None, fraction=0.5)
check(_frac["steps"] == 2, "fraction changed the number of steps")
check([w["seconds"] for w in _frac_rig.walks] == [0.5, 0.25],
      f"fraction=0.5 pushed {[w['seconds'] for w in _frac_rig.walks]}s against "
      f"the recorded [1.0, 0.5] halved to [0.5, 0.25] — a fraction that does "
      f"not shorten the push walks the full distance while the log says it "
      f"stopped short")
check([w["step_sec"] for w in _frac_rig.walks]
      == [w["seconds"] for w in _frac_rig.walks],
      f"a shortened step stopped being pushed in one go: step_sec "
      f"{[w['step_sec'] for w in _frac_rig.walks]}")
check([round(-w["ly"], 6) for w in _frac_rig.walks] == [0.25, 0.30],
      f"fraction moved the stick MAGNITUDE to "
      f"{[-w['ly'] for w in _frac_rig.walks]}; it shortens the push, it does "
      f"not walk the leg slower")
check(_mid and all(w["seconds"] >= 0.5 for w in _mid),
      f"legs walked {[w['seconds'] for w in _mid]}s with SHORT_WALK off; they "
      f"must walk their full recorded distance")
check(all(abs(w["seconds"] - w["step_sec"]) < 1e-9 for w in _mid),
      "the shortened step is no longer pushed in one go")

# The GOAL leg must NOT be shortened: its arrival is confirmed by the prompt,
# and there is no localiser search to close a deliberate gap with.
# Through follow(), so the branch that chooses the fraction is the thing tested.
rig = Rig(); install(rig)
sys.modules["places"] = Places([("middle", 900, 4.0)])
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: True, ink=lambda img: 0.05)
graph_walk.follow(m, "start", "dealer_table", capture=lambda: object(),
                  read_heading=lambda: 90.0, log=lambda *a: None)
# The goal leg does not go through walk_link at ALL — it is handled by
# approach_goal(), which steps and re-checks the prompt. So it can never be
# shortened, and the check is that no shortened push was aimed at it.
_goal = [w for w in rig.walks if "->dealer_table" in w["label"]]
check(_goal == [],
      f"the goal leg was walked as a recorded push ({_goal}); it must go "
      f"through approach_goal(), which steps until the prompt appears rather "
      f"than replaying a distance")

# --- a blocked push: WALL vs NPC, and how to get past --------------------
# The gap between the pool room and the jukebox is narrow — bar stools one side,
# wall the other (user, 2026-09-02) — and NPCs walk into it. That is why the
# same leg blocked at 0.8s, 3.2s, and not at all across three identical trials.
#
# Cross JUMPS (four presses spiked 10.1-12.5 against a 4.67 idle baseline in the
# open). A jump moves nothing sideways, so it is tried first in a narrow gap.
_acts = []


def _run_blocked(moving, clears_after=None):
    """clears_after: index into _acts after which progress becomes real."""
    _acts.clear()
    rig = Rig()

    class _R(Rig):
        def walk_leg(self, lx, ly, seconds, capture, read_heading, label="",
                     log=print, step_sec=None):
            self.walks.append({"lx": lx, "ly": ly, "seconds": seconds,
                               "label": label, "step_sec": step_sec})
            return seconds, 2.0, []          # always blocked

    rig = _R(); install(rig)
    state = {"offset": 0.0, "max_off": 0.0, "min_off": 0.0, "hi_off": 0.0}

    def _fwd(sp, sec, strafe=0.0):
        if strafe:
            state["offset"] += strafe
            # Track the WORST excursion, not just the final offset: trying one
            # side then the other cancels out, so a net of zero says nothing
            # about whether the failed step was actually undone.
            state["max_off"] = max(state.get("max_off", 0.0),
                                   abs(state["offset"]))
            state["min_off"] = min(state.get("min_off", 0.0), state["offset"])
            state["hi_off"] = max(state.get("hi_off", 0.0), state["offset"])
            _acts.append(("strafe", round(strafe, 3)))
        else:
            _acts.append(("push", sec))

    sys.modules["walk_steps"] = types.SimpleNamespace(
        turn_to=lambda t, log=print, **kw: rig.faced.append(t),
        read_heading=lambda: 90.0, walk_forward=_fwd)
    sys.modules["input_controller"] = types.SimpleNamespace(
        press=lambda a, **kw: _acts.append(("press", a)))
    # Geometric progress: zero until `clears_after` actions have happened.
    sys.modules["pose"] = types.SimpleNamespace(
        displacement=lambda a, b: (60.0 if (clears_after is not None
                                            and len(_acts) > clears_after)
                                   else 1.0))
    _t = {"n": 0}

    def cap():
        _t["n"] += 1
        return _Frame(50 + (_t["n"] % 2) * 20 if moving else 50)

    sys.modules["places"] = Places([("middle", 900, 4.0)])
    sys.modules["table_prompt"] = types.SimpleNamespace(
        at_table=lambda img: True, ink=lambda img: 0.05)
    leg = graph_walk.walk_link(m_long, "s", "e", cap, lambda: 90.0,
                               log=lambda *a: None)
    return leg, state


# A MOVING scene must trigger the slip, and JUMP must be tried before strafing:
# a jump cannot wedge the character in the stools, a side-step can.
leg, state = _run_blocked(moving=True, clears_after=None)
_first_press = next((k for k, a in enumerate(_acts) if a[0] == "press"), None)
_first_strafe = next((k for k, a in enumerate(_acts) if a[0] == "strafe"), None)
# ORDER: wait, then jump, then side-step. Measured live 2026-09-02 in the narrow
# passage — jump 0.0px, jump 0.0px, slip right 0.0px, slip left 0.0px, then a
# 2.5s wait displaced 160.4px and the leg continued. When something fills a gap
# one character wide there is nowhere to go around and nothing to jump over; the
# only thing that changes is the NPC. Waiting is also the cheapest and cannot
# wedge the character, so it goes first.
_first_wait = next((k for k, a in enumerate(_acts) if a[0] == "push"), None)
check(_first_wait is not None,
      "a blocked push never tried waiting; measured, waiting is the only escape "
      "that has actually cleared that passage")
check(_first_strafe is None or (_first_press is None or _first_press < _first_strafe),
      f"strafed before jumping (press at {_first_press}, strafe at "
      f"{_first_strafe}) — the side-step risks the stools, the jump does not")

# Failed side-steps must be UNDONE.
check(abs(state["offset"]) < 1e-6,
      f"left offset by {state['offset']:.2f} after failed slips; in a narrow "
      f"passage an un-undone offset is how the earlier crabbing hit the wall")
# The decisive check. Trying right-then-left nets to zero even with NO undo at
# all, so assert the character is never more than ONE side-step off the line at
# any instant — that is what keeps it out of the stools.
check(state["max_off"] <= graph_walk.SLIP_STRAFE + 1e-9,
      f"drifted {state['max_off']:.2f} off the line, more than one side-step "
      f"({graph_walk.SLIP_STRAFE}) — offsets must never compound")
# BOTH sides must genuinely be tried FROM THE LINE. Without the undo the second
# side-step merely cancels the first: the character returns to centre and the
# left side is never actually attempted, while the net offset still reads zero.
check(state["hi_off"] >= graph_walk.SLIP_STRAFE - 1e-9,
      f"the right side was never tried (max positive offset "
      f"{state['hi_off']:.2f})")
check(state["min_off"] <= -graph_walk.SLIP_STRAFE + 1e-9,
      f"the left side was never actually tried (most negative offset "
      f"{state['min_off']:.2f}). Without undoing the right step first, the "
      f"left attempt just cancels it and the character never leaves centre")

# Progress must be judged GEOMETRICALLY. With a moving scene and no real
# displacement, the slip must NOT report success — raw brightness would, because
# an NPC crossing the frame changes the picture enormously while the character
# has not moved.
check(len([a for a in _acts if a[0] == "press"]) >= 1,
      "no jump attempt was recorded at all")

# Once a jump produces real displacement, the escape stops there: no side-step
# is attempted at all. (Presses accumulate across every blocked step in the leg,
# so count STRAFES, which only happen when jumping failed.)
leg, state = _run_blocked(moving=True, clears_after=0)
check(not [a for a in _acts if a[0] == "strafe"],
      f"side-stepped even though an earlier escape had already cleared the "
      f"blocker ({_acts}) — every unnecessary strafe risks the stools")

# The wall/NPC discriminator was REMOVED: standing perfectly still produces
# scene changes of 0.91-6.41, so a motion test cannot separate a walking mouse
# from a wall, and the true-positive side is not measurable on demand. The
# escape therefore runs on every blockage — bounded, self-undoing, and against a
# wall it costs about ten seconds and nothing else.
leg, state = _run_blocked(moving=False)
check(_acts,
      "a blockage produced no escape attempt at all; the escape is meant to run "
      "on every blockage now that the wall/NPC test has been removed")
check(abs(state["offset"]) < 1e-6,
      f"the escape left the character offset by {state['offset']:.2f} even "
      f"against a static blockage")

# --- a run that never met a blocker must not look like a successful escape -
# Pointed out by the user, 2026-09-02: the NPC escape only fires when an NPC is
# actually in the passage. A run that simply never met one is not evidence the
# escape works, and without recording that distinction the escape would look
# "proven" by runs that never exercised it.
leg, state = _run_blocked(moving=True, clears_after=0)
check(leg.get("blockers"),
      "a leg that hit a blocker recorded no blockers — a live run could then "
      "not tell 'never blocked' from 'blocked and escaped'")
check(all(b.get("cleared_by") for b in leg["blockers"]),
      f"a blocker was recorded with no note of what cleared it "
      f"({leg['blockers']})")
check(all(b["cleared_by"] in ("wait", "jump", "strafe_right", "strafe_left")
          for b in leg["blockers"]),
      f"a blocker was cleared by something unnamed "
      f"({[b['cleared_by'] for b in leg['blockers']]}) — the live logs are read "
      f"to decide which escape is worth keeping, so it must say which one")

# A leg that was never blocked records NOTHING, so the two are distinguishable.
rig = Rig(); install(rig)
sys.modules["places"] = Places([("middle", 900, 4.0)])
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: True, ink=lambda img: 0.05)
clean = graph_walk.walk_link(m_long, "s", "e", lambda: object(), lambda: 90.0,
                             log=lambda *a: None)
check(clean.get("blockers") == [],
      f"a clean leg reported blockers ({clean.get('blockers')}) — then every "
      f"run would look like the escape had been exercised")

# --- align to the RECORDED pose before walking a leg -----------------------
# places.identify() answers "which ROOM"; the rooms are large and a
# dead-reckoned leg assumes a POINT. That mismatch is what has cost every run.
# Measured 2026-09-02, lateral alignment takes ~200-360px of error down to
# 7-27px (3 of 3), and the reference used is the node's route_*.jpg — the frame
# from the recorded walk, i.e. the exact pose its outgoing leg started from.
_aligned = []
rig = Rig(); install(rig)
sys.modules["pose"] = types.SimpleNamespace(
    align_lateral=lambda ref, cap, fwd, **kw: _aligned.append(1) or 12.0,
    displacement=lambda a, b: 1.0)
sys.modules["places"] = Places([("middle", 900, 4.0)])
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: True, ink=lambda img: 0.05)
_real_ref = graph_walk._recorded_reference
graph_walk._recorded_reference = lambda node: "test_fixtures/pose/stationary_0.jpg"
try:
    graph_walk.follow(m, "start", "dealer_table", capture=lambda: object(),
                      read_heading=lambda: 90.0, log=lambda *a: None)
finally:
    graph_walk._recorded_reference = _real_ref
check(_aligned,
      "no pose alignment happened at a verified node — the next leg would then "
      "start from wherever in the room the character happened to stop, which "
      "is the mismatch that has cost every run")

# It must NOT align at the goal: arrival there is the prompt, and there is no
# outgoing leg to line up for.
_aligned.clear()
rig = Rig(); install(rig)
sys.modules["pose"] = types.SimpleNamespace(
    align_lateral=lambda ref, cap, fwd, **kw: _aligned.append("goal") or 12.0,
    displacement=lambda a, b: 1.0)
sys.modules["places"] = Places([("dealer_table", 900, 4.0)])
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: True, ink=lambda img: 0.05)
graph_walk._recorded_reference = lambda node: "test_fixtures/pose/stationary_0.jpg"
try:
    graph_walk.follow(m, "middle", "dealer_table", capture=lambda: object(),
                      read_heading=lambda: 90.0, log=lambda *a: None)
finally:
    graph_walk._recorded_reference = _real_ref
check(not _aligned,
      "aligned at the GOAL; there is no outgoing leg to line up for, and the "
      "arrival test there is the prompt")

# A node with no recorded reference must not blow up.
graph_walk._recorded_reference = lambda node: None
try:
    got = graph_walk.align_at_node("nowhere", capture=lambda: object(),
                                   log=lambda *a: None)
finally:
    graph_walk._recorded_reference = _real_ref
check(got is None, f"align_at_node returned {got!r} for a node with no reference")

# --- an impossible route says WHY ----------------------------------------
rig = Rig(); install(rig)
res = graph_walk.follow(m, "nowhere", "dealer_table", capture=lambda: object(),
                        read_heading=lambda: 90.0, log=lambda *a: None)
check(res["arrived"] is False and res["reason"] == "unknown_start",
      f"an unknown start reported {res.get('reason')!r}")
check(not rig.walks, "it walked despite having no route")

# --- consecutive same-bearing steps become ONE push -----------------------
# The recording is a human's stick samples, so a straight 5.13s walk arrives as
# seven steps that merely share a bearing. Replaying them as seven pushes means
# seven accelerations from standstill, and what each one loses is the drift that
# puts the character a metre out by the end. Measured 2026-09-01: the route was
# 40 accelerate/decelerate cycles over 25.5s of walking; merging makes it 15.
_m = graph_walk.merge_steps(
    [{"bearing": 270.0, "dur": 0.8, "speed": 0.2}] * 5)
check(len(_m) == 1, f"five identical steps merged into {len(_m)} pushes, expected 1")
check(abs(_m[0]["dur"] - 4.0) < 1e-6,
      f"merged duration {_m[0]['dur']}, expected the sum 4.0 — merging must "
      f"preserve how far the leg walks, only how many times it starts")

# A real direction change must NOT be merged away.
_m = graph_walk.merge_steps([{"bearing": 270.0, "dur": 0.5, "speed": 0.2},
                             {"bearing": 180.0, "dur": 0.5, "speed": 0.2}])
check(len(_m) == 2, f"a 90-degree turn was merged into {len(_m)} push(es)")

# No push may approach chiaki's input watchdog.
#
# THE BOUND IS THE CONSOLE'S, NOT THIS FILE'S. Until 2026-09-03 this asserted
# `x["dur"] <= graph_walk.MERGE_MAX_SEC`, which rises with the very constant it
# guards: mutation-tested, MERGE_MAX_SEC = 20.0 merged the ten steps into one
# 9.0s push — nearly twice the watchdog — and the whole file stayed green. So
# read the real number out of the patch that defines it, and check both the
# constant and the merged pushes against THAT.
_inject_c = os.path.join(_ROOT, "chiaki-patch", "injectinput.cpp")
_watchdog_m = __import__("re").search(r"INJECT_TIMEOUT_MS\s*=\s*(\d+)",
                                      open(_inject_c).read())
check(_watchdog_m is not None,
      f"no INJECT_TIMEOUT_MS in {_inject_c}. Without it this check has no "
      f"bound of its own and would pass on any push length at all")
_WATCHDOG_SEC = int(_watchdog_m.group(1)) / 1000.0 if _watchdog_m else 0.0
check(abs(_WATCHDOG_SEC - 5.0) < 1e-9,
      f"chiaki now releases injected input after {_WATCHDOG_SEC}s, not the 5s "
      f"every comment here assumes — re-derive MERGE_MAX_SEC before trusting "
      f"anything below")
check(graph_walk.MERGE_MAX_SEC < _WATCHDOG_SEC,
      f"MERGE_MAX_SEC is {graph_walk.MERGE_MAX_SEC}s against a "
      f"{_WATCHDOG_SEC}s watchdog; a push that long is released mid-stride and "
      f"the rest of the leg is walked with the stick centred")
_m = graph_walk.merge_steps([{"bearing": 90.0, "dur": 0.9, "speed": 0.2}] * 10)
check(all(x["dur"] < _WATCHDOG_SEC for x in _m),
      f"a merged push ran {max(x['dur'] for x in _m):.2f}s against chiaki's "
      f"{_WATCHDOG_SEC}s watchdog, after which injected input is released and "
      f"the character silently stops walking")
check(abs(sum(x["dur"] for x in _m) - 9.0) < 1e-6,
      "capping the push length changed the total distance walked")

# The 0/360 seam: 359 and 1 are 2 degrees apart, not 358.
_m = graph_walk.merge_steps([{"bearing": 359.0, "dur": 0.5, "speed": 0.2},
                             {"bearing": 1.0, "dur": 0.5, "speed": 0.2}])
check(len(_m) == 1, "steps either side of north were not recognised as the same "
                    "bearing")
check(_m[0]["bearing"] > 355 or _m[0]["bearing"] < 5,
      f"merged bearing came out {_m[0]['bearing']:.1f}; averaging 359 and 1 as "
      f"plain numbers gives 180 and walks the leg backwards")

# The merged push carries the FASTEST of the steps it replaces. Every other
# merge case in this file uses one speed throughout, so `max(...)` was
# mutation-tested to `min(...)` on 2026-09-03 and the file stayed green — and a
# combined push at the slower stick covers less ground than the two it replaced.
_m = graph_walk.merge_steps([{"bearing": 90.0, "dur": 0.5, "speed": 0.18},
                             {"bearing": 92.0, "dur": 0.5, "speed": 0.30}])
check(len(_m) == 1 and _m[0]["speed"] == 0.30,
      f"merged speed came out {_m[0].get('speed') if _m else None!r} for steps "
      f"recorded at 0.18 and 0.30")

# --- the DURATION WEIGHTING is real, not decoration -----------------------
# Every merge assertion above uses steps of EQUAL duration, so until 2026-09-03
# the weights could be deleted outright and nothing noticed. Mutation-tested:
# rewriting `* prev["dur"]` and `* s["dur"]` to `* 1.0` left the WHOLE FILE
# green (measured, full run); dropping the weights altogether and swapping the
# two over left every merge_steps assertion in the suite green (measured
# against that block, which grep says is the only merge_steps coverage there
# is).
# A 3.0s push and a 0.5s nudge do not contribute equally to where the character
# ends up. Ignoring that aims the combined push 1.43 degrees off the heading it
# actually walked in the case below (102.0000 against 100.5711).
#
# 100.0 for 3.0s then 104.0 for 0.5s. Expected values computed OUTSIDE the
# project (unit vectors and math.atan2 by hand, no graph_walk import):
#   weighted 100.5711   unweighted 102.0000   weights-swapped 103.4289
# Total 3.5s deliberately stays clear of MERGE_MAX_SEC, so a failure here can
# only mean the averaging, never the cap.
_m = graph_walk.merge_steps([{"bearing": 100.0, "dur": 3.0, "speed": 0.2},
                             {"bearing": 104.0, "dur": 0.5, "speed": 0.2}])
check(len(_m) == 1,
      f"a 4-degree drift split into {len(_m)} pushes — this case is here to "
      f"test the WEIGHTING, so it has to merge before it can measure anything")
check(abs(_m[0]["bearing"] - 100.5711) < 0.05,
      f"merged bearing {_m[0]['bearing']:.4f}, expected 100.5711. 102.0000 "
      f"means the durations are not weighting anything and a 0.5s nudge "
      f"counts as much as a 3.0s push; 103.4289 means each weight is applied "
      f"to the wrong step")
check(abs(_m[0]["dur"] - 3.5) < 1e-9,
      f"the weighted merge changed the total duration to {_m[0]['dur']}, "
      f"expected the sum 3.5")

# The running weight must ACCUMULATE. merge_steps folds one step at a time, so
# the push being built has to carry ALL the duration merged into it so far. If
# it reverted to the last step's own dur, a long straight run would be dragged
# around by whatever short step happened to end it.
#
# 358.0 for 1.0s, 358.0 for 1.0s, then 4.0 for 0.5s — the run also straddles
# north, so this covers the seam and the weighting in the same case. Computed
# outside the project as above:
#   correct 359.1989   weight not accumulated 359.9992   weights dropped 1.0000
_m = graph_walk.merge_steps([{"bearing": 358.0, "dur": 1.0, "speed": 0.2},
                             {"bearing": 358.0, "dur": 1.0, "speed": 0.2},
                             {"bearing": 4.0, "dur": 0.5, "speed": 0.2}])
check(len(_m) == 1,
      f"a 6-degree drift across north split into {len(_m)} pushes")
check(abs(((_m[0]["bearing"] - 359.1989 + 180.0) % 360.0) - 180.0) < 0.05,
      f"merged bearing {_m[0]['bearing']:.4f}, expected 359.1989. 359.9992 "
      f"means the merged push stopped carrying the 2.0s already folded into "
      f"it; 1.0000 means the weights are gone entirely")
check(abs(_m[0]["dur"] - 2.5) < 1e-9,
      f"three merged steps totalled {_m[0]['dur']}, expected 2.5")

# The seam again, but PINNED. The 355/5 window above is 10 degrees wide, so a
# merge that simply kept the first step's bearing (359.0) and ignored the
# second passes it. The circular mean of 359 and 1 at equal weight is 0.0 and
# nothing else.
_b = graph_walk.merge_steps([{"bearing": 359.0, "dur": 0.5, "speed": 0.2},
                             {"bearing": 1.0, "dur": 0.5, "speed": 0.2}])[0]["bearing"]
check(min(_b, 360.0 - _b) < 1e-6,
      f"merged bearing {_b!r}; 359 and 1 at equal weight average to exactly "
      f"0.0, so a near miss means the seam is being crossed by luck")

# --- degenerate inputs ----------------------------------------------------
# One step is not an average of anything. Its bearing must survive verbatim.
_m = graph_walk.merge_steps([{"bearing": 217.3, "dur": 0.7, "speed": 0.24}])
check(len(_m) == 1 and _m[0]["bearing"] == 217.3,
      f"a single step came back as {_m}; with nothing to average against, "
      f"217.3 must pass through untouched")
check(graph_walk.merge_steps([]) == [], "an empty step list did not stay empty")

# ...and the caller's own dicts must not be edited. walk_link() hands
# WorldMap.steps_for() straight to merge_steps, and steps_for returns the map's
# OWN list rather than a copy — so merging in place would rewrite the recorded
# leg in memory, and the second lap of a route would walk a merged-twice
# bearing nobody ever recorded.
_orig = [{"bearing": 90.0, "dur": 0.8, "speed": 0.2},
         {"bearing": 94.0, "dur": 0.8, "speed": 0.2}]
graph_walk.merge_steps(_orig)
check([s["bearing"] for s in _orig] == [90.0, 94.0]
      and [s["dur"] for s in _orig] == [0.8, 0.8],
      f"merge_steps edited its input: {_orig}. steps_for() hands out the map's "
      f"own step dicts, so this corrupts world_map.json's leg in memory")

# Antipodal bearings have NO circular mean: the two unit vectors cancel and
# atan2 returns whatever the residue's sign bits say. Nothing in the averaging
# guards against that — the TOLERANCE does, by never letting them meet. This
# asserts the guard, not the arithmetic.
_m = graph_walk.merge_steps([{"bearing": 0.0, "dur": 0.5, "speed": 0.2},
                             {"bearing": 180.0, "dur": 0.5, "speed": 0.2}])
check(len(_m) == 2,
      f"0 and 180 merged into {len(_m)} push(es). Opposite bearings have no "
      f"mean at all — measured with tol=200 this returns 90.0, a heading "
      f"neither step ever pointed at — so the merge tolerance is the only "
      f"thing stopping merge_steps inventing one")

# --- the LAST leg is stepped and checked, not pushed blind ----------------
# Measured 2026-09-01: 11 of 12 end-to-end failures were this one 4.2s leg while
# the four before it landed every time. The recorded distance is right for the
# spot the HUMAN started from; the executor arrives a little differently each
# run, so a single fixed push ends a metre out.
_steps = [{"bearing": 90.0, "dur": 1.0, "speed": 0.22},
          {"bearing": 95.0, "dur": 1.0, "speed": 0.22}]
_pushes = {"n": 0}
_appear_after = {"n": 3}


def _install_approach(appear_after):
    _pushes["n"] = 0
    # Record the ARGUMENTS, not just the count. Counting was all this did until
    # 2026-09-03, and mutation-testing showed how little that covers: aiming at
    # steps[0] instead of the last recorded bearing, dropping the speed to
    # 0.01, and shortening every push to 0.05s ALL left the whole file green,
    # because the number of pushes is identical in each case.
    _pushes["args"] = []
    _appear_after["n"] = appear_after
    rig = Rig(); install(rig)

    def _approach_push(sp, sec, strafe=0.0):
        _pushes["n"] += 1
        _pushes["args"].append((round(sp, 6), round(sec, 6)))

    sys.modules["walk_steps"] = types.SimpleNamespace(
        turn_to=lambda t, log=print, **kw: rig.faced.append(t),
        read_heading=lambda: 90.0,
        walk_forward=_approach_push)
    sys.modules["table_prompt"] = types.SimpleNamespace(
        at_table=lambda img: _pushes["n"] >= _appear_after["n"],
        ink=lambda img: 0.01)
    return rig


rig = _install_approach(3)
ok = graph_walk.approach_goal(_steps, capture=lambda: object(),
                              read_heading=lambda: 90.0, log=lambda *a: None)
check(ok is True, "approach_goal never found a prompt that appeared 3 steps in")
check(_pushes["n"] == 3,
      f"took {_pushes['n']} steps for a prompt that appeared at 3 — it must "
      f"stop the moment the prompt is up, not finish a recorded distance")
# Each push is the recorded SPEED for exactly the APPROACH_STEP_SEC that is
# added to the budget. Asserting sec against the constant is not circular here:
# it is the walked distance and the counted distance agreeing, and a hard-coded
# 0.05s push walked an eighth of what the budget was charged for.
check(_pushes["args"] == [(0.22, round(graph_walk.APPROACH_STEP_SEC, 6))] * 3,
      f"approach pushed {_pushes['args']}; each step must use the recorded "
      f"speed 0.22 and last exactly the step length charged to the budget")
# ...and aimed at the LAST recorded bearing. The leg above turns 90 then 95,
# and approach_goal replays only the final heading — aiming at 90 walks the
# last few feet a step to the side of the table.
check(rig.faced == [95.0, 95.0, 95.0],
      f"approach aimed at {rig.faced}, expected the final recorded bearing "
      f"95.0 on every step")

# A prompt that never appears must cost a bounded number of steps.
_install_approach(10 ** 6)
ok = graph_walk.approach_goal(_steps, capture=lambda: object(),
                              read_heading=lambda: 90.0, log=lambda *a: None)
check(ok is False, "approach_goal claimed success with no prompt ever visible")
_budget_steps = (sum(s["dur"] for s in _steps) * graph_walk.APPROACH_OVERSHOOT
                 / graph_walk.APPROACH_STEP_SEC)
check(_pushes["n"] <= _budget_steps + 1,
      f"walked {_pushes['n']} steps against a budget of about "
      f"{_budget_steps:.0f}; a leg aimed at a wall must cost seconds, not grind")
# _budget_steps is computed FROM APPROACH_OVERSHOOT and APPROACH_STEP_SEC, so
# it rises with them and the check above can never fail on a change to either.
# This is the flat ceiling: whatever those two are tuned to, a 2.0s recorded
# leg aimed at a wall must not turn into minutes of pushing. 25 pushes is
# roughly 17s of console time at the settings in place today; it is a policy
# limit, not a measurement.
check(_pushes["n"] <= 25,
      f"walked {_pushes['n']} pushes for a 2.0s recorded leg that never found "
      f"the prompt. Whatever APPROACH_OVERSHOOT is set to, a failed approach "
      f"has to cost seconds")

# ...and it must not walk at all if the prompt is already up.
_install_approach(0)
ok = graph_walk.approach_goal(_steps, capture=lambda: object(),
                              read_heading=lambda: 90.0, log=lambda *a: None)
check(ok is True and _pushes["n"] == 0,
      f"walked {_pushes['n']} step(s) while already at the table")

# --- a failed approach must NOT move the character -----------------------
# This block previously asserted the OPPOSITE — that reach_table should crab
# around whatever is in the way. Both movement-based recoveries were then built
# and MEASURED, and both made things worse:
#
#   crabbing        walked the character off the spot into a wall, ending with
#                   no table in view at all (prompt ink 0.0)
#   keypoint homing wandered: over six rounds the "strongest" heading jumped
#                   322 -> 350 -> 17 -> 319 -> 354 -> 22 while ink FELL from
#                   0.0224 to 0.0093, because the table scores 109-129 matches
#                   at that distance and pure negatives already reach 114
#
# Standing still preserves the position the leg earned, which the aim sweep can
# still work from; moving on a signal that does not separate throws it away.
_moved = {"n": 0}
rig = Rig(); install(rig)
sys.modules["walk_steps"] = types.SimpleNamespace(
    turn_to=lambda t, log=print, **kw: rig.faced.append(t),
    read_heading=lambda: 90.0,
    walk_forward=lambda sp, sec, strafe=0.0: _moved.__setitem__("n", _moved["n"] + 1))
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: False, ink=lambda img: 0.01)
ok = graph_walk.reach_table(capture=lambda: object(), read_heading=lambda: 90.0,
                            log=lambda *a: None)
check(ok is False,
      "reach_table claimed success with the prompt never visible")
check(_moved["n"] == 0,
      f"reach_table took {_moved['n']} step(s) after the aim sweep failed. Both "
      f"movement recoveries were measured and both LOST the position the leg "
      f"earned — do not re-enable one without a signal that separates")

# ...and when the prompt IS on the arc, it still succeeds by aiming alone.
_moved["n"] = 0
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: True, ink=lambda img: 0.05)
ok = graph_walk.reach_table(capture=lambda: object(), read_heading=lambda: 90.0,
                            log=lambda *a: None)
check(ok is True, "reach_table failed with the prompt plainly visible")

# --- arriving at the table means AIMING, not just standing there ----------
# Measured 2026-09-01: after the final leg the character stood correctly at the
# table but faced ~76-90, where the prompt is absent (ink 0.019 vs a 0.024
# threshold). The SAME position at bearing 60 read 0.0395 with the prompt up,
# and walking closer barely moved it (0.0187 -> 0.0216 over eight pushes)
# because it was already against the table. Without a sweep the last leg fails
# for want of a few degrees.
_sweep_state = {"n": 0}


def _prompt_after_turning(img):
    # Absent at the heading the leg leaves the camera on; present a few turns
    # into the sweep.
    return _sweep_state["n"] > 2


rig = Rig(); install(rig)
sys.modules["places"] = Places([("middle", 0.8, 0.2)])


def _ink(img):
    _sweep_state["n"] += 1
    return 0.04 if _sweep_state["n"] > 2 else 0.019


sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=_prompt_after_turning, ink=_ink)
res = graph_walk.follow(m, "start", "dealer_table", capture=lambda: object(),
                        read_heading=lambda: 90.0, log=lambda *a: None)
check(res["arrived"] is True,
      f"the table was reached but not FACED, and the leg was called a failure: "
      f"{res.get('reason')}. The prompt shows over a narrow arc, so arrival "
      f"has to sweep for it")
check(rig.faced,
      "no camera sweep happened at the table; the executor only ever aimed "
      "where the recorded leg left it")
check(len(rig.faced) < len(graph_walk.FACE_SWEEP),
      f"the sweep turned {len(rig.faced)} times through a "
      f"{len(graph_walk.FACE_SWEEP)}-heading arc even though the prompt "
      f"appeared partway. It must stop when it finds it — every extra turn is "
      f"a second of a live console spent aiming away from a table it had "
      f"already found")

# ...and a sweep must not run at ordinary nodes, only at the table.
rig = Rig(); install(rig)
sys.modules["places"] = Places([("middle", 0.8, 0.2)])
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: True, ink=lambda img: 0.04)
graph_walk.walk_link(m, "start", "middle", lambda: object(), lambda: 90.0,
                     log=lambda *a: None)
check(not rig.faced,
      "the executor swept the camera at an ordinary node; that search exists "
      "for the dealer prompt and costs a turn each time")

# =========================================================================
# "From anywhere": locate(), and the reset fallback that makes it true.
# =========================================================================
m2 = a_map()
m2.confusable = [["office_corridor", "office_door"]]


def with_world(identify_answer, at_table=False):
    sys.modules["places"] = types.SimpleNamespace(
        identify=lambda img, **kw: identify_answer)
    sys.modules["table_prompt"] = types.SimpleNamespace(
        at_table=lambda img: at_table, ink=lambda img: 0.04 if at_table else 0.01)


# Standing at the table is recognised by the PROMPT and short-circuits.
with_world(("middle", 0.9, 0.4), at_table=True)
node, detail = graph_walk.locate(m2, capture=lambda: object(), log=lambda *a: None)
check(node == "dealer_table",
      f"locate() said {node!r} while the dealer prompt was on screen; being "
      f"already at the destination must not be mistaken for somewhere else")

# A recognised node that IS in the graph.
with_world(("middle", 0.80, 0.25))
node, _ = graph_walk.locate(m2, capture=lambda: object(), log=lambda *a: None)
check(node == "middle", f"locate() said {node!r}, expected 'middle'")

# A labelled place that is NOT a graph node cannot be planned from.
with_world(("some_room_not_in_the_graph", 0.90, 0.40))
node, detail = graph_walk.locate(m2, capture=lambda: object(), log=lambda *a: None)
check(node is None,
      f"locate() returned {node!r}, a place the graph has no node for. Routing "
      f"cannot start there, and answering it invites a confident wrong plan")
check("not in the graph" in detail, f"detail {detail!r} does not explain why")

# A confusable node must not be used as a start.
with_world(("office_door", 0.90, 0.40))
m2.mark("office_door")
node, detail = graph_walk.locate(m2, capture=lambda: object(), log=lambda *a: None)
check(node is None,
      "locate() started a route from a node it cannot tell from its neighbour")

# Unrecognised -> reset fallback, and it must actually route afterwards.
reset_calls = []
sys.modules["reset_env"] = types.SimpleNamespace(
    reset_environment=lambda log=print: reset_calls.append(1))
with_world((None, 0.4, 0.02))
rig = Rig(); install(rig)

_seen = {"n": 0}


def _identify_after_reset(img, **kw):
    # Unrecognised at first; after the reset the route is walked and each leg
    # is confirmed by name.
    _seen["n"] += 1
    return (None, 0.4, 0.02) if _seen["n"] == 1 else ("middle", 0.8, 0.25)


sys.modules["places"] = types.SimpleNamespace(identify=_identify_after_reset)
# The prompt is NOT on screen where we start (that is the whole point — we are
# lost), and IS on screen once the last leg has been walked.
_tbl = {"n": 0}


def _at_table_after_walking(img):
    _tbl["n"] += 1
    return _tbl["n"] > 1


sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=_at_table_after_walking, ink=lambda img: 0.04)
m3 = a_map()
m3.mark(graph_walk.SPAWN)
m3.connect(graph_walk.SPAWN, "middle", [{"bearing": 10.0, "dur": 1.0, "speed": 0.25}])
res = graph_walk.go_to_table(m3, capture=lambda: object(),
                             read_heading=lambda: 90.0, log=lambda *a: None)
check(reset_calls, "nowhere was recognised and go_to_table never reset — then "
                   "'from anywhere' only means 'from anywhere I recognise'")
check(res.get("reset") is True, f"result did not record that it reset: {res}")
check(res["arrived"] is True, f"did not arrive after resetting: {res}")

# allow_reset=False must NOT reload the save behind the caller's back.
reset_calls.clear()
_seen["n"] = 0
sys.modules["places"] = types.SimpleNamespace(identify=lambda img, **kw: (None, 0.4, 0.02))
sys.modules["table_prompt"] = types.SimpleNamespace(
    at_table=lambda img: False, ink=lambda img: 0.01)
rig = Rig(); install(rig)
res = graph_walk.go_to_table(m3, capture=lambda: object(),
                            read_heading=lambda: 90.0, log=lambda *a: None,
                            allow_reset=False)
check(not reset_calls,
      "allow_reset=False still reloaded the save — a reload discards an "
      "in-progress match, so it must never happen unasked")
check(res["arrived"] is False and res["reason"] == "unlocated",
      f"expected an honest 'unlocated', got {res}")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  graph_walk: locates itself or resets to a known start; refuses "
      "stepless legs, walks forward (ly<0) along recorded "
      "bearings, halts on STUCK, stops at the first unconfirmed leg, confirms "
      "the table by prompt not appearance, and says why a route is impossible")
