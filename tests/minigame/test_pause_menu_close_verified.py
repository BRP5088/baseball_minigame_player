"""I-58: the pause-menu close after a balance read is a VERIFIED press, and run()
recognises a pause menu left open instead of burning its whole unreadable-screen
budget on it.

WHAT HAPPENED, live, 2026-09-21 (cycles 14 and 15 of the same overnight run --
overnight/run_live_20260921z.log, overnight/run_live_20260922a.log; census of all 16
pause-menu opens across cycles 1-16 in the ISSUES.md entry)
-----------------------------------------------------------------------------------
`read_balance_from_pause_menu()`'s close used to be a SINGLE BLIND
`press("toggle_pause")` with no log line and no verification on the path that
matters: the one post-close check lived in code AFTER the paid-call try/finally, so
it never ran when that call raised `PaidModelDisabled` (the ordinary state with the
paid model off). toggle_pause is a TOGGLE that drops ~15% of presses (CLAUDE.md
sec5) and, once it HAS landed, a second press REOPENS the menu -- so a bare press
can fail silently in either direction. Two consecutive cycles dropped it: no match
in progress, the balance already read correctly, only the close having failed.
run()'s own poll then read the pause book as an unrecognised screen 15 times running
("OCR: ['AUSE', 'MAIN', 'JOBS', ...]") and stopped with `unreadable_screens`, no
match played.

WHAT THIS FILE PINS
--------------------
1. `_close_pause_menu_verified()` closes via `input_controller.press_verified`,
   which presses ONLY while a FRESH, settled read still shows the menu open, and
   never presses again once a fresh read shows it closed (toggle_pause would
   REOPEN it).
2. `run()`'s unreadable-screen branch recognises the pause menu (via
   `pause_menu.is_pause_screen`, gated by `read_ban_counter(img) is None` so the
   ban book -- which clears the same page-brightness threshold, CLAUDE.md sec3 --
   is never mistaken for it), closes it with the SAME verified press instead of
   counting the poll as unreadable, and falls through to the ordinary
   `stuck_count` path when the close itself fails, so a menu that will not close
   still stops the run at the existing `MAX_STUCK_ATTEMPTS` bound.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_sys.path.insert(0, _os.path.join(_ROOT, "tests", "minigame"))

import contextlib
import io
import os

os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import input_controller as ic                                     # noqa: E402
import orchestrator as o                                          # noqa: E402
import pause_menu as pm                                           # noqa: E402
import reset_env                                                  # noqa: E402
from _run_harness import Harness                                  # noqa: E402

failures = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


# =============================================================================
# Part 1: _close_pause_menu_verified() itself -- (A) and (B) from the spec.
# =============================================================================

def _close_with(drop_first=0, close_after_landed=1, always_open=False):
    """Stubs press()/pause_menu.is_pause_screen() and runs the real
    _close_pause_menu_verified() against them.

    - The first `drop_first` presses are recorded but have NO EFFECT (the game
      ignoring them, CLAUDE.md sec5's measured 15.20%).
    - The (close_after_landed)-th LANDED press closes the menu.
    - `always_open`: no press ever has any effect (the menu will not close).

    is_pause_screen is asked FRESH every call (this function itself takes no
    frame argument and re-derives its answer from `landed` each time) -- which
    is the property under test: a stale/cached read would answer the SAME thing
    on every call regardless of how many presses have landed since.
    """
    state = {"presses": [], "landed": 0}

    def fake_press(action, *a, **kw):
        state["presses"].append(action)
        if len(state["presses"]) <= drop_first:
            return
        state["landed"] += 1

    def fake_is_pause_screen(img):
        if always_open:
            return True
        return state["landed"] < close_after_landed

    saved_press, saved_settle, saved_grab, saved_ips = (
        ic.press, o.wait_for_screen_to_settle, o._fast_grab, pm.is_pause_screen)
    ic.press = fake_press
    o.wait_for_screen_to_settle = lambda *a, **k: True
    o._fast_grab = lambda *a, **k: object()
    pm.is_pause_screen = fake_is_pause_screen
    try:
        ok, sent = o._close_pause_menu_verified(log=lambda *a, **k: None)
    finally:
        ic.press, o.wait_for_screen_to_settle, o._fast_grab, pm.is_pause_screen = (
            saved_press, saved_settle, saved_grab, saved_ips)
    return ok, sent, state["presses"]


# --- (A) dropped once, then lands: retries, closes, 2 presses --------------
ok, sent, presses = _close_with(drop_first=1, close_after_landed=1)
check(ok is True and sent == 2 and presses == ["toggle_pause"] * 2,
      f"(A) a dropped first press must be retried and the menu closed on the "
      f"second: ok={ok!r} sent={sent} presses={presses}")

# --- (B) lands on the first press: exactly 1 press, no reopening retry -----
# A stale/cached observe would keep answering "still open" (the value it read
# BEFORE the press) and send a second press -- which, because toggle_pause is a
# toggle, would REOPEN the menu it had just closed. The fresh read this
# function uses sees the change immediately and stops.
ok, sent, presses = _close_with(drop_first=0, close_after_landed=1)
check(ok is True and sent == 1 and presses == ["toggle_pause"],
      f"(B) a press that lands on the FIRST attempt must not be followed by a "
      f"second (fresh reads must be used, not a frame read once and reused): "
      f"ok={ok!r} sent={sent} presses={presses}")

# --- bonus: the menu that never closes reports failure, bounded ------------
ok, sent, presses = _close_with(always_open=True)
check(ok is False and sent == ic.PRESS_VERIFY_TRIES,
      f"a menu that never closes must fail BOUNDED at PRESS_VERIFY_TRIES "
      f"({ic.PRESS_VERIFY_TRIES}), not loop forever or silently give up early: "
      f"ok={ok!r} sent={sent}")


def _close_with_toggle(start_open, drop_first=0):
    """Same idea as _close_with, but models a REAL TOGGLE: the observed state
    flips on every LANDED press, starting from `start_open`, rather than
    "closes after N landed presses". _close_with cannot express "entered
    already CLOSED" (it always starts from open); this can.
    """
    state = {"presses": [], "landed": 0}

    def fake_press(action, *a, **kw):
        state["presses"].append(action)
        if len(state["presses"]) <= drop_first:
            return
        state["landed"] += 1

    def fake_is_pause_screen(img):
        return start_open != (state["landed"] % 2 == 1)   # XOR

    saved_press, saved_settle, saved_grab, saved_ips = (
        ic.press, o.wait_for_screen_to_settle, o._fast_grab, pm.is_pause_screen)
    ic.press = fake_press
    o.wait_for_screen_to_settle = lambda *a, **k: True
    o._fast_grab = lambda *a, **k: object()
    pm.is_pause_screen = fake_is_pause_screen
    try:
        ok, sent = o._close_pause_menu_verified(log=lambda *a, **k: None)
    finally:
        ic.press, o.wait_for_screen_to_settle, o._fast_grab, pm.is_pause_screen = (
            saved_press, saved_settle, saved_grab, saved_ips)
    return ok, sent, state["presses"]


# --- (N1) I-58 skeptic: ok must prove the STATE, not a CHANGE. Entered with
#         the menu ALREADY CLOSED, one press only OPENS it (toggle_pause is a
#         toggle) -- press_verified alone reports that as success (baseline
#         False -> after True IS a change), but the menu is now OPEN, so ok
#         must be False. This is what keeps _close_pause_menu's WARNING
#         branch from being skipped and its "pause menu closed after N
#         press(es)" success line from printing on a menu that is, in fact,
#         still open.
ok, sent, presses = _close_with_toggle(start_open=False)
check(ok is False,
      f"(N1) entered CLOSED, one press only OPENS it: ok must be False (the "
      f"function must confirm the menu now reads closed, not just that "
      f"press_verified saw a change), got ok={ok!r} sent={sent} "
      f"presses={presses}")

# --- (N1) CONTROL: entered OPEN, one press closes it -> ok stays True ------
ok, sent, presses = _close_with_toggle(start_open=True)
check(ok is True and sent == 1 and presses == ["toggle_pause"],
      f"(N1) CONTROL: entered OPEN, one press closes it -- ok must still be "
      f"True: ok={ok!r} sent={sent} presses={presses}")


def _settle_precedes_every_grab():
    """N2 (I-58 skeptic, mutant M1: delete wait_for_screen_to_settle from
    _pause_menu_open). `settled` is set True only inside the settle stub and
    is cleared by every grab immediately after reading it -- so a grab can
    only see True if ITS OWN preceding settle call actually ran. Drives the
    REAL _close_pause_menu_verified (not _pause_menu_open directly) so this
    is checked on every retry, not just the first call.
    """
    state = {"settled": False, "seen": []}

    def fake_settle(*a, **k):
        state["settled"] = True
        return True

    def fake_grab(*a, **k):
        state["seen"].append(state["settled"])
        state["settled"] = False   # must be re-earned by the NEXT settle call
        return object()

    def fake_ips(img):
        return True   # menu always reads open -- press_verified exhausts its budget

    saved = (o.wait_for_screen_to_settle, o._fast_grab, pm.is_pause_screen)
    o.wait_for_screen_to_settle, o._fast_grab, pm.is_pause_screen = (
        fake_settle, fake_grab, fake_ips)
    try:
        o._close_pause_menu_verified(log=lambda *a, **k: None)
    finally:
        o.wait_for_screen_to_settle, o._fast_grab, pm.is_pause_screen = saved
    return state["seen"]


seen = _settle_precedes_every_grab()
check(len(seen) == ic.PRESS_VERIFY_TRIES + 1 and all(seen),
      f"(N2) every read of the pause-screen observe must be preceded by its "
      f"OWN settle call -- got {seen} (expected "
      f"{ic.PRESS_VERIFY_TRIES + 1} entries, all True; deleting the settle "
      f"call from _pause_menu_open leaves every entry False)")


# =============================================================================
# Part 2: run()'s unreadable-screen branch -- (C), (D), (E) from the spec.
#
# Reuses _run_harness.Harness (the project's own run() state-machine rig) for
# every seam except pause_menu.is_pause_screen, which that harness does not
# know about and this file patches directly around each h.run() call.
#
# input_controller.PRESS_VERIFY_SETTLE is dropped to 0 for the duration --
# press_verified sleeps on input_controller's OWN `time` module, not the
# harness's virtual clock, so left at its real 0.45s default these three
# scenarios (up to MAX_STUCK_ATTEMPTS x PRESS_VERIFY_TRIES presses) would cost
# real minutes for no evidentiary gain (tests/rig/test_press_verified.py makes
# the same trade with an explicit settle=0).
# =============================================================================

_saved_settle_const = ic.PRESS_VERIFY_SETTLE
ic.PRESS_VERIFY_SETTLE = 0

try:
    N = o.MAX_STUCK_ATTEMPTS + 3   # more than the bound, so a false stop is visible

    # --- (C) a closable pause menu, no match in progress: closed every time,
    #         the unreadable-screen counter is NEVER incremented -----------
    h = Harness([RuntimeError("LOCAL STATE GAP: UNRECOGNISED SCREEN")] * N,
                balance=500, ban_counter=None)
    saved_ips = pm.is_pause_screen
    # "still open" until a toggle_pause press LANDS this same poll; landed is
    # a per-poll set the harness clears at the top of every _next_state() call,
    # so this is exactly "closes on the first landed press of this poll".
    pm.is_pause_screen = lambda img: "toggle_pause" not in h.landed
    try:
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            h.run(target_wins=99, max_spend=500)
    finally:
        pm.is_pause_screen = saved_ips
    check("toggle_pause" in h.presses,
          "(C) the pause menu must be closed with toggle_pause, not ignored")
    check(h.idx == N,
          f"(C) all {N} closable-pause-menu polls must be consumed WITHOUT the "
          f"run stopping early -- stuck_count must not be incremented for a poll "
          f"that recognised and closed the pause menu; only {h.idx} of {N} were "
          f"consumed before something ended the loop")
    check("Stuck too long on unreadable screens" not in _buf.getvalue(),
          "(C) a closable pause menu must never trip the unreadable-screen stop")

    # --- (D) CONTROL: the ban book must NOT be treated as the pause menu ---
    # is_pause_screen reads True (the ban book clears the same page-brightness
    # gate, CLAUDE.md sec3), but read_ban_counter ANSWERS -- the one signal
    # that already separates the two notebooks. This must fall through to the
    # ordinary unreadable-screen path and stop at the existing bound, exactly
    # as it did before this feature existed.
    h = Harness([RuntimeError("LOCAL STATE GAP: UNRECOGNISED SCREEN")] * N,
                balance=500, ban_counter=3)
    saved_ips = pm.is_pause_screen
    pm.is_pause_screen = lambda img: True
    try:
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            h.run(target_wins=99, max_spend=500)
    finally:
        pm.is_pause_screen = saved_ips
    check("toggle_pause" not in h.presses,
          f"(D) CONTROL: a ban screen (read_ban_counter answers) must never be "
          f"closed with toggle_pause; presses={h.presses}")
    check(h.idx == o.MAX_STUCK_ATTEMPTS,
          f"(D) CONTROL: a ban screen wrongly treated as pause would consume "
          f"more than {o.MAX_STUCK_ATTEMPTS} polls before stopping (or never "
          f"stop) -- it must hit the ordinary unreadable-screen bound exactly "
          f"as before; consumed {h.idx}")
    check("Stuck too long on unreadable screens" in _buf.getvalue(),
          "(D) CONTROL: the ban screen must still stop via the existing "
          "unreadable-screen path")

    # --- (E) a pause menu that NEVER closes: falls through to the ordinary
    #         stuck_count path and still stops at the existing bound --------
    h = Harness([RuntimeError("LOCAL STATE GAP: UNRECOGNISED SCREEN")] * N,
                balance=500, ban_counter=None)
    saved_ips = pm.is_pause_screen
    pm.is_pause_screen = lambda img: True   # never responds to any press
    try:
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            h.run(target_wins=99, max_spend=500)
    finally:
        pm.is_pause_screen = saved_ips
    check(h.presses.count("toggle_pause") >= o.MAX_STUCK_ATTEMPTS,
          f"(E) a menu that never closes must still be TRIED every poll, not "
          f"given up on after the first failure; only "
          f"{h.presses.count('toggle_pause')} toggle_pause press(es) sent")
    check(h.idx == o.MAX_STUCK_ATTEMPTS,
          f"(E) a pause menu that never closes must fall through to the "
          f"EXISTING stuck_count bound ({o.MAX_STUCK_ATTEMPTS}) rather than "
          f"spin forever or stop at a different count; consumed {h.idx}")
    check("Stuck too long on unreadable screens — stopping." in _buf.getvalue(),
          "(E) must stop with the EXISTING stop message/reason "
          "(unreadable_screens), not a new one invented for this feature")

    # --- (N3) I-58 skeptic: OPTIONS must NEVER be pressed at a pause-looking
    #         frame while a match is in progress -- mid-match OPTIONS opens
    #         "Give up?" (CLAUDE.md sec4), one Cross from forfeiting a paid
    #         match. `elif not match_in_progress:` is the gate that stops it;
    #         this pins that gate directly (skeptic mutant M2: de-chain it to
    #         `if True:`, which fires the close mid-match too).
    N3 = 5
    saved_gud = reset_env.give_up_dialog
    reset_env.give_up_dialog = lambda img: False   # no "Give up?" dialog up
    try:
        h = Harness([RuntimeError("LOCAL STATE GAP: UNRECOGNISED SCREEN")] * N3,
                    balance=500, ban_counter=None)
        h.seed["match_in_progress"] = True
        saved_ips = pm.is_pause_screen
        pm.is_pause_screen = lambda img: True   # looks exactly like an open pause menu
        try:
            h.run(target_wins=99, max_spend=500)
        finally:
            pm.is_pause_screen = saved_ips
        check("toggle_pause" not in h.presses,
              f"(N3) match_in_progress=True must NEVER press toggle_pause at "
              f"a pause-looking frame -- OPTIONS mid-match opens 'Give up?', "
              f"one Cross from forfeiting the match; presses={h.presses}")

        # CONTROL: the identical pause-looking frame, match_in_progress=False
        # -- proves the gate is doing something, not that toggle_pause is
        # simply never sent by this harness at all.
        h2 = Harness([RuntimeError("LOCAL STATE GAP: UNRECOGNISED SCREEN")] * N3,
                     balance=500, ban_counter=None)
        saved_ips = pm.is_pause_screen
        pm.is_pause_screen = lambda img: True
        try:
            h2.run(target_wins=99, max_spend=500)
        finally:
            pm.is_pause_screen = saved_ips
        check("toggle_pause" in h2.presses,
              f"(N3) CONTROL: match_in_progress=False must press toggle_pause "
              f"at the same pause-looking frame; presses={h2.presses}")
    finally:
        reset_env.give_up_dialog = saved_gud
finally:
    ic.PRESS_VERIFY_SETTLE = _saved_settle_const


for f in failures:
    print(f"FAIL: {f}")
print(f"{len(failures)} pause-menu close failure(s)"
      if failures else "pause-menu close verification: all checks passed")
_sys.exit(1 if failures else 0)
