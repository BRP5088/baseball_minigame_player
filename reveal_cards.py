"""The two cards PLAYED this at-bat, read off the reveal. Local, no paid call.

WHY THIS EXISTS. pick_opponent_card() takes `reveal_cards`, and the ONLY thing
that ever supplied those was the paid vision model -- which is off. So with the
shipped defaults nothing reads the opponent's card at all, and on 2026-09-16 a
hit with runners on second and third could not be attributed: tie, or fielding
subtraction? The user knew because they were watching. The margin decides the
outcome, so this is the field the engine is blindest without.

THE LAYOUT, MEASURED off a live reveal (1920x1080):

    OURS    at HOME PLATE, bottom centre    power disc (1015, 793)  badge (1129, 736)
    THEIRS  at the MOUND,  centre           power disc (1006, 353)  badge (1109, 305)

and the tactics badge sits up-and-right of its player disc by about (+114, -55)
in both.

THE REVEAL RENDERS SMALLER THAN THE HAND, which is why the hand reader cannot be
pointed at it: its discs are r=13 against the fan's r=19, under DISC_MIN_R (18)
and DISC_MIN_REACH (6), so find_circles finds them and local_hand throws them
away. The DIGIT BANK NEEDS NO CHANGE -- read_digit scores 0.958/0.972 on the
powers and 0.875/0.950 on the badges at r=11, against MIN_SCORE 0.80.

THE ZONES ARE TIGHT ON PURPOSE. During a home run the runners animate THROUGH
the centre row, so a generous mound zone picks up a runner's disc as if it were
the pitcher's card.

AND HOME PLATE HAS THE SAME PROBLEM. This used to read "a runner is never there
-- which is why OURS is the more trustworthy half". That is false: a runner
SCORING stands on the plate, its card renders in ZONE_HOME, and `_side` picks the
LOWEST disc as the played card -- so a runner's card below the played one wins,
confidently (0.966), not as an abstention. Neither half is privileged. `_side`
now REFUSES when more than one disc in a zone reads a legal card power, because
which of two player cards is the matchup is not knowable from position alone.
"""
import os

# x0, y0, x1, y1 as fractions. Both bands hold a player card and, when one was
# attached, its tactics card up and to the right.
# THE POSITIONS ARE FIXED BY ROLE, NOT BY OWNER, AND THAT IS THE WHOLE POINT.
# The PITCHER is always at the mound and the BATTER always at home plate -- so
# while we BAT ours is at home, and while we PITCH ours is at the MOUND. The
# first version hard-coded the batting case and, on the first pitching turn,
# confidently labelled our own 7 as "theirs" and their 8 as "ours". The numbers
# were right and the owners were backwards, which is worse than a misread:
# margin_from would have taken the sign from the wrong side.
ZONE_HOME = (0.44, 0.62, 0.68, 0.92)     # the BATTER's card, whoever owns it
ZONE_MOUND = (0.48, 0.23, 0.62, 0.50)    # the PITCHER's card, whoever owns it

# Kept as aliases so nothing that imported the old names breaks silently -- but
# they are only correct while BATTING, which is why read_reveal takes a phase.
ZONE_OURS = ZONE_HOME
ZONE_THEIRS = ZONE_MOUND

DISC_R = (9, 17)        # the reveal's discs measure 13; the fan's measure 19
DISC_MIN_REACH = 3.0    # the fan's gate is 6 and rejects every reveal disc
READ_R = 11             # the radius read_digit scores best at here
MIN_FRAME_W = 1200      # a crop cannot contain these absolute zones

CARD_POWER_MIN, CARD_POWER_MAX = 4, 9
BONUS_MIN, BONUS_MAX = 1, 2      # section 4: a +3 does not exist in this game


