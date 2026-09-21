"""I-31 (P0 live stop): a readable hand with no readable player BANNER stalled the
first turn of every fresh match, forever -- "LOCAL STATE GAP: phase not read locally".

overnight/run_live_20260921c.log: after "verified 3/3 bans placed" the first turn of a
fresh match hit 15 polls of that gap and stopped with unreadable_screens. The frame
(overnight/crawl/20260921_002544/001_before.png, hand crop kept here as
test_fixtures/phase/i31_fresh_match_tactics_batting.png) has FOUR of five slots
unreadable by banner: two POWER SWING (swing_boost) tactics cards, one occluded player
slot, one tactics slot too dim to type, and exactly ONE readable player banner. Two
votes clear PHASE_MIN_CARDS on their own, but the bug is that `read_phase` never asked
the tactics cards anything -- CLAUDE.md section 4: "Only SWING_BOOST and PITCH_BOOST add
power" is the same four-way split decision_engine.TacticsType encodes, and RULES.md's
observed reveals agree that a tactics card's KIND is tied to which half deals it.

Two layers, both load-bearing on their own:

  (local_state.read_phase)   a readable TACTICS kind is a phase vote too, pooled with
                             the banner votes, still abstaining on disagreement or zero
  (orchestrator.local_game_state)  when the reader STILL abstains on a readable turn
                             screen, fall back to the match's own fixed shape -- batting
                             first, pitching after ROUNDS_PER_HALF turns -- rather than
                             raising a gap a fully-dealt hand should never raise
"""
import contextlib
import io
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import numpy as np                                                      # noqa: E402
from PIL import Image                                                   # noqa: E402

import local_hand as lh                                                 # noqa: E402
import local_state as ls                                                # noqa: E402
import orchestrator                                                     # noqa: E402
import table_prompt                                                     # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# ---- (a) THE EVIDENCE FIXTURE, via read_phase's tactics votes alone -------------------
FIX = os.path.join(_ROOT, "test_fixtures", "phase", "i31_fresh_match_tactics_batting.png")
img = Image.open(FIX).convert("RGB")
ph, detail = ls.read_phase(img)
check("I-31 evidence fixture reads batting (was None before the tactics-vote fix)",
      ph == "batting", f"got {ph!r} detail={detail!r}")
check("...and at least two tactics cards actually voted",
      detail.get("cards", 0) >= 2, f"detail={detail!r}")

# ---- (b) A SYNTHETIC HAND, tactics votes only, no banner reads at all ------------------
# Both readable player banners on this frame could be occluded and the vote must still
# resolve -- PITCH_FOCUS and FIELDING_PLAY exist only in a pitching hand.
_saved_fan, _saved_type, _saved_banner = (
    ls._fan_discs, lh.read_tactics_type, ls.phase_banner_vector)
try:
    def fan_tactics_only(_img):
        # slots 0 and 2 are tactics cards; nothing else was reached.
        return [((0,), 10, 10, "tactics"), None, ((0,), 20, 20, "tactics"), None, None]

    def type_pitch_and_field(_img, slot, cx=None, cy=None):
        return ({0: "pitch_boost", 2: "fielding_boost"}.get(slot), 0.90)

    ls._fan_discs = fan_tactics_only
    lh.read_tactics_type = type_pitch_and_field
    dummy = Image.new("RGB", (979, 307), (10, 10, 10))
    ph_b, detail_b = ls.read_phase(dummy)
    check("synthetic pitch_boost + fielding_boost (no banners) reads pitching",
          ph_b == "pitching", f"got {ph_b!r} detail={detail_b!r}")
    check("...both tactics cards were counted",
          detail_b.get("cards") == 2, f"detail={detail_b!r}")

    # ---- (c) CONFLICTING votes: a PITCHER banner against a swing_boost (batting) card -
    def fan_mixed(_img):
        return [((0,), 10, 10, "player"), ((0,), 20, 20, "tactics"), None, None, None]

    def type_swing_only(_img, slot, cx=None, cy=None):
        return ("swing_boost" if slot == 1 else None, 0.90)

    def banner_fixed(_img, _x, _y):
        return np.array([1.0])

    ls._fan_discs = fan_mixed
    lh.read_tactics_type = type_swing_only
    ls.phase_banner_vector = banner_fixed
    bank = (np.array([[1.0]]), ["pitcher"])   # any banner scores as "pitcher"
    ph_c, detail_c = ls.read_phase(dummy, bank=bank)
    check("a PITCHER banner against a swing_boost tactics vote abstains, never guesses",
          ph_c is None, f"got {ph_c!r} detail={detail_c!r}")
    check("...and both conflicting votes were recorded, not dropped",
          detail_c.get("cards") == 2
          and set(detail_c.get("votes", {})) == {"batting", "pitching"},
          f"detail={detail_c!r}")
finally:
    ls._fan_discs, lh.read_tactics_type, ls.phase_banner_vector = (
        _saved_fan, _saved_type, _saved_banner)

