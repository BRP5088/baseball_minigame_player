"""The end-of-match CARD must be readable, because the arched banner never appears.

2026-09-20, a complete $50 match. local_state.read_result scored EVERY one of the
2,114 logged frames below RESULT_MIN (0.80); the top score across the whole run was
0.553. The arched WINNER/LOSER/DRAW banner the template bank was built for did not
occur once. So when the match ended, the reader said "not a result screen", run()
burned all 15 retries on "unreadable screens" and stopped WITHOUT SCORING A FINISHED
MATCH -- progress_testing.json still read 40W/10L after a loss, and match_in_progress
was still True.

What is actually on screen is a notebook CARD: "DEFEAT!" over a medallion, flavour
text, and a CLOSE button. screen_classifier_experiment.py has carried the real
vocabulary in a comment since it was written -- "a result modal (WINNER / DEFEAT! /
DRAW!)" -- and no reader ever used it.

THIS IS SECTION 10.31 FOR THE SECOND TIME ON THIS EXACT READER. The DRAW! fix added a
third word to a two-word bank and its write-up ends: "before trusting any classifier's
negative population, ask what it CANNOT name." Nobody asked again, and the answer was
a fourth screen.

THE CENSUS, run the way at_table's is -- every frame on disk, one false positive is a
veto:

    frames naming a result word    664, ALL "DEFEAT", contiguous at the match's end
    card dwell time                ~66 s at 10 Hz   (the arched banner held 4.0 s)
    false positives on the 1,450
      non-result frames before it    0

HONEST LIMIT: only DEFEAT is confirmed by a frame. WINNER and DRAW come from that
comment and have never been seen by this reader. They are included because omitting
them makes a win unreadable in exactly the way this loss was -- but the first live win
or draw must be checked against this rather than assumed.
"""
import os as _os
import sys as _sys

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

from PIL import Image                                                # noqa: E402

import local_state as ls                                            # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


FIX = _os.path.join(_ROOT, "test_fixtures", "result_screens",
                    "defeat_live_20260920.png")

# A MISSING FIXTURE IS A FAILURE, NOT A SKIP. This guards the reader whose silence
# cost a scored match.
check(_os.path.exists(FIX), f"fixture missing: {FIX}")
if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)

img = Image.open(FIX)

# --- 1. the card names the outcome ------------------------------------------
res = ls.read_result(img)
check(res["is_result"] is True,
      f"the DEFEAT! card must be recognised as a result screen; got "
      f"is_result={res['is_result']!r}, why={res['why']!r}")
check(res["outcome"] == "loss",
      f"the DEFEAT! card must be scored as a LOSS; got {res['outcome']!r}. "
      "Mapping it wrong is worse than not reading it -- run() acts on the outcome.")

# --- 2. CONTROL: the ARCHED templates did NOT do this ------------------------
# Without this the test passes just as well on a bank that suddenly matched, and
# would not notice the card reader being deleted.
_sc = ls.result_scores(img)
check(max(_sc.values()) < ls.RESULT_MIN,
      f"this fixture no longer reproduces the defect: the template bank scores "
      f"{max(_sc.values()):.3f} >= RESULT_MIN {ls.RESULT_MIN}, so the CARD path is "
      "not what answered and this file pins nothing.")
check("CARD" in res["why"],
      f"the verdict did not come from the card path: why={res['why']!r}")

# --- 3. the reader refuses an ambiguous band ---------------------------------
# Two result words in one title is a bad crop, not a result. A wrong outcome is
# worse than no outcome.
_saved = ls.RESULT_CARD_WORDS
try:
    ls.RESULT_CARD_WORDS = {"DEFEAT": "loss", "EFEAT": "win"}   # both must hit
    _out, _raw = ls.read_result_card(img)
    check(_out is None,
          f"two matching words in one band must REFUSE, not pick one; got {_out!r} "
          f"from {_raw!r}")
finally:
    ls.RESULT_CARD_WORDS = _saved

# --- 4. NEGATIVE CONTROL: a non-result screen must not name an outcome -------
# The census found 0 false positives over 1,450 non-result frames; this pins one of
# them so a widened band or a looser word list fails here.
_NEG = _os.path.join(_ROOT, "test_fixtures", "selected_card",
                     "two_selected_slots01_979.png")
if _os.path.exists(_NEG):
    _n = Image.open(_NEG)
    if _n.width >= 400:                      # read_result needs a full frame
        _o, _r = ls.read_result_card(_n)
        check(_o is None,
              f"a hand/turn frame must NOT name a result word; got {_o!r} from {_r!r}")
else:
    # Fall back to any archived non-result frame rather than skipping silently.
    import glob
    _cands = sorted(glob.glob(_os.path.join(_ROOT, "screenshot_log", "run_*", "*.jpg")))
    check(bool(_cands), "no non-result frame available for the negative control")
    if _cands:
        _o, _r = ls.read_result_card(Image.open(_cands[0]))
        check(_o is None,
              f"an early match frame must NOT name a result word; got {_o!r} ({_r!r})")

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  the DEFEAT! card reads as a loss, the arched bank does not, an ambiguous "
      "band refuses, and a non-result frame names nothing")
