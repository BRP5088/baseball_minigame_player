"""select_card is a TOGGLE, so a press at a card whose state cannot be read is
as likely to put a SELECTED card down as to put an unselected one up.

LIVE, 2026-09-20, pitching half of a paid match. Slot 3 was selected (confirmed by
the user watching the screen). A selected card BRIGHTENS until its power disc has
no dark edge left to trace, so the disc read failed, the row's y came from a
fallback about 66 px BELOW the anchor, and selected_cards -- which compares y
against the DISC anchor -- answered "not selected" with full confidence.

_select_verified then pressed select_card five times at a card that was ALREADY
UP, toggling it, and could not see which way it had gone. The same blindness
propagated: cursor_slot takes `lifted` precisely so a selected card's glow can be
discounted, so with lifted empty the selected card's glow (69.3 against <=26 for
every other slot) won and the cursor read slot 3 while it was really on slot 0.

A BRIGHTNESS DETECTOR WAS MEASURED AND REJECTED rather than shipped. Over 540
archived hand crops plus three frames whose answer is known:

    SELECTED  n=  45   min 109.0  p50 119.0  max 129.0   (and 89 on a known frame)
    RESTING   n=2307   min  28.0  p50  57.0  max 120.0

The populations OVERLAP, so no threshold on that quantity separates them
(CLAUDE.md 10.4) -- the same outcome section 10.35 records for four other attempts
to move this window. So the fix is to ABSTAIN rather than to guess better.

WHAT THIS FILE PINS: when the target's position is unknown, _select_verified
refuses and presses NOTHING. A refusal is recoverable -- the caller re-reads a
fresh frame -- where a toggle is not.
"""
import os as _os
import sys as _sys

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import input_controller as ic                                    # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


N = ic.MAX_HAND_SIZE
_presses = []


def _fake_press(action, *a, **k):
    _presses.append(action)


def look_with(ys, selected=()):
    """A settled five-row read whose y positions are exactly `ys`."""
    def _look():
        return ([0.0] * N, list(ys), N, list(selected))
    return _look


_real_press = ic.press
ic.press = _fake_press
try:
    # --- THE BUG: an unreadable target must NOT be pressed --------------------
    _presses.clear()
    ys = [100, 100, 100, None, 100]          # slot 3's position is unknown
    ok, _sel = ic._select_verified(3, look_with(ys))
    check(ok is False,
          f"_select_verified must REFUSE when the target's position is unknown; "
          f"returned {ok!r}")
    check(_presses == [],
          f"...and it must press NOTHING -- select_card is a toggle, so a blind "
          f"press can DESELECT the card the engine already chose. Pressed: {_presses!r}")

    # --- CONTROL: a readable, unselected target IS pressed --------------------
    # Without this the check above passes just as well on a function that refuses
    # everything and can never select anything at all (CLAUDE.md 10.1).
    _presses.clear()
    ic._select_verified(3, look_with([100, 100, 100, 100, 100]))
    check("select_card" in _presses,
          f"CONTROL: a target whose position IS readable and which is not yet "
          f"selected must still be pressed; pressed {_presses!r} -- if this fails "
          "the refusal check above proves nothing")

    # --- CONTROL: an already-selected target is a success, not a press --------
    _presses.clear()
    ok, _sel = ic._select_verified(3, look_with([100] * N, selected=(3,)))
    check(ok is True and _presses == [],
          f"CONTROL: a target already selected is a SUCCESS and must not be "
          f"pressed again (that would toggle it off); ok={ok!r} pressed={_presses!r}")

    # --- an unknown slot that is NOT the target must not block a good press ---
    _presses.clear()
    ic._select_verified(1, look_with([100, 100, None, None, 100]))
    check("select_card" in _presses,
          f"a slot OTHER than the target being unreadable must not stop the press; "
          f"pressed {_presses!r}")
    # --- AND THE SEAM THAT CARRIES "UNKNOWN" TO IT --------------------------
    # _select_verified only ever sees the ys that hand_cursor_look builds. If that
    # stops marking a fallback-derived player y as unknown, the refusal above can
    # never fire in production no matter how correct it is -- a guard one layer up
    # from the damage, which is CLAUDE.md section 5's recurring shape.
    import orchestrator as _o
    import local_hand as _lh

    _saved = (_o._grab_settle_regions, _lh.cursor_glow, _lh.read_hand,
              _o.homeplate_runner_present)
    try:
        from PIL import Image as _Image
        _blank = _Image.new("L", (int(_lh.ANCHOR_W), 300), 128)
        _rows = [{"x": 100 * (i + 1), "y": 150, "kind": "player", "digit": "5",
                  "y_measured": True, "y_from": "disc" if i != 3 else "fallback"}
                 for i in range(N)]
        _o._grab_settle_regions = lambda names: {"hand": _blank, "home_plate": _blank}
        _o.homeplate_runner_present = lambda crops: False
        _lh.read_hand = lambda img: _rows
        _lh.cursor_glow = lambda img, rows=None, _boxes=None: (None, [0.0] * N, _rows)
        _glow, _ys_out, _n, _sel = _o.hand_cursor_look()
        check(_ys_out[3] is None,
              f"hand_cursor_look must report a player row whose y came from a "
              f"FALLBACK as unknown (None), or _select_verified can never refuse; "
              f"got ys={_ys_out!r}")
        check(_ys_out[0] == 150 and _ys_out[2] == 150,
              f"CONTROL: disc-derived rows must keep their y; got ys={_ys_out!r}")
    finally:
        (_o._grab_settle_regions, _lh.cursor_glow, _lh.read_hand,
         _o.homeplate_runner_present) = _saved
finally:
    ic.press = _real_press

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print("  an unreadable selection refuses instead of pressing a toggle blind, and "
      "a readable one still presses")
