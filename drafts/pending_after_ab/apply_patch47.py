"""patch47: DOOR_STOP_EXTRA_PUSH -- one more step toward the door before the
office-door / top-of-the-stairs turn stop. Ships OFF; the A/B decides.

THE USER, watching the live stream during batch 23 (2026-09-08 09:50,
verbatim):

    "an observation, you should take 1 more step towards the door in the
    beginning of the route. saves you from rubbing against the banister."

THE CENSUS AGREES, and it is the instrument the A/B reads
(agent_progress/closed-loop/review/census_after_129_notes.md, 226 walks since
batch 16). At the turn-only stop at chain 39 the VERIFYING FIT'S SCALE says
where the character stands when it turns:

    39 verified head-on (turned / turned-aligned, 195):  scale median 1.03-1.04, dy ~300;  20 failed (10%)
    39 verified by the LOOK-AROUND (31):                 scale median 0.87-0.88, dy ~236;   9 failed (29%)
    39 unverified (2):                                   scale 0.78-0.79;                   2 failed

Scale under 1 is the scene SMALLER than the reference, i.e. the character
SHORT of the door when it turns -- and the office corridor (chain k 4-19) is
blind for the sensor on every walk: the last credible fit is at k 4-10 and the
pushes to 13, 16 and 19 are dead-reckoned, so nothing in the loop can notice.
The stairs losses of batches 17-23 all begin from that short position (b17 t9,
b18 t14, b19 t17: the look ties at ~31-34 inliers, the un-yaw goes left into
the bannister alcove or into the mouse NPC beside the newel post).

WHAT THIS ADDS: one more push along the WALKING heading, before the stop's
turn, at the same PUSH_MAG and PUSH_SEC as every other push -- no new physical
constant, no new geometry, and the stop's own verification is untouched. It
MOVES THE CHARACTER, which is the shape GRAVEYARD says has failed thirteen
times out of thirteen, so it ships OFF behind a flag and the A/B decides:

    overnight/chain_trials.py ... --arms off,on --flag DOOR_STOP_EXTRA_PUSH

with a per-trial instrument besides arrival: the fit scale of the 39 stop's
verifying fit (0.87 on the looked stops today; ~1.0 if the user is right).

-------------------------------------------------------------------------
WHAT THE REVIEW ROUND CHANGED (2026-09-08, two skeptics)

The rule itself is unchanged. Both CONFIRMED defects were the SAME defect in
two places, and it is this project's own signature shape: a reader selecting
"one iteration's own fit row" by the PROXY `r.get("iteration")`, which was
exact until this patch put TWO recorded rows under one iteration number.

  1. `tools/live_gate_census.py` -- the census that calibrates FIX_MIN /
     WEAK_MIN / STRONG (the audit round, CLAUDE.md 2026-09-07) -- would have
     counted the door step's fit as an iteration's answer, in the ARRIVED and
     FAILED populations both. That fit is taken one push BEFORE the stop is
     verified, so it is a mid-iteration position, and the iteration that has
     one would be weighted twice. Its second half, which neither skeptic
     separated out: the same loop globs `it_NNN_k*.jpg` UNSORTED and matches
     `fs[0]` against a window 30 ahead, so on a door-step iteration `fs[0]`
     was whichever of the two frames the filesystem happened to list first.
     `turn_review.frame_for` already fixed exactly that shape once.
     Both rules are now named functions the suite runs out of the file.

  2. `chain_walk._timeout_diagnosis` counted the door-step row as an
     iteration and took its median over the row's PARTIAL elapsed seconds, so
     a TIMED-OUT trial with the flag on reported more iterations than the walk
     ran -- in the string that decides ARITHMETIC vs NAVIGATION.

And one the skeptics recorded as disclosed-and-cosmetic, fixed because the
tool is the user's standing review rule: `tools/trial_sheet.py` looked its
label up by iteration number and took the FIRST row, which on a door-step
iteration is the door step's -- so the STOP'S OWN frame, the one a reader is
asked to judge the turn on, was labelled "door-step". 10.1's output that
looks like evidence and is not. Its frame order is now deterministic too.

Apply:  .venv/bin/python -B drafts/pending_after_ab/apply_patch47.py [ROOT]
Refuses a second run. All anchors are asserted BEFORE any file is written.
"""
import ast, os, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
C = os.path.join(ROOT, "chain_walk.py")
T = os.path.join(ROOT, "tests", "routing", "test_chain_walk.py")
G = os.path.join(ROOT, "tools", "live_gate_census.py")
S = os.path.join(ROOT, "tools", "trial_sheet.py")
c = open(C).read()
t = open(T).read()
g = open(G).read()
s = open(S).read()

if ("DOOR_STOP_EXTRA_PUSH" in c or "DOOR_STOP_EXTRA_PUSH" in t
        or "is_iteration_fit_row" in g or "def row_for" in s):
    raise SystemExit("ALREADY APPLIED")

# --------------------------------------------------------------------------
# chain_walk.py -- the rule
# --------------------------------------------------------------------------

CONST_ANCHOR = "STOP_TIE_DX_PX = 120.0\n"

