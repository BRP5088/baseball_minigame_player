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

# PROBE THRESHOLDS. The old probe tested `moved > 5.0` while this same file
# records, 139 lines away, that "in-world idle noise alone measures 14-20". So
# the test was satisfied by ANY in-world frame whether or not the press did
# anything, and the failing run's delta of 16.1 sits inside that idle band. A
# threshold under one population (10.4), producing a confident message about a
# press it never measured.
#
# The fix is not a bigger number, it is a PAIRED comparison: each trial takes
# its own NULL sample (capture, wait, capture, no press) and a transport counts
# as alive only when its delta beats that scene's own idle noise. PROBE_RATIO
# does the work; PROBE_FLOOR only stops a frozen picture (null ~ 0) making any
# flicker look like movement.
#
# Both are PROVISIONAL and anchored on one documented population (idle 14-20).
# Nothing has yet measured the pressed population on this rig, so a probe that
# lands between the two is reported AMBIGUOUS rather than guessed at.
PROBE_RATIO = 1.8      # a real turn must beat this scene's idle noise by 1.8x
PROBE_FLOOR = 8.0      # ...and clear this, so a frozen frame cannot qualify
PROBE_GAP_SEC = 0.9    # the settle used for every sample, null included
PROBE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "overnight", "resetfail")
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
    # NOTE WHAT THIS CAN AND CANNOT CATCH. has_focus() is True whenever a chiaki
    # process exists — it does NOT check frontmost while background input is
    # available — so on this machine the only way here is chiaki being absent or
    # pgrep failing. The message used to name only "not frontmost", which is
    # wrong for its one reachable case. The predicate is deliberately unchanged;
    # no delivery path consults it, so tightening it would refuse presses that
    # do land.
    if not ic.has_focus():
        raise ResetError(f"no input can be sent: chiaki_pid()={ic.chiaki_pid()!r} "
                         f"and the frontmost app is {ic.frontmost_app()!r}. "
                         f"Either chiaki is not running, or it is not frontmost "
                         f"and background input is unavailable. Start chiaki "
                         f"(./restart_chiaki.sh) or click the game window.")

    # --- 1. open the pause menu ------------------------------------------
    # LEAVING A MATCH IS NOT AN ATTEMPT AT THE MENU, and gets its own budget.
    # Mid-match OPTIONS opens "Give up?" rather than the pause menu, so getting
    # from a match to the menu costs FOUR passes — OPTIONS, YES, OPTIONS, read
    # — and charging the give-up steps to PAUSE_OPEN_ATTEMPTS spends the budget
    # before the menu is ever asked for.
    menu_tries = give_up_tries = 0
    while menu_tries < PAUSE_OPEN_ATTEMPTS:
        img = cap()
        # A BAN SCREEN IS A NOTEBOOK PAGE TOO, and is_pause_screen cannot tell the two
        # books apart: censused over 10,239 frames, 1,122 of 1,140 ban frames clear
        # PAGE_MIN_FRAC 0.80 (BAN 0.7101..0.8587 against PAUSE 0.9263..0.9446), and
        # MENU_TEXT_MIN_FRAC overlaps completely so no threshold on that quantity
        # separates them. Breaking here on a ban screen means the code below then
        # navigates it AS A MENU -- selected_item() names an entry on 19 of 1,140 ban
        # frames, so up to five dpad_down presses go into a live ban screen. It never
        # named 'Load Last Save' in those 1,140, so no `cross` followed; that is luck,
        # not a guard.
        #
        # The ban counter is the instrument that separates them, already measured: 0
        # false positives off ban screens over 3,000 random frames. Imported lazily --
        # orchestrator pulls in a great deal, and a pure navigation caller should not
        # pay for it until this branch is actually reached.
        if pm.is_pause_screen(img):
            try:
                import orchestrator as _o
                _banned = _o.read_ban_counter(img)
            except Exception:
                _banned = None
            if _banned is not None:
                log(f"  this is a BAN screen (counter reads {_banned}), not the pause "
                    "book — both are notebook pages and is_pause_screen admits either. "
                    "Not navigating it as a menu.")
                raise ResetError(
                    "a ban screen is up, not the pause menu — refusing to press "
                    "dpad_down into it. Leave the ban screen first (TRIANGLE commits "
                    "whatever is banned and starts the match)")
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
            # MEASURE FIRST, THEN ESCALATE, AND ONLY ON THE ONE SIGNATURE THAT
            # ESCALATION CAN FIX. The old code raised here with a message that
            # advised fronting chiaki -- the exact repair the code would never
            # perform: press() reaches focus_chiaki_window only on a path that
            # is unreachable while chiaki runs, and that function then refuses
            # to front anyway whenever background input is available. So the
            # human was told to do by hand the thing the program had decided
            # not to do.
            probe = _probe_transports(ic, cap, log=log)
            escalated = False
            if probe["kbd_verdict"] == "dead" and probe["fifo_verdict"] == "alive":
                # This is the signature that a window is swallowing keys while
                # the stream stays healthy. Fronting is RUDE -- it takes the
                # keyboard from whoever is at the desk, which is the whole
                # reason background input exists -- so it happens only here, on
                # the terminal failure path, and only against this evidence.
                log("  the keyboard transport is dead while the stream is "
                    "alive — fronting chiaki once and retrying")
                import ensure_stream as es
                es._dismiss_mac_crash_dialog(log=log)
                try:
                    es._front_chiaki()
                except Exception as exc:
                    log(f"  could not front chiaki: {exc!r}")
                # osascript leaves Script Editor frontmost (section 5), so
                # CONFIRM chiaki actually came forward rather than assuming it.
                now_front = ic.frontmost_app()
                log(f"  frontmost app is now {now_front!r}")
                escalated = True
                # Deliberately NOT _clear_blocking_ui(): its later rungs press
                # Return (cross, which is JUMP in-world) and the PS button (a
                # Control Center TOGGLE). If the game is actually in-world those
                # move the character and open a console overlay, turning a
                # diagnosis into a new problem.
                ic.press("toggle_pause", post_delay=0.4)
                _t2 = time.time()
                while time.time() - _t2 < PAUSE_OPEN_WAIT_SEC:
                    time.sleep(0.5)
                    if pm.is_pause_screen(cap()):
                        log("  the pause key was being swallowed; fronting "
                            "chiaki cleared it")
                        break
                else:
                    raise ResetError(_diagnose_no_pause(
                        ic, cap, probe=probe, escalated=True, log=log))
            else:
                raise ResetError(_diagnose_no_pause(
                    ic, cap, probe=probe, escalated=escalated, log=log))
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


