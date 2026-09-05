"""pose.DIVERGENCE_FACTOR and pose.STUCK_PX, pinned to the runs that set them.

Both constants were challenged on 2026-09-04 with a plausible story and a
plausible number. Both stories were checked against the 127 align_lateral calls
already on disk in overnight/{newleg,failframes,streak,streak2}.log and
overnight/phase1/{run,step3}.log, and BOTH NUMBERS WERE REFUTED. This test pins
what the logs actually say, so the same two arguments cannot be re-made from
memory.

WHICH GAIN PRODUCED THOSE LOGS — the linchpin, because the case for lowering
DIVERGENCE_FACTOR rested on "no divergence has been measured under the current
gain". The commanded push is a deterministic function of the logged dx, so the
logs identify their own constants: 221 of 221 pushes reproduce exactly at
PX_PER_STRAFE_SEC = 2400 (the current value) and only 56 of 221 at the
open-loop 1200. Those calls ARE the current gain, and one of them diverges.

THE TWO POPULATIONS FOR DIVERGENCE_FACTOR — step-to-step ratio |dx_i|/|dx_i-1|,
n = 129 consecutive pairs:

    inside calls that CONVERGED (n=51)      max ratio 1.186
    the one divergence on record            ratios 2.733 and 5.695

1.5 sits in that gap (geometric middle 1.80). The +175 -> -201 -> +211 -> -215
oscillation quoted as the reason to lower it to ~1.10 was measured at the
OPEN-LOOP gain and is not what divergence looks like now.

THE TWO POPULATIONS FOR STUCK_PX do NOT separate, which is the finding. Fired
reaches 20px, not-fired starts at 3.2px, and not-fired is censored by STUCK_PX
itself. The one non-circular number available refutes the proposed 55: a real
0.10s push moves the view a MEDIAN of 30px (n=129, complete sample), not the
~72px the old comment predicted from the gain model, and 92% of them move less
than 55px.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import pose

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# --------------------------------------------------------------------------
# Replay a REAL logged sequence of dx readings through align_lateral.
#
# Each iteration consumes TWO offset reads: the step's own dx at the top of the
# loop, then a post-push `after` read for the blocked-sideways check. In the
# real runs those two reads sit either side of nothing but a 0.4s settle, so
# `after` IS essentially the next iteration's dx — which is why replaying
# after_i = seq[i+1] reproduces the logged run rather than inventing one.
# --------------------------------------------------------------------------
def replay(seq):
    """Drive align_lateral through a recorded dx sequence. Returns the log."""
    feed = []
    for i, dx in enumerate(seq):
        feed.append(dx)                       # top-of-loop read
        if i + 1 < len(seq):
            feed.append(seq[i + 1])           # post-push `after` read
    lines = []

    def fake_offset(a, b):
        return (feed.pop(0), 0.0) if feed else (0.0, 0.0)

    # `time` is imported INSIDE align_lateral, so patch the module it resolves
    # to rather than an attribute on pose.
    import time as _time
    old_offset, old_sleep = pose.offset, _time.sleep
    pose.offset = fake_offset
    _time.sleep = lambda *a: None
    try:
        pose.align_lateral(ref_img=object(), capture=lambda: object(),
                           walk_forward=lambda *a, **k: None, log=lines.append)
    except Exception as e:
        lines.append(f"RAISED {type(e).__name__}: {e}")
    finally:
        pose.offset = old_offset
        _time.sleep = old_sleep
    return lines


def said(lines, word):
    return any(word in l for l in lines)


# --------------------------------------------------------------------------
# THE LITERALS. Pinned as literals, never against the constant they guard — a
# test that reads `pose.DIVERGENCE_FACTOR <= pose.DIVERGENCE_FACTOR` rises with
# whatever anybody sets and passes forever.
# --------------------------------------------------------------------------
check("DIVERGENCE_FACTOR is 1.5 — above the 1.186 ceiling of every converging "
      "call, below the 2.733 divergence",
      pose.DIVERGENCE_FACTOR == 1.5)
check("STUCK_PX is 20.0 — no value separates these populations, and every "
      "alternative measured aborts more converging calls",
      pose.STUCK_PX == 20.0)

# The gap the factor has to land in, pinned as the two measured extremes. If a
# future run moves either, this says so instead of the constant drifting.
check("1.5 clears the healthy population (max ratio 1.186 inside a call that "
      "converged)", 1.186 < pose.DIVERGENCE_FACTOR)
check("1.5 still catches the recorded divergence (smallest diverging ratio "
      "2.733)", pose.DIVERGENCE_FACTOR < 2.733)

# STUCK_PX must stay under a real minimum push or it calls working corrections
# blocked. MEASURED median is 30px, NOT the ~72px the gain model predicts.
check("STUCK_PX is under the MEASURED median minimum push (30px), not the "
      "modelled 72px", pose.STUCK_PX < 30.0)

# --------------------------------------------------------------------------
# FINDING A. The behaviour, on the real sequences.
# --------------------------------------------------------------------------
# overnight/phase1/step3.log:140 — the ONE divergence on record at the current
# gain. It ran all six steps because the comparison bug meant the guard could
# not fire; with the fix it trips at step 2 (915.7 > 160.8 * 1.5).
DIVERGED = [+715.2, -160.8, +915.7, -162.0, -118.8, +324.7]
lines = replay(DIVERGED)
check("the recorded divergence (step3.log:140) is STOPPED and says so",
      said(lines, "diverging"))
check("and it is stopped at the step that grew 5.7x, not later",
      said(lines, "915") or said(lines, "916"))

# overnight/streak2.log:1007 — CONVERGED to 11.4px, and it contains the largest
# growth any converging call showed (160.7 -> 190.6, ratio 1.186). A factor of
# 1.10 would abort this call. That is the whole case against lowering it.
CONVERGED_WITH_A_BUMP = [+160.7, +190.6, +119.2, +78.0, +55.0, +11.4]
lines = replay(CONVERGED_WITH_A_BUMP)
check("the 1.186 bump inside a converging call is NOT called diverging "
      "(a factor of 1.10 would abort this real run)",
      not said(lines, "diverging"))
check("and that call still reports reaching tolerance",
      said(lines, "within"))

# --------------------------------------------------------------------------
# FINDING B. Raising STUCK_PX aborts calls that demonstrably converged.
#
# All three of these are real runs that reached tolerance. Their tightest
# step-to-step change is 23.0, 28.5 and 21.9px — every one of which is under
# the proposed 55, and two of which are under 30.
# --------------------------------------------------------------------------
CONVERGED = [
    ("streak2.log:1007", [+160.7, +190.6, +119.2, +78.0, +55.0, +11.4], 23.0),
    ("failframes.log:447", [+258.0, +174.5, +146.0, +100.0, +47.8, +19.0], 28.5),
    ("phase1/run.log:86", [+205.9, +162.2, +106.1, +84.2, +50.1, +15.9], 21.9),
]
for name, seq, tightest in CONVERGED:
    lines = replay(seq)
    check(f"{name} converges and is NOT reported blocked "
          f"(its tightest step moved {tightest}px, under the proposed 55)",
          said(lines, "within") and not said(lines, "blocked sideways"))
    check(f"{name}'s tightest step really is under the proposed 55px",
          tightest < 55.0)

# ...while a genuinely blocked run is still caught. overnight/newleg.log:98,
# which ended "dx barely changed (+62 -> +43)".
BLOCKED = [+211.0, +169.0, +142.6, +83.0, +61.9, +43.0]
lines = replay(BLOCKED)
check("a genuinely blocked run (newleg.log:98) is still reported blocked",
      said(lines, "blocked sideways"))
check("and it is not confused with divergence",
      not said(lines, "diverging"))

# --------------------------------------------------------------------------
# The measured populations themselves, so the numbers in the comments cannot
# quietly rot away from the numbers the decisions were made on.
# --------------------------------------------------------------------------
MIN_PUSH_MEDIAN_PX = 30.0      # n=129 complete sample of 0.10s pushes
MODELLED_MIN_PUSH_PX = pose.ALIGN_MIN_SEC * pose.STRAFE_MAG * pose.PX_PER_STRAFE_SEC
check("the gain model still over-predicts a minimum push by ~2.4x — this is "
      "why '20px is well under a real correction' was never true",
      2.0 < MODELLED_MIN_PUSH_PX / MIN_PUSH_MEDIAN_PX < 3.0)

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
