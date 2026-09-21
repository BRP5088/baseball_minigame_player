"""I-35: two recognised transition screens between a reveal resolving and the next
hand's fan appearing -- the "NEW INNING" half-boundary banner, and the settled
REVEAL-RECAP tableau (cards on the diamond, no hand fan).

Before this, `local_game_state()` had no branch for either, and each could sit on
screen 6-14s (`agent_progress/reveal-drops/progress.md`,
`overnight/run_live_20260921n.log`) -- long enough for `MAX_PENDING_READ_FAILURES`
to exhaust and silently drop the pending `match_log.jsonl` row for that at-bat (5
rows dropped in run 21i alone, more in every run since). Logging loss only --
nothing downstream reads the pending row before it resolves -- but it burned the
unreadable-screen budget on screens that are expected, not broken.

WHAT THIS FILE PINS
--------------------
1. `local_state.is_new_inning` / `is_reveal_recap` read the two detector fixtures
   correctly and refuse every REQUIRED negative (a turn screen with the hand fan, a
   genuine result screen, the ban grid, a genuine dealer-prompt-on-screen frame, the
   pause book) -- each filtered by the reader that already owns its category, not by
   folder name (CLAUDE.md 10.15: two of those folders also hold a DIFFERENT reader's
   own hard negatives, which are not genuine members of their category).
2. `local_game_state()` returns `screen="new_inning"` / `"reveal_recap"` end to end
   on the real fixtures, only after result/ban/prompt/turn have all declined.
3. A pending match_log row SURVIVES repeated "reveal_recap"/"new_inning" polls and is
   logged once a real "turn" read arrives, instead of being dropped.
4. CONTROL: a genuinely unreadable screen (read_state_for_turn raising, the pre-
   existing MAX_PENDING_READ_FAILURES path) still drops the row after 3 consecutive
   failures -- this file changes nothing about that path, and proves it.
5. The 30s bound: persisting on a recognised transition past TRANSITION_SCREEN_MAX_SEC
   is treated as stuck (the row is dropped, stuck_count climbs) rather than trusted
   forever.

WHAT IT DOES NOT COVER
-----------------------
"PLAY BALL!", "ROUND N", "PLAY AS THE BATTER/PITCHER" and a fleeting "HOME RUN!" are
other captions in the same gap, found while building this file, and named in neither
detector's docstring as covered -- `is_reveal_recap` happens to catch most of them as
a side effect of its geometric signal, not as a promise (see its docstring). Arbitrary
world/navigation frames are explicitly NOT claimed safe either; see the same docstring.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_sys.path.insert(0, _os.path.join(_ROOT, "tests", "minigame"))

import os
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
os.environ["BASEBALL_TEST_RUN"] = "1"

import contextlib
import glob
import io

from PIL import Image

import local_state
import table_prompt
from _run_harness import Harness, RESULT_WIN, _PLAYED
import orchestrator as o

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


SCREENS_DIR = os.path.join(_ROOT, "test_fixtures", "screens")


def img(name, root=SCREENS_DIR):
    p = os.path.join(root, name)
    if not os.path.exists(p):
        raise SystemExit(f"FIXTURE MISSING: {p} -- this test is not allowed to pass "
                         f"by finding nothing")
    return Image.open(p).convert("RGB")


# =============================================================================
# 1. THE DETECTORS THEMSELVES
# =============================================================================

NEW_INNING_POS = [img(f"new_inning_{i}.jpg") for i in (1, 2, 3)]
RECAP_POS = [img(f"reveal_recap_{i}.jpg") for i in (1, 2, 3)]

for i, im in enumerate(NEW_INNING_POS, 1):
    check(local_state.is_new_inning(im) is True,
          f"is_new_inning: positive #{i} (a genuine 'NEW INNING' sighting) must read True")
for i, im in enumerate(RECAP_POS, 1):
    check(local_state.is_reveal_recap(im) is True,
          f"is_reveal_recap: positive #{i} (a genuine settled tableau) must read True")

# REQUIRED negatives, gathered the same way `agent_progress/issues/I-35/
# measure_screens.py` does: genuine members of each category, filtered by the reader
# that already owns it -- NOT everything a folder happens to hold (CLAUDE.md 10.15;
# result_screens/ and table_prompt_cases/ each also carry a DIFFERENT reader's own
# hard negatives, which score False on read_result/at_table and are excluded here for
# exactly the same reason those readers exclude them).
TURN_WITH_FAN = [img("turn_with_fan_1.jpg"), img("turn_with_fan_2.jpg")]
BAN_SCREENS = ([img(f"ban_screen__{i}.jpg") for i in (0, 1, 2)] +
               [img(os.path.basename(p), root=os.path.join(_ROOT, "test_fixtures", "ban_screen"))
                for p in glob.glob(os.path.join(_ROOT, "test_fixtures", "ban_screen", "*.jpg"))] +
               [img(os.path.basename(p), root=os.path.join(_ROOT, "test_fixtures", "ban_scan"))
                for p in glob.glob(os.path.join(_ROOT, "test_fixtures", "ban_scan", "*.jpg"))])
PAUSE_BOOK = [img(os.path.basename(p), root=os.path.join(_ROOT, "test_fixtures", "pause_menu"))
              for p in glob.glob(os.path.join(_ROOT, "test_fixtures", "pause_menu", "*.png"))]

_result_candidates = ([img(f"result__{i}.jpg") for i in (0,)] +
                      [img(os.path.basename(p), root=os.path.join(_ROOT, "test_fixtures", "result_screens"))
                       for p in glob.glob(os.path.join(_ROOT, "test_fixtures", "result_screens", "*.jpg"))
                       + glob.glob(os.path.join(_ROOT, "test_fixtures", "result_screens", "*.png"))])
GENUINE_RESULTS = [im for im in _result_candidates if local_state.read_result(im).get("is_result")]
check(len(GENUINE_RESULTS) >= 5,
      f"sanity: expected several genuine result-screen fixtures, found {len(GENUINE_RESULTS)}")

_prompt_candidates = ([img(f"match_start_prompt__{i}.jpg") for i in (0, 1)] +
                      [img(os.path.basename(p), root=os.path.join(_ROOT, "test_fixtures", "table_prompt_cases"))
                       for p in glob.glob(os.path.join(_ROOT, "test_fixtures", "table_prompt_cases", "*.jpg"))])
GENUINE_PROMPTS = [im for im in _prompt_candidates if table_prompt.at_table(im)]
check(len(GENUINE_PROMPTS) >= 5,
      f"sanity: expected several genuine dealer-prompt fixtures, found {len(GENUINE_PROMPTS)}")

REQUIRED_NEGATIVES = {
    "turn with hand fan": TURN_WITH_FAN,
    "genuine result screen": GENUINE_RESULTS,
    "ban grid": BAN_SCREENS,
    "genuine dealer prompt": GENUINE_PROMPTS,
    "pause book": PAUSE_BOOK,
}
for label, frames in REQUIRED_NEGATIVES.items():
    check(len(frames) > 0, f"sanity: no fixtures gathered for required negative {label!r}")
    for i, im in enumerate(frames, 1):
        check(local_state.is_new_inning(im) is False,
              f"is_new_inning: required negative {label!r} #{i} must read False")
        check(local_state.is_reveal_recap(im) is False,
              f"is_reveal_recap: required negative {label!r} #{i} must read False")

# The two detectors must also refuse EACH OTHER'S positives and each other's
# captions -- a "NEW INNING" banner must not also read as a settled recap tableau
# (it never shows cards at that moment, see local_state.is_reveal_recap's docstring).
for i, im in enumerate(NEW_INNING_POS, 1):
    check(local_state.is_reveal_recap(im) is False,
          f"is_reveal_recap must not fire on new_inning positive #{i}")

# --- THE NO-HAND-FAN TERM ACTUALLY REJECTS SOMETHING (Opus skeptic mutant A) ---
# The skeptic's census over 9,966 archived frames found ZERO with edge>=0.065 AND a
# hand fan present, so a mutant deleting `local_hand._fan_looks_present` from
# is_reveal_recap survived the whole suite -- the term was inert on every frame that
# exists. This fixture is MANUFACTURED (`agent_progress/issues/I-35/
# build_fan_composite.py`) rather than sighted live: a real fan, pasted onto a real
# recap frame's hand region, leaving the centre (what `edge` measures) untouched. It
# proves the term does something rather than claiming it does on real traffic.
FAN_COMPOSITE = img("reveal_recap_with_fan_synthetic.jpg")
check(local_state._center_card_edge_fraction(FAN_COMPOSITE) >= local_state.REVEAL_RECAP_EDGE_MIN,
      "sanity: the composite's edge score must still clear the gate (the paste must "
      "not have touched the centre region) or this proves nothing")
check(local_state.read_result(FAN_COMPOSITE).get("is_result") is False,
      "sanity: the composite must not be caught by the result exclusion instead")
try:
    import table_prompt as _tp_sanity
    check(_tp_sanity.at_table(FAN_COMPOSITE) is False,
          "sanity: the composite must not be caught by the prompt exclusion instead")
except Exception as exc:
    check(False, f"sanity: table_prompt.at_table raised on the composite ({exc})")
check(local_state.is_reveal_recap(FAN_COMPOSITE) is False,
      "is_reveal_recap must reject a frame combining high centre edge with a real "
      "hand fan -- if this fails with the sanity checks above passing, the "
      "no-hand-fan term itself is not doing the rejecting")

# =============================================================================
# 2. WIRED INTO local_game_state() -- AFTER result/ban/prompt/turn, per the
#    ordering local_game_state() itself documents.
# =============================================================================
_real_fast_grab = o._fast_grab
try:
    o._fast_grab = lambda: NEW_INNING_POS[0]
    st, gap = o.local_game_state(turns_this_half=0)
    check(st is not None and st.get("screen") == "new_inning" and gap is None,
          f"local_game_state() on a real NEW INNING frame: got screen="
          f"{st and st.get('screen')!r}, gap={gap!r}")

    o._fast_grab = lambda: RECAP_POS[0]
    st, gap = o.local_game_state(turns_this_half=0)
    check(st is not None and st.get("screen") == "reveal_recap" and gap is None,
          f"local_game_state() on a real reveal-recap frame: got screen="
          f"{st and st.get('screen')!r}, gap={gap!r}")

    # A required negative must still win: feeding a genuine turn frame must not be
    # shadowed by the new checks (they run last, after "turn" has already returned).
    # turns_this_half=0 supplies the same phase-fallback (I-31) a live caller always
    # has; without it this frame's own phase read abstains and the gap is unrelated
    # to this ticket ("phase not read locally"), which would make the check mean
    # nothing.
    o._fast_grab = lambda: TURN_WITH_FAN[0]
    st, gap = o.local_game_state(turns_this_half=0)
    check(st is not None and st.get("screen") == "turn",
          f"local_game_state() on a real turn frame must still say 'turn', not "
          f"{st and st.get('screen')!r} (gap={gap!r})")
finally:
    o._fast_grab = _real_fast_grab

check("new_inning" in o.VALID_SCREENS and "reveal_recap" in o.VALID_SCREENS,
      "VALID_SCREENS must list both new screen names")

# =============================================================================
# 3. THE PENDING ROW SURVIVES A RUN OF RECOGNISED TRANSITION SCREENS
# =============================================================================
_INFO = {"phase": "batting", "our_card_name": "Test Card", "our_power": 8,
         "our_secondary": 1, "our_tactics_bonus": 0, "our_tactics_kind": None,
         "runners_before": 0, "score_before": 0}
# The reveal's own faceoff -- needed so wait_for_reveal_cards() (stubbed to
# `revealed is not None`) returns True and the turn actually reaches the point
# where matchup_info becomes pending_matchup, instead of raising "reveal cards
# never appeared" and never setting it at all (test_local_misfire_backs_off.py's
# _turn() helper is the precedent for this shape).
_OURS_CARD = {"kind": "player", "name": "Test Card", "power": 8, "secondary": 1}
_THEIRS_CARD = {"kind": "player", "name": "Opponent Card", "power": 5, "secondary": 2}
_OPP_LOCAL = {"opp_power": 5, "opp_tactics_bonus": 0, "opp_tactics_kind": None,
              "_ours_power_seen": 8}


def _run_survival_case(transition_screen, n_polls, label):
    """turn (plays, sets pending_matchup) -> transition_screen * n_polls (must NOT
    drop it, must NOT count as stuck) -> turn (resolves it, logs exactly one row)."""
    logged = []
    real_log_matchup = o.log_matchup
    o.log_matchup = lambda record: logged.append(record)
    screens = (["turn"] + [transition_screen] * n_polls + ["turn"] +
               ["other"] * (o.MAX_UNRECOGNIZED_ATTEMPTS + 1))
    h = Harness(screens, play_results=[(True, dict(_INFO))], balance=500,
                revealed=[_OURS_CARD, _THEIRS_CARD], opp_local=dict(_OPP_LOCAL))
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            h.run(target_wins=99)
    finally:
        o.log_matchup = real_log_matchup
    out = buf.getvalue()
    check(len(logged) == 1,
          f"{label}: expected exactly 1 logged row after {n_polls} polls of "
          f"{transition_screen!r}, got {len(logged)}")
    check("dropping the pending row" not in out,
          f"{label}: the pending row must not be dropped while waiting on a "
          f"recognised transition (stdout contained a drop message)")
    check(f"Unrecognized screen ({transition_screen})" not in out,
          f"{label}: {transition_screen!r} must not be treated as an unrecognised "
          f"screen (it is a named, recognised one)")


_run_survival_case("reveal_recap", 6, "reveal_recap survives 6 polls")
_run_survival_case("new_inning", 6, "new_inning survives 6 polls")

# =============================================================================
# 4. CONTROL: a genuinely unreadable screen still drops the row after 3 failures.
#    Unmodified pre-existing behaviour (MAX_PENDING_READ_FAILURES) -- this proves
#    the new exclusion above did not also swallow the OLD drop path.
# =============================================================================
logged = []
real_log_matchup = o.log_matchup
o.log_matchup = lambda record: logged.append(record)
gap_exc = ValueError("LOCAL STATE GAP: UNRECOGNISED SCREEN -- synthetic, for the test")
screens = (["turn"] + [gap_exc] * 3 + ["turn"] +
           ["other"] * (o.MAX_UNRECOGNIZED_ATTEMPTS + 1))
h = Harness(screens, play_results=[(True, dict(_INFO))], balance=500,
            revealed=[_OURS_CARD, _THEIRS_CARD], opp_local=dict(_OPP_LOCAL))
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        h.run(target_wins=99)
finally:
    o.log_matchup = real_log_matchup
out = buf.getvalue()
check(len(logged) == 0,
      f"CONTROL: 3 consecutive genuinely-unreadable polls must still drop the "
      f"pending row (pre-existing MAX_PENDING_READ_FAILURES behaviour), got "
      f"{len(logged)} row(s) logged")
check("dropping the pending row" in out,
      "CONTROL: the drop message must still print for a genuinely unreadable screen")

# =============================================================================
# 5. THE 30s BOUND: a recognised transition that never advances must eventually
#    be treated as stuck, not trusted forever.
# =============================================================================
logged = []
real_log_matchup = o.log_matchup
o.log_matchup = lambda record: logged.append(record)
# Each poll advances the virtual clock ~0.7s (0.2s motion check + 0.5s time.sleep
# inside the new branch), so >40 polls comfortably crosses TRANSITION_SCREEN_MAX_SEC
# (30s) before the scripted screens run out.
screens = ["turn"] + ["reveal_recap"] * 80
h = Harness(screens, play_results=[(True, dict(_INFO))], balance=500,
            revealed=[_OURS_CARD, _THEIRS_CARD], opp_local=dict(_OPP_LOCAL))
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        h.run(target_wins=99)
finally:
    o.log_matchup = real_log_matchup
out = buf.getvalue()
check("outlasted" in out and "stuck on 'reveal_recap'" in out,
      "the 30s bound must fire and say so when a recognised transition never "
      "advances (stdout did not contain the expected message)")
check(len(logged) == 0,
      f"the 30s bound firing must drop the still-pending row (nothing to log "
      f"yet, the transition never advanced to a real turn), got {len(logged)}")

# =============================================================================
# 6. THE PENDING-ROW SKIP IS NARROW: it names exactly "new_inning"/"reveal_recap"
#    and nothing else -- a screen genuinely named "other" (not a raised exception)
#    is NOT exempted and is resolved the same way it always was. Opus skeptic
#    mutant B: widening the skip tuple to also include "other" survived the whole
#    suite because the CONTROL above uses a scripted Exception (the raise path),
#    never a screen literally named "other" through the SUCCESS path.
#
# Measured directly before writing this: "other"'s default harness payload
# carries your_score=0/opp_score=0 (not None, unlike new_inning/reveal_recap), so
# baseline code resolves (logs) the pending row on the very FIRST "other" poll --
# it is not "dropped" in the unscorable sense, it is scored immediately, same as
# any other successful read. Under the widened-exclusion mutant "other" would
# also be skipped, the row would never be resolved against it, and it would
# still be unresolved when the scripted screens run out -- logged=0. That is the
# behavioural difference this pins.
#
# NO TRAILING "turn" HERE, DELIBERATELY (a first draft of this test had one and
# it did not distinguish baseline from the mutant): "turn" is never excluded
# from the resolution block either way, so a later "turn" rescues the row under
# BOTH the shipped code and the widened-exclusion mutant, making them read
# identical. Only the run staying on "other" the whole time separates them.
# =============================================================================
logged = []
real_log_matchup = o.log_matchup
o.log_matchup = lambda record: logged.append(record)
screens = ["turn"] + ["other"] * (o.MAX_UNRECOGNIZED_ATTEMPTS + 3)
h = Harness(screens, play_results=[(True, dict(_INFO))], balance=500,
            revealed=[_OURS_CARD, _THEIRS_CARD], opp_local=dict(_OPP_LOCAL))
h.run(target_wins=99)
check(len(logged) == 1,
      f"a screen genuinely named 'other' must NOT be exempted by the transition-"
      f"screen skip -- it should resolve the pending row on its own (score "
      f"fields present, unlike new_inning/reveal_recap), got {len(logged)} logged")

# =============================================================================
# 7. NOTED BY THE OPUS SKEPTIC (not a refutation): "new_inning"/"reveal_recap" are
#    RECOGNISED screen names, so unlike "other" they DO clear `acted_screen`
#    (orchestrator.py: `if screen != acted_screen and screen != "other":
#    acted_screen = None`). N2's own comment says "other" is excluded from that
#    specifically to stop `result -> other -> result` double-scoring. A half-faded
#    result screen that reads as "reveal_recap" between two result polls would
#    clear acted_screen the way "other" cannot -- but C1's double-score guard is
#    ALSO independently blocked by `match_in_progress` (QA1-F2, orchestrator.py
#    ~8996: "if not match_in_progress:" -- set False the moment a result scores),
#    so this is not reachable as a hole. Pinned here rather than just argued:
#    reveal_recap in place of "other" in the SAME N2 sequence
#    (test_run_debit_and_scoring.py's own precedent) must still score exactly once.
#
#    Measured while writing this: the SECOND result read still presses
#    close_result (to dismiss the overlay -- QA1-F2's own branch does that on
#    purpose, printing "Result screen with no paid match in progress -- already
#    scored, not counting it again") even though it does not re-score. TWO
#    close_result presses across two result sightings is therefore the CORRECT
#    behaviour, not a symptom -- the invariant that matters is wins, not press
#    count, and asserting exactly one press here would have been a wrong
#    expectation pinned as if it were a requirement.
# =============================================================================
h2 = Harness(["match_start_prompt"] + _PLAYED
             + [RESULT_WIN, "reveal_recap", RESULT_WIN])
final2 = h2.run(target_wins=99)
_close_result_presses = h2.presses.count("close_result")
check(final2["wins"] == 1,
      f"result / reveal_recap (clears acted_screen, unlike 'other') / result "
      f"scored {final2['wins']} wins, expected 1 -- match_in_progress (QA1-F2) "
      f"must still block the double-score C1/N2 exist to prevent")
check(_close_result_presses >= 1,
      f"result / reveal_recap / result never pressed close_result "
      f"({_close_result_presses} times) -- the overlay would be left on screen")


if fails:
    print(f"\n{len(fails)} FAILED")
    raise SystemExit(1)
print("\nall green")
