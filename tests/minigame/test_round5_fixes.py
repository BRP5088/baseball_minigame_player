"""QA round 5: a duplicate disc is not a second card, and a proved-stale flag is cleared.

  _discs DEDUPED BY A FIXED BUCKET GRID (`k = (x // 20, y // 20)`), and candidates
  are collected across every DARK_THRESHOLDS entry -- so the SAME physical disc found
  at two thresholds can differ by ONE PIXEL and straddle a bucket edge. Measured:
  r_001099.jpg yields (1019, 781) and (1020, 781), because 1019 // 20 is 50 and
  1020 // 20 is 51. Harmless until _side began REFUSING when a second disc reads a
  legal card power -- then the duplicate reads as a second player card and throws
  away a power the reader had. That refusal was added the same night, so this is a
  regression the fix created.

  A STALE match_in_progress PLUS THE DEALER PROMPT PRESSED start_match WITH NO DEBIT.
  The branch's own comment says the prompt is "positive proof no match is running" --
  so at that instant the flag is PROVED stale -- and it then pressed anyway, with no
  debit, no max_spend check, no save_progress and the flag still set. "NO RE-DEBIT
  happens here ... the accounting is untouched either way" is true only if THIS
  process did the debit; match_in_progress is loaded from disk, so on a fresh process
  the $50 leaves the wallet and the record never hears about it.

FIXTURES LIVE IN test_fixtures/, NEVER IN agent_progress/. This test read its
corpus from agent_progress/base-timing/reveal/ until 2026-09-17, and CLAUDE.md
says of that directory: "agent_progress/ is gitignored and safe to delete
wholesale". A test whose evidence lives somewhere documented as disposable is
one tidy-up from losing it. See test_fixtures/reveal_frames/README.md.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image

import reveal_cards as rc

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


# --- 1. the duplicate-disc frame reads again --------------------------------
FRAME = os.path.join(_ROOT, "test_fixtures/reveal_frames/r_001099.jpg")
if os.path.exists(FRAME):
    im = Image.open(FRAME).convert("RGB")
    cs = rc._discs(im, rc.ZONE_HOME)
    close = [(a, b) for i, a in enumerate(cs) for b in cs[i + 1:]
             if abs(a[0] - b[0]) <= rc.DISC_R[1] and abs(a[1] - b[1]) <= rc.DISC_R[1]]
    check(not close,
          f"no two discs within DISC_R of each other — the bucket-edge duplicate is "
          f"gone: {close}")
    rv = rc.read_reveal(im, "batting")
    check(rv["ours"]["power"] == 7,
          f"...and the frame's power reads again: {rv['ours']['power']} "
          f"(discs={rv['ours']['discs']}; it was None with discs=3 and ambiguous=2)")
else:
    check(False, f"FIXTURE MISSING: {FRAME} — this check cannot silently skip")

# --- 2. CONTROL: a genuine second card still refuses ------------------------
# Without this the dedupe could have removed the ambiguity guard entirely. home_run
# holds a real runner's card (5) beside the played card (7), 75px apart.
HR = os.path.join(_ROOT, "test_fixtures/reveal_banner/home_run.jpg")
hv = rc.read_reveal(Image.open(HR).convert("RGB"), "batting")
check(hv["ours"]["power"] is None and hv["ours"].get("ambiguous") == 2,
      f"CONTROL: a genuine second CARD POWER still refuses "
      f"(power={hv['ours']['power']}, ambiguous={hv['ours'].get('ambiguous')})")

# --- 3. the stale-flag branch clears instead of pressing --------------------
import ast
_src = open(os.path.join(_ROOT, "orchestrator.py")).read()
_i = _src.index('the dealer\'s \\"Play ($50)\\" prompt is')
_seg = _src[_i:_i + 1600]
check("match_in_progress = False" in _seg and "save_progress(" in _seg,
      "the branch that PROVES match_in_progress stale now clears and persists it")
check(_seg.index("continue") < _seg.index('press("start_match")')
      if 'press("start_match")' in _seg else True,
      "...and continues BEFORE pressing start_match, so the next poll takes the "
      "ordinary debit path rather than spending $50 with no accounting")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
