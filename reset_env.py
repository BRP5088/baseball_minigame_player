"""Reset the testing environment: reload the last save.

Re-copying the save is the ONLY step of a session that needs a human. Every
other part — preflight, bans, play, logging, stopping at the spend cap —
already runs unattended, so automating this is what turns "runs while you
watch" into "runs overnight".

THE SEQUENCE, all verified live on 2026-08-26:

    Options                     -> pause menu opens
    Down (until verified)       -> "Load Last Save" is highlighted
    Cross                       -> confirmation dialog appears
    Cross                       -> YES; the world reloads in ~6s

Reproduced many times. POSITION is reproducible; FACING IS NOT. Measured spawn
headings across clean resets: 57, 87, 89, 90, 91 degrees — a ~34 degree spread,
not a constant. An earlier version of this note claimed 97-98 every time and
called facing deterministic; that was three samples read through a compass that
was itself miscalibrated at the time, and it is wrong.

This matters because a replayed walk cannot assume a starting heading. It has
to READ the heading and steer relative to it. Anchoring on a fixed spawn
bearing, or rejecting a reading because it disagrees with one, will throw away
good data and start the route pointing somewhere it never intended.

WHAT MAKES IT SAFE
------------------
Nothing on this path deletes anything: there is no save SELECTION step, and
both ways to misstep fail harmlessly. One extra Down lands on "Load" (a save
picker); two lands on "Quit to Main Menu". Neither destroys data, but both
would silently derail an unattended run, so every step is VERIFIED rather than
assumed:

  * navigation reads the HIGHLIGHT back, so a dropped D-pad press cannot leave
    the cursor one row off unnoticed;
  * the commit is gated on the screen actually having changed;
  * "loaded" is the compass REAPPEARING, not a guessed sleep.

THE FAILURE MODE THAT ACTUALLY BIT US
-------------------------------------
The `o` key stopped reaching the game while `look_right` and `walk_left` kept
working. So "is input reaching the game" and "is THIS key reaching the game"
are different questions, and retrying blindly would have spun forever against
a problem only the user could fix (window focus). When the pause menu will not
open, this probes whether other input still lands and reports WHICH of the two
situations it is.
"""

import argparse
import os
import time

import numpy as np
from PIL import Image
import pytesseract

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-reset-env")

PAUSE_OPEN_ATTEMPTS = 3
GIVE_UP_ATTEMPTS = 3   # bounded separately: quitting a match is not a menu try
PAUSE_OPEN_WAIT_SEC = 4.0  # poll this long for the menu before pressing again
LATE_MENU_WAIT_SEC = 6.0   # ...and this long once more before giving up
PAUSE_SETTLE_SEC = 2.0
MENU_STEP_SEC = 0.8
SELECTION_READ_TRIES = 4      # the menu animates; one bad frame is not ambiguity
SELECTION_RETRY_SEC = 0.5
# Mean pixel change proving the screen really CHANGED. Measured live
# 2026-09-01, all on the screens this gate actually runs on:
#
#     pause-screen idle noise   1.68 - 4.16 over ten 0.4s samples (mean 2.92)
#     YES accepted (-> loading) 29.26
#     dialog appears            ~78
#
# At 2.0 the gate sat BELOW the screen's own animation, so the very first
# noise sample cleared it. That is not theoretical: it burned all three reset
# attempts on 2026-09-01 — the run believed YES had landed, then waited out the
# full 45s for a world that had never started loading, three times, and played
# no matches at all. Polling was added earlier to fix this and could not: a
# threshold under the noise floor is cleared by the first sample, however long
# you poll.
#
# 12.0 is the geometric middle of the two measurements that matter (4.16 noise,
# 29.26 smallest true positive) — ~2.9x above noise, ~2.4x below signal.
#
# NOT VALID IN-WORLD: idle camera drift there measures 14-20, well above this.
# This gate only ever runs on the pause and dialog screens; do not reuse it.
CONFIRM_DELTA_MIN = 12.0
CONFIRM_PRESS_ATTEMPTS = 3    # the YES press is verified, not assumed
COMMIT_PRESS_ATTEMPTS = 3     # ...and so is the press that OPENS the dialog
CONFIRM_WAIT_SEC = 4.0        # how long the dialog gets to animate in before
                              # its absence is called a dropped press
LOAD_TIMEOUT_SEC = 45.0


# The centre of the "Give up?" dialog. OCRs cleanly at every threshold tried
# (110/140/170) on a live 1920x1080 window capture.
GIVE_UP_BOX = (0.30, 0.40, 0.70, 0.50)


