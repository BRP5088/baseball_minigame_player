"""THE RESULT SCREEN, read locally -- and the gate held between two measured populations.

This reader is what removes the last paid call from the turn loop. Before it,
`local_game_state()` could only ever claim `screen: "turn"`, so a match that had ENDED came
back as a hand-reader gap and the run either stalled or bought a paid answer.

WHAT THIS FILE PINS
-------------------
1. RESULT_MIN is the LITERAL 0.75, not a value derived from the reader (CLAUDE.md 10.11).
2. Every held-out result frame -- from runs that supplied no template, at three different
   geometries -- reads as a result AND names the right class.
3. The three highest-scoring NON-result frames found in every census taken (72,318 frames:
   16,381 stills plus every 20th frame of all 17 archived run videos) read as NOT a result.
   That census has ZERO false positives; its four highest sub-gate scores were extracted
   and looked at, and all four are result screens caught HALF FADED, so the reader's only
   error is an abstention during the fade.
4. The animating-in frame -- the medallion on its way up, no banner yet -- reads NOT a
   result. That is the reader's honest limit: a single grab at the wrong instant says no,
   which is why the caller polls.
5. The gate's own population separation, asserted as an EMPTY BAND with the literals in it,
   so shrinking either margin fails here rather than silently in a live run.

WHAT IT DOES NOT COVER
----------------------
The LOSER bank is one template, cut from one frame. Four held-out losers from two other
runs read correctly, so the class is not untested -- but it is thinner than the winner side
(23 held-out frames), and a LOSER rendered differently (a different resolution mode, say)
has never been seen.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image
import local_state

FIX = os.path.join(_ROOT, "test_fixtures", "result_screens")
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


def img(name):
    p = os.path.join(FIX, name)
    if not os.path.exists(p):
        raise SystemExit(f"FIXTURE MISSING: {p} -- this test is not allowed to pass "
                         f"by finding nothing")
    return Image.open(p)


# --- 1. the constant is pinned as a literal ------------------------------------------
check(local_state.RESULT_MIN == 0.75,
      "RESULT_MIN is the literal 0.75 -- the midpoint of the empty band 0.543..0.955")
check(local_state.RESULT_MARGIN == 0.10,
      "RESULT_MARGIN is the literal 0.10 -- a tie-breaker floor, not a fitted value")

# --- 2. held-out result frames ---------------------------------------------------------
RESULTS = [("heldout_winner_a.jpg", True), ("heldout_winner_b.jpg", True),
           ("heldout_winner_960.jpg", True),
           ("heldout_loser_a.jpg", False), ("heldout_loser_b.jpg", False)]
res_scores = []
for name, won in RESULTS:
    r = local_state.read_result(img(name))
    top = max(r["winner"], r["loser"])
    res_scores.append(top)
    check(r["is_result"] is True and r["won"] is won,
          f"{name}: is_result={r['is_result']} won={r['won']} (wanted {won}) -- {r['why']}")

# --- 3. the highest-scoring negatives in every census taken ---------------------------
NEGATIVES = ["top_negative_questlog_0543.jpg", "top_negative_turn_768.jpg",
             "top_negative_turn_1920.jpg", "animating_in_not_yet_a_result.jpg"]
neg_scores = []
for name in NEGATIVES:
    r = local_state.read_result(img(name))
    top = max(r["winner"], r["loser"])
    neg_scores.append(top)
    check(r["is_result"] is False and r["won"] is None,
          f"{name}: is_result={r['is_result']} won={r['won']} (wanted False/None) "
          f"-- best {top:.3f}")

# --- 4. the band is EMPTY, and the gate is inside it ----------------------------------
check(max(neg_scores) < local_state.RESULT_MIN < min(res_scores),
      f"the gate sits BETWEEN the populations: negatives max {max(neg_scores):.3f} "
      f"< {local_state.RESULT_MIN} < results min {min(res_scores):.3f}")
# and with real headroom -- a gate 0.01 from either population is not a gate
check(min(res_scores) - max(neg_scores) > 0.30,
      f"the band is {min(res_scores) - max(neg_scores):.3f} wide, not a hairline")

# --- 5. the class margin ---------------------------------------------------------------
for name, _ in RESULTS:
    r = local_state.read_result(img(name))
    check(abs(r["winner"] - r["loser"]) > 0.30,
          f"{name}: WINNER and LOSER differ by {abs(r['winner'] - r['loser']):.3f}, "
          f"far above the {local_state.RESULT_MARGIN} tie floor")

# --- 6. a crop is NOT a frame ----------------------------------------------------------
# read_result takes the WHOLE frame; the search window is a fraction of it. A crop that
# cannot hold a template must come back NOT READ, never "not a result screen".
tiny = img("heldout_winner_a.jpg").crop((0, 0, 40, 20))
r = local_state.read_result(tiny)
check(r["is_result"] is None and "too small" in r["why"],
      f"a crop too small for the templates abstains rather than answering: {r['why']}")

# --- 7. a TIE abstains rather than picking -------------------------------------------
# No real frame has ever scored the two words within RESULT_MARGIN of each other -- every
# held-out result is 0.36-0.58 apart -- so this branch cannot be reached with a fixture.
# It is driven at the seam instead: the DECISION is what is under test here, not the
# correlation, and a rule nothing exercises is a rule that can rot (CLAUDE.md 10.1).
_real_scores = local_state.result_scores
try:
    local_state.result_scores = lambda im: {"winner": 0.90, "loser": 0.86}
    r = local_state.read_result(img("heldout_winner_a.jpg"))
    check(r["is_result"] is True and r["won"] is None and "too close" in r["why"],
          f"two words 0.04 apart: is_result={r['is_result']} won={r['won']} -- {r['why']}")
    local_state.result_scores = lambda im: {"winner": 0.90, "loser": 0.60}
    r = local_state.read_result(img("heldout_winner_a.jpg"))
    check(r["is_result"] is True and r["won"] is True,
          "...and 0.30 apart is answered, so the tie rule is not blocking real reads")
finally:
    local_state.result_scores = _real_scores

# --- 8. the orchestrator asks the result reader FIRST, and ACTS on it ------------------
# The source-order check alone is not enough: neutering the `if` that consumes the answer
# leaves the call site -- and the substring -- exactly where it was.
_src = open(os.path.join(_ROOT, "orchestrator.py")).read()
i_res = _src.find("local_state.read_result(full)")
i_hand = _src.find("cards, why = local_hand_cards(hand_img)")
check(0 < i_res < i_hand,
      "local_game_state reads the result screen BEFORE the hand -- a finished match has "
      "no hand, and asking the hand first names the wrong missing reader")

import orchestrator as _o
for name, won in (("heldout_winner_a.jpg", True), ("heldout_loser_a.jpg", False)):
    _real_grab = _o._fast_grab
    try:
        _o._fast_grab = lambda _n=name: img(_n)
        st, gap = _o.local_game_state()
    finally:
        _o._fast_grab = _real_grab
    check(st is not None and st.get("screen") == "result"
          and st.get("result_won") is won and gap is None,
          f"local_game_state on {name} returns screen={st and st.get('screen')!r} "
          f"result_won={st and st.get('result_won')!r} (wanted 'result'/{won}), gap={gap!r}")

if fails:
    print(f"\n{len(fails)} FAILED")
    raise SystemExit(1)
print("\nall green")
