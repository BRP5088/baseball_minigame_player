"""THE POWER DIGIT AND THE SHIELD DIGIT AT BAN SCALE, pinned.

orchestrator.ocr_ban_card_name's own docstring records that tesseract cannot read this font
-- "7 thresholds x 5 psm modes, zero correct reads" -- and CLAUDE.md section 3 records that
the HAND's digit bank is right on only 3 of 7 ban cards. Both are true of OCR and of a bank
cut at the wrong scale. They are not true of a SPRITE MATCH sized from the card box.

THE TRUTH IN THIS FILE WAS READ OFF THE FIXTURES BY EYE, from contact sheets in
agent_progress/ban-digit-bank/sheets/, and is written here as LITERALS. It is not the
reader's own output, and it is not ocr_ban_card_name's either.

The populations either side of every gate are literals too, from
agent_progress/ban-digit-bank/progress.md. A gate is checked against THOSE, never against
itself (CLAUDE.md 10.11).
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

from PIL import Image
import ban_grid as bg
import ban_digits as bd

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


def F(name):
    return _os.path.join(_ROOT, "test_fixtures", "ban_digits", name)


# NAMED, never globbed: a live run appends to test_fixtures/harvest and to screenshot_log,
# and CLAUDE.md section 2 records a profile that went 15 -> 9 because a test globbed a
# directory a run was writing to.
FRAMES = ["players_1920.jpg", "scale_2000.png", "whole_sprite_trap_1920.jpg",
          "tactics_1920.jpg", "midscroll_1920.jpg", "midscroll_video_1920.jpg"]

# (power, secondary) per cell, read BY EYE off the fixture. None = the card is LOCKED
# (faded), which nothing can read and which both readers must refuse.
# (power, secondary, roster card) per cell, read BY EYE off the fixture; the NAME is there
# so the bank can be held out card by card below. None = the card is LOCKED (faded), which
# nothing can read and which both readers must refuse.
TRUTH = {
    # 1920x1080, the capture size the bank was cut at. r0c3 is the trap: its card art is a
    # stadium fence with a legible 5 and a legible 4 painted on it, inside the SHIELD's own
    # search window, and the card has no badge.
    "players_1920.jpg": {
        (0, 0): (7, 1, "Johnny Drawers"), (0, 1): (5, 1, "Mama Jody Gain"), (0, 2): None,
        (0, 3): (6, 0, "Jenny Jody Gain"), (0, 4): (5, 3, "Donny Mekesz"),
        (1, 0): None, (1, 1): None, (1, 3): (4, 0, "Joshua Diaz"),
        (1, 4): (6, 0, "Justin Young")},
    # 2000x1125 -- the SCALE CHECK. The same sprite is drawn ~4.5% larger here and no
    # template was cut at this size. It also carries the only 8s and 9s and a secondary 2.
    "scale_2000.png": {
        (0, 0): None, (0, 1): (4, 3, 'Johnny "Blaze" Sweets'),
        (0, 2): (7, 0, "Johnny C-Train Goudenberg"), (0, 3): (8, 0, "Charlie Pepper"),
        (0, 4): (9, 2, "Josef Bunz-Konicky"),
        (1, 0): (8, 1, "Rube Sharp"), (1, 1): (8, 1, 'Austin "Cur" Bunz'), (1, 2): None,
        (1, 3): (4, 3, "William Brown"), (1, 4): (7, 0, "Jeremiah Curd")},
    # THE MUTANT TRAP. r0c0 and r1c1 are power-5 PITCHERs that the one-stage version of this
    # reader -- match the whole disc, take the digit off the winning template -- gets WRONG,
    # 5 read as 8 and 5 read as 4, with the SHIPPED bank. Without this frame the glyph box
    # could be widened back to the whole sprite and every other check here still passed.
    "whole_sprite_trap_1920.jpg": {
        (0, 0): (5, 0, "Papa Jody Gain"),
        (0, 1): (4, 3, 'Daniel "The Rat-Ta-Train" Cruz'), (0, 2): None,
        (0, 3): (9, 0, "Joel Blunt"), (0, 4): (5, 1, "Bartholomew Creasley"),
        (1, 0): (5, 3, "Jake Saucepan Black"), (1, 1): (5, 0, "Mickey Brown"), (1, 2): None},
}

# THE MEASURED POPULATIONS, as literals. agent_progress/ban-digit-bank/progress.md carries
# the commands. Leave-one-CARD-out over 1,105 held-out cells from 25 cards, plus 500 locked
# and 394 tactics cells as the negatives.
POWER_GLYPH_LOCKED_MAX = 0.454     # n=500 locked cells
POWER_GLYPH_TACTICS_MAX = 0.429    # n=394 tactics cells
POWER_GLYPH_MISSING_MAX = 0.824    # n=262 cells read with their OWN digit cut from the bank
POWER_GLYPH_TRUE_MIN = 0.911       # n=1,105 held-out cells that read correctly
SHIELD_TACTICS_MAX = 0.471         # n=394
SHIELD_NO_BADGE_MAX = 0.564        # n=427 cards whose secondary really is 0
SHIELD_LOCKED_MAX = 0.576          # n=500
SHIELD_BADGE_MIN = 0.822           # n=486 cards that really carry a badge
SHIELD_GLYPH_MISSING_MAX = 0.914   # n=153, same trick on the shield
SHIELD_GLYPH_TRUE_MIN = 0.982      # n=153
# the ON-CARD detector, from oncard_final.py
ONCARD_DISPLACED_MAX = 0.708       # n=8,400: 1,200 cells x 7 shifts of >= 0.08 card heights
ONCARD_TACTICS_MAX = 0.728         # n=200 owned tactics cells
ONCARD_PLAYER_MIN = 0.859          # n=1,199 player cells with their own card dropped
ONCARD_MIDSCROLL = -0.173          # the one genuinely displaced cell in the whole corpus

print("0. fixtures")
missing = [f for f in FRAMES if not _os.path.exists(F(f))]
check(not missing, f"every named fixture is present (missing: {missing})")
if missing:
    raise SystemExit(1)
IMG = {f: Image.open(F(f)).convert("RGB") for f in FRAMES}
ROWS = {f: bg.find_card_rows(IMG[f]) for f in FRAMES}
check(all(ROWS[f] for f in FRAMES), "ban_grid finds card rows on all four")

print("1. the bank")
bank = bd._bank()
check(sorted(bank.get("power", {})) == [4, 5, 6, 7, 8, 9],
      f"power templates cover exactly 4-9 ({sorted(bank.get('power', {}))}) -- CLAUDE.md "
      f"section 4: there is no 1, 2 or 3 power card in the game")
check(sorted(bank.get("shield", {})) == [1, 2, 3],
      f"shield templates cover 1-3 and DELIBERATELY have no 0 class "
      f"({sorted(bank.get('shield', {}))}): secondary 0 is the ABSENCE of the sprite, and a "
      f"template of 'nothing' would be a template of one card's art")
counts = {d: len(v) for d, v in bank.get("power", {}).items()}
check(counts and min(counts.values()) >= 8,
      f"and there are several templates per digit, one per example, never averaged "
      f"(CLAUDE.md 10.30): {counts}")
sizes = {t.shape for _, ts in bank.get("power", {}).items() for t, _, _, _src in ts}
check(len(sizes) > 1 and all(40 <= s[0] <= 56 and 38 <= s[1] <= 54 for s in sizes),
      f"templates are NATIVE-size crops of the disc and therefore differ by a pixel or two "
      f"-- if they were all one shape they would have been resampled to a common box, "
      f"which is the half of CLAUDE.md 10.30 that destroyed the discrimination: "
      f"{sorted(sizes)}")

print("2. every hand-read cell, at both capture sizes")
for f, truth in TRUTH.items():
    img, rows = IMG[f], ROWS[f]
    w = img.size[0]
    right = wrong = abstained = 0
    for (r, c), want in sorted(truth.items()):
        pd, pv = bd.read_power(img, rows, r, c)
        sd, sv = bd.read_shield(img, rows, r, c)
        if want is None:
            check(pd is None and sd is None,
                  f"{f} r{r}c{c} is LOCKED and both readers refuse it (got {pd}/{sd})")
            continue
        ok = (pd, sd) == want[:2]
        check(ok, f"{f} r{r}c{c} ({want[2]}) reads {pd}/{sd}, truth {want[0]}/{want[1]} "
                  f"(scores {pv:.3f}/{sv:.3f})")
        right += ok
        wrong += (pd is not None and pd != want[0]) or (sd is not None and sd != want[1])
        abstained += pd is None or sd is None
    print(f"     {f} ({w}px): {right} right / {wrong} WRONG / {abstained} abstained")

print("3. the trap cell: card ART with legible digits inside the shield window")
# players_1920 r0c3 is a 6/0 whose background fence carries a printed 5 and 4 in the upper
# right. A bare-glyph search finds them; the template carries the shield's dark body and
# white rim, so it does not.
sd, sv = bd.read_shield(IMG["players_1920.jpg"], ROWS["players_1920.jpg"], 0, 3)
check(sd == 0, f"r0c3 reads NO badge ({sd}) though its art holds a legible 5 and 4")
check(sv <= SHIELD_NO_BADGE_MAX,
      f"and it scores {sv:.3f}, inside the measured no-badge population (max "
      f"{SHIELD_NO_BADGE_MAX}), not near the badge population (min {SHIELD_BADGE_MIN})")

print("4. CONTROL: a tactics row has no power disc and no badge, and nothing must read")
img, rows = IMG["tactics_1920.jpg"], ROWS["tactics_1920.jpg"]
read_any = [(r, c) for r in range(len(rows)) for c in range(5)
            if bd.read_power(img, rows, r, c)[0] is not None]
check(not read_any, f"no cell on the tactics row returns a power ({read_any})")
worst = max(bd._read(img, rows, r, c, None, "power", bd.POWER_WIN)[2]
            for r in range(len(rows)) for c in range(5))
check(worst <= POWER_GLYPH_TACTICS_MAX + 0.02,
      f"and the best glyph score anywhere on it is {worst:.3f}, in the measured tactics "
      f"population (max {POWER_GLYPH_TACTICS_MAX})")

print("4b. CONTROL: an OWNED TACTICS card, which carries a white digit disc of its own")
# whole_sprite_trap r1c3 and r1c4 are POWER SWING cards showing a bonus badge -- a white
# disc with a 1 and a 2 in it, in the card's top strip. It is a DIFFERENT sprite from the
# power disc and it must not be read as power: CLAUDE.md section 4, powers run 4-9 and a
# tactics bonus is 1 or 2.
img, rows = IMG["whole_sprite_trap_1920.jpg"], ROWS["whole_sprite_trap_1920.jpg"]
for c in (3, 4):
    pd, pv = bd.read_power(img, rows, 1, c)
    check(pd is None,
          f"r1c{c} is a POWER SWING card with a bonus disc on it and read_power refuses it "
          f"(got {pd} at {pv:.3f})")

print("5. CONTROL: a mid-scroll frame, where the row box is not on a card")
# The single abstention in 1,105 held-out cells. The card has slid half a row, so the box
# holds the page header and no disc. read_power says so; read_shield CANNOT -- a displaced
# window scores like a card with no badge, and no threshold separates those.
img, rows = IMG["midscroll_1920.jpg"], ROWS["midscroll_1920.jpg"]
pd, pv = bd.read_power(img, rows, 0, 1)
check(pd is None, f"read_power abstains on the displaced cell (got {pd})")
check(pv < POWER_GLYPH_TRUE_MIN,
      f"its glyph score {pv:.3f} is below every correct read ever measured "
      f"({POWER_GLYPH_TRUE_MIN})")

print("6. every gate sits in an EMPTY BAND between two measured populations (10.4)")
check(max(POWER_GLYPH_LOCKED_MAX, POWER_GLYPH_TACTICS_MAX,
          POWER_GLYPH_MISSING_MAX) < bd.POWER_MIN < POWER_GLYPH_TRUE_MIN,
      f"POWER_MIN {bd.POWER_MIN} is above locked {POWER_GLYPH_LOCKED_MAX} / tactics "
      f"{POWER_GLYPH_TACTICS_MAX} / A DIGIT NOT IN THE BANK {POWER_GLYPH_MISSING_MAX}, and "
      f"below a real digit's {POWER_GLYPH_TRUE_MIN}. The missing-class number is why it is "
      f"not 0.70: there, a held-out 8 read as a 5 at 0.809 on all three power-8 cards "
      f"(CLAUDE.md 10.31)")
check(SHIELD_GLYPH_MISSING_MAX < bd.SHIELD_GLYPH_MIN < SHIELD_GLYPH_TRUE_MIN,
      f"SHIELD_GLYPH_MIN {bd.SHIELD_GLYPH_MIN} is above a badge whose digit is NOT in the "
      f"bank ({SHIELD_GLYPH_MISSING_MAX}) and below a real one ({SHIELD_GLYPH_TRUE_MIN})")
check(max(SHIELD_NO_BADGE_MAX, SHIELD_LOCKED_MAX, SHIELD_TACTICS_MAX)
      < bd.SHIELD_ABSENT_MAX <= bd.SHIELD_PRESENT_MIN < SHIELD_BADGE_MIN,
      f"the shield's TWO gates ({bd.SHIELD_ABSENT_MAX}, {bd.SHIELD_PRESENT_MIN}) both lie "
      f"in the band {max(SHIELD_NO_BADGE_MAX, SHIELD_LOCKED_MAX)} .. {SHIELD_BADGE_MIN}")
check(bd.SHIELD_ABSENT_MAX < bd.SHIELD_PRESENT_MIN,
      f"and they are NOT the same number: between them is 'cannot say', not 'no badge' -- "
      f"this reader picks which card to ban in a match that costs $50")

print("7. the 4-9 range rule")
check(bd.POWER_RANGE == (4, 9), f"the rule is 4-9 ({bd.POWER_RANGE}), CLAUDE.md section 4")
# Honest about its status: the bank holds only 4-9, so on the template arm this rule can
# never fire. It is a CONTRACT guard on what read_power may return, and check 1 is what
# keeps it honest -- adding a 3-template to the bank would make it live.
sd_bank = bd._bank().get("shield", {})
check(0 not in sd_bank,
      "and read_power can never emit a digit outside it, because the bank has no other "
      "class -- the rule guards the contract, not a measured failure")

print("8. THE READER STILL WORKS ON A CARD NO TEMPLATE WAS CUT FROM")
# Without this the whole file is decorative on the question that matters: a template matches
# its own source crop at 1.000 (CLAUDE.md 10.22 / 10.30), and the shipped bank holds a crop
# from every card in these fixtures. Here each cell is read by a bank with ITS OWN card
# dropped -- the same leave-one-card-out condition the 1,105-cell measurement was taken
# under. One card at a time, not the whole frame at once: dropping every card in a frame
# also deletes whole DIGIT classes (all three power-8 cards sit on scale_2000.png), which
# measures something else entirely -- check 9 below.
for f, truth in TRUTH.items():
    img, rows = IMG[f], ROWS[f]
    right = bad = 0
    for (r, c), want in sorted(truth.items()):
        if want is None:
            continue
        held = bd._bank(drop_cards={want[2]})
        pd, _ = bd.read_power(img, rows, r, c, bank=held)
        sd, _ = bd.read_shield(img, rows, r, c, bank=held)
        if (pd, sd) == want[:2]:
            right += 1
        else:
            bad += 1
            check(False, f"{f} r{r}c{c} ({want[2]}) held out: {pd}/{sd}, truth "
                         f"{want[0]}/{want[1]}")
    check(bad == 0, f"{f}: {right} cells read correctly with their own card dropped from "
                    f"the bank, {bad} not")

print("9. A DIGIT THE BANK DOES NOT HOLD MUST ABSTAIN, NOT BECOME THE NEAREST ONE")
# CLAUDE.md 10.31. Measured, not feared: with every power-8 template removed, all three
# power-8 cards read 5 at glyph 0.809 -- above the 0.70 gate this shipped with first. The
# gate is 0.87 for exactly this reason and for no other; locked and tactics cards were
# already refused at 0.70.
img, rows = IMG["scale_2000.png"], ROWS["scale_2000.png"]
no8 = bd._bank()
no8 = {"power": {d: ts for d, ts in no8["power"].items() if d != 8}, "shield": no8["shield"]}
for (r, c) in ((0, 3), (1, 0), (1, 1)):
    pd, pv = bd.read_power(img, rows, r, c, bank=no8)
    check(pd is None,
          f"r{r}c{c} is a power 8; with no 8 in the bank read_power abstains (got {pd} at "
          f"{pv:.3f}) rather than answering the nearest digit it happens to hold")
    check(pv <= POWER_GLYPH_MISSING_MAX + 0.01,
          f"and its score {pv:.3f} sits in the measured missing-class population "
          f"(max {POWER_GLYPH_MISSING_MAX}), below every correct read ever seen "
          f"({POWER_GLYPH_TRUE_MIN})")

print("10. ON A CARD, OR NOT -- A POSITIVE TEST, NOT AN ABSENCE")
# read_shield used to answer 0 whenever no badge cleared the gate, and a window that is not
# on a card scores the same ~0.40 as a card that has no badge: one population, no gate. The
# fix is a landmark -- the card's own top-left corner, where the box says it should be.
for f, truth in TRUTH.items():
    img, rows = IMG[f], ROWS[f]
    for (r, c), want in sorted(truth.items()):
        ok, sc = bd.on_card(img, rows, r, c)
        if want is None:
            check(ok is None, f"{f} r{r}c{c} is locked: on_card has nothing to measure ({ok})")
        else:
            check(ok is True, f"{f} r{r}c{c} ({want[2]}) is on a card ({ok} at {sc:.3f})")
img, rows = IMG["midscroll_1920.jpg"], ROWS["midscroll_1920.jpg"]
ok, sc = bd.on_card(img, rows, 0, 1)
check(ok is False, f"the mid-scroll cell is NOT on a card ({ok} at {sc:.3f})")
check(sc <= ONCARD_MIDSCROLL + 0.05,
      f"and it scores {sc:.3f} -- the lowest of all 1,200 player cells measured "
      f"({ONCARD_MIDSCROLL}), found by the detector on its own")
sd, _ = bd.read_shield(img, rows, 0, 1)
check(sd is None,
      f"so read_shield refuses it ({sd}) instead of calling it secondary 0 -- which is what "
      f"it used to do, and what it did for 134 of 250 shifted cards that HAVE a badge")
img, rows = IMG["tactics_1920.jpg"], ROWS["tactics_1920.jpg"]
tac = [(r, c, bd.on_card(img, rows, r, c)) for r in range(len(rows)) for c in range(5)]
live = [(r, c, v) for r, c, v in tac if v[0] is not None]
check(live and all(v[0] is False for _, _, v in live),
      f"an owned TACTICS card is refused too -- it is on a card but has no secondary stat at "
      f"all, so None beats 0: {[(r, c, round(v[1], 3)) for r, c, v in live]}")

print("11. A DISPLACED ROW MUST NOT PRODUCE A SHIELD ANSWER")
# The failure this closes, reproduced on a real frame: shift the row box and re-read. Before
# the landmark, every shifted cell answered 0 -- confidently, for cards that carry a badge.
img, rows = IMG["players_1920.jpg"], ROWS["players_1920.jpg"]
truth = TRUTH["players_1920.jpg"]
for d in (0.15, -0.15, 0.30):
    moved = [{**row, "top": row["top"] + d * (row["bottom"] - row["top"]),
              "bottom": row["bottom"] + d * (row["bottom"] - row["top"])} for row in rows]
    ans = [(r, c, bd.read_shield(img, moved, r, c)[0]) for (r, c), w in sorted(truth.items())
           if w is not None]
    check(all(a is None for _, _, a in ans),
          f"shifted {d:+.2f} rows: every cell refuses ({[a for _, _, a in ans]})")
    pw = [bd.read_power(img, moved, r, c)[0] for (r, c), w in sorted(truth.items()) if w is not None]
    check(all(p is None for p in pw),
          f"and read_power refuses too, as it always did ({pw})")

print("12. the on-card gate sits in an empty band between three measured populations")
check(max(ONCARD_DISPLACED_MAX, ONCARD_TACTICS_MAX) < bd.ON_CARD_MIN < ONCARD_PLAYER_MIN,
      f"ON_CARD_MIN {bd.ON_CARD_MIN} is above a displaced window "
      f"({ONCARD_DISPLACED_MAX}) and an owned tactics card ({ONCARD_TACTICS_MAX}), and below "
      f"a player card ({ONCARD_PLAYER_MIN})")
check(bd.CORNER_SEARCH <= 0.03,
      f"the corner is matched with only {bd.CORNER_SEARCH} card heights of slack: at 0.080 "
      f"the displaced population climbs back to 0.989, because a generous search finds the "
      f"DISPLACED card and answers yes, which is the bug")

print("13. shield 0 is now a POSITIVE statement")
img, rows = IMG["players_1920.jpg"], ROWS["players_1920.jpg"]
sd, sv = bd.read_shield(img, rows, 0, 3)            # Jenny Jody Gain, 6/0
ok, oc = bd.on_card(img, rows, 0, 3)
check(sd == 0 and ok is True,
      f"r0c3 reads 0 AND the box is on a card (on_card {oc:.3f}) -- both halves, not one "
      f"score that failed")

print("14. A REAL MID-SCROLL FRAME, FROM A SESSION THAT SUPPLIED NO TEMPLATES")
# midscroll_video_1920.jpg comes out of overnight/runs/20260908_235423_.../stream.mp4 -- a
# different day from every still the bank was cut from, and a different image path (H.264
# then JPEG, not a direct grab). ban_grid reports THREE rows on it: the top one's boxes sit
# over the "BANNED CARDS 0/3" header with the cards drawn below them, and the other two are
# framed correctly. The same frame therefore carries both answers at once.
#
# Row 0's labels resolved from the NAME BANNER, which does land inside the box while the
# power disc does not -- exactly the silent mislabel this detector closes.
img, rows = IMG["midscroll_video_1920.jpg"], ROWS["midscroll_video_1920.jpg"]
check(len(rows) == 3, f"ban_grid reports 3 rows on it ({len(rows)})")
for c in (1, 2, 4):            # 0 and 3 are locked/unsure on that row
    ok, sc = bd.on_card(img, rows, 0, c)
    check(ok is False, f"row 0 col {c} box is over the header, not on a card ({ok} at {sc:.3f})")
    check(bd.read_power(img, rows, 0, c)[0] is None and
          bd.read_shield(img, rows, 0, c)[0] is None,
          f"row 0 col {c}: both readers refuse it")
# rows 1 and 2 ARE on cards and read correctly -- row 2 is CLIPPED by the frame's bottom
# edge (visible 0.66), which is what caught a real bug: card_box clamps its box to the
# frame, so every fraction measured against a card HEIGHT was a third short there.
VIDEO_TRUTH = {(1, 0): (8, 1), (1, 1): (8, 1), (1, 3): (4, 3), (1, 4): (7, 0),
               (2, 0): (4, 1), (2, 1): (4, 2), (2, 3): (4, 3), (2, 4): (6, 0)}
for (r, c), want in sorted(VIDEO_TRUTH.items()):
    pd, sd = bd.read_power(img, rows, r, c)[0], bd.read_shield(img, rows, r, c)[0]
    check((pd, sd) == want, f"r{r}c{c} reads {pd}/{sd}, truth {want[0]}/{want[1]}")
check(rows[2]["visible"] < 0.75 and bd.on_card(img, rows, 2, 0)[0] is True,
      f"and the clipped bottom row (visible {rows[2]['visible']}) is still recognised as "
      f"being on a card -- the window takes the card's HEIGHT from the row, not from the "
      f"clamped card_box")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
