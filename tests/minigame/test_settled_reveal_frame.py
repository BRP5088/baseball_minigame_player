"""The reveal must not be read from a frame where the cards are still flying in.

reveal_frame_for() hands back the PEAK of a possibly-OPEN episode, and Episode's
own docstring justifies that with "at the peak the cards are fully drawn".
Measured 2026-09-17 that is false early on: read 1.3s in, the peak frame had both
discs at y 0.543/0.547 -- clumped in the GAP between ZONE_MOUND (<=0.50) and
ZONE_HOME (>=0.62) -- and the pitcher's disc was not detectable anywhere in it.

The cards enter FROM THE SIDES (x 0.403 and 0.642) and converge to x 0.52-0.59.
Census over 403 reveal frames across 12 corpora: both zones read on 258; of the
116 where neither does, 106 hold fewer than two discs at all; the 10 that remain
are every one an OPENING frame. So the ZONES are right and the FRAME is wrong.

THIS IS WHY NO BOX IS WIDENED. A box spanning the gap would read cards in transit,
and in transit their positions do not correspond to their final sides -- it could
call the wrong card the pitcher and yield a CONFIDENT WRONG MARGIN where the
honest answer is None. Trading an abstention for a wrong number on a logged field
is the one trade this project cannot afford (10.23).

The fixtures are REAL frames, committed: two settled, two caught mid-animation.
"""
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


F = lambda p: Image.open(os.path.join(_ROOT, p))
SETTLED = "test_fixtures/reveal_kind_truth/live/t2_ours_swing1_theirs_none/r_000.jpg"
MIDAIR = "test_fixtures/reveal_banner/midanim_opener.jpg"
MIDAIR2 = "test_fixtures/reveal_frames/r_000000.jpg"

# ---- the gate ----
check(o.reveal_frame_readable(F(SETTLED)) is True,
      "a SETTLED frame is readable (both power discs land in their zones)")
check(o.reveal_frame_readable(F(MIDAIR)) is False,
      "a MID-ANIMATION frame is not (midanim_opener: discs at x 0.403 and 0.642)")
check(o.reveal_frame_readable(F(MIDAIR2)) is False,
      "...nor is the opening frame of an archived burst (r_000000)")
check(o.reveal_frame_readable(None) is False,
      "and None is not readable rather than a raise")

# ---- THE BUDGET, PINNED AS A LITERAL (10.11 -- never assert against the constant
# you are guarding). It sits BETWEEN two measured populations: the longest UNUSABLE
# PREFIX over the two live bursts is 0.94s (turn1; turn2 0.88s) and the shortest
# READABLE WINDOW is 5.64s (turn1 t+0.94..6.58; turn2 t+0.88..12.80).
check(o.REVEAL_SETTLE_MAX_SEC == 2.5,
      f"the settle budget is 2.5s, not {o.REVEAL_SETTLE_MAX_SEC} "
      "(clears the 0.94s worst prefix by 2.7x; under half the 5.64s shortest window)")


def run(watcher_frame, grabs, budget=0.4):
    """Drive the real settled_reveal_frame with a stubbed watcher and camera."""
    got = {"n": 0}
    saved = (o.reveal_frame_for, o._fast_grab, o.REVEAL_SETTLE_MAX_SEC, o.REVEAL_SETTLE_POLL)

    def cam(*a, **k):
        i = got["n"]
        got["n"] += 1
        return grabs[i] if i < len(grabs) else (grabs[-1] if grabs else None)

    try:
        o.reveal_frame_for = lambda *a, **k: watcher_frame
        o._fast_grab = cam
        o.REVEAL_SETTLE_MAX_SEC = budget
        o.REVEAL_SETTLE_POLL = 0.01
        out = o.settled_reveal_frame(123.0)
    finally:
        (o.reveal_frame_for, o._fast_grab,
         o.REVEAL_SETTLE_MAX_SEC, o.REVEAL_SETTLE_POLL) = saved
    return out, got["n"]

settled, midair = F(SETTLED), F(MIDAIR)

out, n = run(settled, [midair])
check(out is settled and n == 0,
      f"a readable watcher frame is used AS IS, with no re-grab (re-grabs={n})")

out, n = run(midair, [midair, settled])
check(out is settled and n >= 2,
      f"an in-flight watcher frame is replaced by a settled re-grab (re-grabs={n})")

# NEVER WORSE THAN BEFORE. If nothing settles inside the budget the caller gets
# exactly the frame it would have got without this function existing.
out, n = run(midair, [midair])
check(out is midair and n >= 1,
      f"when nothing settles, the watcher's own frame is returned (re-grabs={n})")

out, n = run(None, [midair])
check(out is None,
      "and a None from the watcher stays None -- the poll fallback already ran")

# CONTROL: without this the rows above pass against a function that always re-grabs
# or never does. The two counts must DIFFER.
_, n_ready = run(settled, [midair])
_, n_flight = run(midair, [midair, settled])
check(n_ready == 0 and n_flight > 0,
      f"CONTROL: re-grabs happen only when needed ({n_ready} vs {n_flight})")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
