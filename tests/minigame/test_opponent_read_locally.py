"""The opponent's card must be read LOCALLY, or no at-bat is logged at all.

read_matchup_reveal is the PAID model. PAID_MODEL_ENABLED went False on
2026-09-12, and the reveal block is wrapped in a try whose own comment reads
"any failure here is swallowed and this turn just doesn't get logged" -- with
`pending_matchup = matchup_info` INSIDE it, after the paid call. So every at-bat
since raised PaidModelDisabled and was dropped entirely. Not mislabelled: absent.

Checked rather than reasoned: match_log.jsonl's last row is 2026-09-10, and three
live plays on 2026-09-17 added none.

Section 3 claims "Nothing is lost by it. The local ladder covers every field" and
names a reader for each. Every field but this one: reveal_cards was imported by
four tests and three tools and by NO production module.

THE FIXTURES ARE REAL FRAMES WITH KNOWN GROUND TRUTH, because we played them:

    t2   ours Johnny Drawers 7/1 + POWER SWING +1 = 8   theirs Mickey Brown 5, no tactics
         -> margin 3, and the live scoreboard went 0-0 to 2-0: an automatic HOME RUN
    t1   ours Austin "Cur" Bunz 8/1 + POWER SWING +2 = 10  theirs Jenny Jody Gain 6 + PITCH FOCUS +2
         -> the kind reader abstains on their banner, so the honest margin is NONE
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
T2 = "test_fixtures/reveal_kind_truth/live/t2_ours_swing1_theirs_none/r_000.jpg"
# r_002, not r_000: the t1 set was sampled on "our tactics card is on screen",
# which is the criterion for the KIND reader and not for a two-sided read, so
# only 3 of its 25 frames have the opponent readable. A fixture chosen for one
# question does not automatically answer another.
T1 = "test_fixtures/reveal_kind_truth/live/t1_ours_swing2_theirs_pitch2/r_002.jpg"
MIDAIR = "test_fixtures/reveal_banner/midanim_opener.jpg"

# ---- the reader ----
opp = o.opponent_from_reveal(F(T2), "batting")
check(opp is not None and opp["opp_power"] == 5,
      f"t2: the opponent reads as power 5 (Mickey Brown) -> {opp}")
check(opp is not None and opp["opp_tactics_bonus"] is None,
      "...with no tactics card, which is what was on screen")

check(o.opponent_from_reveal(F(MIDAIR), "batting") is None,
      "a mid-animation frame yields None rather than a guess")
check(o.opponent_from_reveal(None, "batting") is None,
      "and a missing frame is None, not a raise into the turn loop")

# ---- END TO END: the margin and the outcome the game's own rule gives ----
# Our side is the ENGINE'S OWN CHOICE, never read from the screen.
row2 = {"phase": "batting", "our_power": 7, "our_tactics_bonus": 1,
        "our_tactics_kind": "swing_boost"}
row2.update(o.opponent_from_reveal(F(T2), "batting"))
m2 = o.reveal_margin(row2)
check(m2 == 3, f"t2 margin is 3 (ours 7+1=8 vs theirs 5), got {m2}")
out2, basis2 = o.classify_outcome(m2, 2, 1, 0)
check(out2 == "home_run" and basis2 == "margin",
      f"...so the game's rule names it a HOME RUN on the MARGIN basis, "
      f"not the score delta -- got {out2}/{basis2}")

# THE ABSTENTION, AND IT IS THE POINT. Their PITCH FOCUS +2 is a real read bonus
# whose KIND did not clear TACTICS_KIND_MIN, and effective_power refuses to price
# an unknown kind at zero -- so no margin, rather than a wrong one.
row1 = {"phase": "batting", "our_power": 8, "our_tactics_bonus": 2,
        "our_tactics_kind": "swing_boost"}
row1.update(o.opponent_from_reveal(F(T1), "batting"))
check(row1["opp_power"] == 6, f"t1: the opponent reads as power 6, got {row1['opp_power']}")
check(row1["opp_tactics_bonus"] == 2,
      f"...carrying a +2 badge, got {row1['opp_tactics_bonus']}")
m1 = o.reveal_margin(row1)
check(m1 is None,
      f"and the margin ABSTAINS because their bonus's kind did not read, got {m1}")

# CONTROL: the same row with the kind KNOWN does produce a margin, so the
# abstention above is the kind reader's doing and not a dead code path.
row1_known = dict(row1, opp_tactics_kind="pitch_boost")
check(o.reveal_margin(row1_known) == 2,
      f"CONTROL: told their kind, the margin is 2 (10 vs 6+2), got {o.reveal_margin(row1_known)}")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