CONST_NEW = CONST_ANCHOR + '''# ONE MORE STEP TOWARD THE DOOR BEFORE THE OFFICE-DOOR STOP TURNS (ships OFF;
# the A/B decides).
#
# THE USER, watching the live stream during batch 23 (2026-09-08 09:50,
# verbatim): "an observation, you should take 1 more step towards the door in
# the beginning of the route. saves you from rubbing against the banister."
#
# THE STOP'S OWN FIT SCALE SAYS THE SAME THING, and it is this rule's
# instrument (agent_progress/closed-loop/review/census_after_129_notes.md,
# 226 walks since batch 16):
#     39 verified head-on (195 walks)      scale median 1.03-1.04   10% failed
#     39 verified by the LOOK-AROUND (31)  scale median 0.87-0.88   29% failed
#     39 unverified (2)                    scale 0.78-0.79          both failed
# Scale under 1 is the scene SMALLER than the reference: the character SHORT
# of the door when it turns. The corridor is blind for the sensor on every
# walk -- the last credible fit is at chain 4-10 and the pushes to 13, 16 and
# 19 are dead-reckoned -- so nothing in the loop can notice, and the stairs
# losses of batches 17-23 all begin from that short position (the turn goes
# into the bannister alcove, or into the mouse NPC beside the newel post).
#
# HOW FAR ONE PUSH IS, READ OFF THE CHAIN ITSELF rather than chosen: the
# corridor's push targets are 10, 13, 16 and 19, one PLAN_STEP_UNITS apart,
# and the 39 stop's own stationary run spans waypoints 21..39 (the human
# standing still and turning). So one more PUSH_MAG x PUSH_SEC push carries
# the character about three recorded frames -- from waypoint 19's spot INTO
# the span the recording turned in, not past it.
#
# WHAT IT CANNOT DO, said plainly: the step is taken BEFORE the stop's turn,
# so it cannot be conditioned on the stop's fit -- that fit is only measured
# after the turn, and the 195 head-on walks that already stand at scale 1.03
# get the step too. Gating on the scale would need a number inside a
# population the loop cannot read until it is too late to act on it (10.4).
# That cost is exactly what the A/B weighs, and the `door-step` row carries
# the fit taken right after the push, so the on arm's own rows say whether it
# overshoots rather than leaving it to be argued about.
#
# It MOVES THE CHARACTER, which is the shape GRAVEYARD closed thirteen times
# out of thirteen (both survivors move nothing), so it ships OFF and an A/B
# decides: `--arms off,on --flag DOOR_STOP_EXTRA_PUSH`.
DOOR_STOP_EXTRA_PUSH = False
# THE STOP IT APPLIES TO, AND IT IS CHAIN-SPECIFIC: 39 is the office-door /
# top-of-the-stairs turn-only stop of chains/route_user_1853, the drive every
# batch walks. It is an index into THAT recording and not a property of the
# world -- another chain's door stop is another number, and a chain with no
# stop there leaves the rule dormant, because no plan entry ever equals it.
DOOR_STOP_INDEX = 39
# How many extra pushes. ONE, because one step is what the user asked for.
DOOR_STOP_EXTRA_PUSHES = 1
# THE ACTION THE EXTRA PUSH RECORDS, and the reason it is a name and not a
# bare literal: it is the FIRST row this module has ever written that shares
# an iteration number with another row, and three readers select "one
# iteration's own fit" by asking whether a row HAS an iteration number --
# `_timeout_diagnosis` below, `tools/live_gate_census.py`, and
# `tools/trial_sheet.py`. That proxy was exact until this row existed. Each
# of those three now excludes this action by name, and each has a test.
DOOR_STEP_ACTION = "door-step"
'''

INIT_ANCHOR = ("    walk_heading = None         # the last heading a push was made along\n"
               "    last_cmd = None             # the last heading actually commanded\n")

INIT_NEW = INIT_ANCHOR + (
    "    door_stepped = False        # this SERVICING of DOOR_STOP_INDEX has had\n"
    "                                # its extra push (DOOR_STOP_EXTRA_PUSH)\n")

STEP_ANCHOR = "        turned = False\n        if heading is not None and (\n"

STEP_NEW = '''        # ONE MORE STEP TOWARD THE DOOR (DOOR_STOP_EXTRA_PUSH), BEFORE THE
        # TURN AND NOT AFTER. The point is to reach the stop and turn THERE:
        # the user watched the loop turn short and rub along the banister, and
        # the stop's verifying fit scale of 0.87 on the looked stops measures
        # the same thing. A push taken AFTER the turn would run along the
        # STOP'S heading -- into the stairs -- which is the opposite change.
        #
        # ONCE PER SERVICING. A turn-back, a turn-wait and a turn-retry all
        # come round the loop to this same plan entry, and that is the same
        # stop, not a second step; `door_stepped` is cleared only by an
        # iteration that services something else, so a re-approach after a
        # rescue or a look-back regression -- which walks other targets to get
        # back here -- takes the step again, deliberately. A stop the plan
        # SKIPS (a wide relocalisation carrying k past it) is never unpacked
        # as `plan[pi]` at all, so this cannot fire on one.
        #
        # Nothing else changes for the WALK: the push is the ordinary
        # PUSH_MAG/PUSH_SEC one along the heading the walk arrived on, its
        # frame is captured and recorded as evidence, and the stop is then
        # turned to and verified exactly as before. The row is evidence only --
        # it moves no counter, spends no blind budget and gates nothing.
        #
        # IT DOES CHANGE ONE THING FOR THE READERS, and that is why
        # DOOR_STEP_ACTION exists: this row shares its iteration number with
        # the row that resolves the stop, and it is recorded FIRST. Every
        # reader that selected an iteration's own fit by "does this row carry
        # an iteration number" now excludes this action by name.
        servicing_door_stop = not do_push and target_k == DOOR_STOP_INDEX
        if not servicing_door_stop:
            door_stepped = False
        elif (DOOR_STOP_EXTRA_PUSH and not door_stepped
                and walk_heading is not None):
            door_stepped = True
            for step_i in range(1, max(1, int(DOOR_STOP_EXTRA_PUSHES)) + 1):
                if (last_cmd is None
                        or abs((walk_heading - last_cmd + 540.0) % 360.0 - 180.0)
                        > TURN_SKIP_DEG):
                    turn_to(walk_heading)
                    last_cmd = walk_heading
                push(PUSH_MAG, PUSH_SEC)
                res["pushes"] += 1
                img_d = capture()
                _save(shots, iteration, k, img_d, log, suffix=f"_door{step_i}")
                fix_d = chain.locate(img_d, target_k)
                inl_d = 0 if fix_d is None else (getattr(fix_d, "inliers", 0) or 0)
                sc_d = None if fix_d is None else getattr(fix_d, "scale", None)
                sc_d = None if sc_d is None else round(float(sc_d), 2)
                record({"iteration": iteration, "k": k, "target": target_k,
                        "fix": _fix_row(fix_d), "action": DOOR_STEP_ACTION,
                        "lateral": None,
                        "door_step": {"n": step_i,
                                      "heading": round(walk_heading, 1)},
                        "at_end": False,
                        "seconds": round(now() - it_t0, 2),
                        "elapsed": round(now() - t0, 2)})
                log(f"    it {iteration:3d}  k={k:3d} -> {target_k:3d}  "
                    f"door-step {step_i}/{DOOR_STOP_EXTRA_PUSHES}: one more "
                    f"push along {walk_heading:.1f} before the stop turns "
                    f"(the frame after it fits {inl_d} inliers, scale {sc_d})")

''' + STEP_ANCHOR