def _probe_transports(ic, cap, log=print):
    """Measure BOTH input transports against this scene's own idle noise.

    WHY BOTH. Buttons and sticks travel different paths (section 5), and the old
    probe used `press("look_right")`, which is in STICK_AXES and not in
    BUTTON_BITS -- so it exits inside `_inject_press` on the FIFO and never
    touches a key. The pause key is in BUTTON_BITS with INJECT_BUTTONS False, so
    it cannot take that path. The diagnostic therefore measured the FIFO and drew
    a conclusion about the keyboard: "other input IS reaching the game ... the
    'o' key specifically is not landing -- check that the chiaki window has
    keyboard focus." Nothing in the run supported any of that.

    `press_background` is the missing control: it ignores STICK_AXES and posts
    KEYMAP['look_right'] = '=' straight to chiaki's pid over Quartz -- the SAME
    transport the pause key uses, with the same observable (the camera turns)
    and the same undo. It already existed with zero callers.

    WHY A NULL SAMPLE. See PROBE_RATIO. Absolute deltas cannot answer this: the
    old 5.0 gate sits under the 14-20 idle noise this file documents, so it said
    "input is reaching the game" about any in-world frame. Pairing each probe
    against a null taken moments earlier divides that noise out.

    Returns a dict and asserts nothing. Frames are saved as PNG -- never JPEG,
    because re-encoding a frame can change what the compass reads (2026-09-06).
    """
    def _delta(a, b):
        return float(np.abs(_grey(b) - _grey(a)).mean())

    stamp = os.path.join(PROBE_DIR, str(int(time.time() * 1000)))
    try:
        os.makedirs(stamp, exist_ok=True)
    except Exception:
        stamp = None

    def _keep(img, name):
        if not stamp:
            return
        try:
            img.convert("RGB").save(os.path.join(stamp, f"{name}.png"))
        except Exception:
            pass

    # (1) NULL: the same two captures and the same wait, with NO press between
    # them. This is the control, and it must come first so nothing in flight
    # from an earlier press leaks into it.
    a = cap()
    time.sleep(PROBE_GAP_SEC)
    b = cap()
    null = _delta(a, b)
    _keep(b, "null")

    # (2) KEYBOARD, the transport that actually failed.
    kbd_sent = False
    try:
        kbd_sent = bool(ic.press_background("look_right", hold_seconds=0.3,
                                            post_delay=0.4))
    except Exception as exc:
        log(f"  probe: press_background raised {exc!r}")
    time.sleep(PROBE_GAP_SEC)
    c = cap()
    kbd = _delta(b, c)
    _keep(c, "kbd")
    try:
        ic.press_background("look_left", hold_seconds=0.3, post_delay=0.4)
    except Exception:
        pass
    time.sleep(PROBE_GAP_SEC)
    d = cap()

    # (3) FIFO, unchanged from the original probe, so its answer stays
    # comparable with every message this function has ever printed.
    ic.press("look_right", hold_seconds=0.3, post_delay=0.4)
    time.sleep(PROBE_GAP_SEC)
    e = cap()
    fifo = _delta(d, e)
    _keep(e, "fifo")
    ic.press("look_left", hold_seconds=0.3, post_delay=0.4)

    def _verdict(v):
        """alive / dead / ambiguous, against this trial's own null."""
        bar = max(PROBE_FLOOR, null * PROBE_RATIO)
        if v > bar:
            return "alive"
        # <= not <: a transport that moved the picture by exactly this
        # scene's own idle noise moved NOTHING. Strict < left the commonest
        # real case -- a dead transport reading the idle floor -- classified
        # ambiguous, which is a refusal to answer a question the data answers.
        if v <= max(PROBE_FLOOR, null):
            return "dead"
        return "ambiguous"

    return {"null": null, "kbd": kbd, "fifo": fifo, "kbd_sent": kbd_sent,
            "kbd_verdict": _verdict(kbd), "fifo_verdict": _verdict(fifo),
            "frames": stamp}


