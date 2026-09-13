"""THE BAN SCREEN'S DECISIONS, pulled out of the viewer so they can be tested.

tools/state_viewer.py builds a Tk window at import, so nothing could ever import it to
check its logic -- and affected_tests.py says so out loud: "state_viewer.py -> NO TEST
IMPORTS IT. Nothing here can prove this change; the full suite cannot either." Most of a
day's work went into that file. These are the parts that decide something, with the OCR
plumbing left behind.

Nothing here touches the console, the network or a file. Every function is a decision about
values already read.
"""

# POWER RUNS 4 TO 9. There is no 1, 2 or 3 power card in the game (CLAUDE.md section 4), so
# a digit outside that is a known misread rather than a surprising card.
POWER_RANGE = (4, 9)

# A TACTICS BONUS IS 1 OR 2, AND 2 ONLY ON POWER SWING. Over 299 hand-labelled tactics
# cards: POWER SWING +1 60% / +2 40%, and SPEED BOOST, PITCH FOCUS and FIELDING PLAY +1 on
# every single card between them. Zero 3s anywhere; the paid model recorded eleven "+3"
# rows and one "+11", which is how we know what a reader inventing a bonus looks like.
#
# The card-aware half earns its place immediately: the viewer showed "Speed Boost +2" on a
# live screen, which the card census says cannot exist. Without the label the badge reader
# had no way to know that and neither did anyone reading the panel.
BONUS_VALUES = ("1", "2")
BONUS_TWO_ONLY_ON = "POWER SWING"


def rowkey(rows):
    """A stable id for WHERE the grid is, used to clear held values when it scrolls.

    NOT the scroll level: read_ban_scroll_level returns None often enough that keying on it
    would leave values held forever, showing the previous page's names over the new page's
    cards -- a stale answer that looks exactly like a confident one (CLAUDE.md 10.1).
    """
    if not rows:
        return None
    return tuple(round(r["top"], 2) for r in rows)


def latch(state, key, value, scrollkey):
    """The value to SHOW, holding the last good one until a new one is confirmed.

    THE READER IS NOT FLAKY, THE PICTURE IS. Running the OCR twenty times on ONE crop
    returns the identical answer every time; it is the FRAMES that differ, because this is
    an H.264 stream and chiaki logs corrupt frames during normal play. So an answer that
    arrived once is better evidence than a blank that arrived after it.

    The rule is the project's own -- local_hand_cards commits only to a hand that read twice
    running: a NEW value must be seen twice before it replaces the held one, and None never
    replaces anything. `state` is a dict the caller owns and this mutates.
    """
    if state.get("scroll") != scrollkey:
        state.clear()
        state.update({"scroll": scrollkey, "held": {}, "cand": {}})
    state.setdefault("held", {})
    state.setdefault("cand", {})
    held = state["held"].get(key)
    if value is None:
        return held
    if value == held:
        state["cand"].pop(key, None)
        return held
    if held is None:
        # THE FIRST SIGHTING IS HELD, NOT MERELY SHOWN. It was only shown, and the test
        # written to cover this caught it within a minute: an abstention arriving straight
        # after the first good read found nothing held and blanked the cell. Two agreeing
        # reads are the bar for CHANGING an answer, not for having one.
        state["held"][key] = value
        return value
    if state["cand"].get(key) == value:
        state["held"][key] = value
        state["cand"].pop(key, None)
        return value
    state["cand"][key] = value
    return held


# HOW OFTEN A SETTLED CELL IS RE-READ ANYWAY. Not never: a first read that happened to land
# on a degraded frame would otherwise be held forever with nothing able to correct it, which
# is a stale answer wearing a confident one's clothes.
#
# THE NUMBER IS NOT TUNED, AND SAYING SO IS THE HONEST PART. To settle wrong, a reader has
# to return the SAME WRONG ANSWER TWICE RUNNING -- and across every corpus measured on
# 2026-09-13 these readers do not return wrong answers at all, they abstain:
#
#     type banner vs each card's ROLE (a different reader, a different box)   156 of 156
#     ban_digits power and shield vs the roster, held-out cells               219 of 219
#     ban_digits leave-one-CARD-out, 1,105 cells, per class                   0 wrong
#
# Zero wrong in every one. So this guards a failure that has never been observed, and no
# measurement can choose 12 over 6 or 30 until one is. It is cheap insurance at a cost of
# about one extra read per cell every six seconds, and it is written down as insurance
# rather than dressed up as a tuned constant.
#
# What WOULD move it: a single confirmed case of a cell holding a wrong value. The instrument
# already exists -- tools/state_viewer.py --ticks N films the panel in one process.
REFRESH_EVERY = 12


def held(state, key):
    """The value being held for this cell, or None. Read-only."""
    return (state.get("held") or {}).get(key)


def needs_read(state, keys, tick, refresh_every=REFRESH_EVERY):
    """Is there anything left to learn about this cell on this pass?

    THE READERS ARE THE WHOLE COST. Profiled at steady state, reading the name and the type
    of every unlocked cell is over two thirds of a slow pass -- and once the latch is
    holding both, every one of those calls returns an answer that is thrown away. A cell
    that has already answered is re-read only on the refresh beat.
    """
    if tick % refresh_every == 0:
        return True
    return not all(held(state, k) for k in keys)


