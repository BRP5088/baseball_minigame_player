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

HONEST LIMIT WAS: only DEFEAT was confirmed by a frame. WINNER is now confirmed too
(2026-09-20, WIN #41, run_20260920_194419) -- see section 5 below. DRAW still comes
from that comment alone and has never been seen by this reader.

WINNER'S CONFIRMATION LOOKS DIFFERENT FROM DEFEAT'S, AND THAT IS WORTH SAYING PLAINLY.
The winning match's result screen never dropped into the notebook card in the ~5s of
frames captured before the process exited (the wallet was too low to continue) -- it
sat on the ARCHED "WINNER" banner over the diamond, which the template bank in
RESULT_TEMPLATES already reads correctly (score 0.912-0.932, clear of RESULT_MIN).
So read_result()'s full pipeline answers this frame from the TEMPLATES, not the card,
same as every other archived winner. What IS new: read_result_card() itself, called
directly, independently reads WINNER off this same frame (raw OCR 'WINNER Y') -- the
card path works on the word, it is just not the path THIS match's screen happened to
need. That is the confirmation section 5 pins.
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
#
# I-30: used to fabricate a fake second key ("EFEAT", a substring of "DEFEAT")
# to force two hits under the OLD substring matcher. Under the word-boundary
# fix "EFEAT" can no longer match at all (there is no boundary between the D
# and the E it would need), so the ambiguity is built the honest way instead:
# mock the OCR text to contain two REAL, SEPARATE whole words.
import ocr_glyphs as _og3                                                   # noqa: E402
_saved_ocr3 = _og3.image_to_text
try:
    _og3.image_to_text = lambda *a, **k: "DEFEAT WINNER"
    _out, _raw = ls.read_result_card(img)
    check(_out is None,
          f"two matching words in one band must REFUSE, not pick one; got {_out!r} "
          f"from {_raw!r}")
finally:
    _og3.image_to_text = _saved_ocr3

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

# --- 5. THE FIRST CONFIRMED WIN -----------------------------------------------------
# 2026-09-20, WIN #41, run_20260920_194419/20260920_194917_198.jpg. Unlike DEFEAT,
# this frame's arched templates ALREADY clear RESULT_MIN, so the full pipeline answers
# from result_scores(), not from the card -- that is asserted below rather than hidden.
# What this pins is read_result_card() ITSELF: called directly, it independently reads
# WINNER off this frame (raw OCR 'WINNER Y'), which is the confirmation I-04 asked for.
WIN_FIX = _os.path.join(_ROOT, "test_fixtures", "result_screens", "winner_live_20260920.png")
check(_os.path.exists(WIN_FIX), f"fixture missing: {WIN_FIX}")
if _os.path.exists(WIN_FIX):
    wimg = Image.open(WIN_FIX)

    _wout, _wraw = ls.read_result_card(wimg)
    check(_wout == "win",
          f"the card reader must read the WINNER band as win; got {_wout!r} from {_wraw!r}")
    check("WINNER" in _wraw,
          f"the raw OCR text should contain WINNER; got {_wraw!r}")

    # the full pipeline also reads win end to end -- via the arched banner this time
    _wres = ls.read_result(wimg)
    check(_wres["is_result"] is True and _wres["outcome"] == "win",
          f"the WIN frame must be read as win end to end; got is_result="
          f"{_wres['is_result']!r} outcome={_wres['outcome']!r}, why={_wres['why']!r}")

    # HONESTY CHECK, the mirror of section 2's control: on THIS frame the templates DO
    # clear RESULT_MIN, so the pipeline verdict above came from result_scores(), not
    # from the card -- unlike DEFEAT. If this ever goes False without the fixture
    # changing, something about the template bank regressed, not the card reader.
    _wsc = ls.result_scores(wimg)
    check(max(_wsc.values()) >= ls.RESULT_MIN,
          f"expected the arched bank to already answer this frame "
          f"({max(_wsc.values()):.3f} against RESULT_MIN {ls.RESULT_MIN}); if it no "
          f"longer does, re-check why 'why' above still says win.")


# --- 6. I-30: A SUBSTRING MATCH SCORED A PHANTOM DRAW -------------------------------
# 2026-09-20, live, round 1, 0-0. A batter card OCR'd as "JOHNNY DRAWERS" (see
# test_fixtures/result_screens/phantom_draw_20260920.png -- the real frame, screenshot_log/
# run_20260920_224358/20260920_225512_083.jpg, scoreboard 0-0-0, one card reading "JOHNNY
# DRAWERS" sitting in RESULT_CARD_BAND) and the OLD `k in up` substring test matched "DRAW"
# inside "DRAWERS". read_result_card now matches a WHOLE WORD via \b regex.
#
# The archived frame itself is a real-image negative control -- but its raw OCR output is
# NOT reproducible offline: scanned against EVERY ONE of the 7,093 frames of that run
# (agent_progress/issues/I-30/scan_draw_hits.py), read_result_card's OCR never once
# contains the substring "DRAW" on any of them. The live capture that produced 'JOHNNY
# DRAWERS' evidently differs from what the 10Hz screenshot logger archived (CLAUDE.md
# section 3: capture geometry/quality is not guaranteed to match across capture paths).
# So the mechanism is pinned directly, against the EXACT OCR string the incident's own log
# line recorded, with OCR itself stubbed out -- deterministic, and it is what the code
# actually does with that string, not a guess about it.
DRAW_FIX = _os.path.join(_ROOT, "test_fixtures", "result_screens",
                         "phantom_draw_20260920.png")
check(_os.path.exists(DRAW_FIX), f"fixture missing: {DRAW_FIX}")
if _os.path.exists(DRAW_FIX):
    dimg = Image.open(DRAW_FIX)
    _dout, _draw = ls.read_result_card(dimg)
    check(_dout is None,
          f"the phantom-draw frame must read no result word; got {_dout!r} from {_draw!r}")
    _dres = ls.read_result(dimg)
    check(_dres["outcome"] != "draw",
          f"the phantom-draw frame must not be scored as a draw; got outcome="
          f"{_dres['outcome']!r}, why={_dres['why']!r}")

import ocr_glyphs as _og                                                    # noqa: E402
_saved_ocr = _og.image_to_text
try:
    # The exact raw text overnight/run_live_20260920i.log:488 recorded:
    # "[state] the templates missed this banner; OCR read it: 'JOHNNY DRAWERS'"
    _og.image_to_text = lambda *a, **k: "JOHNNY DRAWERS"
    _blank = Image.new("RGB", (768, 432), (0, 0, 0))   # only width is read before OCR
    _out, _raw = ls.read_result_card(_blank)
    check(_out is None,
          f"'JOHNNY DRAWERS' must not read as a result word; got {_out!r} from {_raw!r}")
    check(_raw == "JOHNNY DRAWERS", f"raw OCR text mutated unexpectedly: {_raw!r}")

    # The word ITSELF must still be read as a whole token, both bare and with the
    # game's own punctuation.
    _og.image_to_text = lambda *a, **k: "DRAW!"
    _out2, _raw2 = ls.read_result_card(_blank)
    check(_out2 == "draw", f"'DRAW!' must still read as draw; got {_out2!r} from {_raw2!r}")

    # Same fix, same rule, for WINNER and DEFEAT (the task's own ask: "same for
    # WINNER/DEFEAT") -- a longer word that merely STARTS with one of ours must not
    # match either.
    _og.image_to_text = lambda *a, **k: "DEFEATED FOES"
    _out3, _raw3 = ls.read_result_card(_blank)
    check(_out3 is None,
          f"'DEFEATED' must not match DEFEAT as a substring; got {_out3!r} from {_raw3!r}")

    _og.image_to_text = lambda *a, **k: "RUNNER WINNER"
    _out4, _raw4 = ls.read_result_card(_blank)
    check(_out4 == "win",
          f"WINNER must still be read as a whole word inside a longer line; got "
          f"{_out4!r} from {_raw4!r}")
finally:
    _og.image_to_text = _saved_ocr

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  the DEFEAT! card reads as a loss, the arched bank does not, an ambiguous "
      "band refuses, a non-result frame names nothing, the WINNER card word is "
      "now confirmed by a live frame too, and 'JOHNNY DRAWERS' no longer reads as a draw")
