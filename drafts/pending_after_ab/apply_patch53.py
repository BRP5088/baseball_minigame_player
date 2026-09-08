"""patch53: two OBSERVABILITY-ONLY gaps. No behaviour changes, no constant moves.

(A) THE HARNESS'S CONFIG PRINT IS MISSING THE FLAGS SHIPPED TODAY. `config()`
exists so "a run whose own parameters are not in its own result file cannot be
compared with the next one" -- its own docstring. Three booleans that DECIDE
something in the walk are absent: STOP_LOOK_YAW (patch45),
STOP_YAW_NEAR_FIT_ONLY (patch46) and STOP_YAW_SKIP_LAST_STOP (patch51), plus
DOOR_STOP_EXTRA_PUSH (patch50). A reader of today's logs cannot tell from the
log which of them was live, which is exactly the failure the docstring names.

(B) `turn_to` LOGS THE ERROR IT LEFT, NEVER THE ERROR IT WAS ASKED TO CORRECT.
Measured 2026-09-08: a turn happens before 80.5% of pushes (617 real turns
against 149 no-ops over batches 23/24/26), takes a median of ONE stick push,
and costs ~569 ms of a 1440 ms iteration -- of which 350 ms is the bare 0.35
literal in this loop. So turning is about 40% of the walk. Whether that is
necessary is a question about how FAR it turns, and that number is not on disk
anywhere: the only error logged is the one remaining at exit, which is bounded
by TURN_TOLERANCE by construction and is therefore CLAUDE.md 10.12's vacuous
statistic ("68 of 68 turn steps had |want - got| <= 4.0" measured the loop's own
exit condition). This adds the asked-for error and the stick time to the line
the loop already writes on every real turn.

WHAT THIS IS NOT. No threshold moves, no control flow changes, nothing is
removed. TURN_TOLERANCE, the 0.35 settle and plan_turn are untouched: the point
is to be able to ASK whether they are right, which is not possible today.

Usage: python apply_patch53.py [ROOT]     (asserts every anchor, THEN writes)
"""
import ast
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
H = os.path.join(ROOT, "overnight", "chain_trials.py")
S = os.path.join(ROOT, "slow_traverse.py")
h = open(H).read()
s = open(S).read()

edits_h = [
 ("""            "END_PUSH_UNITS": chain_walk.END_PUSH_UNITS,
            "end_iteration_budget": chain_walk.end_iteration_budget()}
""",
  """            "END_PUSH_UNITS": chain_walk.END_PUSH_UNITS,
            # The stop-yaw family and the door step DECIDE something in the
            # walk, so a log that does not name them cannot be compared with
              # the next one -- this function's own reason for existing.
            "STOP_LOOK_YAW": chain_walk.STOP_LOOK_YAW,
            "STOP_YAW_NEAR_FIT_ONLY": chain_walk.STOP_YAW_NEAR_FIT_ONLY,
            "STOP_YAW_SKIP_LAST_STOP": chain_walk.STOP_YAW_SKIP_LAST_STOP,
            "DOOR_STOP_EXTRA_PUSH": chain_walk.DOOR_STOP_EXTRA_PUSH,
            "end_iteration_budget": chain_walk.end_iteration_budget()}
"""),
]

edits_s = [
 ("""            else:
                log(f"        turn to {target:.1f}: TURNED to {now:.1f} "
                    f"(err {err:+.1f}) in {i} push(es)")
""",
  """            else:
                # `err` here is what is LEFT, which is inside `tolerance` by
                # construction and so says nothing (10.12). `asked` is the
                # error this call was given and `sent` the stick time it spent
                # -- the two numbers needed to ask whether TURN_TOLERANCE and
                # the 0.35 s settle below are worth what turning costs (~40% of
                # the walk). Recorded, not acted on.
                log(f"        turn to {target:.1f}: TURNED to {now:.1f} "
                    f"(err {err:+.1f}) in {i} push(es), asked "
                    f"{asked:+.1f} deg, stick {sent:.2f}s")
"""),
 ("""    for i in range(max_steps):
        now = read_heading()
""",
  """    asked, sent = 0.0, 0.0      # the FIRST error seen, and the stick time
    for i in range(max_steps):   # spent on it; both for the log line only
        now = read_heading()
"""),
 ("""        err = (target - now + 540) % 360 - 180
        if abs(err) <= tolerance:
""",
  """        err = (target - now + 540) % 360 - 180
        if i == 0:
            asked = err
        if abs(err) <= tolerance:
"""),
 ("""        ar.send([f"right_x {ar.to_axis(mag if err > 0 else -mag)}",
                 "right_y 0", "left_x 0", "left_y 0"])
        time.sleep(secs)
""",
  """        ar.send([f"right_x {ar.to_axis(mag if err > 0 else -mag)}",
                 "right_y 0", "left_x 0", "left_y 0"])
        sent += secs
        time.sleep(secs)
"""),
]

# ---------------------------------------------- assert EVERYTHING, then write
for a, b in edits_h:
    assert h.count(a) == 1, ("harness anchor", a[:50], h.count(a))
for a, b in edits_s:
    assert s.count(a) == 1, ("slow_traverse anchor", a[:50], s.count(a))
assert "STOP_YAW_SKIP_LAST_STOP" not in h, "config already names the flag"
assert "asked" not in s.split("def turn_to")[1][:2000], "turn_to already logs it"
# the settle and the tolerance are NOT touched by this patch
assert s.count("        time.sleep(0.35)\n") == 1
# TURN_TOLERANCE appears TWICE -- the constant and a docstring quoting it
# (10.10: count the occurrences before trusting a match). Pin the LINE.
assert s.count("TURN_TOLERANCE = 4.0       # degrees") == 1

for a, b in edits_h:
    h = h.replace(a, b)
for a, b in edits_s:
    s = s.replace(a, b)

ast.parse(h)
ast.parse(s)
# It appears TWICE on its own line -- as the dict KEY and as the attribute
# read from chain_walk. Pin the key, which is the thing that reaches a log.
assert h.count('"STOP_YAW_SKIP_LAST_STOP":') == 1
assert s.count("asked, sent = 0.0, 0.0") == 1
assert s.count("sent += secs") == 1
assert s.count("asked = err") == 1
assert s.count("asked {asked:+.1f} deg, stick {sent:.2f}s") == 0  # it is f-split
assert 'f"{asked:+.1f} deg, stick {sent:.2f}s"' in s
# UNCHANGED, re-checked after the writes
assert s.count("        time.sleep(0.35)\n") == 1
# TURN_TOLERANCE appears TWICE -- the constant and a docstring quoting it
# (10.10: count the occurrences before trusting a match). Pin the LINE.
assert s.count("TURN_TOLERANCE = 4.0       # degrees") == 1

open(H, "w").write(h)
open(S, "w").write(s)
print("patch53 applied to", ROOT)
