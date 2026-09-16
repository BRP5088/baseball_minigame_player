"""The two cards PLAYED, read off the reveal. Local, no paid call.

pick_opponent_card() takes `reveal_cards`, and the ONLY source of those was the
PAID model -- which is off. So nothing read the opponent's card, and on
2026-09-16 a hit with runners on second and third could not be attributed:
a tie, or fielding subtraction? The margin decides the outcome.

Plain asserts: four incompatible check() signatures live in this suite and a
reversed call to a name-first one can never fail.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

from PIL import Image

import reveal_cards as rc

FIX = os.path.join(_ROOT, "test_fixtures/reveal_banner/reveal_cards.jpg")
fails = []


def want(label, cond, detail=""):
    if cond:
        print(f"ok   {label}")
    else:
        fails.append(label)
        print(f"FAIL {label}  {detail}")


want("the fixture is present", os.path.exists(FIX), FIX)
if os.path.exists(FIX):
    im = Image.open(FIX)
    # PASS THE PHASE EXPLICITLY. This fixture is from the BATTING half, and
    # reading it on the default proved only that the default happens to be
    # "batting" -- not that batting is handled.
    r = rc.read_reveal(im, phase="batting")

    # GROUND TRUTH, read off the frame BY EYE: ours is Johnny Drawers, BATTER 7,
    # with a POWER SWING +2. Theirs is Bartholomew Creasley, PITCHER 5, with a
    # PITCH FOCUS +1.
    want("our power reads 7", r["ours"]["power"] == 7, str(r["ours"]))
    want("our bonus reads +2", r["ours"]["bonus"] == 2, str(r["ours"]))
    want("their power reads 5", r["theirs"]["power"] == 5, str(r["theirs"]))
    want("their bonus reads +1", r["theirs"]["bonus"] == 1, str(r["theirs"]))

    # THE ZONES MUST NOT SWALLOW A RUNNER. During a home run the runners animate
    # THROUGH the centre row -- Austin "Cur" Bunz sits at x=1232 in this very
    # frame -- so a generous mound zone reads a runner's disc as the pitcher's
    # card. Two discs per side is the whole matchup; three means a runner got in.
    want("the mound zone holds exactly the played pair", r["theirs"]["discs"] == 2,
         f"{r['theirs']['discs']} discs -- a runner may have been included")
    want("the home zone holds exactly the played pair", r["ours"]["discs"] == 2,
         f"{r['ours']['discs']} discs")

    # THE MARGIN ABSTAINS RATHER THAN GUESSING. Section 4: only SWING_BOOST and
    # PITCH_BOOST add power, so a +1 of unknown kind CANNOT enter a margin. This
    # frame has exactly that, and an answer here would be an invention.
    m, why = rc.margin_from(r, "batting")
    want("a +1 of unknown kind refuses to produce a margin", m is None, str(why))
    want("and it says why", "KIND" in (why or ""), str(why))

    # A +2 IS ALWAYS A POWER SWING (section 4: the only card ever above +1), so
    # that case resolves for free and MUST produce a number.
    faked = {"ours": dict(r["ours"]), "theirs": dict(r["theirs"], bonus=2)}
    m2, why2 = rc.margin_from(faked, "batting")
    want("two +2s give a margin", m2 == (7 + 2) - (5 + 2), f"{m2} / {why2}")

    # SIGN FOLLOWS THE BATTER, in both phases.
    m3, _ = rc.margin_from(faked, "pitching")
    want("the sign flips while pitching", m3 == -m2, f"{m3} vs {m2}")

    # AN IMPOSSIBLE POWER IS A MISREAD, NOT A CARD (powers run 4-9).
    want("the power range is the roster's",
         (rc.CARD_POWER_MIN, rc.CARD_POWER_MAX) == (4, 9),
         f"{rc.CARD_POWER_MIN}-{rc.CARD_POWER_MAX}")
    want("a +3 is not accepted as a bonus", rc.BONUS_MAX == 2,
         "section 4: a +3 does not exist in this game")

    # THE CLAMP MUST ACTUALLY FIRE, and the fixture cannot show that: its powers
    # are 7 and 5, both in range, so REMOVING the clamp changes nothing and a
    # mutant that deleted it SURVIVED. Drive an out-of-range digit through the
    # real code path instead. Section 4: powers run 4-9 across all 33 catalogued
    # cards, and 1 and 2 are the TACTICS BONUS digits -- which the disc's own
    # template bank contains, so the reader can and does produce them.
    import local_hand as _lh
    _real_digit = _lh.read_digit
    try:
        _lh.read_digit = lambda img, circle: ("1", 0.99)     # a bonus digit, not a power
        bogus = rc.read_reveal(im)
        want("an out-of-range power is dropped, not invented",
             bogus["ours"]["power"] is None and bogus["theirs"]["power"] is None,
             f"ours={bogus['ours']['power']} theirs={bogus['theirs']['power']} "
             f"-- a 1 is a tactics bonus digit, not a card's power")
        m4, _w4 = rc.margin_from(bogus, "batting")
        want("and no margin is built on it", m4 is None, str(m4))
    finally:
        _lh.read_digit = _real_digit

    # A CROP MUST BE REFUSED. The zones are absolute fractions of the WHOLE
    # frame; handed a crop they would land on nothing and answer anyway.
    try:
        rc.read_reveal(Image.new("RGB", (400, 300)))
        raised = False
    except ValueError:
        raised = True
    want("a too-small frame raises rather than answering", raised)

# THE OWNERS SWAP BY PHASE, and getting that wrong is worse than a misread: the
# numbers come out right and the SIDES come out backwards, so margin_from takes
# the sign from the wrong card. Live on 2026-09-16, the first pitching turn read
# our own 7 as "theirs" and their 8 as "ours" -- the positions are fixed by ROLE
# (pitcher at the mound, batter at home), not by owner.
PITCH_FIX = os.path.join(_ROOT, "test_fixtures/reveal_banner/reveal_pitching.jpg")
want("the pitching fixture is present", os.path.exists(PITCH_FIX), PITCH_FIX)
if os.path.exists(PITCH_FIX):
    pim = Image.open(PITCH_FIX)
    # GROUND TRUTH: we pitched a 7/0 and the opponent batted an 8. It was a hit
    # (margin 1) and their batter reached first -- observed on the diamond.
    pr = rc.read_reveal(pim, phase="pitching")
    want("while pitching, OURS is the card at the MOUND", pr["ours"]["power"] == 7,
         f"we pitched a 7; got {pr['ours']['power']}")
    want("while pitching, THEIRS is the card at HOME", pr["theirs"]["power"] == 8,
         f"they batted an 8; got {pr['theirs']['power']}")
    want("the role names are independent of owner",
         pr["pitcher"]["power"] == 7 and pr["batter"]["power"] == 8, str(pr))
    pm, pw = rc.margin_from(pr, "pitching")
    want("the margin is the batter's, and it is 1 (a hit, not a home run)",
         pm == 1, f"{pm} / {pw}")
    want("and 1 is under the automatic home-run margin", pm < 3)

    # THE SAME FRAME READ AS IF WE WERE BATTING MUST SWAP THE OWNERS. Without
    # this a reader that ignored `phase` entirely would pass everything above.
    br = rc.read_reveal(pim, phase="batting")
    want("reading the same frame as batting swaps ours and theirs",
         br["ours"]["power"] == 8 and br["theirs"]["power"] == 7, str(br))

# THE BATTING HALF, CHECKED THE SAME WAY THE PITCHING HALF IS. The swap was
# found on a pitching turn, so batting is the side at risk of passing by
# coincidence -- it is the default, and a reader that ignored `phase` entirely
# would look perfect here.
if os.path.exists(FIX):
    bat = rc.read_reveal(im, phase="batting")
    want("while batting, OURS is the card at HOME", bat["ours"]["power"] == 7,
         f"we batted Johnny Drawers 7; got {bat['ours']['power']}")
    want("while batting, THEIRS is the card at the MOUND", bat["theirs"]["power"] == 5,
         f"they pitched Creasley 5; got {bat['theirs']['power']}")
    want("our POWER SWING +2 lands on our side", bat["ours"]["bonus"] == 2, str(bat["ours"]))
    want("their PITCH FOCUS +1 lands on theirs", bat["theirs"]["bonus"] == 1, str(bat["theirs"]))

    flip = rc.read_reveal(im, phase="pitching")
    want("the batting frame read as pitching swaps the owners",
         flip["ours"]["power"] == 5 and flip["theirs"]["power"] == 7, str(flip))
    want("but the ROLE names do not move",
         flip["batter"]["power"] == 7 and flip["pitcher"]["power"] == 5, str(flip))

# THE MARGIN IS INVARIANT TO PHASE: it is always the BATTER's power minus the
# PITCHER's (reveal_margin's own rule). The zone swap and the sign swap cancel
# exactly, so a frame must give the same number read either way -- and a bug in
# only ONE of the two swaps shows up here as a sign flip.
if os.path.exists(PITCH_FIX):
    mb, _ = rc.margin_from(rc.read_reveal(pim, phase="batting"), "batting")
    mp, _ = rc.margin_from(rc.read_reveal(pim, phase="pitching"), "pitching")
    want("the margin does not depend on which side we are on", mb == mp == 1,
         f"batting says {mb}, pitching says {mp} -- one of the two swaps is wrong")

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
