"""patch71 -- the hand is FIVE CARDS IN A FIXED FAN, so segment the cards before reading.

Measured over the 57 vision-labelled hands in overnight/local_hand/agreement.jsonl, with
alignment PROVEN (the card count matches AND the set of tactics slots matches):

    shipped, searching the whole strip for discs      ALIGNED 10/57   WRONG 3
    the five-slot fan                                 ALIGNED 57/57   WRONG 0
    HELD OUT, the 15 five-card bakeoff hands          ALIGNED 15/15   WRONG 0
                                     (shipped there)  ALIGNED  5/15

Everything here was found by four independent agents and then re-derived by four
independent skeptics who re-implemented the metric before reading anyone's scorer. Three
things this patch carries are MY corrections on top of that work.

WHAT THIS PATCH DOES, in the order it matters:

1. circle_finder.find_circles takes a dark threshold. A 9 or a 7 TOUCHES its disc's outline
   ring; at DARK=110 the two label as one ~45x100 component, the size gate discards it, and
   the whole CARD vanishes. A second pass at 90 raises per-card disc recall 254/285 ->
   265/285. The default is unchanged, so no existing caller moves.

2. local_hand reads the FAN. Each slot is a measured 2D anchor, every candidate goes to its
   nearest slot, and the count therefore cannot be wrong. Kind comes from WHERE the disc
   sits: a tactics card carries its disc 60-83 px further left, inside the wreath.

3. MY CORRECTION ONE -- six bad templates are removed. Three are mislabelled (#1283 is a 6
   labelled 7, #1284 a 5 labelled 6, #1296 a 4 labelled 7) and three are not digits at all
   (#1272, #1285, #1295). Each matches its offending crop at correlation 1.0000, i.e. it was
   cut from that very frame and labelled one card off. THEY ARE MINE: I cut them last night
   using positional alignment on count-matching hands, which is the exact unsound method I
   had proven unsound an hour earlier. They cause 4 of the 5 remaining wrong digits. Two
   agents found them independently and I rendered all six and looked before deleting.

4. MY CORRECTION TWO -- the ungated fallback stops calling a card "player". On that path
   there is no positional evidence, and the shipped reader claiming "player" for every disc
   it found is what read "Power Swing bonus 2" as a power-2 batter at score 0.972 and
   "Fielding Play" as a 6 at 0.993. Three discriminators were measured against both
   populations and ALL THREE OVERLAP (ring darkness, blob size beside the disc, and shield
   presence -- 23% of PLAYER cards carry no shield). The fan path has a measured signal and
   may say "player"; the fallback has none and now says "unknown".

5. MY CORRECTION THREE -- the module docstring's KNOWN GAPS were stale. It claimed the
   templates cover only 1,2,4,5,7,8, that a tactics bonus can show a 3 (the user confirmed
   2026-09-09 that THE GAME HAS NO 3), and that nothing tells a tactic from a player card.

WHAT IS STILL NOT KNOWN, kept because it decides whether this may ever replace the paid
call: a tactics card's TYPE is unread, and only swing and pitch boosts add power.
"""
import io
import os
import shutil

import numpy as np

SRC = ("/private/tmp/claude-502/-Users-bpatterson-Documents-Claude-Cowork-Personal-"
       "Auto-Baseball/e6392fcc-4b59-4ace-b5b6-76c4bf041181/scratchpad/skeptic/prop2")

# ---- ASSERT EVERY ANCHOR BEFORE WRITING ANY FILE (CLAUDE.md 10.19) --------------------
new_cf = io.open(os.path.join(SRC, "circle_finder.py"), encoding="utf-8").read()
new_lh = io.open(os.path.join(SRC, "local_hand.py"), encoding="utf-8").read()
assert "def find_circles(img, dark_thr=DARK):" in new_cf, "cf: threshold parameter missing"
assert "SLOT_PLAYER = [(195, 195)" in new_lh, "lh: player anchors missing"
assert "SLOT_TACTICS = [(132, 194)" in new_lh, "lh: tactics anchors missing"
assert "ANCHOR_W = 979.0" in new_lh, "lh: the geometry scale is missing"
assert "img.width / ANCHOR_W" in new_lh, "lh: anchors are not scaled to the crop"