# --------------------------------------------------------------------------
# chain_walk.py -- the first reader: the timeout diagnosis
# --------------------------------------------------------------------------

DIAG_ANCHOR = '    per = sorted(r["seconds"] for r in res["fixes"] if r.get("iteration"))\n'

DIAG_NEW = ('''    # ONE ITERATION'S OWN ROW, NOT EVERY ROW CARRYING ITS NUMBER. A
    # DOOR_STEP_ACTION row is an extra push taken INSIDE an iteration: it
    # shares the iteration's number with the row that resolves the stop, and
    # its `seconds` is the PARTIAL elapsed time up to the push, not a whole
    # iteration. Counted here it reported more iterations than the walk ran
    # (`res["iterations"]` is the loop's own counter and is right) and pulled
    # the median down -- inside the string that decides ARITHMETIC against
    # NAVIGATION, which is the whole reason this function exists.
    per = sorted(r["seconds"] for r in res["fixes"]
                 if r.get("iteration") and r.get("action") != DOOR_STEP_ACTION)
''')

# --------------------------------------------------------------------------
# tools/live_gate_census.py -- the second reader: the gate populations
# --------------------------------------------------------------------------

GATE_HEAD_ANCHOR = 'ch = chain.Chain.load("chains/route_user_1853", log=lambda m: None)\n'

GATE_HEAD_NEW = '''
def is_iteration_fit_row(r):
    """Is this row ONE ITERATION'S OWN in-window fit -- the unit of this census?

    A row carrying a fit and an iteration number WAS that, exactly, until
    2026-09-08. `chain_walk.DOOR_STOP_EXTRA_PUSH` breaks the equivalence: a
    `door-step` row is an extra push taken INSIDE an iteration, fitted at a
    position the walk has not yet verified as the stop, and it shares its
    iteration number with the stop's own row. Counted here it would weight the
    iterations that have one twice over and mix a mid-iteration fit into the
    very populations FIX_MIN / WEAK_MIN / STRONG are calibrated against -- a
    gate landing inside a population it was not measured on (CLAUDE.md 10.4),
    arriving by the back door of an unrelated patch.

    Named rather than inlined so the suite can run it: this file does its work
    at module level and cannot be imported, so
    tests/routing/test_chain_walk.py compiles this definition out of the file
    and drives it with the rows a real walk records.
    """
    f = r.get("fix")
    return bool(f and f.get("inliers") is not None and r.get("iteration")
                and r.get("action") != "door-step")


def frame_for(shots, iteration):
    """The iteration's OWN frame -- SORTED, because an iteration saves several.

    A rescue saves its three look frames beside the iteration's own, and a
    door step saves `_door1`. This census matches ONE frame per sampled
    iteration against a window 30 ahead, and an unsorted glob handed it
    whichever the filesystem listed first -- so the FAR population could be
    measured on a frame taken at a different spot in the same iteration. The
    base name sorts before any suffix ("." < "_"). Same fix, same reason, as
    `turn_review.frame_for`.
    """
    fs = sorted(glob.glob(os.path.join(shots, f"it_{int(iteration):03d}_k*.jpg")))
    return fs[0] if fs else None


''' + GATE_HEAD_ANCHOR

GATE_LOOP_ANCHOR = '''        f = r.get("fix")
        if not f or f.get("inliers") is None or not r.get("iteration"):
            continue
        (near_arr if arrived else near_fail).append(int(f["inliers"]))
        if r["iteration"] % 4:
            continue
        fs = glob.glob(os.path.join(d, f"it_{int(r['iteration']):03d}_k*.jpg"))
        if not fs:
            continue
        k = int(r["k"])
        hint = k + 30 if k + 33 < n else max(0, k - 33)
        fx = ch.locate(Image.open(fs[0]), hint, window=3)
'''

