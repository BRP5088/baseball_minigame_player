"""EACH RUNNER'S SPEED, READ OFF THEIR BASE -- the field read_runners said was out of reach.

read_runners' docstring used to end "a disc reader cannot supply a name. THIS READER CANNOT
FEED IT". The user, 2026-09-12: "enough things have changed that I don't think that's true
anymore. make it work." The shield badge on a base card is the runner's speed, and it reads.

WHY IT IS SEARCHED AND NOT CROPPED (CLAUDE.md 10.23). The badge is a sprite, so
matchTemplate over a scale sweep answers "is it there" and "which digit" at once, with no
assumption about where it sits. The bank is local_hand's, cut from HAND cards in a
DIFFERENT archive, and the winning scale on a base crop is ~0.70 -- so no base crop can
match itself, which is 10.22's self-match trap closed by construction rather than by care.

THE POPULATIONS, over 1,278 saved base crops. Occupancy comes from the COIN and DISC
detectors, which touch no shield template, so the labels are not this reader's own answers
(10.31 -- the census that cannot discover its own missing class):

    EMPTY    n=1106   badge score max 0.592
    OCCUPIED n= 172   p05 0.857, median 0.892, one outlier at 0.492

The shipped SHIELD_MIN (0.69) already sits between them. No constant was invented for this.

AND THE BADGE IS NOT THE CARD'S ROSTER SECONDARY, which is the finding that makes it worth
reading at all. The same named card shows different values at different moments -- Bunz
1x31 and 2x8, Fisto 3x3 and 1x2, Sharp 1x22 and 2x1 -- and among roster cards sharing each
one's POWER, none carries the observed value, so a name mix-up cannot produce it. It is a
LIVE number: what this runner will advance NOW, which is exactly what a speed boost changes
for one turn and what a baserunning or animation model needs.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os, glob, collections
os.environ["BASEBALL_TEST_RUN"] = "1"
from PIL import Image
import local_state as ls
import local_hand as lh

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


CROPS = _os.path.join(_ROOT, "overnight", "local_hand")
occ, emp, read, false_reads = 0, 0, 0, 0
digits, occ_scores, emp_scores = collections.Counter(), [], []
pairs = []   # (speed, score) per occupied crop, for the gate check below
for base in ("first", "second", "third"):
    for p in sorted(glob.glob(_os.path.join(CROPS, f"{base}_base_*.png"))):
        r = ls.read_base(Image.open(p), base)
        if r["occupied"] is None:
            continue
        if r["occupied"]:
            occ += 1
            occ_scores.append(r["speed_score"])
            pairs.append((r["speed"], r["speed_score"]))
            if r["speed"] is not None:
                read += 1
                digits[r["speed"]] += 1
        else:
            emp += 1
            # read_base short-circuits: it looks for a badge only on an OCCUPIED base, so
            # its speed_score on an empty one is 0.0 by construction. Scoring that would
            # measure the short-circuit and not the discrimination -- the guard has to ask
            # what the badge search ACTUALLY returns on a bare base, which is the number
            # that would matter if the occupancy check ever let one through.
            emp_scores.append(ls.base_badge(Image.open(p))[0])
            if r["speed"] is not None:
                false_reads += 1

print("1. the corpus is really there (an empty scan must not pass)")
check(occ >= 150 and emp >= 900, f"{occ} occupied and {emp} empty base crops scored")

print("2. a bare base NEVER reads a speed")
check(false_reads == 0,
      f"{false_reads} of {emp} empty bases read a badge — a speed on a base with no runner "
      f"would feed a phantom into anything that uses it")
check(max(emp_scores) < lh.SHIELD_MIN,
      f"the loudest empty base SEARCHED DIRECTLY scores {max(emp_scores):.3f}, still under "
      f"the gate {lh.SHIELD_MIN} — so the gate, not just the occupancy check, is what stops it")

print("3. a runner's speed reads, nearly always")
check(read >= occ - 2, f"{read} of {occ} occupied bases read a speed")
check(sorted(digits) and min(digits) >= 1 and max(digits) <= 3,
      f"every digit read is in 1..3 {dict(sorted(digits.items()))} — never 0, which would "
      f"be a distance where the game has none, and never above 3")

print("4. the gate actually GATES — a below-threshold badge abstains")
# THE FIRST VERSION OF THIS FILE DID NOT CHECK THIS, and two mutants survived because of
# it: deleting the threshold, and comparing against 0.0, both left "171 of 172 read" intact
# since the loose `read >= occ - 2` tolerated reading the one sub-gate crop. A gate whose
# removal changes no assertion is decorative (CLAUDE.md 10.9).
_leaked = [(sp, sc) for sp, sc in pairs if sp is not None and sc < lh.SHIELD_MIN]
check(not _leaked,
      f"no occupied crop reads a speed from a badge under the gate {lh.SHIELD_MIN} "
      f"(leaked: {_leaked[:4]})")
_below = [(sp, sc) for sp, sc in pairs if sc < lh.SHIELD_MIN]
check(bool(_below),
      f"and the corpus really contains a sub-gate crop to abstain on ({len(_below)}), so "
      f"this check is not passing by having nothing to reject")

print("5. the gate sits BETWEEN the two populations (CLAUDE.md 10.4)")
_q = lambda v, p: sorted(v)[int(p * (len(v) - 1))]
check(max(emp_scores) < lh.SHIELD_MIN <= _q(occ_scores, 0.05),
      f"empty max {max(emp_scores):.3f} < SHIELD_MIN {lh.SHIELD_MIN} <= occupied p05 "
      f"{_q(occ_scores, 0.05):.3f}")
# PINNED AS LITERALS so raising the constant cannot make its own guard pass (10.11).
check(0.55 <= max(emp_scores) <= 0.65, f"the empty ceiling is where it was measured "
                                       f"({max(emp_scores):.3f}, measured 0.592)")
check(_q(occ_scores, 0.05) >= 0.80, f"and the occupied floor too ({_q(occ_scores, 0.05):.3f}, "
                                    f"measured 0.857)")

print("6. read_runners surfaces the speeds, in base order, only for runners on")
_ts = "1789010519550701000"
_im = {b: Image.open(_os.path.join(CROPS, f"{b}_base_{_ts}.png"))
       for b in ("third", "second", "first")}
out = ls.read_runners(_im["third"], _im["second"], _im["first"])
check(out["count"] == 2, f"two runners on this frame (got {out['count']})")
check(out["speeds"] == [1, 1], f"and their speeds, third-to-first (got {out['speeds']})")
check(len(out["speeds"]) == out["count"],
      "one speed per runner ON base — an empty base contributes nothing, not a zero")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