def give_up_dialog(img):
    """True if the in-match "Give up?" confirmation is on screen.

    OPTIONS does NOT open the pause menu during a match — it opens this. Without
    knowing that, the reset pressed OPTIONS, saw no pause menu, and concluded
    "the pause menu will not open and NO input is reaching the game", which was
    exactly backwards: the press had worked and put this dialog up. Two whole
    runs died on that misdiagnosis on 2026-09-01, both times with a perfectly
    healthy stream.
    """
    w, h = img.size
    x0, y0, x1, y1 = GIVE_UP_BOX
    c = img.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1))).convert("L")
    c = c.resize((c.width * 3, c.height * 3), Image.LANCZOS)
    for thr in (110, 140, 170):
        b = c.point(lambda p, t=thr: 0 if p < t else 255)
        if "give up" in pytesseract.image_to_string(
                b, config="--psm 7").strip().lower():
            return True
    return False


class ResetError(RuntimeError):
    """Raised when the reset cannot be completed safely."""


def _grey(img):
    return np.asarray(img.convert("L"), dtype=float)


def _clear_match_flags(progress_file, log=print):
    """Clear match_in_progress/bans_done_this_match after a confirmed reload.

    Money fields are NEVER touched — the wallet is whatever the save holds, and
    only a pause-menu read may set `balance`. Failing here must not turn a
    successful reset into an exception, so it logs and moves on: the reset
    really did happen, and losing the bookkeeping is strictly better than
    raising ResetError at a caller that has already reloaded the game.
    """
    try:
        import json
        with open(progress_file) as fh:
            rec = json.load(fh)
        if not (rec.get("match_in_progress") or rec.get("bans_done_this_match")):
            return
        rec["match_in_progress"] = False
        rec["bans_done_this_match"] = False
        tmp = progress_file + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(rec, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, progress_file)
        log(f"  cleared match_in_progress in {progress_file} — the reload "
            f"discarded any match, so the record was stale")
    except Exception as e:
        log(f"  WARNING: could not clear match_in_progress in "
            f"{progress_file} ({type(e).__name__}: {e}) — a stale flag can "
            f"make the next run spend an UNTRACKED $50")