GATE_LOOP_NEW = '''        if not is_iteration_fit_row(r):
            continue
        (near_arr if arrived else near_fail).append(int(r["fix"]["inliers"]))
        if r["iteration"] % 4:
            continue
        fp = frame_for(d, r["iteration"])
        if fp is None:
            continue
        k = int(r["k"])
        hint = k + 30 if k + 33 < n else max(0, k - 33)
        fx = ch.locate(Image.open(fp), hint, window=3)
'''

# --------------------------------------------------------------------------
# tools/trial_sheet.py -- the third reader: the label a human is shown
# --------------------------------------------------------------------------

SHEET_HEAD_ANCHOR = 'def main(tn, log=os.path.join(ROOT, "overnight", "chain_trials.log")):\n'

SHEET_HEAD_NEW = '''def row_for(rows, path):
    """The journal row THIS FRAME belongs to.

    An iteration has always been able to save more than one FRAME (a rescue's
    three looks), and since `chain_walk.DOOR_STOP_EXTRA_PUSH` it can record
    more than one ROW: the door step's row shares the stop's iteration number
    and is written FIRST. Looking the label up by number alone therefore put
    "door-step" on the STOP'S OWN frame -- the frame the user's standing rule
    asks a reader to judge the turn on. A label that reads as evidence and is
    not is CLAUDE.md 10.1, and this tool is where a reader meets it.

    Falls back to the iteration's first row, so a frame with no door step, or
    a suffix nothing has taught this function about, labels as it always did.
    """
    base = os.path.basename(path)
    itn = int(re.search(r"it_(\\d+)_", base).group(1))
    here = [r for r in rows if r["iteration"] == itn]
    extra = "_door" in base
    return next((r for r in here if (r.get("action") == "door-step") == extra),
                here[0] if here else None)


''' + SHEET_HEAD_ANCHOR

SHEET_LOOP_ANCHOR = '''    fs = sorted(glob.glob(os.path.join(d, "it_[0-9][0-9][0-9]_k*[0-9].jpg")), key=lambda p: int(re.search(r"it_(\\d+)_", p).group(1)))
    ims = []
    for p in fs[::3]:
        im = cv2.resize(cv2.imread(p), (320, 180)); itn = int(re.search(r"it_(\\d+)_", p).group(1))
        row = next((r for r in rows if r["iteration"] == itn), None)
'''

SHEET_LOOP_NEW = '''    fs = sorted(glob.glob(os.path.join(d, "it_[0-9][0-9][0-9]_k*[0-9].jpg")), key=lambda p: (int(re.search(r"it_(\\d+)_", p).group(1)), p))
    ims = []
    for p in fs[::3]:
        im = cv2.resize(cv2.imread(p), (320, 180)); itn = int(re.search(r"it_(\\d+)_", p).group(1))
        row = row_for(rows, p)
'''

# --------------------------------------------------------------------------
# tests/routing/test_chain_walk.py
# --------------------------------------------------------------------------

TEST_ANCHOR = "class NeverTouchesTheForbidden(unittest.TestCase):\n"