# ---- (d) orchestrator.local_game_state's MATCH-STATE FALLBACK, reader abstaining ------
# Same stub ladder as test_should_redraw_incomplete.py section 6: everything before the
# hand is stubbed out of the way, and local_state.read_phase always abstains here so the
# fallback is the only thing that can produce a phase at all.
saved = (orchestrator._fast_grab, orchestrator.crop_gameplay_regions,
         orchestrator.local_hand_cards, orchestrator.read_ban_counter,
         ls.read_result, ls.read_phase, ls.read_runners, table_prompt.at_table)
try:
    dummy_frame = object()
    orchestrator._fast_grab = lambda: dummy_frame
    orchestrator.crop_gameplay_regions = lambda full: [
        ("hand", dummy_frame), ("third_base", dummy_frame),
        ("second_base", dummy_frame), ("first_base", dummy_frame)]
    orchestrator.read_ban_counter = lambda full: None
    ls.read_result = lambda full: {"is_result": False}
    ls.read_phase = lambda img: (None, {"votes": {}, "cards": 0})   # ALWAYS abstains
    ls.read_runners = lambda *a: {"count": 0}
    table_prompt.at_table = lambda full: False

    five_cards = [{"kind": "player", "name": None, "power": 5, "secondary": 0,
                  "hand_index": i} for i in range(5)]
    orchestrator.local_hand_cards = (
        lambda hand_img, phase=None, homeplate_runner=False: (five_cards, None))

    # A fresh match: no turns played this half yet.
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        st, gap = orchestrator.local_game_state(turns_this_half=0)
    check("fresh-match state (turns_this_half=0) falls back to batting",
          st is not None and st.get("phase") == "batting",
          f"gap={gap!r} st={st!r}")
    check("...and never raises 'phase not read locally' with a readable hand",
          gap is None, f"gap={gap!r}")
    check("...logging that the fallback fired",
          "phase from match state (reader abstained)" in out.getvalue(),
          out.getvalue())

    # After the half boundary: a full batting half has already been played.
    st2, gap2 = orchestrator.local_game_state(turns_this_half=orchestrator.ROUNDS_PER_HALF)
    check("after the half boundary (turns_this_half=ROUNDS_PER_HALF) falls back to pitching",
          st2 is not None and st2.get("phase") == "pitching",
          f"gap2={gap2!r} st2={st2!r}")

    # CONTROL: with no hint at all, the old refusal survives untouched.
    st3, gap3 = orchestrator.local_game_state()
    check("CONTROL: no turns_this_half hint -> the old refusal still fires",
          st3 is None and gap3 == "phase not read locally", f"gap3={gap3!r} st3={st3!r}")
finally:
    (orchestrator._fast_grab, orchestrator.crop_gameplay_regions,
     orchestrator.local_hand_cards, orchestrator.read_ban_counter,
     ls.read_result, ls.read_phase, ls.read_runners, table_prompt.at_table) = saved

# ---- (d) I-37 REGRESSION: `_fan_discs` must not disagree with `read_hand` about --------
# whether the fan is there at all. `local_state._fan_discs` used to carry its OWN
# reimplementation of that gate (first a median-residual check, later untouched when
# `local_hand.read_hand`'s gate moved to a COUNT rule and again when I-37 broadened that
# count to pool white-disc/wreath candidates) -- so on a genuine hand with 2 of 5 slots
# occluded, `read_hand` admitted the fan (5 rows, 2 correctly marked unreadable per
# CLAUDE.md 10.28) while `_fan_discs` rejected it outright, and `read_phase` abstained
# with ZERO votes on a hand carrying two perfectly legible player banners. Bisected in
# the main checkout against tests/minigame/test_hand_memory_persists.py: with local_hand.py
# at ccdd46b (pre-I-37) the test passed; with the I-37 gate it failed on exactly this
# frame, kept here as a named fixture (never glob agent_progress/deal-frames/, which is
# gitignored, absent in a fresh checkout, and live-written -- CLAUDE.md section 2).
FAN_FIX = os.path.join(_ROOT, "test_fixtures", "hand_reads",
                        "i37_fan_discs_disagreed_with_read_hand.png")
_fimg = Image.open(FAN_FIX).convert("RGB")
_frows = lh.read_hand(_fimg)
check("I-37 regression fixture: read_hand recognises the fan (5 rows)",
      len(_frows) == 5, f"got {len(_frows)} rows: {_frows!r}")
_fbest = ls._fan_discs(_fimg)
check("...and _fan_discs agrees a fan is present (not None)",
      _fbest is not None, f"got {_fbest!r}")
_fph, _fdetail = ls.read_phase(_fimg)
check("...so read_phase gets real votes instead of abstaining at cards=0",
      _fdetail.get("cards", 0) > 0, f"detail={_fdetail!r}")
check("...and derives the correct phase (batting) from them",
      _fph == "batting", f"got {_fph!r} detail={_fdetail!r}")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
