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
    r = rc.read_reveal(im)

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

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