def _diagnose_no_pause(ic, cap, probe=None, escalated=False, log=print):
    """Say what was MEASURED, and name a cause only when the measurement has one.

    This used to press one stick, compare the result against a threshold below
    the documented noise floor, and then assert that the 'o' key specifically
    was not landing because of keyboard focus -- a claim about a transport it
    never touched. Two hours went into that sentence. It now reports the numbers
    and, when they do not separate, says so instead of guessing.
    """
    p = probe if probe is not None else _probe_transports(ic, cap, log=log)
    where = f"  frames: {p['frames']}" if p.get("frames") else ""
    nums = (f"(null {p['null']:.1f}, keyboard {p['kbd']:.1f}, "
            f"FIFO {p['fifo']:.1f}; a transport counts as alive above "
            f"{max(PROBE_FLOOR, p['null'] * PROBE_RATIO):.1f})")
    tail = f"\n{ic.press_path_summary()}\n{where}".rstrip()
    if escalated:
        tail = ("\n  chiaki was fronted and the crash dialog dismissed, and the "
                "menu still did not open") + tail
    k, f = p["kbd_verdict"], p["fifo_verdict"]

    if k == "alive" and f == "alive":
        return ("the pause menu will not open, and BOTH input transports are "
                f"alive {nums}. The key reached chiaki; the GAME did not open "
                "the book. Look at game state — a 'Give up?' dialog the OCR "
                "missed, a PS5 overlay, or OPTIONS toggling a menu that "
                "animated in late." + tail)
    if k == "dead" and f == "alive":
        return ("the pause menu will not open. The FIFO/stick path is alive but "
                f"the KEYBOARD transport is not {nums}"
                f"{'' if p['kbd_sent'] else ' — and press_background REFUSED to send, so the Quartz path itself is unavailable'}"
                ". Candidates, none of them established here: a modal Qt dialog "
                "holding chiaki's key window, chiaki not being the active app, "
                "a stale pid, or a revoked Accessibility grant." + tail)
    if k == "dead" and f == "dead":
        return ("the pause menu will not open and NEITHER transport moved the "
                f"picture {nums} — the stream or the console is the problem, "
                "not the keys." + tail)
    return ("the pause menu will not open, and the probes CANNOT SAY why "
            f"{nums}: at least one landed between this scene's idle noise and "
            "the bar, so no cause is asserted. Read the frames." + tail)


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
