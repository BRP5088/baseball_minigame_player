"""I-64: the TYPE banner missed plainly visible tactics cards because BANNER_SEARCH's
x step (4px) straddled the true peak, which sits at ox = +-2 for these cards -- never
sampled by ..., -4, 0, 4, .... The RANGE (+-12x/+-6y) was already enough; measured by
widening it to +-32x/+-16y and getting the SAME recoveries as just halving the x step
(agent_progress/issues/I-64/step1a_results.json vs step1b). See local_hand.py's
BANNER_SEARCH comment for the full measurement, including the FALSE column: over 1613
real player-card banner reads at the same finer step, the maximum is 0.714 -- 0.136
under MIN_TYPE_SCORE (0.85), still an empty band between the two populations.

Ground truth is the user's hand labels (test_fixtures/user_truth/20260923_c20-26/
labels.json): of 14 readable tactics slots, this fix recovers 6, all correct, 0 wrong
(agent_progress/issues/I-64/measure_step1e_ground_truth.py). Five of the six are
fixtured here (test_fixtures/tactics_banner_misses, picked for TYPE diversity), plus
the single real PLAYER card whose fine-step banner score comes closest to the gate
(0.714) across the whole corpus -- the control that must NOT flip. Losing either
direction is worse than the bug this ticket fixes: a tactics card silently
un-recovering costs one paid-model call same as before; a player card gaining a
fabricated tactics type would play the wrong card for $50.

A second cause -- the neighbouring card clipping the banner's left edge -- was
measured and is NOT shipped (see local_hand.py's comment above read_tactics_type):
a right-only match recovers 4 more of the 14, but it also defeats
tests/minigame/test_i22_pitch_boost_slot3.py's mutation guard, so it is left as a
documented, reproducible finding rather than a change to this file.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image                                                   # noqa: E402

import local_hand                                                       # noqa: E402

FIX = os.path.join(_ROOT, "test_fixtures", "tactics_banner_misses")
fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


data = json.load(open(os.path.join(FIX, "expected.json")))

# ---- 1. THE STEP, PINNED AS A LITERAL --------------------------------------------
# A test that compares against the constant itself rises with it and passes forever
# (CLAUDE.md 10.11 / METHODOLOGY.md).
xs = sorted({ox for ox, _ in local_hand.BANNER_SEARCH})
check("BANNER_SEARCH's x step is 2 (was 4)", xs[1] - xs[0] == 2, str(xs[:3]))
check("BANNER_SEARCH's x range is unchanged (+-12)", xs[0] == -12 and xs[-1] == 12, str((xs[0], xs[-1])))

# ---- 2. THE FIVE MISSES NOW RECOVER THEIR TYPE ------------------------------------
n_graded = 0
for m in data["misses"]:
    img = Image.open(os.path.join(FIX, m["file"])).convert("RGB")
    rows = local_hand.read_hand(img)
    i = m["slot"]
    if i >= len(rows):
        check(f"q{m['q']} {m['file']} slot {i}: row exists", False, "row missing")
        continue
    row = rows[i]
    n_graded += 1
    check(f"q{m['q']} {m['file']} slot {i}: still kind=='tactics'", row.get("kind") == "tactics",
          f"got {row.get('kind')!r}")
    check(f"q{m['q']} {m['file']} slot {i}: TYPE now reads (was None at the shipped step)",
          row.get("type") == m["expected_type"], f"got {row.get('type')!r}")
check("the miss fixtures actually graded something", n_graded >= 3, f"{n_graded} cards")

# ---- 3. THE CONTROL: the closest real player card must NOT flip -------------------
p = data["player"]
img = Image.open(os.path.join(FIX, p["file"])).convert("RGB")
rows = local_hand.read_hand(img)
i = p["slot"]
row = rows[i] if i < len(rows) else {}
check(f"{p['file']} slot {i}: still kind=='player'", row.get("kind") == p["expected_kind"],
      f"got {row.get('kind')!r}")
check(f"{p['file']} slot {i}: digit unaffected", row.get("digit") == p["expected_digit"],
      f"got {row.get('digit')!r}")
check(f"{p['file']} slot {i}: no tactics type leaked onto a player row",
      row.get("type") is None, f"got {row.get('type')!r}")

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
