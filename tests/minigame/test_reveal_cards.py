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
# THE FIXTURE MUST EXIST. Behind a bare os.path.exists these checks vanish
# SILENTLY if the frame is pruned, and the file still passes -- while what they
# guard is the zone-by-ROLE fix, i.e. reading OUR card as THEIRS on a pitching
# turn. A gone check reads exactly like a passing one (10.1).
want("the reveal fixture exists", os.path.exists(FIX), FIX)
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
    # A +1 WHOSE KIND DID NOT READ still refuses -- but this frame's banners DO
    # read now, so the case has to be built rather than taken from the fixture.
    # (It used to be asserted against the fixture itself, which was correct only
    # while nothing could name a kind.)
    _unk = {"ours": {"power": 7, "bonus": 1, "kind": None,
                     "kind_detail": "best swing_boost 0.4 under 0.75"},
            "theirs": {"power": 5, "bonus": None, "kind": None}}
    m, why = rc.margin_from(_unk, "batting")
    want("a +1 of unknown kind refuses to produce a margin", m is None, str(why))
    want("and it says why", "KIND did not read" in (why or ""), str(why))

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
want("the pitching reveal fixture exists", os.path.exists(PITCH_FIX), PITCH_FIX)
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
# THE FIXTURE MUST EXIST. Behind a bare os.path.exists these checks vanish
# SILENTLY if the frame is pruned, and the file still passes -- while what they
# guard is the zone-by-ROLE fix, i.e. reading OUR card as THEIRS on a pitching
# turn. A gone check reads exactly like a passing one (10.1).
want("the reveal fixture exists", os.path.exists(FIX), FIX)
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
want("the pitching reveal fixture exists", os.path.exists(PITCH_FIX), PITCH_FIX)
if os.path.exists(PITCH_FIX):
    mb, _ = rc.margin_from(rc.read_reveal(pim, phase="batting"), "batting")
    mp, _ = rc.margin_from(rc.read_reveal(pim, phase="pitching"), "pitching")
    want("the margin does not depend on which side we are on", mb == mp == 1,
         f"batting says {mb}, pitching says {mp} -- one of the two swaps is wrong")

# THE TACTICS KIND, AND WHAT IT LETS THE MARGIN DO. Section 4: only SWING and
# PITCH boosts add power. A Speed Boost or Fielding Play carries a nonzero bonus
# that adds NONE, so putting one into a margin is the same size of error as
# leaving out one that belongs.
# THE FIXTURE MUST EXIST. Behind a bare os.path.exists these checks vanish
# SILENTLY if the frame is pruned, and the file still passes -- while what they
# guard is the zone-by-ROLE fix, i.e. reading OUR card as THEIRS on a pitching
# turn. A gone check reads exactly like a passing one (10.1).
want("the reveal fixture exists", os.path.exists(FIX), FIX)
if os.path.exists(FIX):
    kr = rc.read_reveal(im, phase="batting")
    want("our POWER SWING is named", kr["ours"]["kind"] == "swing_boost", str(kr["ours"]))
    want("their PITCH FOCUS is named", kr["theirs"]["kind"] == "pitch_boost", str(kr["theirs"]))
    km, kw = rc.margin_from(kr, "batting")
    # GROUND TRUTH: 7 + POWER SWING +2 against 5 + PITCH FOCUS +1 is a margin of
    # exactly 3, and the game printed HOME RUN! for 4 runs with the bases loaded.
    want("a +1 of KNOWN power-adding kind now enters the margin", km == 3,
         f"{km} / {kw} -- expected (7+2)-(5+1)")
    want("and 3 is the automatic home-run margin", km >= 3)

# A KIND THAT ADDS NO POWER MUST BE EXCLUDED, and this fixture is the case that
# proves the banner is doing the work: we pitched a FIELDING PLAY and they batted
# a SPEED BOOST, and NEITHER bonus digit read. Reading the kind only where a bonus
# was found would report "no tactics" on both -- right here by luck, since neither
# adds power, and wrong by 1 or 2 the moment it is a swing boost.
FIELD_FIX = os.path.join(_ROOT, "test_fixtures/reveal_banner/reveal_fielding.jpg")
want("the fielding fixture is present", os.path.exists(FIELD_FIX), FIELD_FIX)
if os.path.exists(FIELD_FIX):
    fim = Image.open(FIELD_FIX)
    fr = rc.read_reveal(fim, phase="pitching")
    want("our FIELDING PLAY is named from its banner alone",
         fr["ours"]["kind"] == "fielding_boost", str(fr["ours"]))
    want("their SPEED BOOST is named from its banner alone",
         fr["theirs"]["kind"] == "speed_boost", str(fr["theirs"]))
    want("neither bonus digit read, which is the point",
         fr["ours"]["bonus"] is None and fr["theirs"]["bonus"] is None, str(fr))
    fm, fw = rc.margin_from(fr, "pitching")
    # GROUND TRUTH: our 6 against their 5. Neither tactics card adds power, so the
    # margin is -1 -- an out, which is what the diamond showed.
    want("a no-power kind is excluded from the margin", fm == -1, f"{fm} / {fw}")
    want("and the reason names the kinds", "adds no power" in (fw or ""), str(fw))

