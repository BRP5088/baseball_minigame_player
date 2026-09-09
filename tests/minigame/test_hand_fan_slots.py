"""The hand is FIVE CARDS IN A FIXED FAN, and reading it that way is what made the reader
agree with the paid model about POSITIONS.

WHY THIS FILE EXISTS. The reader used to search the whole strip for discs, so it could
return any number of card positions -- measured over the 57 vision-labelled hands it
returned between 3 and 8, and only 10 of 57 agreed with the paid model about which slot
held which card. That is not a cosmetic problem: when the positions are wrong, every digit
after the first error is attributed to the wrong card, and a hand can be scored 100%
correct while reading a power off a mouse's face. It happened -- two of the old reader's
"correct" digits were card art, and its 10 aligned hands contained 2 coincidences.

    shipped, whole-strip search      ALIGNED 10/57   WRONG 3     held-out bakeoff  5/15
    the five-slot fan                ALIGNED 57/57   WRONG 0     held-out bakeoff 15/15

The checks below guard the properties that produced that, not the number itself.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image                                                   # noqa: E402

import circle_finder                                                    # noqa: E402
import local_hand                                                       # noqa: E402

FIX = os.path.join(_ROOT, "test_fixtures", "hand_digits")
fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


expected = json.load(open(os.path.join(FIX, "expected.json")))

# ---- 1. THE PROPERTY THAT MOVED THE NUMBER: the KIND of every slot matches the paid
# model. This is what "aligned" means, and it is what the old reader failed on 47 of 57
# hands. A hand with a tactics card must not report five players.
for fname, meta in sorted(expected.items()):
    rows = local_hand.read_hand(Image.open(os.path.join(FIX, fname)).convert("RGB"))
    paid = meta["paid"]
    check(f"{fname}: five card positions", len(rows) == len(paid), f"got {len(rows)}")
    if len(rows) == len(paid):
        got = [r["kind"] for r in rows]
        want = [c["kind"] for c in paid]
        check(f"{fname}: kinds match the paid model",
              [g == w for g, w in zip(got, want)] == [True] * len(want),
              f"got {got} want {want}")
        bad = [(i, r["digit"], c.get("power")) for i, (r, c) in enumerate(zip(rows, paid))
               if c["kind"] == "player" and r["digit"] is not None
               and str(r["digit"]) != str(c["power"])]
        check(f"{fname}: no digit contradicts the paid model", not bad, str(bad))

# ---- 1b. KIND COMES FROM WHERE THE DISC SITS, and that is the only signal there is.
# A tactics card carries its disc 60-83 px further LEFT, inside its wreath. Measured over
# the 57-hand corpus, 79 of 83 tactics slots are decided by that offset and only 4 by the
# empty-slot default below -- so this is the load-bearing mechanism, not a tie-break.
# THE FIXTURES NAMED HERE WERE CHOSEN BECAUSE POSITION DECIDES THEM: an earlier pair
# happened to be default-decided, and a mutant that set the tactics anchors equal to the
# player anchors SURVIVED the whole file.
#
# Nothing else can supply this. A gate on the card's dark fraction was scanned over 2,688
# windows (4 widths x 14 offsets x 16 bands x 3 heights) against 202 player and 83 tactics
# slots and every window's populations OVERLAP; so do ring darkness, blob size beside the
# disc, and shield presence -- 23% of PLAYER cards carry no shield (CLAUDE.md 10.4).
for fname in ("tactics_bypos0.png", "tactics_bypos1.png"):
    meta = expected[fname]
    rows = local_hand.read_hand(Image.open(os.path.join(FIX, fname)).convert("RGB"))
    want = [c["kind"] for c in meta["paid"]]
    check(f"{fname}: kind decided by disc position matches the paid model",
          [r["kind"] for r in rows] == want, f"got {[r['kind'] for r in rows]}")
    for i in meta["tactics_decided_by_position"]:
        check(f"{fname}: slot {i} is tactics because a disc sits at the tactics anchor",
              rows[i]["kind"] == "tactics", f"got {rows[i]['kind']}")
# The anchors must actually differ, or "position" decides nothing.
check("the tactics anchors sit LEFT of the player anchors, by 60-83 px",
      all(60 <= p[0] - t[0] <= 83
          for p, t in zip(local_hand.SLOT_PLAYER, local_hand.SLOT_TACTICS)),
      str([p[0] - t[0] for p, t in zip(local_hand.SLOT_PLAYER, local_hand.SLOT_TACTICS)]))

# ---- 2. A SHORT HAND MUST NOT BE FORCED INTO FIVE SLOTS. Late in a match a hand shrinks
# and the fan RE-CENTRES, so the anchors do not apply. Ungated is the safe answer; five
# phantom slots is not.
for short in ("short018.png", "short003.png"):
    p = os.path.join(FIX, short)
    if not os.path.exists(p):
        check(f"{short} present", False, "fixture missing")
        continue
    rows = local_hand.read_hand(Image.open(p).convert("RGB"))
    check(f"{short}: not forced to five slots", len(rows) != 5, f"got {len(rows)} rows")
    check(f"{short}: falls back, so claims no kind it cannot see",
          all(r["kind"] != "player" for r in rows), str([r["kind"] for r in rows]))

# ---- 3. THE ANCHORS ARE SCALED TO THE CROP. They were measured on a 979-wide crop, which
# is a 1920x1080 capture; CLAUDE.md section 3 records 1867x1050 captures in the SAME
# session, a 952-wide crop. Unscaled anchors drop this from 57/57 to 31/57 with no error
# anywhere -- the signature failure of this project.
ref = os.path.join(FIX, "hand025.png")
base = local_hand.read_hand(Image.open(ref).convert("RGB"))
for w, h in ((952, 298), (1200, 376)):
    scaled = Image.open(ref).convert("RGB").resize((w, h), Image.LANCZOS)
    rows = local_hand.read_hand(scaled)
    check(f"a {w}x{h} crop still reads five slots", len(rows) == len(base),
          f"got {len(rows)} against {len(base)} at native size")
    if len(rows) == len(base):
        check(f"a {w}x{h} crop reads the same digits",
              [r["digit"] for r in rows] == [r["digit"] for r in base],
              f"{[r['digit'] for r in rows]} vs {[r['digit'] for r in base]}")
check("anchors are declared in the crop width they were measured at",
      local_hand.ANCHOR_W == 979.0, str(local_hand.ANCHOR_W))

# ---- 4. THE SECOND DARK PASS EXISTS AND THE PRIMARY WINS TIES. A 9 or a 7 touches its
# disc's ring and the two label as one oversized blob at 110; a pass at 90 recovers the
# card. The order is load-bearing, not cosmetic: reversing it took WRONG from 5 to 10,
# because a blob found at 90 has a tighter box than the crop the templates were cut at.
# Three passes, PRIMARY FIRST and the brightest LAST. 110 is the normal disc; 90 recovers
# a 9 or 7 whose ink fuses with the disc ring; 130 recovers the card UNDER THE CURSOR, which
# the game lifts and HIGHLIGHTS so its ink goes too bright for 110 to see. The order is
# load-bearing in both directions: a looser pass winning a tie read 5 digits one too high.
check("three dark thresholds, primary first and brightest last",
      tuple(local_hand.DARK_THRESHOLDS) == (110, 90, 130),
      str(local_hand.DARK_THRESHOLDS))
check("find_circles takes a threshold and defaults to the shipped one",
      circle_finder.find_circles.__defaults__ == (circle_finder.DARK,),
      str(circle_finder.find_circles.__defaults__))

# ---- 5. NO TEMPLATE MAY DUPLICATE ANOTHER UNDER A DIFFERENT LABEL. Six templates were
# removed for exactly this: three cut from a live frame and labelled one card off (a 6
# labelled 7, a 5 labelled 6, a 4 labelled 7) and three that were not digits. Each matched
# its own offending crop at correlation 1.0000 and read it wrong forever after.
import numpy as np                                                      # noqa: E402
vecs, digits = local_hand._templates()
S = vecs @ vecs.T
np.fill_diagonal(S, -1.0)
lab = np.array(digits)
clash = [(int(i), int(j), lab[i], lab[j])
         for i, j in zip(*np.where(S > 0.999)) if i < j and lab[i] != lab[j]]
check("no two near-identical templates carry different labels", not clash,
      f"{len(clash)} clashing pairs, e.g. {clash[:3]}")
check("every template label is a digit the game can show",
      set(digits) <= set("124567 89".replace(" ", "")), str(sorted(set(digits))))
check("no template is labelled 3 -- the game has no 3", "3" not in set(digits))

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