def _discs(img, zone):
    """Disc candidates inside `zone`, nearest-first by x. Never raises."""
    from circle_finder import find_circles
    import local_hand as lh
    w, h = img.size
    x0, y0, x1, y1 = zone
    lo, hi = int(w * x0), int(w * x1)
    top, bot = int(h * y0), int(h * y1)
    seen, out = set(), []
    for thr in lh.DARK_THRESHOLDS:
        try:
            cs = find_circles(img, thr)
        except Exception:
            continue
        for c in cs:
            x, y, r = c[0], c[1], c[2]
            if not (lo <= x <= hi and top <= y <= bot):
                continue
            if not (DISC_R[0] <= r <= DISC_R[1]) or c[3] < DISC_MIN_REACH:
                continue
            k = (x // 20, y // 20)
            if k in seen:
                continue
            seen.add(k)
            out.append((x, y, r))
    out.sort(key=lambda c: (c[1], c[0]))
    return out


def _side(img, zone):
    """{'power', 'bonus', 'power_score', 'bonus_score'} for one side of the reveal.

    The PLAYER disc is the LOWER of the two; the tactics badge rides above and to
    the right. Every value is None when it did not read -- never a guess, because
    a fabricated power feeds straight into a margin and mislabels the at-bat it
    was invented to describe.
    """
    import local_hand as lh
    cs = _discs(img, zone)
    out = {"power": None, "bonus": None, "power_score": 0.0, "bonus_score": 0.0,
           "discs": len(cs), "kind": None, "kind_detail": None}
    if not cs:
        return out
    # lowest y = the player card; anything meaningfully above it is the badge
    sc = img.width / REF_W          # the offsets below are px measured at REF_W
    player = max(cs, key=lambda c: c[1])
    badge = None
    for c in cs:
        if c is player:
            continue
        if c[1] < player[1] - 20 * sc and c[0] > player[0] - 20 * sc:
            # THE NEAREST QUALIFYING DISC, NOT THE HIGHEST. This kept the SMALLEST
            # y, i.e. the disc furthest ABOVE the player card, while the module's
            # own measured badge offset is (+114, -55) -- so the nearest qualifying
            # disc IS the badge and a higher one is an interloper. Every candidate
            # is already above the player, so the nearest is the LARGEST y.
            #
            # LATENT, NOT OBSERVED. No frame on disk picks a different disc under
            # the two rules: on home_run.jpg the only other disc in the zone is a
            # runner's card at x=973, and the existing `c[0] > player[0] - 20` test
            # already excludes it. This is a correctness fix toward the measured
            # offset, not a repair of a failure anyone has seen, and it is recorded
            # that way so a later reader does not cite it as evidence of one.
            if badge is None or c[1] > badge[1]:
                badge = c
    d, s = lh.read_digit(img, (player[0], player[1], READ_R * sc, 4.0, 1))
    if d is not None and CARD_POWER_MIN <= int(d) <= CARD_POWER_MAX:
        out["power"] = int(d)
    out["power_score"] = round(float(s), 4)

    # A SECOND PLAYER CARD DOES APPEAR AT HOME PLATE, AND THE RULE HERE IS AN
    # ASSUMPTION THAT WAS NEVER MEASURED AGAINST ONE.
    #
    # The module docstring claimed "a runner is never there". That is false.
    # Measured on test_fixtures/reveal_banner/home_run.jpg, ZONE_HOME holds THREE
    # discs where the same at-bat's earlier frame holds two:
    #
    #     y=718  digit=5  score 0.967   <- a SECOND player card (a runner)
    #     y=736  digit=2  score 0.948   <- the tactics badge (+2)
    #     y=793  digit=7  score 0.983   <- the played card
    #
    # BE PRECISE ABOUT WHAT THAT SHOWS, because the first write-up of this finding
    # was not: the runner rendered ABOVE the played card, so `max(cs, key=y)` picked
    # correctly on this frame. A runner rendering BELOW the played card is asserted,
    # NOT observed -- no frame on disk shows it.
    #
    # The refusal is not for the unobserved case. It is because "lowest disc = the
    # played card" is a positional assumption that was designed for a zone holding
    # ONE player card, and nothing has measured it across a population that holds
    # two. With two legal card powers in the zone the reader cannot KNOW which is
    # the matchup; answering would be relying on an untested layout rule, and a
    # fabricated margin mislabels the row it was invented to describe.
    #
    # It is cheap, because the digits are already read, and it costs little: the
    # frames it refuses are home-run reveals, where reveal_banner names the outcome
    # outright and the margin is redundant. If a measured layout rule ever arrives,
    # this is the place to replace the refusal with it.
    if out["power"] is not None:
        others = 0
        for c in cs:
            if c is player:
                continue
            dd, _ss = lh.read_digit(img, (c[0], c[1], READ_R * sc, 4.0, 1))
            if dd is not None and CARD_POWER_MIN <= int(dd) <= CARD_POWER_MAX:
                others += 1
        if others:
            out["power"] = None
            out["ambiguous"] = others + 1
            out["why"] = (f"{others + 1} discs in this zone read a legal card power "
                          "— a runner on the plate renders here too, and which card "
                          "is the matchup is not knowable from position alone")
    if badge is not None:
        d, s = lh.read_digit(img, (badge[0], badge[1], READ_R * sc, 4.0, 1))
        # A BONUS OUTSIDE 1-2 IS A MISREAD, NOT A CARD (section 4: a +3 does not
        # exist, and the paid model recorded eleven of them plus one +11).
        if d is not None and BONUS_MIN <= int(d) <= BONUS_MAX:
            out["bonus"] = int(d)
        out["bonus_score"] = round(float(s), 4)
    return out


# The banner sits BELOW its badge on the card. Measured across both sides and both
# phases: the text spans about (-85, +6) to (+35, +40) from the badge centre, and
# the four banners run 115-142 px wide.
# THE BANNER IS SEARCHED FOR IN THE WHOLE ZONE, NOT AT AN OFFSET FROM A BADGE.
# Two versions anchored on the tactics badge and both failed, the second silently:
# _discs does not reliably find a tactics badge at all -- on the HOME side it
# returned the PLAYER card's power disc at (1008, 789) instead of the badge at
# ~(1130, 738), so the band landed 120 px away and barely overlapped the word. It
# still produced a number (0.197) rather than an error, which is 10.1's family,
# and a spot-check passed only because the badge position was hand-fed.
#
# 10.23's rule is the fix: SEARCH FOR THE ASSET. The zone already contains the
# whole card, matchTemplate finds the best position inside it, and nothing has to
# be assumed about where the badge sits.
# THE PAD IS GENEROUS, AND IT HAS TO BE. The zones themselves are deliberately
# TIGHT so a runner animating through the centre is not read as the played card --
# but that tightness clips the BANNER: PITCH FOCUS spans to x=1211 while
# ZONE_MOUND ends at 1190, so pitch_boost matched 0 of 21 held-out frames at a
# pad of 8. Widening the band is safe here in a way that widening the zone is
# not: this search matches four specific WORDS, and a runner's card carries a
# BATTER/PITCHER banner, not a tactics one.
# THE REFERENCE GEOMETRY EVERY TEMPLATE AND PIXEL OFFSET BELOW WAS MEASURED AT.
# The zones are FRACTIONS and scale with the capture; the template bank is a fixed
# uint8 array handed to matchTemplate at native size, and BANNER_ZONE_PAD is raw
# pixels. Mixing the two means a 4% change in width puts the banner and its template
# at different scales and the correlation collapses -- measured on the sibling
# reveal_banner reader, where HOME RUN! went 1.000 at 1920 to 0.517 at 2000 against
# a gate of 0.80. 2000 is the width orchestrator._fast_grab actually asks for, so
# that is the live path, not a hypothetical.
REF_W = 1920

BANNER_ZONE_PAD = 45                 # px at REF_W; scaled at use
# THE GATE IS MEASURED, NOT PICKED -- see tools/banner_kind_census.py and the
# numbers recorded beside it in the test.
TACTICS_KIND_MIN = 0.75
FRAGMENT_MIN_W = 100

_TBANK = None


def _tactics_bank():
    global _TBANK
    if _TBANK is None:
        import numpy as np
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "reveal_tactics_templates.npz")
        with np.load(p) as z:
            _TBANK = [(k.split("__")[0], z[k]) for k in z.files]
    return _TBANK


