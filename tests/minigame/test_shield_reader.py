"""The shield reader must find the badge, read it, and say 0 only when there is none.

WHY THIS FILE EXISTS. `hand_to_cards()` requires `secondary` on EVERY player card,
so while the shield was unread the local path could not build a hand at all -- local
state coverage sat at 0% no matter how good the other readers were. This is the
reader that unblocked it.

TWO LOCATORS FAILED BEFORE THIS ONE, and both failed silently at high confidence:
the first hunted DARK blobs and located the neighbouring card's power disc (its
contact sheet showed 4s and 5s where a shield only ever shows 1-3); the second added
a polarity test and found 14 badges in 339 cards. What works is SEARCHING for the
sprite with matchTemplate -- the same fix that rescued the runners reader -- because
the badge rides with the card when the cursor lifts it, so no fixed offset can hold.

THE LABELS ARE NOT MINE. Every value pinned below is one the paid vision model and
this reader reached INDEPENDENTLY and agreed on. A fixture pinned to this reader's
own output would assert against the thing it guards (CLAUDE.md 10.11, 10.22).
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image                                                   # noqa: E402

import local_hand                                                       # noqa: E402

FIX = os.path.join(_ROOT, "test_fixtures", "shields")
fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# ---- 0. the fixtures, and an anti-vacuity floor -------------------------------------
# A file that passes by finding nothing is worse than no file (CLAUDE.md 10.12), so the
# corpus is asserted before anything is read from it.
data = json.load(open(os.path.join(FIX, "expected.json")))
hands = data["hands"]
pinned = [(h["file"], c["slot"], c["secondary"]) for h in hands for c in h["cards"]]
check("fixtures present", len(hands) >= 6, f"{len(hands)} hands")
check("enough pinned cards to mean anything", len(pinned) >= 20, f"{len(pinned)} cards")

# AND IT MUST COVER EVERY VALUE INCLUDING 0. Without this a reader that answered one
# number forever would pass whichever number happened to dominate the fixtures -- and
# 0 is the one that matters most, because "no badge" is the answer the two failed
# locators got wrong in opposite directions.
values = {s for _, _, s in pinned}
check("every shield value is represented, 0 included",
      values >= {0, 1, 2, 3}, f"covers {sorted(values)}")

# ---- 1. the templates are on disk and are the sprites, not an empty file -------------
tpl = local_hand._shield_templates()
check("badge templates load", set(tpl) == {1, 2, 3}, f"digits {sorted(tpl)}")
check("templates are the badge, not a stub",
      all(t.shape == (local_hand.SHIELD_SIZE[1], local_hand.SHIELD_SIZE[0]) for t in tpl.values()),
      str({k: v.shape for k, v in sorted(tpl.items())}))

# ---- 2. THE GATE SITS BETWEEN TWO MEASURED POPULATIONS, AND IS PINNED AS A LITERAL ---
# Measured over 1,155 player cards: shielded p05 0.843, unshielded p99 0.541. A test
# that compared the constant against itself would rise with it and pass forever
# (CLAUDE.md 10.11), so both edges of the empty band are written out here.
check("SHIELD_MIN sits inside the empty band 0.541 .. 0.843",
      0.541 < local_hand.SHIELD_MIN < 0.843, f"SHIELD_MIN={local_hand.SHIELD_MIN}")
check("SHIELD_MIN is the value that was measured", local_hand.SHIELD_MIN == 0.69,
      str(local_hand.SHIELD_MIN))

# ---- 3. it reads every pinned card ---------------------------------------------------
read = 0
for h in hands:
    img = Image.open(os.path.join(FIX, h["file"])).convert("RGB")
    rows = local_hand.read_hand(img)
    for c in h["cards"]:
        i = c["slot"]
        got = rows[i].get("secondary") if i < len(rows) else None
        read += 1
        check(f"{h['file']} slot {i}: secondary {c['secondary']}",
              got == c["secondary"], f"got {got}")
check("every pinned card was actually read", read == len(pinned), f"{read}/{len(pinned)}")

# ---- 4. AND IT NEVER INVENTS A BADGE ON A CARD THAT HAS NONE -------------------------
# This is the half worth more. A wrong `secondary` plays a card with the wrong
# second stat in a $50 match and nothing reports an error; a missing one costs one
# API call. Scored separately so a reader that got good at 1/2/3 by answering
# generously cannot hide it in the overall rate.
zeros = [(f, s) for f, s, v in pinned if v == 0]
wrong_zero = 0
for h in hands:
    img = Image.open(os.path.join(FIX, h["file"])).convert("RGB")
    rows = local_hand.read_hand(img)
    for c in h["cards"]:
        if c["secondary"] != 0:
            continue
        if c["slot"] < len(rows) and rows[c["slot"]].get("secondary") not in (0, None):
            wrong_zero += 1
check("no badge is invented on an unshielded card",
      wrong_zero == 0, f"{wrong_zero} of {len(zeros)} invented")

# ---- 5. the reader is honest when it cannot run --------------------------------------
# It must return None -- "ask the paid model" -- rather than 0, which is a real answer.
# A crop too small to hold a badge is the case that actually occurs, when a hand crop
# lands short at the frame edge.
tiny = Image.new("RGB", (40, 30), (0, 0, 0))
d, sc = local_hand.read_shield(tiny, 20, 15)
check("a crop too small to search abstains rather than answering 0",
      d is None, f"returned {d} at {sc}")

# ---- 6. every player row carries the field hand_to_cards needs -----------------------
img = Image.open(os.path.join(FIX, hands[0]["file"])).convert("RGB")
rows = local_hand.read_hand(img)
players = [r for r in rows if r["kind"] == "player"]
check("read_hand puts secondary on every player row",
      bool(players) and all("secondary" in r for r in players),
      f"{sum('secondary' in r for r in players)}/{len(players)}")
check("and its score, so a caller can abstain on a weak read",
      all("secondary_score" in r for r in players))

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