TEST_NEW = r'''class DoorStopExtraPush(unittest.TestCase):
    """(o) ONE MORE STEP TOWARD THE DOOR before the office-door stop turns.

    The user, watching the live stream during batch 23 (2026-09-08, verbatim):
    "an observation, you should take 1 more step towards the door in the
    beginning of the route. saves you from rubbing against the banister."

    The census says the same thing (agent_progress/closed-loop/review/
    census_after_129_notes.md, 226 walks): the chain-39 stop verified head-on
    fits at scale 1.03 and fails 10% of the time; verified only by the
    look-around it fits at 0.87 -- the scene 13% smaller than the reference,
    i.e. the character SHORT of the door -- and fails 29%. The corridor is
    blind for the sensor (last credible fit at k 4-10; 13/16/19 dead-reckoned),
    so the loop cannot see that it stopped short.

    The flag ships OFF and the A/B decides, so these tests drive it BOTH ways
    and pin the OFF path's console events as literals: a mutant that ignores
    the flag must fail here.

    AND THE ROW IT ADDS IS THE FIRST IN THIS MODULE TO SHARE AN ITERATION
    NUMBER WITH ANOTHER ROW. Three readers -- `_timeout_diagnosis`,
    `tools/live_gate_census.py` and `tools/trial_sheet.py` -- selected "one
    iteration's own fit" by asking whether a row carried an iteration number,
    a proxy that was exact until now. The last four tests here are those
    readers, driven with the rows and the frames a REAL walk writes, because a
    row nobody reads correctly is CLAUDE.md 10.1's evidence that is not.

    THE CHAIN. wp2 is the turn-only stop (ly = 0.0, a stationary run of one),
    reached after one walking push at 90 deg; the pushes after it carry 10 deg,
    so every turn shows up in the event list as its own entry.
    """

    ROWS = [(90.0, -0.35), (0.0, 0.0), (10.0, -0.35), (10.0, -0.35)]

    def _wps(self, rows=None):
        wps = [Wp(0, 90.0)]
        for i, (h, ly) in enumerate(rows or self.ROWS, start=1):
            w = Wp(i, h)
            w.lx = 0.0
            w.ly = ly
            wps.append(w)
        return wps

    def _rig(self, wps, fixes, table_at, wide=None, lookback="script"):
        ch = FakeChain(len(wps), fixes, default=None, wide=wide,
                       lookback=lookback)
        ch.waypoints = wps
        return Rig(ch, table_at=table_at)

    def _at(self, index):
        """Point the rule at THIS chain's stop, restored afterwards."""
        prev = chain_walk.DOOR_STOP_INDEX
        chain_walk.DOOR_STOP_INDEX = index
        self.addCleanup(setattr, chain_walk, "DOOR_STOP_INDEX", prev)

    def _flag(self, on):
        prev = chain_walk.DOOR_STOP_EXTRA_PUSH
        chain_walk.DOOR_STOP_EXTRA_PUSH = on
        self.addCleanup(setattr, chain_walk, "DOOR_STOP_EXTRA_PUSH", prev)

    # ---- the constants -----------------------------------------------------

    def test_the_flag_ships_OFF_and_the_index_is_this_chains_door_stop(self):
        # Literals (10.11): a test that reads the constant it guards passes
        # forever. 39 is chains/route_user_1853's office-door stop and ONE
        # push is what the user asked for.
        self.assertIs(chain_walk.DOOR_STOP_EXTRA_PUSH, False)
        self.assertEqual(chain_walk.DOOR_STOP_INDEX, 39)
        self.assertEqual(chain_walk.DOOR_STOP_EXTRA_PUSHES, 1)
        self.assertEqual(chain_walk.DOOR_STEP_ACTION, "door-step")
        # It invents no physical constant: the push is the ordinary one.
        self.assertEqual(chain_walk.PUSH_MAG, 0.45)
        self.assertEqual(chain_walk.PUSH_SEC, 0.40)

    def test_the_plan_this_class_uses_has_its_stop_where_it_says(self):
        # ANTI-VACUITY for every test below: if the plan had no turn-only
        # target at 2, "no extra push" would pass for the wrong reason.
        self.assertEqual(chain_walk.plan_indices(self._wps()),
                         [(1, True, 90.0), (2, False, 0.0), (3, True, 10.0),
                          (4, True, 10.0)])

    # ---- the OFF path, pinned as literals ----------------------------------

    def test_with_the_flag_OFF_the_console_sequence_is_UNCHANGED(self):
        # THE CONTROL, and the shipped path. Every console call, in order.
        self._flag(False)
        self._at(2)
        rig = self._rig(self._wps(),
                        [Fix(k=1), Fix(k=2, inliers=200)], table_at=4)
        res = rig.go()
        self.assertEqual(rig.events, [
            ("capture", 1), ("at_table", 1, False),
            ("turn", 90.0), ("push", 0.45, 0.4),
            ("capture", 2), ("at_table", 2, False),
            ("turn", 0.0), ("capture", 3), ("at_table", 3, False),
            ("turn", 10.0), ("push", 0.45, 0.4),
            ("capture", 4), ("at_table", 4, True)])
        self.assertEqual([f["action"] for f in res["fixes"]],
                         ["advanced", "turned", "arrived"])
        self.assertEqual(res["pushes"], 2)
        self.assertTrue(res["arrived"])

    # ---- the ON path -------------------------------------------------------

    def _walk_with_a_door_step(self, shots=None):
        """ONE REAL WALK with the flag on, whose rows the readers below read.

        Nothing about the readers' tests is hand-written: the rows, their
        iteration numbers and the frame names all come from this walk, so a
        renamed action or a renamed suffix breaks them rather than passing.
        """
        self._flag(True)
        self._at(2)
        rig = self._rig(self._wps(),
                        [Fix(k=1), Fix(k=2, inliers=90, scale=0.87),
                         Fix(k=2, inliers=200)], table_at=5)
        res = rig.go(**({"shots": shots} if shots else {}))
        self.assertEqual([f["action"] for f in res["fixes"]],
                         ["advanced", "door-step", "turned", "arrived"])
        return res

    def test_the_extra_push_comes_BEFORE_the_stops_turn_and_only_once(self):
        # The same walk with the flag on: ONE more push, along the WALKING
        # heading (90, already commanded, so no turn of its own), before the
        # turn to the stop's 0.0 -- and the stop then verifies exactly as it
        # did with the flag off.
        self._flag(True)
        self._at(2)
        rig = self._rig(self._wps(),
                        [Fix(k=1), Fix(k=2, inliers=90, scale=0.87),
                         Fix(k=2, inliers=200)], table_at=5)
        res = rig.go()
        self.assertEqual(rig.events, [
            ("capture", 1), ("at_table", 1, False),
            ("turn", 90.0), ("push", 0.45, 0.4),
            ("capture", 2), ("at_table", 2, False),
            ("push", 0.45, 0.4), ("capture", 3),          # THE DOOR STEP
            ("turn", 0.0), ("capture", 4), ("at_table", 4, False),
            ("turn", 10.0), ("push", 0.45, 0.4),
            ("capture", 5), ("at_table", 5, True)])
        pushes = [i for i, e in enumerate(rig.events) if e[0] == "push"]
        turn0 = next(i for i, e in enumerate(rig.events)
                     if e[0] == "turn" and e[1] == 0.0)
        self.assertEqual(len([i for i in pushes if i < turn0]), 2,
                         "the walking push and the door step, both before the "
                         "stop's turn")
        self.assertEqual([f["action"] for f in res["fixes"]],
                         ["advanced", "door-step", "turned", "arrived"])
        self.assertEqual(res["pushes"], 3, "the door step counts as a push")
        self.assertTrue(res["arrived"])

    def test_the_extra_push_is_commanded_along_the_WALKING_heading(self):
        # WHICH WAY THE STEP GOES, pinned where it can be seen. In the test
        # above the walking heading is ALREADY the commanded one, so the step
        # needs no turn of its own and the event list cannot say which heading
        # it would have used -- and a step run along the STOP'S heading would
        # go into the stairs, the exact opposite of this change. With the
        # turn-skip off every turn is commanded, so the step's own heading is
        # on the list: 90, the heading the walk arrived on, not the stop's 0.
        self._flag(True)
        self._at(2)
        rig = self._rig(self._wps(),
                        [Fix(k=1), Fix(k=2, inliers=90, scale=0.87),
                         Fix(k=2, inliers=200)], table_at=5)
        res = always_turning(rig.go)
        self.assertEqual(rig.events, [
            ("capture", 1), ("at_table", 1, False),
            ("turn", 90.0), ("push", 0.45, 0.4),
            ("capture", 2), ("at_table", 2, False),
            ("turn", 90.0), ("push", 0.45, 0.4),           # THE DOOR STEP
            ("capture", 3),
            ("turn", 0.0), ("capture", 4), ("at_table", 4, False),
            ("turn", 10.0), ("push", 0.45, 0.4),
            ("capture", 5), ("at_table", 5, True)])
        self.assertEqual([f["action"] for f in res["fixes"]],
                         ["advanced", "door-step", "turned", "arrived"])

    def test_the_door_step_row_carries_its_own_fix_and_says_which_push_it_was(self):
        # The row is EVIDENCE: the fit after the extra push is what the A/B's
        # instrument (the stop's fit scale) is read from, so it is recorded
        # rather than thrown away (10.1, "a measurement taken and discarded").
        self._flag(True)
        self._at(2)
        rig = self._rig(self._wps(),
                        [Fix(k=1), Fix(k=2, inliers=90, scale=0.87),
                         Fix(k=2, inliers=200)], table_at=5)
        res = rig.go()
        row = res["fixes"][1]
        self.assertEqual(row["action"], "door-step")
        self.assertEqual(row["k"], 1, "k is untouched by the extra push")
        self.assertEqual(row["target"], 2)
        self.assertIsNone(row["lateral"])
        self.assertEqual(row["door_step"], {"n": 1, "heading": 90.0})
        self.assertEqual(row["fix"]["inliers"], 90)
        self.assertEqual(row["fix"]["scale"], 0.87)
        self.assertEqual(rig.chain.locate_calls[1], 2,
                         "the door step's frame is located against the STOP, "
                         "which is the scene it was pushed toward")
        self.assertEqual(rig.strafes(), [], "it steers nothing")

    def test_a_stop_that_is_not_the_DOOR_STOP_gets_no_extra_push(self):
        # THE MUTANT THIS EXISTS FOR: a rule that fires at every stop. With
        # the flag ON and the index pointing somewhere this chain never
        # reaches, the sequence is the OFF one, call for call.
        self._flag(True)
        self._at(7)
        rig = self._rig(self._wps(),
                        [Fix(k=1), Fix(k=2, inliers=200)], table_at=4)
        res = rig.go()
        self.assertEqual(rig.events, [
            ("capture", 1), ("at_table", 1, False),
            ("turn", 90.0), ("push", 0.45, 0.4),
            ("capture", 2), ("at_table", 2, False),
            ("turn", 0.0), ("capture", 3), ("at_table", 3, False),
            ("turn", 10.0), ("push", 0.45, 0.4),
            ("capture", 4), ("at_table", 4, True)])
        self.assertNotIn("door-step", [f["action"] for f in res["fixes"]])
        self.assertEqual(res["pushes"], 2)

    def test_one_door_step_per_SERVICING_however_often_the_stop_comes_round(self):
        # A stop whose frame fits nothing is served again and again -- one step
        # back, one wait, then a retry push -- and every one of those returns
        # to this same plan entry. That is the SAME stop, not four more steps.
        self._flag(True)
        self._at(2)
        wps = self._wps([(90.0, -0.35), (0.0, 0.0), (0.0, -0.35), (0.0, -0.35)])

        def tied_at(k):
            # Credible, and NOT verification: a near-tied runner-up at another
            # place whose dx disagrees. The one shape that buys a retry (see
            # test_a_turn_stop_that_does_not_match_is_retried_after_one_more_push).
            f = Fix(k=k, inliers=90, second=90)
            f.second_k, f.second_dx = 8, 900.0
            return f

        # it1 push -> Fix(1); the door step's own frame; then the stop reads a
        # credible TIE at the EARLIER waypoint 1 three times, with both looks
        # blank each time (back, wait, retry), and the fourth read verifies.
        rig = self._rig(wps, [Fix(k=1), Fix(k=2, inliers=90, scale=0.87),
                              tied_at(1), None, None,   # stop + both looks
                              tied_at(1), None, None,   # ... after the step back
                              tied_at(1), None, None,   # ... after the wait
                              Fix(k=2, inliers=200)], table_at=99,
                        lookback=None)
        res = without_stuck(rig.go, time_cap=60.0)
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:5], ["advanced", "door-step", "turn-back",
                                    "turn-wait", "turn-retry"], acts)
        self.assertEqual(acts.count("door-step"), 1,
                         "one servicing of the stop, one step toward the door")
        self.assertIn("turned", acts, "ANTI-VACUITY: the stop was serviced "
                                      "four times and did verify in the end")

    def test_a_stop_SKIPPED_by_a_relocalisation_takes_no_step(self):
        # The pointer walks over a turn-only entry when a wide relocalisation
        # carries k past it: no turn_to, no push, no stop. The step must not
        # fire for a stop the walk never serviced.
        self._flag(True)
        self._at(5)
        rows = [(90.0, -0.35)] * 4 + [(0.0, 0.0)] + [(10.0, -0.35)] * 3
        wps = self._wps(rows)
        self.assertEqual([p for p in chain_walk.plan_indices(wps) if not p[1]],
                         [(5, False, 0.0)], "the stop is at 5")
        rig = self._rig(wps, [], table_at=4,
                        wide=Fix(k=7, inliers=170, second=20))
        res = rig.go()
        acts = [f["action"] for f in res["fixes"]]
        self.assertEqual(acts[:2], ["blind-advance", "relocalised"], acts)
        self.assertNotIn("door-step", acts)
        self.assertEqual([f["k"] for f in res["fixes"]][1], 7,
                         "ANTI-VACUITY: k really did jump past the stop at 5")

    # ---- the three readers of the row it adds ------------------------------
    #
    # Found by two skeptics reviewing this patch, and both were the SAME
    # defect: a reader selecting "one iteration's own fit row" with the proxy
    # `r.get("iteration")`. That proxy was exact until this patch recorded a
    # second row under one iteration number.

    @staticmethod
    def _tool_funcs(rel, *names):
        """Run named top-level functions OUT of a tool that is a SCRIPT.

        `tools/live_gate_census.py` does its work at module level -- it loads
        the chain and globs every journal as it imports -- so the suite cannot
        import it the way `TheRescueReachesTheReaders` imports
        collision_census. Compiling ITS OWN FunctionDef nodes and nothing else
        runs the real source of the rules under test, so a mutant in either
        one fails here, without running the census.

        It never skips: a missing file or a missing function is a failure that
        names the fix.
        """
        import glob as _glob
        import re as _re
        path = os.path.join(_ROOT, *rel)
        assert os.path.exists(path), f"{path} is missing"
        tree = ast.parse(open(path).read(), path)
        ns = {"glob": _glob, "os": os, "re": _re, "json": json}
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in names:
                exec(compile(ast.Module(body=[node], type_ignores=[]),
                             path, "exec"), ns)
        missing = [n for n in names if n not in ns]
        assert not missing, f"{path} defines no {missing}"
        return [ns[n] for n in names]

    def test_the_timeout_diagnosis_counts_ITERATIONS_not_ROWS(self):
        # `_timeout_diagnosis` is the string that decides whether a TIMED OUT
        # trial was the CHAIN's length or the WALKING -- 10.1's "two paths
        # with identical output", and the fix for each is the opposite of the
        # other. Its population was every row carrying an iteration number, so
        # the door step made it report one iteration too many and took the
        # median over the door step's PARTIAL elapsed seconds.
        res = self._walk_with_a_door_step()
        with_it = [r for r in res["fixes"] if r.get("iteration")]
        self.assertEqual(len({r["iteration"] for r in with_it}),
                         len(with_it) - 1,
                         "ANTI-VACUITY: exactly one iteration has two rows")
        msg = chain_walk._timeout_diagnosis(res, 5, 1, 1000.0)
        self.assertTrue(msg.startswith("NAVIGATION"), msg)
        self.assertIn(f"{len(with_it) - 1} iterations", msg)
        self.assertNotIn(f"{len(with_it)} iterations", msg)
        own = sorted(r["seconds"] for r in with_it
                     if r["action"] != "door-step")
        self.assertIn(f"median {own[len(own) // 2]:.2f}s", msg,
                      "and the median is over whole iterations")

    def test_the_gate_census_does_not_take_the_door_step_for_an_iterations_fit(self):
        # `tools/live_gate_census.py` builds the populations FIX_MIN /
        # WEAK_MIN / STRONG are calibrated against (the audit round). The door
        # step's fit is taken one push BEFORE the stop is verified -- a
        # mid-iteration position the walk has not accepted -- and it would
        # have entered NEAR twice for one iteration.
        is_fit, = self._tool_funcs(("tools", "live_gate_census.py"),
                                   "is_iteration_fit_row")
        res = self._walk_with_a_door_step()
        by_action = {r["action"]: r for r in res["fixes"]}
        self.assertFalse(is_fit(by_action["door-step"]))
        self.assertTrue(is_fit(by_action["advanced"]),
                        "ANTI-VACUITY: a real fit row is still counted")
        self.assertTrue(is_fit(by_action["turned"]))
        # ... and the rules it already had are still rules.
        self.assertFalse(is_fit({"iteration": 3, "fix": None}))
        self.assertFalse(is_fit({"iteration": 3, "fix": {"inliers": None}}))
        self.assertFalse(is_fit({"iteration": 0, "fix": {"inliers": 90}}))

    def test_the_gate_census_reads_the_iterations_OWN_frame(self):
        # The second half of the same contamination, and it is the FAR
        # population: the census globs `it_NNN_k*.jpg` UNSORTED and matches
        # `fs[0]` against a window 30 ahead. A door-step iteration saves two
        # frames, taken one push apart, so `fs[0]` was whichever the
        # filesystem listed first. `turn_review.frame_for` fixed exactly this
        # shape once already, for the rescue's three look frames.
        import glob as _glob
        import re as _re
        frame_for, = self._tool_funcs(("tools", "live_gate_census.py"),
                                      "frame_for")
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        self._walk_with_a_door_step(shots=d)
        doors = _glob.glob(os.path.join(d, "*_door*.jpg"))
        self.assertEqual(len(doors), 1,
                         "ANTI-VACUITY: the walk saved one door-step frame")
        itn = int(_re.search(r"it_(\d+)_",
                             os.path.basename(doors[0])).group(1))
        both = _glob.glob(os.path.join(d, f"it_{itn:03d}_k*.jpg"))
        self.assertEqual(len(both), 2,
                         "ANTI-VACUITY: that iteration has two frames on disk")
        base = [p for p in both if "_door" not in os.path.basename(p)]
        self.assertEqual(frame_for(d, itn), base[0])
        self.assertIsNone(frame_for(d, 999), "no frames, no answer")
        # ... and NOT because of the order a walk happens to write them in.
        # A walk writes the iteration's own frame first, so an unsorted glob
        # would answer correctly here and be wrong the moment anything else
        # touched the directory. Written door-first, it answers wrongly.
        d2 = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d2)
        for suffix in ("_door1", "_rescue_look0", ""):
            open(os.path.join(d2, f"it_007_k16{suffix}.jpg"), "w").close()
        self.assertEqual(os.path.basename(frame_for(d2, 7)), "it_007_k16.jpg")

    def test_the_gate_census_actually_CALLS_the_two_rules(self):
        # A rule a script defines and does not use is 10.1's no-op that looks
        # like a fix. The script's body cannot be imported, so the check is on
        # its own parse tree: with the function definitions taken out, both
        # names must still be CALLED by what remains.
        path = os.path.join(_ROOT, "tools", "live_gate_census.py")
        tree = ast.parse(open(path).read(), path)
        body = [n for n in tree.body if not isinstance(n, ast.FunctionDef)]
        called = {n.func.id for st in body for n in ast.walk(st)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn("desc", called,
                      "ANTI-VACUITY: this scan can see the script's own calls")
        self.assertIn("is_iteration_fit_row", called)
        self.assertIn("frame_for", called)

    def test_the_trial_sheet_labels_each_frame_with_ITS_OWN_row(self):
        # trial_sheet is what the user's standing rule runs on every failed
        # trial, and a reader agent judges the turn from the label. It looked
        # the label up by iteration number and took the FIRST row -- which on
        # a door-step iteration is the door step's -- so the STOP'S OWN frame
        # was labelled "door-step". Loaded BY PATH, like the other tests of
        # this tool, so it cannot pick up another module of the same name.
        import glob as _glob
        import importlib.util
        import re as _re
        spec = importlib.util.spec_from_file_location(
            "trial_sheet_door_step", os.path.join(_ROOT, "tools",
                                                  "trial_sheet.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        rows = self._walk_with_a_door_step(shots=d)["fixes"]
        door = _glob.glob(os.path.join(d, "*_door*.jpg"))[0]
        itn = int(_re.search(r"it_(\d+)_", os.path.basename(door)).group(1))
        base = [p for p in _glob.glob(os.path.join(d, f"it_{itn:03d}_k*.jpg"))
                if "_door" not in os.path.basename(p)][0]
        self.assertEqual(mod.row_for(rows, door)["action"], "door-step")
        self.assertEqual(mod.row_for(rows, base)["action"], "turned",
                         "the stop's own frame keeps the stop's own outcome")
        # THE CONTROL, and it is the strong form: every frame that is NOT the
        # door step's labels EXACTLY as the old lookup labelled it -- including
        # `it_000`, the frame saved before the first iteration, which has no
        # row of its own and never had one.

        def old(path):
            n = int(_re.search(r"it_(\d+)_", os.path.basename(path)).group(1))
            return next((r for r in rows if r["iteration"] == n), None)

        others = [p for p in _glob.glob(os.path.join(d, "it_*_k*.jpg"))
                  if f"it_{itn:03d}_" not in os.path.basename(p)]
        self.assertTrue(others, "ANTI-VACUITY: the walk saved other frames")
        self.assertIn(None, [old(p) for p in others],
                      "ANTI-VACUITY: it_000 has no row, then as now")
        for p in others:
            self.assertEqual(mod.row_for(rows, p), old(p))


'''