def tactics_kind_scores(full_frame, zone):
    """{kind: best correlation} for the tactics banner anywhere in `zone`.

    `zone` is ZONE_HOME or ZONE_MOUND -- the same fractional boxes read_reveal
    uses, so the caller never has to locate the badge.
    """
    import cv2
    import numpy as np
    w, h = full_frame.size
    s = w / REF_W
    pad = int(round(BANNER_ZONE_PAD * s))
    x0, y0, x1, y1 = zone
    box = (max(0, int(w * x0) - pad), max(0, int(h * y0) - pad),
           min(w, int(w * x1) + pad), min(h, int(h * y1) + pad))
    band = np.asarray(full_frame.convert("L").crop(box), dtype=np.uint8)
    out = {}
    for kind, tpl in _tactics_bank():
        if s != 1.0:
            tpl = cv2.resize(tpl, (max(1, int(round(tpl.shape[1] * s))),
                                   max(1, int(round(tpl.shape[0] * s)))),
                             interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        # THE FRAGMENT FLOOR SCALES WITH THE TEMPLATE. It is a PIXEL width measured
        # at REF_W, so comparing a scaled template against the raw literal would
        # reject every legitimate template on a smaller capture and wave fragments
        # through on a larger one. Kept immediately before the match, deliberately:
        # placed earlier it guards what was LOADED rather than what is USED.
        if tpl.shape[1] < FRAGMENT_MIN_W * s:
            continue
        if tpl.shape[0] > band.shape[0] or tpl.shape[1] > band.shape[1]:
            continue
        r = cv2.matchTemplate(band, tpl, cv2.TM_CCOEFF_NORMED)
        out[kind] = max(out.get(kind, -1.0), float(r.max()))
    return out


def read_tactics_kind(full_frame, zone):
    """(kind, detail) for the tactics card in `zone` (ZONE_HOME or ZONE_MOUND).

    None means NOT READ. It never guesses: section 4 says only SWING and PITCH
    boosts add power, so a wrong kind puts a bonus into a margin that should not
    be there -- or leaves one out that should.
    """
    try:
        sc = tactics_kind_scores(full_frame, zone)
    except Exception as exc:
        return None, f"banner reader could not run ({exc})"
    if not sc:
        return None, "no template fitted the band"
    kind = max(sc, key=sc.get)
    if sc[kind] < TACTICS_KIND_MIN:
        return None, f"best {kind} {sc[kind]:.3f} under {TACTICS_KIND_MIN}"
    return kind, f"{kind} {sc[kind]:.3f}"


def read_reveal(full_frame, phase="batting"):
    """{'ours', 'theirs', 'batter', 'pitcher'} from a reveal frame.

    `phase` is REQUIRED to name the owners, because only the ROLES have fixed
    positions. `batter` and `pitcher` are the same two dicts under their
    role names, for a caller that cares which side of the at-bat a card is on
    rather than who played it.

    THE TACTICS KIND IS NOT READ, and that is a stated gap rather than a silent
    one. Only SWING_BOOST and PITCH_BOOST add power (section 4), so a +1 that is
    a Speed Boost or a Fielding Play must NOT enter a margin -- and a badge digit
    alone cannot tell them apart. `margin` is therefore returned only when it can
    be computed without that ambiguity; see margin_from().
    """
    if full_frame.width < MIN_FRAME_W:
        raise ValueError(f"read_reveal needs the whole frame; got {full_frame.width}px")
    batter = _side(full_frame, ZONE_HOME)
    pitcher = _side(full_frame, ZONE_MOUND)
    # THE KIND IS ALWAYS READ, NOT ONLY WHERE A BONUS DIGIT WAS FOUND.
    #
    # The two signals fail independently and the BANNER is the stronger one: the
    # bonus digit comes from _side's disc search, which does not reliably locate a
    # tactics BADGE (on the home side it returns the player card's power disc
    # instead), while the banner reads on 11-19 of 22 held-out frames per kind at
    # zero false positives over 258 wrong-kind readings.
    #
    # Reading the kind only when a bonus was found made a FIELDING PLAY we had
    # ourselves just played come back as "no tactics". The margin happened to be
    # right, because fielding adds no power -- but a SWING boost whose badge went
    # unread would have understated the margin by 1 or 2, which is the difference
    # between a hit and an automatic home run.
    for side, zone in ((batter, ZONE_HOME), (pitcher, ZONE_MOUND)):
        side["kind"], side["kind_detail"] = read_tactics_kind(full_frame, zone)
    ours, theirs = (batter, pitcher) if phase == "batting" else (pitcher, batter)
    return {"ours": ours, "theirs": theirs, "batter": batter, "pitcher": pitcher}


def margin_from(reveal, phase):
    """(margin, why). None when it cannot be known -- never a guess.

    A +2 IS ALWAYS A POWER SWING: section 4's census over 299 hand-labelled
    tactics cards has POWER SWING as the only card ever above +1. So a +2
    resolves the kind for free, and a +1 does not.
    """
    o, t = reveal["ours"], reveal["theirs"]
    if o["power"] is None or t["power"] is None:
        return None, "a power did not read"
    # SECTION 4: ONLY SWING AND PITCH BOOSTS ADD POWER. A Speed Boost or a Fielding
    # Play carries a nonzero bonus that adds NONE, so the KIND has to be known
    # before a bonus may enter a margin -- putting one in that does not belong
    # there is the same size of error as leaving one out that does.
    ADDS_POWER = {"swing_boost", "pitch_boost"}

    def eff(side, holder):
        kind = side.get("kind")
        if side["bonus"] is None:
            # NO BONUS DIGIT. The banner still decides whether that is safe.
            if kind is None:
                # "NEITHER READER SAW ANYTHING" IS NOT "NOTHING IS THERE".
                #
                # Both readers abstaining is two failures, not evidence of absence
                # -- and one of them is KNOWN weak here: _discs "does not reliably
                # find a tactics badge at all" (this module's own comment, after it
                # returned the PLAYER card's power disc on the home side). This
                # branch concluded "no tactics seen" and returned a NUMBER that
                # feeds a margin, while the branch below correctly ABSTAINS on the
                # STRONGER evidence combination (bonus read, kind not). It answered
                # on the emptier one and refused on the fuller one.
                #
                # THE POSITIVE SIGNAL IS THE DISC COUNT, and _side already carries
                # it. A played card is one disc; a played card WITH a tactics card
                # is more. So exactly one disc is real evidence that nothing was
                # played alongside it, and anything else is unknown.
                if side.get("discs") == 1:
                    return (side["power"],
                            f"{holder} {side['power']} (one disc in the zone: no "
                            "tactics card is present)")
                return None, (f"{holder} has {side.get('discs')} discs in its zone "
                              "and NEITHER the badge nor the banner named a tactics "
                              "kind -- two readers failing is not evidence that none "
                              "was played")
            if kind in ADDS_POWER:
                # A tactics card IS there and it DOES add power -- we just cannot
                # say how much (+1 or +2, and Power Swing is the only card that
                # can be either). Guessing here is the difference between a hit
                # and an automatic home run.
                return None, (f"{holder} played a {kind}, which adds power, but its "
                              f"bonus digit did not read -- could be +1 or +2")
            return (side["power"],
                    f"{holder} {side['power']} ({kind} adds no power, bonus unread)")
        if kind in ADDS_POWER:
            return (side["power"] + side["bonus"],
                    f"{holder} {side['power']}+{side['bonus']} ({kind})")
        if kind is not None:
            # a speed or fielding boost: real, read, and adds no power
            return side["power"], f"{holder} {side['power']} ({kind} adds no power)"
        if side["bonus"] == 2:
            # THE FALLBACK, AND IT IS STILL SOUND. Section 4's census over 299
            # hand-labelled tactics cards has POWER SWING as the only card ever
            # above +1, so a +2 resolves its own kind even when the banner did not
            # read. It is kept BELOW the banner because a read beats an inference.
            return (side["power"] + 2,
                    f"{holder} {side['power']}+2 (banner unread; a +2 is a Power Swing)")
        return None, (f"{holder} has a +{side['bonus']} whose KIND did not read "
                      f"({side.get('kind_detail')}) -- a swing/pitch boost adds power "
                      f"and a speed/fielding boost does not")
    a, wa = eff(o, "ours")
    b, wb = eff(t, "theirs")
    if a is None or b is None:
        return None, "; ".join(x for x in (None if a else wa, None if b else wb) if x)
    # THE SIGN IS ALWAYS FROM THE BATTER'S SIDE (reveal_margin's rule). read_reveal
    # has already resolved ours/theirs by phase, so this is a plain subtraction
    # in batting terms and must NOT flip again -- doing both was the bug that
    # made a pitching margin read backwards twice over.
    m = a - b if phase == "batting" else b - a
    return m, f"{wa} vs {wb}"