UNGATED = '''        out.append({"x": c[0], "kind": "player", "digit": d, "score": round(s, 3)})'''
assert new_lh.count(UNGATED) == 1, f"lh: ungated player claim x{new_lh.count(UNGATED)}"

OLD_GAPS = '''KNOWN GAPS, stated because they decide whether this may replace the paid call:
  * the templates cover 1, 2, 4, 5, 7, 8. The roster says a power circle can also show
    6 and 9, and a tactics bonus can show 3. Those three have no template yet, so this
    reader ABSTAINS on them rather than guessing -- which is why read_hand returns None
    for a digit it cannot match, and why the caller must treat None as "ask the API".
  * the shield digit is white on a DARK shield, the exact inverse of this detector's
    target. It is not read here at all.
  * a tactic and a player card are told apart by the BANNER, not the circle, and no
    banner is read here.'''
assert new_lh.count(OLD_GAPS) == 1, "lh: KNOWN GAPS block not found verbatim"

z = np.load("digit_templates.npz")
V, D = z["vectors"], [str(s) for s in z["digits"]]
BAD = {1272: "not a digit", 1283: "a 6 labelled 7", 1284: "a 5 labelled 6",
       1285: "not a digit", 1295: "not a digit", 1296: "a 4 labelled 7"}
assert len(D) == 1314, f"template bank is {len(D)}, expected 1314 -- indices would shift"
assert [D[k] for k in (1283, 1284, 1296)] == ["7", "6", "7"], "the accused labels moved"

NEW_GAPS = '''KNOWN GAPS, stated because they decide whether this may replace the paid call:
  * A TACTICS CARD'S TYPE IS NOT READ, and that is the gap that matters. CLAUDE.md section
    4: only swing and pitch boosts add power, while speed and fielding boosts carry a
    nonzero bonus that adds NONE. orchestrator derives that type from the card's NAME, and
    no banner is read here -- so a hand holding a tactics card still needs the paid call to
    decide what to play. 14 of 15 measured hands hold at least one.
  * The tactics BONUS is not read either. Its digit sits fused inside the wreath.
  * The shield digit is white on a DARK shield, the exact inverse of this detector's
    target. It is not read here at all.
  * Which cards are PLAYER and which are TACTICS is decided by WHERE the disc sits in its
    slot, and only on the fan path. When the fan does not fit -- a short hand, an empty
    table -- there is no such evidence and every position comes back "unknown".
  * Templates cover 1, 2, 4, 5, 6, 7, 8, 9. THE GAME HAS NO 3 (the user, 2026-09-09) and no
    player card has ever shown a power of 1, 2 or 3: powers run 4 to 9, and 1 and 2 appear
    only as tactics bonuses. A digit that matches nothing comes back None, which the caller
    must treat as NOT READ -- never as absent.'''

NEW_UNGATED = '''        # NOT "player". Off the fan there is no positional evidence of kind, and
        # claiming it read a tactics card as a batter -- see KNOWN GAPS above.
        out.append({"x": c[0], "kind": "unknown", "digit": d, "score": round(s, 3)})'''

# ---- every anchor held; now write ----------------------------------------------------
shutil.copyfile(os.path.join(SRC, "circle_finder.py"), "circle_finder.py")
out = new_lh.replace(OLD_GAPS, NEW_GAPS, 1).replace(UNGATED, NEW_UNGATED, 1)
assert '"kind": "player", "digit": d' not in out, "an unevidenced player claim survived"
io.open("local_hand.py", "w", encoding="utf-8").write(out)

keep = [i for i in range(len(D)) if i not in BAD]
np.savez_compressed("digit_templates.npz", vectors=V[keep],
                    digits=np.array([D[i] for i in keep]))
print(f"circle_finder.py + local_hand.py written")
print(f"templates {len(D)} -> {len(keep)}; dropped " +
      ", ".join(f"#{k} ({why})" for k, why in sorted(BAD.items())))
