"""The LOCAL path must not act on a reading the paid path would have rejected.

validate_game_state exists to turn a hallucinated card into "a clear, retryable error
instead of a stack trace pointing at the wrong function". It has exactly ONE call site:
read_game_state -- the PAID reader. With PAID_MODEL_ENABLED False (the shipped default
and the user's standing instruction) every turn takes local_game_state and the validator
runs for nobody.

That was harmless while the runner could not play at all: until 2026-09-13
read_state_for_turn made the orientation read paid, so run() died after 15 stuck
attempts every match. Fixing that turned a dead branch into a LIVE unvalidated one, so
the two readings the validator would have caught now reach the engine.

    a power of 1      digit_templates.npz holds 1 x200 and 2 x200 -- the TACTICS BONUS
                      digits -- and read_digit argmaxes the whole bank while `kind` is
                      decided separately, so a player row can carry one. Found in the
                      archive: hand_samples/hand_20260824_201140_317.jpg slot 0 reads '1'.
    a missing score   local_game_state sets your_score/opp_score only inside a try, with
                      no setdefault, and play_one_turn indexes them unconditionally.

Both are fixed where the path actually runs, not where the validator sits.
"""
import glob
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import orchestrator as o
import local_hand

fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


def hand(*powers):
    return [{"kind": "player", "digit": str(p), "secondary": "1", "_art": None}
            for p in powers]


def read(rows):
    _saved = local_hand.read_hand
    try:
        local_hand.read_hand = lambda *a, **k: rows
        o._hand_memory.clear()
        return o.local_hand_cards("FRAME")
    finally:
        local_hand.read_hand = _saved
        o._hand_memory.clear()


# --- a power outside 4-9 is a MISREAD, and must not reach the engine ---------
# THE HARM, reproduced by the sweep that found it: a true hand [9,5,4,4,5] read as
# [1,5,4,4,5] puts max power at 5, under REDRAW_POWER_THRESHOLD, so should_redraw
# fires and the engine discards min(power) -- THE REAL 9. One of only two discards
# in the match, spent to throw the best card in it.
cards, why = read(hand(1, 9, 5, 4, 4))
_powers = [] if cards is None else sorted(c["power"] for c in cards)
check(cards is not None and 1 not in _powers,
      f"a power of 1 reached the hand: {_powers}")
check(9 in _powers,
      f"the rest of the hand must survive a single misread (10.28), got {_powers}")
check(cards is not None and len(cards) == 4,
      f"expected 4 usable cards, got {cards if cards is None else len(cards)}")

for bad in (0, 1, 2, 3, 10, 11, 99):
    c2, _w2 = read(hand(bad, 9, 5, 4, 4))
    _p2 = [] if c2 is None else [x["power"] for x in c2]
    check(bad not in _p2, f"power {bad} reached the hand: {_p2}")

# CONTROL: every LEGAL power must still come through, or this rule would quietly
# empty the hand and read exactly like a working guard (10.1).
for good in range(o.CARD_POWER_MIN, o.CARD_POWER_MAX + 1):
    c3, _w3 = read(hand(good, 9, 5, 4, 4))
    _p3 = [] if c3 is None else [x["power"] for x in c3]
    check(good in _p3 and len(_p3) == 5,
          f"CONTROL: legal power {good} was dropped — got {_p3}")

# ...and the range is pinned to the roster, not to a literal typed here twice
# (10.11: a test that asserts against the constant it guards passes forever).
check((o.CARD_POWER_MIN, o.CARD_POWER_MAX) == (4, 9),
      f"the power range moved to {o.CARD_POWER_MIN}-{o.CARD_POWER_MAX}; section 4 says "
      "4-9 over all 33 catalogued cards, and 1-2 are the tactics bonus digits")

# --- the score KEYS must always exist ---------------------------------------
# A None score is harmless: decision_engine reads none of your_score, opp_score,
# target_score or batters_used, and section 4 says the score must not change which card
# to play. It is the MISSING KEY that ends the match -- play_one_turn indexes it, run()
# counts 15 stuck attempts and stops with stop_reason="turn_action_failed", $50 spent.
#
# BEHAVIOURAL. A first version of this check exec'd the setdefault lines out of the
# source, which is a source-text assertion wearing a disguise -- the exact thing that
# broke twice in this session on correct code. Drive the real function instead, with
# ocr_scoreboard raising the way a missing scoreboard crop makes it raise.
import local_state


def local_state_with_broken_scoreboard():
    saved = (o._fast_grab, o.crop_gameplay_regions, o.ocr_scoreboard,
             local_hand.read_hand, local_state.read_phase,
             local_state.read_result, local_state.read_runners)
    try:
        o._fast_grab = lambda: "FRAME"
        # the three base crops too: local_game_state treats an unread diamond as a
        # GAP, not a default, so without them the state never reaches the score keys
        o.crop_gameplay_regions = lambda img: [
            ("hand", "H"), ("scoreboard", "S"),
            ("first_base", "B1"), ("second_base", "B2"), ("third_base", "B3")]
        o.ocr_scoreboard = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("no scoreboard on this frame"))
        local_hand.read_hand = lambda *a, **k: hand(9, 5, 4, 4, 5)
        local_state.read_phase = lambda *a, **k: ("batting", {})
        local_state.read_result = lambda *a, **k: {"is_result": False, "outcome": None}
        local_state.read_runners = lambda *a, **k: {"count": 0, "bases": {},
                                                    "occupied": {}, "speeds": {}}
        o._hand_memory.clear()
        return o.local_game_state()
    finally:
        (o._fast_grab, o.crop_gameplay_regions, o.ocr_scoreboard,
         local_hand.read_hand, local_state.read_phase,
         local_state.read_result, local_state.read_runners) = saved
        o._hand_memory.clear()