# A POWER-ADDING KIND WITH NO BONUS DIGIT MUST ABSTAIN, not guess. Power Swing is
# the only card that can be +1 OR +2, so the difference is a hit versus an
# automatic home run.
_fake = {"ours": {"power": 7, "bonus": None, "kind": "swing_boost"},
         "theirs": {"power": 5, "bonus": None, "kind": None}}
_m, _w = rc.margin_from(_fake, "batting")
want("a swing boost with an unread bonus refuses to produce a margin", _m is None, str(_m))
want("...and says the bonus could be +1 or +2", "+1 or +2" in (_w or ""), str(_w))

# THE KIND GATE, PINNED AS LITERALS against the measured populations (10.11 --
# never assert against the constant you are guarding). Census over 344 held-out
# readings from frames that supplied no template, tools/banner_kind_census.py:
#
#     RIGHT kind   p50 0.961   max 0.997
#     WRONG kind   p50 0.438   p99 0.703   MAX 0.710
#
# NOTE these two checks exist BECAUSE outcome alone cannot catch a loosened gate:
# on this corpus there is NO frame where a wrong kind outscores the right one
# between 0.60 and 0.75, so dropping the gate to 0.60 changes no fixture's answer
# and two mutants survived until the constant itself was pinned.
want("the kind gate clears the measured wrong-kind MAX",
     rc.TACTICS_KIND_MIN > 0.710,
     f"wrong kinds reach 0.710 over 258 held-out readings; got {rc.TACTICS_KIND_MIN}")
want("...and sits under the right-kind median",
     rc.TACTICS_KIND_MIN < 0.961,
     f"right kinds sit at p50 0.961; got {rc.TACTICS_KIND_MIN}")

# AND THE GATE ACTUALLY GATES. Drive a score that sits in the wrong-kind band and
# require an abstention -- this is what catches the gate being removed outright.
_real_scores = rc.tactics_kind_scores
try:
    rc.tactics_kind_scores = lambda frame, zone: {"swing_boost": 0.70,
                                                  "speed_boost": 0.41}
    _k, _d = rc.read_tactics_kind(None, rc.ZONE_HOME)
    want("a best score inside the wrong-kind band is refused", _k is None,
         f"named {_k!r} on a 0.70 score, which wrong kinds reach")
    rc.tactics_kind_scores = lambda frame, zone: {"swing_boost": 0.97,
                                                  "speed_boost": 0.41}
    _k, _d = rc.read_tactics_kind(None, rc.ZONE_HOME)
    want("...but a clear score is accepted", _k == "swing_boost", f"{_k!r} / {_d}")
finally:
    rc.tactics_kind_scores = _real_scores

# THE TWO PLAYERS HOLD SEPARATE DECKS, SO OUR CENSUS RESOLVES ONLY OUR OWN CARD.
#
# margin_from used to read "a +2 IS ALWAYS a Power Swing" from section 4's census
# over 299 hand-labelled tactics cards -- a census taken entirely from OUR OWN HAND
# (`hand_labels*.json`, every key a `hand_*.jpg` fan crop). On 2026-09-17 a
# PITCH FOCUS +2 was read off the OPPONENT'S mound, legible in the frame, which
# refutes the premise for their side and only their side.
#
# The margin that day came out right by luck -- Power Swing and Pitch Focus both add
# power. The error it leaves open is a FIELDING PLAY +2 of theirs, credited 2 power
# it does not add: the hit/home-run boundary this function exists to protect.
_ours2 = {"ours":   {"power": 7, "bonus": 2, "kind": None},
          "theirs": {"power": 5, "bonus": None, "kind": None, "discs": 1}}
_m, _w = rc.margin_from(_ours2, "batting")
want("a +2 of OURS with an unread banner still resolves (our own deck's census)",
     _m == 4, f"{_m} / {_w}")

_theirs2 = {"ours":   {"power": 7, "bonus": None, "kind": None, "discs": 1},
            "theirs": {"power": 5, "bonus": 2, "kind": None}}
_m2, _w2 = rc.margin_from(_theirs2, "batting")
want("a +2 of THEIRS with an unread banner ABSTAINS, never guesses",
     _m2 is None, f"{_m2} / {_w2}")
want("...and the reason names the separate decks",
     "SEPARATE" in (_w2 or "").upper(), str(_w2))

# CONTROL 1: the abstention is about the UNREAD BANNER, not about their side. A read
# banner still beats the inference, so their +2 counts when it is actually seen.
_theirs_read = {"ours":   {"power": 7, "bonus": None, "kind": None, "discs": 1},
                "theirs": {"power": 5, "bonus": 2, "kind": "pitch_boost"}}
_m3, _w3 = rc.margin_from(_theirs_read, "batting")
want("a +2 of theirs that the BANNER read is still counted", _m3 == 0, f"{_m3} / {_w3}")

# CONTROL 2: and the failure the fix exists for -- a read FIELDING PLAY +2 of theirs
# adds no power, so it must not enter the margin at all.
_theirs_field = {"ours":   {"power": 7, "bonus": None, "kind": None, "discs": 1},
                 "theirs": {"power": 5, "bonus": 2, "kind": "fielding_play"}}
_m4, _w4 = rc.margin_from(_theirs_field, "batting")
want("a FIELDING PLAY +2 of theirs adds no power to the margin", _m4 == 2, f"{_m4} / {_w4}")

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