def reset_environment(log=print, progress_file=None):
    """Reload the last save. Returns the spawn bearing in degrees.

    Raises ResetError rather than pressing on when a step cannot be confirmed.
    A half-completed reset leaves the game in an unknown state, and an
    unattended caller has no way to recover from that — better to stop loudly.

    `progress_file` — CLEAR THE MATCH FLAGS when the reset succeeds.

    A successful return here PROVES no match is running: this function answers
    "Give up?" if one was, reloads the save, and waits for the world. So this is
    the one moment where clearing `match_in_progress` is safe, and CLAUDE.md's
    warning ("often NOT stale — check the screen first") is satisfied because
    the reset IS the screen check.

    Leaving it stale is not cosmetic. Measured 2026-09-04: a stale flag plus a
    real dealer prompt makes orchestrator's recovery path press `start_match`
    believing the $50 was already paid — so the money leaves the in-game wallet,
    `balance` is never debited, and `max_spend` cannot stop it. 25 call sites
    reload the save and only `run_cycles` repaired the record, so every
    navigation run left the flag armed.

    Defaults to None so a pure navigation caller writes nothing — but if you
    track money, PASS IT.
    """
    import compass
    import input_controller as ic
    import orchestrator as o
    import pause_menu as pm

    def cap():
        return compass.fast_capture()          # 111ms vs 3058ms

    # Focus before anything else. Without it every press below vanishes and
    # each step fails for a reason that has nothing to do with the real cause.
    if not ic.has_focus():
        raise ResetError(f"chiaki is not the frontmost app "
                         f"({ic.frontmost_app()!r} is) — no input will reach "
                         f"the game. Click the game window and retry.")

    # --- 1. open the pause menu ------------------------------------------
    # LEAVING A MATCH IS NOT AN ATTEMPT AT THE MENU, and gets its own budget.
    # Mid-match OPTIONS opens "Give up?" rather than the pause menu, so getting
    # from a match to the menu costs FOUR passes — OPTIONS, YES, OPTIONS, read
    # — and charging the give-up steps to PAUSE_OPEN_ATTEMPTS spends the budget
    # before the menu is ever asked for.
    menu_tries = give_up_tries = 0
    while menu_tries < PAUSE_OPEN_ATTEMPTS:
        img = cap()
        if pm.is_pause_screen(img):
            break
        if give_up_dialog(img):
            if give_up_tries >= GIVE_UP_ATTEMPTS:
                raise ResetError("the 'Give up?' dialog will not clear after "
                                 f"{GIVE_UP_ATTEMPTS} YES presses — the match "
                                 "cannot be left, so the pause menu is "
                                 "unreachable")
            give_up_tries += 1
            log("  a match is in progress — 'Give up?' is up, answering YES "
                "so the pause menu can be reached (the reload discards it)")
            ic.press("cross", post_delay=0.4)
            time.sleep(PAUSE_SETTLE_SEC)
            continue
        # POLL FOR THE MENU, DO NOT RE-PRESS ON A TIMER. OPTIONS is a TOGGLE:
        # if the menu takes longer to animate in than the fixed wait, the next
        # press CLOSES it again, and the attempts run out in antiphase with the
        # screen. Observed 2026-09-01 — the reset raised "the pause menu will
        # not open" while the menu was, in fact, open a moment later.
        ic.press("toggle_pause", post_delay=0.4)
        menu_tries += 1
        _t = time.time()
        while time.time() - _t < PAUSE_OPEN_WAIT_SEC:
            time.sleep(0.4)
            if pm.is_pause_screen(cap()):
                break
    else:
        # ONE LAST, LONGER LOOK BEFORE CONDEMNING IT. The menu sometimes
        # animates in after the per-attempt poll window closes, and the failure
        # that follows is actively misleading: on 2026-09-02 this raised "the
        # pause menu will not open and NO input is reaching the game (probe
        # delta 4.9)" while the menu was, in fact, open — is_pause_screen()
        # then read True on 15 consecutive samples.
        #
        # The probe in _diagnose_no_pause() is what produced that claim, and it
        # cannot support it: in-world idle noise alone measures 14-20, so a
        # delta of 4.9 says the screen was not even in the world, not that
        # input was dead.
        _t = time.time()
        while time.time() - _t < LATE_MENU_WAIT_SEC:
            time.sleep(0.5)
            if pm.is_pause_screen(cap()):
                log(f"  pause menu appeared late, after "
                    f"{time.time() - _t:.1f}s of extra waiting")
                break
        else:
            raise ResetError(_diagnose_no_pause(ic, cap))
    log(f"  pause menu open (selected {pm.selected_item(cap())!r})")

    # --- 2. navigate to Load Last Save, verifying each step --------------
    def _read_selection():
        """Selected entry, retried past transient frames.

        selected_item() abstains whenever it cannot tell — which is correct,
        and is what stops a dropped D-pad press committing on the wrong row.
        But the menu ANIMATES, and a single unreadable frame mid-animation is
        not the same thing as a genuinely ambiguous menu. Retrying separates
        the two: a real ambiguity persists, a transition does not.
        """
        for _ in range(SELECTION_READ_TRIES):
            sel = pm.selected_item(cap())
            if sel is not None:
                return sel
            time.sleep(SELECTION_RETRY_SEC)
        return None

    for _ in range(5):
        sel = _read_selection()
        if sel == "Load Last Save":
            break
        if sel is None:
            raise ResetError("cannot tell which menu entry is selected after "
                             f"{SELECTION_READ_TRIES} reads — refusing to "
                             "press blindly")
        ic.press("dpad_down")
        time.sleep(MENU_STEP_SEC)
    else:
        raise ResetError("never landed on 'Load Last Save'")
    log("  selected: Load Last Save")

    # --- 3. commit, gated on the dialog actually appearing ---------------
    before = _grey(cap())
    ic.press("cross")
    # POLL for the dialog rather than sleeping a fixed 1.2s and measuring once.
    # Measured live 2026-08-31: the dialog animated in slower than 1.2s, so the
    # single reading caught 2.7 — noise, but above CONFIRM_DELTA_MIN — and the
    # code walked on to send its YES into a screen with no dialog on it yet.
    # That YES became the press that OPENED the dialog, and the reset then sat
    # in front of it for the full 45s waiting for a world nobody had asked for.
    #
    # A real dialog reads ~78. Polling costs nothing when it is already up
    # (first sample returns), and the threshold stays where the fixture-backed
    # test pins it rather than being raised to paper over the timing.
    # THE OPENING PRESS IS RETRIED, not just the YES below. A dropped press
    # here failed three separate runs on 2026-09-01 with "no confirmation
    # dialog appeared (delta 2.4/3.0)" while the very next manual cross opened
    # it at delta 83.8 — the press was lost, not the detector wrong. The YES
    # press has been retried since it first failed; this one never was.
    #
    # Retrying is safe HERE because the precondition is re-checked: the menu
    # must still be showing 'Load Last Save'. If the dialog did open and this
    # merely missed it, the screen is no longer the pause menu and no further
    # press is sent.
    delta = 0.0
    for _attempt in range(COMMIT_PRESS_ATTEMPTS):
        _t0 = time.time()
        while time.time() - _t0 < CONFIRM_WAIT_SEC:
            time.sleep(0.4)
            delta = float(np.abs(_grey(cap()) - before).mean())
            if delta >= CONFIRM_DELTA_MIN:
                break
        if delta >= CONFIRM_DELTA_MIN:
            break
        if not pm.is_pause_screen(cap()):
            break            # something changed; do not press into the unknown
        if _read_selection() != "Load Last Save":
            break            # no longer on Load Last Save; pressing is unsafe
        log(f"  no dialog yet (delta {delta:.1f}) — the commit press did not "
            f"land, retrying ({_attempt + 1}/{COMMIT_PRESS_ATTEMPTS})")
        ic.press("cross")
    if delta < CONFIRM_DELTA_MIN:
        raise ResetError(f"no confirmation dialog appeared (delta {delta:.1f})")
    log(f"  confirmation dialog up (delta {delta:.1f}) -> YES")

    # The YES press gets VERIFIED like every other step. Unverified, it was the
    # one blind press left in the sequence, and it duly failed live: the dialog
    # stayed up, nothing loaded, and the reset sat waiting out its full 45s
    # timeout for a world that was never coming. A dropped keystroke here is
    # indistinguishable from a slow load unless the screen is checked.
    for attempt in range(CONFIRM_PRESS_ATTEMPTS):
        pre = _grey(cap())
        ic.press("cross")
        time.sleep(1.5)
        if float(np.abs(_grey(cap()) - pre).mean()) >= CONFIRM_DELTA_MIN:
            break
        log(f"  YES press {attempt + 1} did not register, retrying")
    else:
        raise ResetError("the confirmation dialog never accepted YES — the "
                         "cross key is not reaching the game")

    # --- 4. wait for the WORLD, not for a duration -----------------------
    t0 = time.time()
    while time.time() - t0 < LOAD_TIMEOUT_SEC:
        time.sleep(1.5)
        bearing = compass.read_bearing(cap())
        if bearing is not None:
            log(f"  world back after {time.time() - t0:.1f}s, "
                f"spawn bearing {compass.describe(bearing)}")
            if progress_file:
                _clear_match_flags(progress_file, log)
            return bearing
    raise ResetError(f"compass never reappeared within {LOAD_TIMEOUT_SEC:.0f}s "
                     "— the load may have failed, or the game is on a screen "
                     "this does not recognise")


