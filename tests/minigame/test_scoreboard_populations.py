"""ocr_scoreboard reads TURN screens and is unreliable on RESULT screens.

CLAUDE.md carried this as "CANNOT READ A LEGIBLE BOARD ... unmeasured rate, open".
Measured 2026-09-17, and the shape is narrower than the entry implied:

    turn / reveal screens   33 of 33 read BOTH rows   100%
    result screens           4 of  8 read both         50%, and every one-row
                             failure is the OPPONENT row

Pinned because a repair aimed at "the reader is unreliable" would be aimed at the
wrong thing, and because run() already prefers read_result's named outcome on the
result screen for exactly this reason (10.31: "a wrong score is worse than no
score, because run() acts on it").

THE DENOMINATOR IS THE POINT. A first pass over 1,400 archived frames put it at
1.2% -- which is not a failure rate, it is the share of the archive that is a turn
screen at all. A rate needs a population where the thing being read is PRESENT.
"""
import glob
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image

import orchestrator as o

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


def read(path):
    im = Image.open(path).convert("RGB")
    if im.width < 1200:
        return None
    sb = dict(o.crop_gameplay_regions(im)).get("scoreboard")
    if sb is None:
        return None
    sc = o.ocr_scoreboard(sb) or {}
    return sc.get("your"), sc.get("opponent")


TURN = sorted(glob.glob(os.path.join(_ROOT, "agent_progress/base-timing/reveal/r_*.jpg")))
check(len(TURN) >= 20, f"the turn-screen corpus is present ({len(TURN)} frames) — "
                       "an empty glob must not pass")

both = sum(1 for f in TURN if (r := read(f)) and r[0] is not None and r[1] is not None)
check(both == len(TURN),
      f"ocr_scoreboard reads BOTH rows on every turn/reveal frame: {both}/{len(TURN)}")

RES = sorted(glob.glob(os.path.join(_ROOT, "test_fixtures/result_screens/*.jpg")))
check(len(RES) >= 5, f"the result-screen corpus is present ({len(RES)} frames)")

rows = [r for f in RES if (r := read(f)) is not None]
one_row = [r for r in rows if (r[0] is None) != (r[1] is None)]
check(len(one_row) >= 1,
      f"the result screen still produces partial reads ({len(one_row)} of {len(rows)}) "
      "— if this becomes 0 the entry in CLAUDE.md should be re-measured, not deleted")
check(all(r[1] is None for r in one_row),
      f"...and every partial read is the OPPONENT row, which is the specific defect: "
      f"{one_row}")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
