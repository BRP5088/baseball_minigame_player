"""at_table() must not fire on a frame with no prompt.

THE BUG. MATCH_MIN was 0.15, which sits BELOW the highest measured negative.
Measured over all 3262 archived demo frames after at_table() fired on a frame
showing no prompt at all:

    score < 0.15    1817 frames   the bulk of the route
    0.15 - 0.25       52 frames   INCLUDING A CONFIRMED FALSE POSITIVE
    0.25 - 0.40      366 frames   genuine prompts start here
    0.40 - 0.60       28 frames   trough
    0.60 +           924 frames   clear prompts

The negative anchor was eyeballed and then confirmed by the user: the quest log
is open and its text supplies both the ink and the stroke correlation, and the
player is not close enough for the game to offer the prompt at all.

WHY IT MATTERS TWICE. at_table() is the authority for "arrived at the dealer
table" — CLAUDE.md says dealer_table is a POSE and must never be confirmed by
identify() — AND it gates the Square press that spends $50. A false positive
records an arrival that did not happen and can commit money at nothing.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image
import table_prompt as tp

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# Both anchors are REAL FRAMES, committed in demos/. A missing fixture is a
# failure, not a skip — eleven files in this suite refuse to silently skip and
# this is not going to be the twelfth.
NEG = os.path.join(_ROOT, "demos/walk2_pauses_20260828_044514/f_0049.22.jpg")
POS = os.path.join(_ROOT, "demos/spawn_to_table_20260827_212516/f_0054.32.jpg")

for p in (NEG, POS):
    if not os.path.exists(p):
        print(f"FAIL missing anchor frame {p} — this test cannot run, and a "
              f"test that cannot run must not report success")
        sys.exit(1)

neg, pos = Image.open(NEG), Image.open(POS)
ns, ps = tp.score(neg), tp.score(pos)

print(f"  negative anchor scores {ns:.4f}   positive anchor scores {ps:.4f}")

check("the quest-log frame with NO prompt is rejected", tp.at_table(neg) is False)
check("the frame with a legible prompt is accepted", tp.at_table(pos) is True)

# THE GAP ITSELF. Pinned as literals — comparing MATCH_MIN to itself would pass
# for any value, which is exactly how it drifted to 0.15 unnoticed.
check("MATCH_MIN sits ABOVE the confirmed negative", tp.MATCH_MIN > ns)
check("MATCH_MIN sits BELOW the confirmed positive", tp.MATCH_MIN < ps)
check("MATCH_MIN is the value measured into the gap", tp.MATCH_MIN == 0.25)

# The negative anchor clears INK_MIN, which is why ink alone cannot save this.
check("ink alone does NOT separate these two (so score must)",
      tp.ink(neg) >= tp.INK_MIN)

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
