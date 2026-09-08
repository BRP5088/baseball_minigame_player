"""patch43 (2026-09-08): a LOST RESCUE — one terminal rung before the walk ends.

WHAT ENDS A TRIAL TODAY. `chain_walk.walk()` counts LOST_MAX (13) iterations
with nothing credible after the blind budget and returns
`finish("lost at k=... ")`. That branch is the end of the walk.

WHY A RESCUE, AND WHY THIS SHAPE. Every lost trial of the night has one shape
(agent_progress/closed-loop/review/census_after_129_notes.md and the readers
beside it — notes_cur_t04_1788853535.md, notes_cur_t12_1788856027.md,
notes_b16_t16.md): the character is PINNED against geometry or an NPC in the
portrait room / bar entrance (chain k 100-140), the view does not change for
thirteen iterations, and the escape ladder cannot open it. Measured over every
journal on disk, a credible fix within 3 rows of the rung, in the bar stretch
(k 120-170):

    jump   14/55        BACK    0/27        left   36/106      right   5/69

One step back has NEVER freed a bar-entrance pin. Every reader's "what a human
would have done" is the same: back straight out a full step or two, then LOOK
for the doorway or the room they had just been facing, then carry on.

AND THE ESTIMATE IS AHEAD OF THE CHARACTER when this happens: turn-early and
blind advances carry k 20-60 waypoints past where the character stands (the
`reloc_past_129_census` and `blind_after_129_census` runs beside those notes).
So the look must search around the LAST CREDIBLE SIGHTING, not around k. That
is the whole reason this is not just another escape rung.

THE RUNG, precisely:

  * fires only at `lost >= LOST_MAX`, and at most LOST_RESCUE_MAX = 1 time per
    walk — a second loss ends the walk exactly as today. It therefore costs an
    arriving trial NOTHING and changes no other path;
  * ... and only if the cap can pay for it: see THE CAP, below;
  * back(PUSH_MAG, LOST_RESCUE_BACK_SEC) where LOST_RESCUE_BACK_SEC =
    2 * BACK_SEC = 1.0 s: two of the existing step-backs, not a new physical
    constant;
  * three looks — the current heading, then STOP_LOOK_DEG (-25, +25) — each
    matched with `chain.locate(img, max(last_cred_k - LOST_RESCUE_LOOKBACK, 0),
    window=WIDE_AHEAD)`, i.e. a window that starts a little BEHIND the last
    credible sighting and reaches WIDE_AHEAD ahead of it;
  * believed only at STRONG_MIN_INLIERS (165), the existing wide-search gate —
    above the live census's wrong-place MAXIMUM of 164
    (overnight/census/live_gate_census.json). No new inlier threshold;
  * stop at the first believed look, like the stop look-around;
  * believed -> k is the fix's waypoint, the plan pointer re-derives from it
    (the same re-aim the rewind and the look-back regression do), the camera
    turns to that entry's heading, the counters reset, THE END TURN'S YAW AND
    THE ONE-SHOT TURN-EARLY GO WITH THEM (see THE RESETS, below), and the row
    is `"rescued"` carrying a `"rescue"` dict;
  * not believed -> a `"rescue-failed"` row with the same dict, the camera
    turns back to the heading it started from, and the walk ends EXACTLY as
    today: the same "lost" row, the same `finish(...)` wording, so every
    harness and reader still parses it;
  * the three frames are saved through `_save` as `_rescue_look0` /
    `_rescue_lookL` / `_rescue_lookR`, so a reader can see what the rescue saw.

Nothing else moves: no physical constant is touched, no guard is removed, the
ladder, the budgets and the failure strings are unchanged.

--------------------------------------------------------------------------
THE THREE THINGS THE FIRST DRAFT GOT WRONG (two skeptics, 2026-09-08). All
three are the project's own signature shape — state that outlives the
measurement it was made from, and a rung that runs where it cannot be paid for.

THE CAP. The rescue is the one rung that costs more than an ordinary
iteration: a step back plus up to three turn-and-look pairs plus the turn
back. Swept offline (probes/probe_time_cap.py, `time_cap` 20.0 to 30.0 in 0.1
steps) the LOST_MAX iteration cost 3.30 s and the walk ran **3.20 s past its
own cap** — capped at 25.4 s it ended at 28.60 s — and still reported "lost".
A harness that sizes an external kill timer off `time_cap` had 3.2 s less
slack on this one failure mode than on every other iteration (§10.14 is this
project's own history of exactly that arithmetic). So the rung is not STARTED
unless its step back alone still fits inside the cap, and the looks STOP the
moment the cap is reached. What is left is bounded by one look plus the turn
back — the granularity the loop already has, since it turns and pushes before
it checks the clock.

THE RESETS. A successful rescue moves the character (a step back) and moves
the estimate (k, and the plan pointer with it), so state measured before it is
refuted by it. Two pieces were left standing and both were reproduced:

  * `end_yaw`, the degrees an END TURN adds to every remaining tail heading.
    probes/probe_end_yaw.py: a walk turns -30.5 deg toward the dealer at the
    tail, goes blind, is rescued, correctly re-aims to the plan's raw 95.0 —
    and the very next iteration commands 64.5, the stale offset riding a
    heading measured from a position the rescue has just backed away from.
    The `regressed` branch already zeroes it for exactly this reason and says
    so; the rescue is the same kind of re-aim. The BUDGET (`end_turns`) is NOT
    restored, exactly as `regressed` does not restore it.
  * `turned_early`, the one-shot "turn toward the stop instead of pushing into
    whatever is there". probes/probe_turned_early.py: the walk turns early at
    a stop, is lost, is rescued back BEFORE that same stop — and cannot take
    the cheap turn again, so it falls into misses and rungs and dies lost one
    stop later with no second rescue. `"relocalised"` — believed at the same
    STRONG_MIN_INLIERS — re-arms it through PROGRESS_ACTIONS; a rescue is the
    same evidence and now re-arms it too.

THE READERS. `"rescue-failed"` costs seconds and is pure waste, so it joins
`tools/collision_census.py`'s WASTE tuple — without it a region whose trials
die through a rescue reports LESS waste than one dying through a plain miss.
And `"rescued"` is the highest-stakes turn in a rescued trial, so it joins
`tools/turn_review.py`'s filter — the project's own review rule is "look at
the turns first" and that tool showed every turn but this one. `frame_for`
also picks its frame with `sorted()`, so an iteration that saved suffixed
frames beside its own (`_rescue_look*`, and the stop look-around's `_pan*`
before it) tiles the base frame rather than whichever one the filesystem
happened to list first.

NOT CHANGED, AND WHY. `walk_heading` is also stale after a rescue, and it is
reachable: probes/probe_walk_heading2.py drives a `turn-retry` that pushes
along the heading of a push made BEYOND the stop it is now retrying. But
`grep -n walk_heading chain_walk.py` finds exactly ONE writer, inside
`if do_push:`, so EVERY branch that moves k backwards and rewinds `pi`
without pushing leaves it stale — and `regressed` has shipped that way since
before this patch. It is a pre-existing gap the rescue newly makes reachable,
not one it introduces, and a fix belongs in its own patch that fixes both
branches rather than one smuggled in here.

`last_cred_scale` is likewise not refreshed from the believed look, and that
is deliberate: it feeds `_blind_cap`, a measured lever, and leaving the older
(higher) reading standing is the conservative direction — a smaller blind
budget near a stop, never a larger one.
--------------------------------------------------------------------------

TESTS (tests/routing/test_chain_walk.py, classes LostRescue and
TheRescueReachesTheReaders): one rescue that believes its +25 look and
arrives; the budget (a second loss gets no rescue); all-120-inlier looks ->
"rescue-failed" and the literal failure string of today; no rescue at
lost == LOST_MAX - 1; the window anchored at last_cred_k - 6 rather than at k;
no rescue when the cap cannot pay for its step back; the looks stopping at the
cap; the END TURN's yaw dropped; the turn-early re-armed; and the two reader
tools reached. Three existing tests that reach the lost branch are updated
where the new row or the new step back is visible to them, and each keeps the
assertion it was written for.

MUTANTS CAUGHT (scratch copy, one at a time, __pycache__ cleared between):
  rescue removed                      -> the behavioural tests of LostRescue
  LOST_RESCUE_MAX = 2                 -> test_a_second_loss_gets_no_second_rescue
  a look believed at 120 inliers      -> test_looks_under_the_strong_gate_fail_the_rescue
  window anchored at k                -> test_the_rescue_searches_behind_the_last_credible_k
  the cap pre-gate removed            -> test_no_rescue_when_the_cap_cannot_pay_for_the_step_back
  the per-look cap check removed      -> test_the_looks_stop_when_the_cap_is_reached
  `end_yaw = 0.0` removed             -> test_a_rescue_drops_the_END_TURNs_yaw
  `turned_early = False` removed      -> test_a_rescue_re_arms_the_one_shot_turn_early
  "rescue-failed" out of WASTE        -> test_a_failed_rescue_is_counted_as_waste
  "rescued" out of the turn filter    -> test_the_review_tool_shows_the_rescues_turn
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
CC = os.path.join(ROOT, "tools", "collision_census.py")
TR = os.path.join(ROOT, "tools", "turn_review.py")
c = open(C).read()
t = open(T).read()
cc = open(CC).read()
tr = open(TR).read()
if ("LOST_RESCUE_MAX" in c or "class LostRescue" in t
        or "rescue-failed" in cc or "rescued" in tr):
    raise SystemExit("ALREADY APPLIED")

# ---------------------------------------------------------------- chain_walk
CONSTANTS = '''LOST_MAX = 13
# THE LOST RESCUE: ONE terminal rung, after the ladder and before the walk
# ends. Every lost trial of 2026-09-08 is one shape (census_after_129_notes.md
# and its readers): pinned against geometry or an NPC at k 100-140, the view
# unchanged for thirteen iterations, and the ladder unable to open it — a
# credible fix follows `escape:back` 0 of 27 times in the bar stretch, `right`
# 5 of 69, `left` 36 of 106. What a human does there is back STRAIGHT OUT a
# full step and look for the room they were facing. ONE per walk: a second
# loss ends the walk exactly as before, so an arriving trial pays nothing.
LOST_RESCUE_MAX = 1
# Two of the existing step-backs, not a new physical constant: one BACK_SEC
# has never freed a pin (0 of 27), and the readers describe backing out of a
# doorway, not off a wall.
LOST_RESCUE_BACK_SEC = 2 * BACK_SEC
# ... and the looks search from a little BEHIND the last CREDIBLE sighting,
# because when this fires the estimate is typically 20-60 waypoints ahead of
# the character (turn-early and blind advances carried it there), so a window
# around k is a window around somewhere the character has never been. The
# window reaches WIDE_AHEAD past its start, which is the same span the wide
# relocalisation searches.
LOST_RESCUE_LOOKBACK = 6
'''

RESCUE = '''            if (lost >= LOST_MAX and rescues < LOST_RESCUE_MAX
                    and now() - t0 + LOST_RESCUE_BACK_SEC < time_cap):
                # THE LOST RESCUE (see LOST_RESCUE_MAX). Back out, look around
                # the LAST CREDIBLE SIGHTING, and go on if something strong
                # fits. It fires once per walk and only here, so it cannot
                # touch a trial that is not already over.
                #
                # AND ONLY IF THE CAP CAN PAY FOR IT. This is the one rung that
                # costs more than an iteration — a step back plus up to three
                # turn-and-look pairs plus the turn back — and a rescue that
                # finishes after the cap is worthless anyway, because the next
                # top-of-loop check returns "timed out" before the walk can use
                # it. Unguarded it ran the walk 3.20 s past a 25.4 s cap and
                # still reported "lost" (probe_time_cap.py), so an external
                # ceiling sized off `time_cap` had that much less slack here
                # than on every other iteration (§10.14). The step back is the
                # one part whose duration is known in advance; the looks are
                # bounded below, inside the loop.
                rescues += 1
                h0 = last_cmd if last_cmd is not None else heading
                from_k = k
                back(PUSH_MAG, LOST_RESCUE_BACK_SEC)
                # NOT `k`: when a walk is lost the estimate is ahead of the
                # character, so the window that could contain the view is the
                # one around the last thing the SENSOR actually saw.
                start = max(last_cred_k - LOST_RESCUE_LOOKBACK, 0)
                looks_plan = [(0.0, "_rescue_look0")]
                for _d in STOP_LOOK_DEG:
                    looks_plan.append((_d, "_rescue_lookL" if _d < 0
                                       else "_rescue_lookR"))
                looks = 0
                best = None                  # (degrees, inliers, fix)
                for ddeg, sfx in looks_plan:
                    if now() - t0 >= time_cap:
                        # The cap owns the walk. The step back is already paid
                        # for and the first look always fits behind it (the
                        # gate above reserved exactly that much), so this can
                        # only ever drop the second and third.
                        break
                    if ddeg != 0.0:
                        if h0 is None:
                            continue         # nothing to yaw about
                        turn_to((h0 + ddeg) % 360.0)
                    img2 = capture()
                    looks += 1
                    _save(shots, iteration, k, img2, log, suffix=sfx)
                    f2 = chain.locate(img2, start, window=WIDE_AHEAD)
                    i2 = 0 if f2 is None else (getattr(f2, "inliers", 0) or 0)
                    if f2 is not None and (best is None or i2 > best[1]):
                        best = (ddeg, i2, f2)
                    if best is not None and best[1] >= STRONG_MIN_INLIERS:
                        # Stop at the first BELIEVED look, exactly as the stop
                        # look-around does: STRONG_MIN_INLIERS is above the
                        # wrong-place maximum, so another direction can only
                        # cost a turn, a capture and a locate.
                        break
                rescue = {"looks": looks, "from_k": from_k, "to_k": None,
                          "deg": None if best is None else best[0],
                          "inliers": None if best is None else best[1]}
                if best is not None and best[1] >= STRONG_MIN_INLIERS:
                    ddeg, i2, f2 = best
                    k = min(int(f2.k), n - 1)
                    last_cred_k = k
                    rescue["to_k"] = k
                    # The same re-aim the rewind and the look-back regression
                    # make when they move k: the plan pointer re-derives as
                    # the first entry past k.
                    pi = 0
                    while pi < len(plan) and plan[pi][0] <= k:
                        pi += 1
                    h2 = plan[pi][2] if pi < len(plan) else plan_last_heading
                    if h2 is not None:
                        turn_to(h2)
                        last_cmd = h2
                    lost = 0
                    misses = 0
                    stalls = 0
                    blind = 0
                    escapes = 0
                    unverified_turn = False
                    early_stop = False
                    # THE RESCUE MOVED THE CHARACTER AND THE ESTIMATE, so two
                    # more pieces of state measured before it are refuted with
                    # it. Both were left standing in the first draft and both
                    # were reproduced offline.
                    #
                    # end_yaw is the degrees an END TURN added to every
                    # remaining tail heading, measured from a position this
                    # rung has just contradicted and backed away from. Left
                    # standing it rides the re-aimed heading too: a walk that
                    # turned -30.5 at the tail and was correctly re-aimed to
                    # 95.0 commanded 64.5 on the very next push
                    # (probe_end_yaw.py). The `regressed` branch zeroes it for
                    # the same reason and in the same words; like that branch,
                    # this one does NOT restore the BUDGET (`end_turns`).
                    end_yaw = 0.0
                    # turned_early is the one-shot "turn toward the stop
                    # instead of pushing into whatever is there". It is
                    # re-armed by progress the sensor SAW — and this is that,
                    # believed at the same STRONG_MIN_INLIERS as
                    # `relocalised`, which re-arms it through PROGRESS_ACTIONS.
                    # Left set, a walk rescued back BEFORE the stop it had
                    # already turned early at could not take that cheap turn
                    # again, fell into the rungs, and died lost one stop later
                    # with no second rescue (probe_turned_early.py).
                    turned_early = False
                    action = "rescued"
                    record({"iteration": iteration, "k": k, "target": target_k,
                            "fix": _fix_row(f2), "action": action,
                            "lateral": None, "rescue": rescue,
                            "at_end": at_end,
                            "seconds": round(now() - it_t0, 2),
                            "elapsed": round(now() - t0, 2)})
                    log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  "
                        f"rescued: backed {LOST_RESCUE_BACK_SEC:.1f}s and "
                        f"looked {looks} time(s) from {start}; {i2} inliers "
                        f"at {ddeg:+.0f} deg put k at {k} (was {from_k})")
                    continue
                # Nothing strong: leave the camera where the walk had it and
                # end exactly as before — the "lost" row and its wording are
                # what every harness and reader parses.
                if h0 is not None:
                    turn_to(h0)
                    last_cmd = h0
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix), "action": "rescue-failed",
                        "lateral": None, "rescue": rescue, "at_end": at_end,
                        "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  "
                    f"rescue-failed: backed {LOST_RESCUE_BACK_SEC:.1f}s and "
                    f"looked {looks} time(s) from {start}; best "
                    f"{rescue['inliers']} inliers, under {STRONG_MIN_INLIERS}")
            if lost >= LOST_MAX:
'''

edits_c = [
 # the constants, immediately after LOST_MAX
 ('''LOST_MAX = 13
''', CONSTANTS),
 # the counter, beside the one it bounds
 ('''    lost = 0                    # iterations with nothing credible, budget spent
''',
  '''    lost = 0                    # iterations with nothing credible, budget spent
    rescues = 0                 # LOST RESCUES spent this walk (LOST_RESCUE_MAX)
'''),
 # the rung itself, immediately above the branch that ends the walk
 ('''            if lost >= LOST_MAX:
''', RESCUE),
]

# --------------------------------------------------------------------- tools
edits_cc = [
 # a failed rescue is seconds spent and nothing gained: it is WASTE. Without
 # this a region whose trials die through a rescue reports LESS waste than one
 # dying through a plain miss, which is backwards.
 ('''WASTE = ("stalled", "weak", "miss", "turn-retry", "turn-back", "turn-wait", "lost")
''',
  '''WASTE = ("stalled", "weak", "miss", "turn-retry", "turn-back", "turn-wait", "lost",
         "rescue-failed")
'''),
]

edits_tr = [
 # "look at the turns first" (the user's rule) — and the LOST RESCUE's re-aim
 # is the highest-stakes turn a rescued trial makes, so it belongs in the tile.
 ('''    return [r for r in rows if str(r.get("action", "")).startswith(("turned", "turn-retry"))]
''',
  '''    return [r for r in rows if str(r.get("action", "")).startswith(
        ("turned", "turn-retry", "rescued"))]
'''),
 # SORTED, because an iteration can save frames BESIDE its own -- the stop
 # look-around's `_pan*` and the lost rescue's `_rescue_look*` -- and the base
 # name sorts first ("." < "_"). Unsorted, the tile showed whichever frame the
 # filesystem happened to list first.
 ('''    fs = glob.glob(os.path.join(shots, f"it_{iteration:03d}_k*.jpg"))
    return fs[0] if fs else None
''',
  '''    fs = sorted(glob.glob(os.path.join(shots, f"it_{iteration:03d}_k*.jpg")))
    return fs[0] if fs else None
'''),
]

# ------------------------------------------------------------ test_chain_walk
NEW_TESTS = '''class ScriptedWide(FakeChain):
    """A FakeChain whose WIDE answers depend on the HINT.

    The blind path's forward wide search is hinted at `k + 1`; the lost
    rescue's looks are hinted BEHIND the last credible sighting. Keying the
    script on the hint is what lets one test script the rescue's three looks
    without the eighteen wide searches the blind phase makes first eating them
    — and it is also how `test_the_rescue_searches_behind_the_last_credible_k`
    can show WHERE the rescue looked rather than merely that it looked.
    """

    def __init__(self, *a, at_hint=None, **kw):
        super().__init__(*a, **kw)
        self.at_hint = {h: list(v) for h, v in (at_hint or {}).items()}

    def locate(self, img, k_hint, window=3):
        if window >= chain_walk.WIDE_AHEAD:
            self.wide_calls.append(k_hint)
            queued = self.at_hint.get(k_hint)
            if queued:
                return queued.pop(0)
            return self.wide
        return super().locate(img, k_hint, window=window)


class RescueRig(Rig):
    """A Rig whose prompt appears once the RESCUE's step back has happened.

    A capture number would be an arithmetic constant three tests would have to
    agree on; "the prompt is on screen on the first frame after the walk backed
    out and turned" is the thing the test means. The escape ladder's own back
    rung is BACK_SEC (0.5 s), so it cannot trigger this.
    """

    def at_table(self, img):
        v = any(e[0] == "back" and e[2] == chain_walk.LOST_RESCUE_BACK_SEC
                for e in self.events)
        self.events.append(("at_table", img.n, v))
        return v


class LostRescue(unittest.TestCase):
    """(o) ONE terminal rung before a walk ends LOST: back out, look around the
    LAST CREDIBLE sighting, and carry on if something strong fits.

    Every lost trial of 2026-09-08 (census_after_129_notes.md, and the readers
    notes_cur_t04_1788853535.md / notes_cur_t12_1788856027.md / notes_b16_t16.md)
    is the same picture: pinned against geometry or an NPC at k 100-140, the
    view unchanged for thirteen iterations, and the ladder unable to open it —
    `escape:back` is followed by a credible fix 0 of 27 times in the bar
    stretch. The estimate is 20-60 waypoints AHEAD of the character by then, so
    the looks search around `last_cred_k`, never around `k`.

    THE LAST FOUR TESTS ARE THE INTERACTION SUITE, one per defect two skeptics
    demonstrated against the first draft on 2026-09-08. Each is the project's
    own signature shape: a rung running where it cannot be paid for, and state
    that outlives the measurement it was made from.
    """

    # A 30-waypoint chain of all-push targets: ten credible fits (k 1..10),
    # then the sensor goes blind for good — six blind advances (k 11..16) and
    # the thirteen LOST_MAX iterations that end the walk. `lookback=None` so
    # the look-back does not eat the script; `default=None` is the blindness.
    CREDIBLE = 10

    def chain(self, at_hint=None):
        return ScriptedWide(30, [Fix(k=i) for i in range(1, self.CREDIBLE + 1)],
                            default=None, lookback=None, at_hint=at_hint)

    def test_the_constants(self):
        # Literals, not the constants themselves (§10.11): a test that reads
        # the value it guards passes at any value.
        self.assertEqual(chain_walk.LOST_RESCUE_MAX, 1)
        self.assertEqual(chain_walk.LOST_RESCUE_BACK_SEC, 1.0)
        self.assertEqual(chain_walk.LOST_RESCUE_BACK_SEC, 2 * chain_walk.BACK_SEC)
        self.assertEqual(chain_walk.LOST_RESCUE_LOOKBACK, 6)
        self.assertEqual(chain_walk.LOST_MAX, 13)
        self.assertEqual(chain_walk.STRONG_MIN_INLIERS, 165)
        self.assertEqual(chain_walk.STOP_LOOK_DEG, (-25.0, 25.0))

    def test_a_lost_walk_backs_out_looks_around_and_carries_on(self):
        # The +25 look is the one that fits, at 170 inliers naming waypoint 13
        # (three past the last credible sighting at 10). The walk takes it and
        # arrives; without the rescue it would have ended at iteration 29.
        ch = self.chain(at_hint={4: [Fix(k=13, inliers=120),
                                     Fix(k=13, inliers=120),
                                     Fix(k=13, inliers=170)]})
        rig = RescueRig(ch, table_at=None)
        res = rig.go(time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts.count("rescued"), 1, acts)
        self.assertNotIn("lost", acts)
        self.assertNotIn("rescue-failed", acts)
        self.assertTrue(res["arrived"])
        self.assertIsNone(res["failure"])
        self.assertEqual(acts[-1], "arrived", acts[-4:])
        row = res["fixes"][acts.index("rescued")]
        self.assertEqual(row["rescue"], {"looks": 3, "deg": 25.0,
                                         "inliers": 170, "from_k": 16,
                                         "to_k": 13})
        self.assertEqual(row["k"], 13, "k came from the look, not from the plan")
        # ONE step back, of two BACK_SECs, before the looks.
        backs = [e for e in rig.events if e[0] == "back" and e[2] == 1.0]
        self.assertEqual(len(backs), 1)
        self.assertEqual(backs[0][1], chain_walk.PUSH_MAG)
        # The looks: the walking heading was 170.0 (the target 17's heading),
        # so -25 and +25 are 145.0 and 195.0, and the rescue then aims at the
        # plan entry past k=13 — target 14, heading 140.0.
        turns = [e[1] for e in rig.events if e[0] == "turn"]
        i_back = [i for i, e in enumerate(rig.events) if e[0] == "back"][0]
        after = [e[1] for e in rig.events[i_back:] if e[0] == "turn"]
        self.assertEqual(after[:3], [145.0, 195.0, 140.0], after[:5])
        self.assertIn(170.0, turns, "the walking heading the looks yaw about")

    def test_a_second_loss_gets_no_second_rescue(self):
        # The budget. Same walk with no prompt ever: it is rescued once, walks
        # on, goes blind again, and the SECOND loss ends it exactly as today.
        ch = self.chain(at_hint={4: [Fix(k=13, inliers=120),
                                     Fix(k=13, inliers=120),
                                     Fix(k=13, inliers=170)]})
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts.count("rescued"), 1, acts)
        self.assertEqual(acts.count("rescue-failed"), 0, acts)
        self.assertEqual(acts[-1], "lost")
        self.assertTrue(res["failure"].startswith("lost at k="), res["failure"])
        self.assertEqual(len([e for e in rig.events
                              if e[0] == "back" and e[2] == 1.0]), 1,
                         "exactly one rescue step back in the whole walk")
        # ... and the walk really did get lost a second time: k had moved on
        # from where the rescue put it.
        self.assertGreater(res["k_final"], 13)

    def test_looks_under_the_strong_gate_fail_the_rescue(self):
        # 120 inliers is a live wrong-place count (the census's p95 is 126 and
        # its maximum 164): believing it would move the estimate 60 waypoints
        # on a wrong match. The rescue records what it saw, turns back, and the
        # walk ends with the SAME failure string as before this patch.
        ch = self.chain(at_hint={4: [Fix(k=13, inliers=120)] * 3})
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[-2:], ["rescue-failed", "lost"], acts[-4:])
        self.assertEqual(
            res["failure"],
            "lost at k=16 of 29: 13 iterations with no credible fix after "
            "6 blind advances",
            "the failure wording every harness and reader parses must not move")
        row = res["fixes"][-2]
        self.assertEqual(row["rescue"], {"looks": 3, "deg": 0.0,
                                         "inliers": 120, "from_k": 16,
                                         "to_k": None})
        self.assertIsNone(row["fix"], "the loop's own fix was None")
        # the camera is put back where the walk had it
        turns = [e[1] for e in rig.events if e[0] == "turn"]
        self.assertEqual(turns[-1], 170.0)

    def test_no_rescue_before_LOST_MAX(self):
        # Twelve lost iterations and then a credible fix: the rung must not
        # fire at LOST_MAX - 1. The anti-vacuity half is the middle of the
        # walk — twelve misses and four escape rungs — so this cannot pass by
        # never getting near a loss.
        fixes = ([Fix(k=i) for i in range(1, self.CREDIBLE + 1)]
                 + [None] * 18 + [Fix(k=17, inliers=120)])
        ch = ScriptedWide(30, fixes, default=None, lookback=None)
        rig = Rig(ch, table_at=31)
        res = rig.go(time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:10], ["advanced"] * 10)
        self.assertEqual(acts[10:16], ["blind-advance"] * 6)
        self.assertEqual(acts[16:28],
                         ["miss", "miss", "escape:jump",
                          "miss", "miss", "escape:back",
                          "miss", "miss", "escape:left",
                          "miss", "miss", "escape:right"], acts[16:28])
        self.assertEqual(acts[28], "advanced", "the twelfth lost iteration recovered")
        self.assertFalse([a for a in acts if a.startswith("rescue")], acts)
        self.assertEqual([e for e in rig.events
                          if e[0] == "back" and e[2] == 1.0], [],
                         "no rescue step back before LOST_MAX")
        self.assertTrue(res["arrived"])

    def test_the_rescue_searches_behind_the_last_credible_k(self):
        # THE POINT OF THE RUNG. The last credible sighting was waypoint 10;
        # blind advances carried k to 16. The three looks must be hinted at
        # 10 - 6 = 4 — the ground the character may actually be standing on —
        # and NOT at k, which is where the plan thinks it is.
        ch = self.chain(at_hint={4: [Fix(k=13, inliers=120),
                                     Fix(k=13, inliers=120),
                                     Fix(k=13, inliers=170)]})
        rig = RescueRig(ch, table_at=None)
        res = rig.go(time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertIn("rescued", acts, acts[-4:])
        row = res["fixes"][acts.index("rescued")]
        self.assertEqual(row["rescue"]["from_k"], 16, "k when the rescue fired")
        self.assertEqual(ch.wide_calls[-3:], [4, 4, 4],
                         "the three looks are hinted at last_cred_k - 6")
        self.assertNotIn(4, ch.wide_calls[:-3],
                         "and nothing else in this walk asked there")
        self.assertNotIn(16, ch.wide_calls[-3:], "not anchored at k")
        self.assertNotIn(10, ch.wide_calls[-3:], "and not at last_cred_k itself")

    # ---- the interaction suite (two skeptics, 2026-09-08) ----

    def test_no_rescue_when_the_cap_cannot_pay_for_the_step_back(self):
        # THE CAP OWNS THE WALK. Uncapped this scenario's LOST_MAX iteration
        # costs 3.30 s of rescue and the walk ends at 28.60 s; capped at 25.4 s
        # the first draft still ran to 28.60 — 3.20 s past its own ceiling —
        # and reported "lost", so a harness sizing an external kill timer off
        # `time_cap` had that much less slack here than anywhere else (§10.14).
        # The rung reserves its step back or does not start.
        #
        # The rescue is reached at 25.80 s, so a cap of 26.5 cannot pay for the
        # 1.0 s back and the walk must end exactly as it did before patch43.
        ch = self.chain(at_hint={4: [Fix(k=13, inliers=170)]})
        rig = Rig(ch, table_at=None)
        res = rig.go(time_cap=26.5)
        acts = [f["action"] for f in res["fixes"]]
        self.assertFalse([a for a in acts if a.startswith("rescue")], acts[-4:])
        self.assertEqual(acts[-1], "lost")
        self.assertEqual([e for e in rig.events
                          if e[0] == "back" and e[2] == 1.0], [])
        self.assertLessEqual(res["seconds"], 26.5,
                             "and the walk stays inside its own cap")
        # ANTI-VACUITY: the same chain with room to spare IS rescued, so this
        # cannot pass by the scenario never reaching the rung.
        ch2 = self.chain(at_hint={4: [Fix(k=13, inliers=170)]})
        rig2 = Rig(ch2, table_at=None)
        acts2 = [f["action"] for f in rig2.go(time_cap=400.0)["fixes"]]
        self.assertIn("rescued", acts2, acts2[-4:])

    def test_the_looks_stop_when_the_cap_is_reached(self):
        # ... and the looks are bounded too. The step back lands at 26.80 s,
        # look0 costs a capture (0.1) and each of the other two a turn and a
        # capture (0.6), so a 27.0 s cap pays for two looks and not the third.
        # Uncapped the same walk takes all three: that is the control, and it
        # is what a deleted check would show here.
        def looks_at(cap):
            ch = self.chain()                     # every look reads nothing
            rig = Rig(ch, table_at=None)
            res = rig.go(time_cap=cap)
            rows = [f for f in res["fixes"] if f["action"] == "rescue-failed"]
            self.assertEqual(len(rows), 1, [f["action"] for f in res["fixes"]])
            return rows[0]["rescue"]["looks"], res["seconds"]
        self.assertEqual(looks_at(400.0)[0], 3)
        self.assertEqual(looks_at(27.0)[0], 2)
        # What is left is one look plus the turn back — the granularity the
        # loop already has, since it turns and pushes before it reads the clock.
        self.assertLessEqual(looks_at(27.0)[1] - 27.0, 1.2)

    def test_a_rescue_drops_the_END_TURNs_yaw(self):
        # THE END TURN'S OFFSET IS MEASURED FROM A POSITION THE RESCUE BACKS
        # AWAY FROM. This walk turns -30.5 deg toward the dealer at the tail
        # (dx -600 / PX_PER_DEG), goes blind, and is rescued back to waypoint
        # 17, where the plan pointer re-derives onto target 20 and the camera
        # is aimed at its recorded 95.0. With the offset left standing the very
        # next push commanded 95.0 - 30.5 = 64.5 — a heading nowhere near the
        # tail — which is exactly what `regressed` zeroes end_yaw to prevent.
        wps = EndTurnTowardTheDealer._wps([89.5] * 3 + [95.0] * 10)
        ch = ScriptedWide(len(wps),
                          [Fix(k=i) for i in (1, 4, 7, 10, 13, 16)]
                          + [Fix(k=17, dx=-600.0)],
                          default=None, lookback=None,
                          at_hint={11: [Fix(k=17, inliers=170)]})
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = without_stuck(rig.go, time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts.count("rescued"), 1, acts)
        i = acts.index("rescued")
        self.assertEqual(res["fixes"][i]["k"], 17)
        turns = [round(e[1], 1) for e in rig.events if e[0] == "turn"]
        self.assertEqual(turns, [0.0, 89.5, 59.0, 64.5, 95.0],
                         "walk east, turn at the stop, TURN -30.5 toward the "
                         "dealer, carry it onto the next tail heading — then "
                         "the rescue drops it and aims at the RECORDED 95.0")
        self.assertNotIn(64.5, turns[4:],
                         "the stale offset must not ride the re-aimed heading")
        # ANTI-VACUITY: the end turn really did happen and really did ride one
        # heading before the rescue.
        self.assertEqual([r["lateral"]["end_turn"] for r in res["fixes"]
                          if r["lateral"] and "end_turn" in r["lateral"]],
                         [-30.5])

    def test_a_rescue_re_arms_the_one_shot_turn_early(self):
        # TURN-EARLY IS RE-ARMED BY PROGRESS THE SENSOR SAW, and a rescue is
        # that — believed at the same STRONG_MIN_INLIERS as `relocalised`,
        # which re-arms it through PROGRESS_ACTIONS. This walk turns early at
        # the stop (plan entry 5), takes it unverified, is lost, and is rescued
        # back to waypoint 7 — BEFORE that same stop. Approaching it blind
        # again it must be able to turn early again; left set, the flag sent it
        # into the misses and rungs instead and it died lost one stop later
        # with no second rescue left.
        wps = EndTurnTowardTheDealer._wps([89.5] * 3 + [95.0] * 10)
        ch = ScriptedWide(len(wps), [Fix(k=1), Fix(k=4), Fix(k=7, scale=2.6)],
                          default=None, lookback=None,
                          at_hint={1: [Fix(k=7, inliers=170)]})
        ch.waypoints = wps
        rig = Rig(ch, table_at=None)
        res = without_stuck(rig.go, time_cap=400.0)
        acts = [f["action"] for f in res["fixes"]]
        i = acts.index("rescued")
        self.assertEqual(acts.count("turn-early"), 2, acts)
        self.assertLess(acts.index("turn-early"), i, acts)
        self.assertGreater(acts.index("turn-early", i), i,
                           "the second turn-early is AFTER the rescue")
        self.assertEqual(res["fixes"][i]["rescue"]["to_k"], 7)


class TheRescueReachesTheReaders(unittest.TestCase):
    """(p) A NEW ACTION THAT NO READER KNOWS IS A HOLE IN THE EVIDENCE.

    `chain_walk` owns this vocabulary and two tools under `tools/` consume it
    by name: `collision_census.py` buckets the seconds a walk wastes, and
    `turn_review.py` tiles the frame at every turn because the user's review
    rule is "look at the turns first". A new action that neither knows is
    counted nowhere and shown nowhere, and nothing fails — §10.1's shape. The
    tools are loaded BY PATH so this test needs no sys.path change and cannot
    pick up some other module of the same name.
    """

    @staticmethod
    def _load(name, rel):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(_ROOT, rel))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    @staticmethod
    def _quiet(fn, *a):
        """Run a tool's entry point without its report or its warnings.

        `collision_census.main` PRINTS its table, and both tools read their
        journal with a bare `open()` and leak the handle. The leak is
        pre-existing, has nothing to do with this patch, and is not this
        test's to fix or to report — but an unsuppressed ResourceWarning in
        the suite's output is noise a reader has to learn to ignore.
        """
        import contextlib
        import io
        import warnings
        with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            return fn(*a)

    def _journal(self, rows):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        p = os.path.join(d, "t01.jsonl")
        with open(p, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\\n")
        return d, p

    def test_a_failed_rescue_is_counted_as_waste(self):
        cc = self._load("collision_census_under_test",
                        os.path.join("tools", "collision_census.py"))
        # k=120 is the bar counter region, which is where the rescue fires.
        d, p = self._journal([
            {"iteration": 1, "k": 120, "action": "miss", "seconds": 1.0},
            {"iteration": 2, "k": 120, "action": "rescue-failed", "seconds": 3.3},
            {"iteration": 3, "k": 120, "action": "lost", "seconds": 0.0},
        ])
        per_region = self._quiet(cc.main, os.path.join(d, "*.jsonl"))
        got = per_region[cc.region(120)]
        self.assertEqual(got["waste_it"], 3,
                         "miss, rescue-failed and lost are all waste")
        self.assertAlmostEqual(got["waste_s"], 4.3, places=6)
        self.assertEqual(got["lost_here"], 1)

    def test_a_successful_rescue_is_not_counted_as_waste(self):
        # The control for the test above: a rescue that WORKED is progress,
        # and counting it as waste would make the census argue for removing
        # the one rung that saved the trial.
        cc = self._load("collision_census_under_test2",
                        os.path.join("tools", "collision_census.py"))
        d, p = self._journal([
            {"iteration": 1, "k": 120, "action": "rescued", "seconds": 3.3},
            {"iteration": 2, "k": 120, "action": "arrived", "seconds": 0.0},
        ])
        per_region = self._quiet(cc.main, os.path.join(d, "*.jsonl"))
        self.assertEqual(per_region[cc.region(120)]["waste_it"], 0)

    def test_the_review_tool_shows_the_rescues_turn(self):
        tr = self._load("turn_review_under_test",
                        os.path.join("tools", "turn_review.py"))
        d, p = self._journal([
            {"iteration": 1, "k": 1, "action": "advanced"},
            {"iteration": 2, "k": 2, "action": "turned"},
            {"iteration": 3, "k": 3, "action": "turn-retry"},
            {"iteration": 4, "k": 4, "action": "rescued"},
            {"iteration": 5, "k": 5, "action": "rescue-failed"},
            {"iteration": 6, "k": 6, "action": "blind-advance"},
        ])
        got = [r["action"] for r in self._quiet(tr.turn_rows, p)]
        self.assertEqual(got, ["turned", "turn-retry", "rescued"],
                         "the rescue's re-aim is a turn; a walk that ENDED at "
                         "rescue-failed has no turn worth tiling")

    def test_the_review_tool_picks_a_frame_DETERMINISTICALLY(self):
        # A rescued iteration saves its three look frames beside its own, so an
        # unsorted glob tiled whichever the filesystem listed first. The base
        # name sorts before any suffix ("." < "_").
        tr = self._load("turn_review_under_test2",
                        os.path.join("tools", "turn_review.py"))
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for suffix in ("_rescue_lookR", "_rescue_look0", "", "_rescue_lookL"):
            open(os.path.join(d, f"it_007_k16{suffix}.jpg"), "w").close()
        self.assertEqual(os.path.basename(tr.frame_for(d, 7)), "it_007_k16.jpg")


if __name__ == "__main__":
'''

edits_t = [
 ('''if __name__ == "__main__":
''', NEW_TESTS),
 # the walk now records the rescue's attempt before the lost row
 ('''        self.assertEqual(acts[-1], "lost")
        self.assertEqual(len(acts), 6 + 13, "six blind, thirteen lost, then out")
''',
  '''        self.assertEqual(acts[-2:], ["rescue-failed", "lost"])
        self.assertEqual(len(acts), 6 + 13 + 1,
                         "six blind, thirteen lost, one LOST RESCUE that "
                         "found nothing, then out")
'''),
 # ... and the rescue's step back reaches walk_leg as a second ly > 0 leg
 ('''        backs = [l for l in self.legs if l["ly"] > 0.0]
        self.assertEqual(len(backs), 1, "the back rung is one walk_leg with ly > 0")
''',
  '''        backs = [l for l in self.legs if l["ly"] > 0.0]
        self.assertEqual([b["seconds"] for b in backs], [0.5, 1.0],
                         "the ladder's back rung (BACK_SEC), then the LOST "
                         "RESCUE's (2 x BACK_SEC), both with ly POSITIVE")
'''),
]

# ------------------------------------------------ every anchor, before any write
for a, b in edits_c:
    assert c.count(a) == 1, ("chain_walk anchor", a.split("\n")[0][:70], c.count(a))
for a, b in edits_t:
    assert t.count(a) == 1, ("test anchor", a.split("\n")[0][:70], t.count(a))
for a, b in edits_cc:
    assert cc.count(a) == 1, ("collision_census anchor", a.split("\n")[0][:70], cc.count(a))
for a, b in edits_tr:
    assert tr.count(a) == 1, ("turn_review anchor", a.split("\n")[0][:70], tr.count(a))
assert "class LostRescue" in NEW_TESTS and "ScriptedWide" in NEW_TESTS
assert "class TheRescueReachesTheReaders" in NEW_TESTS
assert "rescues = 0" in edits_c[1][1]
# the three fixes the skeptics' findings bought, asserted as TEXT in the block
# that is about to be written, so a hand-edit that drops one cannot apply.
assert "now() - t0 + LOST_RESCUE_BACK_SEC < time_cap" in RESCUE
assert RESCUE.count("if now() - t0 >= time_cap:") == 1
assert "\n                    end_yaw = 0.0\n" in RESCUE
assert "\n                    turned_early = False\n" in RESCUE

for a, b in edits_c:
    c = c.replace(a, b)
for a, b in edits_t:
    t = t.replace(a, b)
for a, b in edits_cc:
    cc = cc.replace(a, b)
for a, b in edits_tr:
    tr = tr.replace(a, b)
ast.parse(c)
ast.parse(t)
ast.parse(cc)
ast.parse(tr)
open(C, "w").write(c)
open(T, "w").write(t)
open(CC, "w").write(cc)
open(TR, "w").write(tr)
print("patch43 applied to", ROOT)
