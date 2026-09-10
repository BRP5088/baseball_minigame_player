"""THE RESULT SCREEN and THE BAN SCREEN, read locally, and the gap message that names them.

These two readers are what let the turn loop run without a paid call. Before them
`local_game_state()` could only ever claim "turn", so every other screen fell through to the
hand reader and came back as `hand: 0 rows, expected 5` -- naming a reader that was working
perfectly. That stalled a live run on 2026-09-10 with $50 already committed.

WHAT THIS FILE PINS
-------------------
1. RESULT_MIN and RESULT_MARGIN are LITERALS, not values read back off the reader
   (CLAUDE.md 10.11).
2. All THREE banners read, and name the right outcome, on frames from runs that supplied no
   template -- including DRAW, which a two-class reader could never see, and including the
   FLAT mid-animation form that the first bank missed entirely.
3. The highest-scoring genuine NON-result frames stay under the gate.
4. The BAN screen classifies at BOTH geometries -- the live 2000x1125 and 1920x1080.
5. `local_game_state()` returns the right screen end to end for all of them, and returns an
   UNRECOGNISED SCREEN gap -- not a hand failure -- for anything else.
6. A draw is carried as `result_outcome`, and run() prefers that over the scoreboard.

WHAT IT DOES NOT COVER
----------------------
The bank's DRAW and LOSER templates come from one run each. Cross-run held-out frames read
correctly (51 draw, 22 loser, 269 winner, 0 class errors), but a banner rendered in some way
no archived run contains has never been seen.
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
import orchestrator

FIX = os.path.join(_ROOT, "test_fixtures", "result_screens")
BAN = os.path.join(_ROOT, "test_fixtures", "ban_screen")
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


def img(d, name):
    p = os.path.join(d, name)
    if not os.path.exists(p):
        raise SystemExit(f"FIXTURE MISSING: {p} -- this test is not allowed to pass "
                         f"by finding nothing")
    return Image.open(p)


# --- 1. the constants are pinned as literals -------------------------------------------
check(local_state.RESULT_MIN == 0.75,
      "RESULT_MIN is the literal 0.75")
check(local_state.RESULT_MARGIN == 0.10,
      "RESULT_MARGIN is the literal 0.10 -- a tie-breaker floor, not a fitted value")
check(local_state.RESULT_CLASSES == {"winner": "win", "loser": "loss", "draw": "draw"},
      "all THREE banners are known -- a two-class reader stalls forever on a draw")

# --- 2. every banner, on held-out frames ------------------------------------------------
RESULTS = [("heldout_winner_a.jpg", "win"), ("heldout_winner_b.jpg", "win"),
           ("heldout_winner_960.jpg", "win"),
           ("heldout_loser_a.jpg", "loss"), ("heldout_loser_b.jpg", "loss"),
           # the FLAT mid-animation form: the first bank scored this 0.497 and called it
           # "not a result screen"
           ("heldout_loser_flat.jpg", "loss"),
           # DRAW, from two different runs, neither of which supplied a template
           ("heldout_draw_768.jpg", "draw"), ("heldout_draw_poll.jpg", "draw")]
res_scores = []
for name, want in RESULTS:
    r = local_state.read_result(img(FIX, name))
    top = max(r["scores"].values())
    res_scores.append(top)
    check(r["is_result"] is True and r["outcome"] == want,
          f"{name}: is_result={r['is_result']} outcome={r['outcome']!r} (wanted {want!r}) "
          f"at {top:.3f}")

# --- 3. the genuine negatives stay under the gate ---------------------------------------
# NOTE: a frame named "top_negative_turn_768" used to live here. It is a DRAW screen, and
# the two-class reader filed it as the highest-scoring non-result frame precisely because it
# could not see the word. It is now heldout_draw_768.jpg above. Adjudicate by eye before
# calling anything a negative.
NEGATIVES = ["top_negative_questlog_0543.jpg", "top_negative_turn_1920.jpg",
             "animating_in_not_yet_a_result.jpg"]
neg_scores = []
for name in NEGATIVES:
    r = local_state.read_result(img(FIX, name))
    top = max(r["scores"].values())
    neg_scores.append(top)
    check(r["is_result"] is False and r["outcome"] is None,
          f"{name}: is_result={r['is_result']} outcome={r['outcome']!r} at {top:.3f}")

check(max(neg_scores) < local_state.RESULT_MIN < min(res_scores),
      f"the gate sits BETWEEN the populations: negatives max {max(neg_scores):.3f} "
      f"< {local_state.RESULT_MIN} < results min {min(res_scores):.3f}")

# --- 4. a crop is not a frame ------------------------------------------------------------
tiny = img(FIX, "heldout_winner_a.jpg").crop((0, 0, 40, 20))
r = local_state.read_result(tiny)
check(r["is_result"] is None and "too small" in r["why"],
      f"a crop too small for the templates abstains rather than answering: {r['why']}")

# --- 5. a TIE abstains rather than picking ----------------------------------------------
# No real frame has ever scored two words within RESULT_MARGIN, so this branch cannot be
# reached with a fixture; it is driven at the seam instead.
_real = local_state.result_scores
try:
    local_state.result_scores = lambda im: {"winner": 0.90, "loser": 0.86, "draw": 0.40}
    r = local_state.read_result(img(FIX, "heldout_winner_a.jpg"))
    check(r["is_result"] is True and r["outcome"] is None and "too close" in r["why"],
          f"two words 0.04 apart abstain: outcome={r['outcome']!r} -- {r['why']}")
    local_state.result_scores = lambda im: {"winner": 0.40, "loser": 0.42, "draw": 0.90}
    r = local_state.read_result(img(FIX, "heldout_winner_a.jpg"))
    check(r["is_result"] is True and r["outcome"] == "draw",
          "...and a clear third-word win is still answered, so the rule is not blocking reads")
finally:
    local_state.result_scores = _real

# --- 6. the BAN screen, at BOTH geometries ----------------------------------------------
for name in ("ban_0of3_2000x1125.jpg", "ban_0of3_1920x1080.jpg"):
    im = img(BAN, name)
    check(orchestrator.read_ban_counter(im) == 0,
          f"{name} {im.size}: the N/3 counter reads 0")
    check(local_state.read_result(im)["is_result"] is False,
          f"{name}: and it is NOT mistaken for a result screen")

# --- 7. local_game_state end to end ------------------------------------------------------
CASES = [("heldout_winner_a.jpg", FIX, "result", "win"),
         ("heldout_loser_a.jpg", FIX, "result", "loss"),
         ("heldout_draw_768.jpg", FIX, "result", "draw"),
         ("ban_0of3_2000x1125.jpg", BAN, "ban_screen", None),
         ("ban_0of3_1920x1080.jpg", BAN, "ban_screen", None)]
_grab = orchestrator._fast_grab
for name, d, screen, outcome in CASES:
    try:
        orchestrator._fast_grab = lambda _p=os.path.join(d, name): Image.open(_p)
        st, gap = orchestrator.local_game_state()
    finally:
        orchestrator._fast_grab = _grab
    check(st is not None and st.get("screen") == screen
          and st.get("result_outcome") == outcome and gap is None,
          f"local_game_state({name}) -> screen={st and st.get('screen')!r} "
          f"result_outcome={st and st.get('result_outcome')!r} (wanted {screen!r}/{outcome!r})")

# A DRAW must NOT be carried as result_won=False, which run() would log as a LOSS.
try:
    orchestrator._fast_grab = lambda: img(FIX, "heldout_draw_768.jpg")
    st, _ = orchestrator.local_game_state()
finally:
    orchestrator._fast_grab = _grab
check(st is not None and st.get("result_won") is None and st.get("result_outcome") == "draw",
      f"a draw carries result_won={st and st.get('result_won')!r} (must be None) and "
      f"result_outcome={st and st.get('result_outcome')!r}")
# and it must supply NO scores -- ocr_scoreboard misreads the result screen, and run()
# PREFERS scores, so a wrong one would be acted on
check(st is not None and st.get("your_score") is None and st.get("opp_score") is None,
      "a result state supplies NO scoreboard numbers -- ocr_scoreboard misreads that screen")

# --- 8. an unrecognised screen names ITSELF, not the hand --------------------------------
for name in ("animating_in_not_yet_a_result.jpg", "top_negative_questlog_0543.jpg"):
    try:
        orchestrator._fast_grab = lambda _p=os.path.join(FIX, name): Image.open(_p)
        st, gap = orchestrator.local_game_state()
    finally:
        orchestrator._fast_grab = _grab
    check(st is None and gap is not None and "UNRECOGNISED SCREEN" in gap,
          f"{name}: the gap names the SCREEN, not the hand -- {(gap or '')[:70]}")

# --- 9. run() ACTS on the local outcome, scored through the real loop --------------------
# A source-order check is not enough here: neutering the `if` that consumes the answer
# leaves the assignment -- and the substring -- exactly where it was, and the check still
# passes. This drives run() and reads the progress rows it wrote.
_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _run_harness import Harness

DRAW_STATE = {"screen": "result", "result_outcome": "draw", "result_won": None,
              "hand": [], "runners": [], "discards_left": 2, "phase": "batting",
              "your_score": None, "opp_score": None}
# The result is repeated because run() CONFIRMS a result seen before MIN_PLAYS_FOR_RESULT
# cards have been played, rather than believing one misread frame -- that gate is what stops
# a transition overlay re-arming the $50 debit (tests/minigame/test_early_result_double_debit.py).
h = Harness(["match_start_prompt", "turn"] + [dict(DRAW_STATE) for _ in range(5)], balance=500)
h.run(target_wins=99)
w, l, d = (h.saves[-1][0], h.saves[-1][1], h.saves[-1][2]) if h.saves else (0, 0, 0)
check(d == 1 and w == 0 and l == 0,
      f"a result carrying result_outcome='draw' with NO scores logs {w}W/{l}L/{d}D "
      f"-- expected exactly 1 draw. Without the preference run() falls to "
      f"`win if result_won else loss` and records a LOSS.")

_src = open(os.path.join(_ROOT, "orchestrator.py")).read()
i_local = _src.find('local_outcome = state_json.get("result_outcome")')
i_scores = _src.find("elif your_score is not None and opp_score is not None:")
check(0 < i_local < i_scores,
      "...and it is read BEFORE the score comparison -- the word is measured reliable on "
      "the result screen and ocr_scoreboard is not")

if fails:
    print(f"\n{len(fails)} FAILED")
    raise SystemExit(1)
print("\nall green")