# --------------------------------------------------------------------------
# assert EVERY anchor, exactly once, BEFORE any write (10.19)
# --------------------------------------------------------------------------
for name, hay, anchor in (("chain_walk CONST", c, CONST_ANCHOR),
                          ("chain_walk INIT", c, INIT_ANCHOR),
                          ("chain_walk STEP", c, STEP_ANCHOR),
                          ("chain_walk DIAG", c, DIAG_ANCHOR),
                          ("test ANCHOR", t, TEST_ANCHOR),
                          ("gate HEAD", g, GATE_HEAD_ANCHOR),
                          ("gate LOOP", g, GATE_LOOP_ANCHOR),
                          ("sheet HEAD", s, SHEET_HEAD_ANCHOR),
                          ("sheet LOOP", s, SHEET_LOOP_ANCHOR)):
    n = hay.count(anchor)
    assert n == 1, (name, repr(anchor[:60]), n)

c = c.replace(CONST_ANCHOR, CONST_NEW)
c = c.replace(INIT_ANCHOR, INIT_NEW)
c = c.replace(STEP_ANCHOR, STEP_NEW)
c = c.replace(DIAG_ANCHOR, DIAG_NEW)
t = t.replace(TEST_ANCHOR, TEST_NEW + TEST_ANCHOR)
g = g.replace(GATE_HEAD_ANCHOR, GATE_HEAD_NEW)
g = g.replace(GATE_LOOP_ANCHOR, GATE_LOOP_NEW)
s = s.replace(SHEET_HEAD_ANCHOR, SHEET_HEAD_NEW)
s = s.replace(SHEET_LOOP_ANCHOR, SHEET_LOOP_NEW)

ast.parse(c)
ast.parse(t)
ast.parse(g)
ast.parse(s)
open(C, "w").write(c)
open(T, "w").write(t)
open(G, "w").write(g)
open(S, "w").write(s)
print("patch47 applied to", ROOT)
