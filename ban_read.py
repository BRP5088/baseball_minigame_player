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

    A SHIELD IS ONLY REPORTED WHEN THE POWER ANSWERED. The bank's own honest limit: its
    shield cannot tell "this card has no badge" from "this window is not on a card" -- a
    displaced window scores ~0.40 and a real no-badge card up to 0.564, one population with
    no gate between them. read_power DOES catch the displaced window, so it is what says a
    card is there at all.
    """
    if card is not None and getattr(card, "power", None) is not None:
        return str(card.power), str(card.secondary), "roster"
    bp, bs = bank
    if bp is not None:
        return str(bp), ("-" if bs is None else str(bs)), "bank"
    if bs is not None:
        return "-", "-", "bank"
    if ocr_power is not None and power_ok(ocr_power):
        return "?" + str(ocr_power), "-", "ocr"
    return "-", "-", "ocr"


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