def kind_of(type_result):
    """'player' | 'tactics' | None, from what read_card_type returned.

    None IS ITS OWN ANSWER AND MUST NOT BECOME 'player'. It did, by falling through a draw
    branch, and the result was four player windows painted over a tactics card -- an
    abstention wearing a confident answer's clothes (the user spotted it, 2026-09-13).
    """
    if isinstance(type_result, tuple):
        return "tactics"
    if isinstance(type_result, str):
        return "player"
    return None


def power_ok(digit):
    """Is this a power a card could actually have?"""
    try:
        return POWER_RANGE[0] <= int(digit) <= POWER_RANGE[1]
    except (TypeError, ValueError):
        return False


def bonus_ok(digit, label=None):
    """Is this a tactics bonus THIS card could actually have?

    Pass the card's label when it is known. Without it the check is the loose one -- 1 or 2
    -- because refusing a legitimate POWER SWING +2 for want of a label would be worse than
    admitting an occasional wrong 2.
    """
    d = str(digit)
    if d not in BONUS_VALUES:
        return False
    if d == "2" and label is not None:
        return str(label).upper().strip() == BONUS_TWO_ONLY_ON
    return True


def values_for(card=None, bank=(None, None), ocr_power=None):
    """(power, second, source) for one PLAYER card, choosing between three readers.

    THE NAME IS THE BEST READER AND IT IS NOT A DIGIT READER. ocr_ban_card_name resolves the
    name banner to a roster PlayerCard that already carries power and secondary exactly, so
    where the name reads there is nothing to OCR. Measured: on all 12 cells where the digit
    OCR contradicted the roster, the crop plainly showed the ROSTER's digit -- an 8 read as
    5, a 6 read as 5, a 7 read as 9, the ball sprite clipping the disc every time.

    THE BANK IS SECOND. 219 of 219 on held-out cells for both fields.

    THE SHIELD USED TO NEED THE POWER BESIDE IT, AND NO LONGER DOES. The bank's original
    limit was that its shield could not tell "this card has no badge" from "this window is
    not on a card" -- a displaced window scored ~0.40 and a real no-badge card up to 0.564,
    one population with no gate. Leaning on read_power to prove a card was there was a
    workaround, and it cost the shield on any card whose disc was occluded.
    ban_digits.on_card now answers it directly, by matching the card's TOP-LEFT CORNER: a
    2D landmark, because the top strip and the top-RIGHT corner are each dominated by a
    straight border RUN and a line looks the same at every y -- both score up to 0.997 on a
    window shifted UP. Measured: displaced windows max 0.708, owned tactics cards max
    0.728, real player cards min 0.859 with the card's own templates held out. Re-read with
    the row box shifted a tenth of a card, the shield went from 134 WRONG to zero.
    So a shield is trusted on its own now. It still needs SOMETHING to have answered --
    both None means nothing read this cell at all.
    """
    if card is not None and getattr(card, "power", None) is not None:
        return str(card.power), str(card.secondary), "roster"
    bp, bs = bank
    if bp is not None:
        return str(bp), ("-" if bs is None else str(bs)), "bank"
    if bs is not None:
        return "-", str(bs), "bank"
    if ocr_power is not None and power_ok(ocr_power):
        return "?" + str(ocr_power), "-", "ocr"
    return "-", "-", "ocr"


def display_name(roster_name=None, raw_name=None, type_result=None, locked=False):
    """The ONE name a cell shows, whatever kind of card it is. None means "unknown".

    THIS EXISTS BECAUSE A TACTICS CARD'S NAME WAS NOT GOING THROUGH THE LATCH. A player
    card is named by the roster and that answer was held; a tactics card was named from
    THIS FRAME's type read, so the moment that read abstained the name fell back to the
    player path -- which is None for a tactics card -- and the cell printed "unknown". The
    user watched it flip "Fielding Play" / "unknown" with the cursor sitting on it.

    The fix is not a second latch, it is computing the name ONCE, from every source, and
    latching THAT. A value assembled after the latch cannot be held by it.

    Order: the roster names a player card; the tactics label names a tactics card; a raw
    banner read names a card the roster has never seen; a locked card says so.
    """
    if roster_name:
        return roster_name
    if isinstance(type_result, tuple) and len(type_result) == 2:
        return str(type_result[1]).title()
    if raw_name:
        return str(raw_name).title()
    return "locked" if locked else None


def boxes_for(kind):
    """Which sub-boxes belong on a card of this kind. () when the kind is unknown.

    A tactics card is a DIFFERENT LAYOUT, not a player card with different words: its label
    is centred at y 0.175-0.214 where the player ribbon is upper-left and ends at 0.13, and
    its badge is top CENTRE at x 0.43-0.62 where the player disc is top right at 0.72-0.94.
    Disjoint in both axes, so the wrong set cannot be a near miss.
    """
    if kind == "tactics":
        return ("tac_label", "tac_bonus")
    if kind == "player":
        return ("name", "type", "power", "shield")
    return ()