def _diagnose_no_pause(ic, cap):
    """Distinguish 'no input reaches the game' from 'the o key specifically'.

    Live on 2026-08-26 the pause key stopped landing while other keys still
    worked, and the fix was on the user's side. Retrying would never have
    surfaced that; naming which case it is does.
    """
    # The reticle answers "is input reaching the game" outright, so only the
    # ambiguous case still needs a probe press.
    if not ic.has_focus():
        return (f"the pause menu will not open and chiaki is not frontmost "
                f"({ic.frontmost_app()!r} is) — click the game window.")
    before = _grey(cap())
    ic.press("look_right", hold_seconds=0.3, post_delay=0.4)
    time.sleep(0.9)
    moved = float(np.abs(_grey(cap()) - before).mean())
    # Undo the probe so a failed reset does not also leave the camera turned.
    ic.press("look_left", hold_seconds=0.3, post_delay=0.4)
    if moved > 5.0:
        return ("the pause menu will not open, but other input IS reaching the "
                f"game (probe turned the camera, delta {moved:.1f}). The 'o' "
                "key specifically is not landing — check that the chiaki "
                "window has keyboard focus.")
    return ("the pause menu will not open and NO input is reaching the game "
            f"(probe delta {moved:.1f}) — chiaki is probably not focused, or "
            "the stream is not running.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Reload the last save.")
    ap.add_argument("--live", action="store_true",
                    help="actually perform the reset (default: describe only)")
    args = ap.parse_args()
    if not args.live:
        print(__doc__)
        print("Pass --live to actually perform the reset.")
    else:
        try:
            reset_environment()
            print("  RESET OK")
        except ResetError as exc:
            raise SystemExit(f"  RESET FAILED: {exc}")