_st, _gap = local_state_with_broken_scoreboard()
check(_st is not None, f"the state came back as a GAP ({_gap}) — cannot test the keys")
if _st is not None:
    check("your_score" in _st and "opp_score" in _st,
          f"an ocr_scoreboard that RAISES leaves the score keys absent: "
          f"{sorted(_st)} — play_one_turn indexes them and the match dies after 15 polls")
    check(_st.get("your_score") is None and _st.get("opp_score") is None,
          f"an unreadable scoreboard must default to None, not a number: "
          f"your={_st.get('your_score')!r} opp={_st.get('opp_score')!r}")
    # ...and the caller must survive it, which is the thing that actually matters.
    try:
        _ = _st["your_score"], _st["opp_score"]
        _indexable = True
    except KeyError:
        _indexable = False
    check(_indexable, "play_one_turn's unconditional index would still raise")

# --- THE HAND CROP MUST REACH ITS READER AT THE WIDTH IT WAS CALIBRATED AT ----
# The reader is not scale-free: find_circles' and _card_digit_box's size gates are RAW
# PIXELS (DISC_MIN_R 18, DISC_WHITE_SIZE 30-50, DIGIT_W 6-26), so a crop a few percent
# wide falls outside them. The rig captures 2000x1125, whose hand crop is 1020 px against
# the 979 the reader was measured at, and at that width the fan reads MARGINALLY -- over
# one live match's own frames, 12 of 20 player cards, failures TOTAL rather than partial.
# All 22 decisions came back "Playing None" and not one card was played.
#
# NOTHING ON DISK COULD HAVE CAUGHT IT: every archived run is 1920x1080, whose hand crop
# is exactly 979, so the corpus sits at the calibration width by construction.
from PIL import Image
import local_hand as _lh

# NAMED, not globbed. The first version of this block globbed diagnostics/*/ -- a
# directory a LIVE RUN writes to -- and picked up an older bundle that is not a turn
# screen at all, so the read checks failed against the wrong picture. That is exactly
# the rule CLAUDE.md states after test_map_admit was fed 165 live leg-end frames and a
# pinned profile moved with no code change: name the fixture files.
_FIX_GEOM = os.path.join(_ROOT, "test_fixtures", "capture_geometry",
                         "turn_2000x1125_hand_unreadable.png")
check(os.path.exists(_FIX_GEOM),
      f"the capture-geometry fixture is missing ({_FIX_GEOM}) — this is the actual frame "
      "a $50 match stalled on, and without it nothing here is measured")
if os.path.exists(_FIX_GEOM):
    _src = Image.open(_FIX_GEOM)
    for _w, _h in ((2000, 1125), (1920, 1080), (1867, 1050)):
        _im = _src if _src.size == (_w, _h) else _src.resize((_w, _h), Image.LANCZOS)
        _crop = dict(o.crop_gameplay_regions(_im)).get("hand")
        check(_crop is not None and _crop.width == int(_lh.ANCHOR_W),
              f"at {_w}x{_h} the hand crop reaches the reader at "
              f"{None if _crop is None else _crop.width}px, not ANCHOR_W "
              f"{int(_lh.ANCHOR_W)} — the size gates are raw pixels, so a crop that is "
              "a few percent wide reads nothing and every decision becomes 'Playing None'")

    # ...and ONLY the hand. Every other region has its OWN anchor --
    # SCOREBOARD_ANCHOR_W 359, BASE_ANCHOR_W third/second/first 221/288/220 -- and each
    # reader divides by its own. Normalising them all to the hand's 979 would silently
    # rescale every one of those. A mutant that dropped the `label == "hand"` test
    # SURVIVED the first version of this file.
    import local_state as _ls
    _im2 = _src.resize((2000, 1125), Image.LANCZOS)
    _crops2 = dict(o.crop_gameplay_regions(_im2))
    for _label in ("scoreboard", "first_base", "second_base", "third_base"):
        _c = _crops2.get(_label)
        if _c is None:
            continue
        _frac = o.GAMEPLAY_REGIONS_FRAC[_label]
        _expect = int(2000 * _frac[2]) - int(2000 * _frac[0])
        check(_c.width == _expect,
              f"the {_label} crop came back {_c.width}px, not its own {_expect}px — only "
              f"the HAND may be normalised; {_label}'s reader divides by a different "
              "anchor and rescaling it silently moves every window inside it")

    # ...and it must actually READ at the live geometry, not merely be the right width.
    _im2k = _src if _src.size == (2000, 1125) else _src.resize((2000, 1125), Image.LANCZOS)
    _rows = _lh.read_hand(dict(o.crop_gameplay_regions(_im2k))["hand"])
    _readable = sum(1 for r in _rows if r.get("kind") == "player" and r.get("digit"))
    check(len(_rows) == 5,
          f"the fan came back as {len(_rows)} rows at 2000x1125, not 5")
    check(_readable >= 3,
          f"only {_readable} player cards read at the LIVE capture geometry — this is the "
          "frame a $50 match stalled on, and it reads 4 at the calibration width")

print("\n" + ("FAILED: " + "; ".join(fails) if fails else "all checks passed"))
sys.exit(1 if fails else 0)
