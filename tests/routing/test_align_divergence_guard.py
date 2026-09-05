"""align_lateral's divergence guard must be able to FIRE.

THE BUG. The guard read

    if last is not None and abs(dx) > last * 1.5 and i > 0:

but `last = abs(dx)` was assigned ~25 lines above, so the test was
`abs(dx) > abs(dx) * 1.5` — always False. It never fired once since it was
written. And because that branch owns the only "diverging" log line, its
absence from every log read as "it never diverged".

It was written for a MEASURED oscillation: with the open-loop gain the loop went
dx +175 -> -201 -> +211 -> -215, each step making the pose worse. That is the
behaviour this guard exists to stop, and it was not stopping it.

Two catalogue items at once: a bound that cannot be reached, inside a branch
that writes nothing.
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


def run_with(offsets):
    """Drive align_lateral through a scripted sequence of dx values."""
    seq = list(offsets)
    lines = []

    def fake_offset(a, b):
        return (seq.pop(0), 0.0) if seq else (0.0, 0.0)

    # `time` is imported INSIDE align_lateral, so patch the module it resolves
    # to rather than an attribute on pose.
    import time as _time
    old_offset, old_sleep = pose.offset, _time.sleep
    pose.offset = fake_offset
    _time.sleep = lambda *a: None
    try:
        pose.align_lateral(
            ref_img=object(),
            capture=lambda: object(),
            walk_forward=lambda *a, **k: None,
            log=lines.append,
        )
    except Exception as e:
        lines.append(f"RAISED {type(e).__name__}: {e}")
    finally:
        pose.offset = old_offset
        _time.sleep = old_sleep
    return lines


# Each iteration consumes TWO offset reads: the step's own dx, then a post-push
# read for the "blocked sideways" check. The sequences below are written to that
# rhythm — get it wrong and the stuck-check fires first and masks everything.
#
# DIVERGING: 175 then 300. The guard trips when a step exceeds 1.5x the
# previous one (300 > 175 * 1.5), which is the shape of the measured
# oscillation (+175 -> -201 -> +211 -> -215) it was written for.
lines = run_with([175.0, 100.0, 300.0, 100.0, 320.0, 100.0])
check("a diverging loop is STOPPED and says so",
      any("diverging" in l for l in lines))

# CONVERGING: 131 -> 88 -> 46 -> 3, the real measured convergence at
# portrait_room. It must NOT trip the guard, or every run would stop early.
lines = run_with([131.0, 88.0, 88.0, 46.0, 46.0, 3.0, 3.0, 3.0])
check("a converging loop is NOT called diverging",
      not any("diverging" in l for l in lines))
check("and a converging loop reports reaching tolerance",
      any("within" in l for l in lines))
check("each correction step is logged with its dx",
      sum(1 for l in lines if "align: step" in l) >= 2)

# The blocked-sideways case must still be distinguishable from both.
lines = run_with([136.0, 136.0, 136.0, 136.0])
check("a laterally blocked character is reported as blocked, not diverging",
      any("blocked sideways" in l for l in lines)
      and not any("diverging" in l for l in lines))

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
