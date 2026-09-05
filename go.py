"""Drive the character from the office spawn to the Baseball Cards table.

    python3 go.py [n]      run n attempts, report the streak

HOW IT WORKS, and why it is this and not the other twelve things tried
---------------------------------------------------------------------
Reset to the office spawn, then replay the recorded controller input at its
original 50Hz timing. That is all.

The long detour was assuming the game was too nondeterministic for that.
Measured, it is not: three replays of the same macro from the same save ended
within 1.0 degree of each other. What made every earlier attempt fail was
RECONSTRUCTING the walk — decoding a heading per frame, turning to a bearing,
walking forward — which loses the ground the player covered while turning, and
compounds. Sending the player's own inputs back reproduces the walk directly.

Two things had to be true for this to work, and both took a while:

  * The replay must not DRIFT. Every sample is scheduled against one absolute
    start time rather than sleeping between samples; measured, 1 sample in 3192
    arrives late.
  * The recording must start where the reset puts you. The first two recordings
    did not, which is why replaying them from a reset walked into a wall.

BOX/SQUARE IS NEVER PRESSED. It starts a match and spends $50 of in-game money.
Arriving at the prompt is the goal; pressing it is not.
"""

import os
import sys
import time

import aim
import analog_replay as ar
import compass
import jukebox
import walk_steps as ws
import ensure_stream
import inject_reset
import macro_replay
import table_prompt as tp

DEMO = "demos/walk3_full_20260828_050731"
# Stop the macro SHORT of where the recording ended, and let the closed-loop
# nudge cover the last stretch.
#
# The macro's error is roughly symmetric: sometimes it stops a step short of the
# table, sometimes it carries past it to the next table along. Those two are not
# equally fixable. Falling short leaves the dealer in plain view and a few
# forward steps fix it — measured 5/5. Overshooting leaves her behind the
# character and out of frame, where the nudge has nothing to steer by and even a
# full sweep did not reliably re-find her.
#
# So bias deliberately toward the correctable failure.
END_T = 60.5

# Where to stop and re-aim. Chosen just before the final eastward turn to the
# table (which the recording makes around t=57.6), so the last and most
# position-sensitive stretch begins from a corrected heading.
SPLIT_T = 50.0
_HEADINGS = None


def _recorded_heading(t):
    """What the recording's compass read at time t."""
    global _HEADINGS
    if _HEADINGS is None:
        import json
        _HEADINGS = json.load(open("route3_headings.json"))
    near = [h for h in _HEADINGS if abs(h["t"] - t) < 0.6]
    if not near:
        return None
    return min(near, key=lambda h: abs(h["t"] - t))["heading"]


# CORRECT THE HEADING AT EVERY CHECKPOINT, not once at SPLIT_T.
#
# route3_headings.json holds 696 recorded headings across the walk and the route
# used exactly ONE of them. The walk turns constantly — 86.8 -> 269.3 -> 323.7
# -> 4.5 -> 336.9 -> 3.0 -> 44.8 -> 87.0 — so yaw drift compounds across every
# one of those turns with nothing to pull it back, and nothing at all after
# t=50. Measured 2026-09-01: a run ended at heading 124.8 where the recording
# says 87.0, a 38 degree error, and walked somewhere else entirely.
#
# This is a correction, NOT a reconstruction. The walk is still the recorded
# stick input replayed at its own timing — the thing that made every earlier
# attempt work. Only the yaw is nudged back onto the recording's profile at
# each boundary, which is exactly what the single SPLIT_T correction already
# did successfully; there is simply no reason it should happen once.
#
# Spaced ~10s early (drift accumulates slowly) and tightened over the final
# approach, where the recording turns hardest and position matters most.
CHECKPOINTS = (SPLIT_T, 60.5)   # A/B 2026-09-01: single correction, as this morning

# Below this, turning costs more than the error is worth: turn_to has its own
# tolerance and a sub-2-degree correction is inside the compass's own noise.
HEADING_CORRECT_MIN_DEG = 2.0


def _correct_heading(t, log=print):
    """Pull yaw back onto the recording's profile at time t.

    READS THE COMPASS WITH RETRIES, and says so when it cannot. A single
    read_bearing() on a frame captured moments after a walk often returns None
    — the needle is mid-animation — and the first version of this returned
    silently in that case. Measured 2026-09-01: a whole run made ZERO
    corrections across every checkpoint of every attempt and logged nothing at
    all, so a correction step that never ran looked exactly like a correction
    step that had nothing to do. ws.read_heading() retries, which is what the
    turn controller itself uses for the same reason.
    """
    want = _recorded_heading(t)
    if want is None:
        log(f"      t={t:.0f}s no recorded heading for this checkpoint")
        return
    have = ws.read_heading()
    if have is None:
        log(f"      t={t:.0f}s compass unreadable — cannot correct here")
        return
    err = (want - have + 540) % 360 - 180
    if abs(err) > HEADING_CORRECT_MIN_DEG:
        log(f"      t={t:.0f}s heading {have:.1f} vs recorded {want:.1f} "
            f"({err:+.1f}) — correcting")
        # KEEP WHAT THE TURN ACHIEVED, and let turn_to speak. Both were thrown
        # away: the returned heading, and turn_to's own messages — including
        # "no compass reading; cannot turn to an absolute bearing", the line
        # added today precisely so this failure would be visible.
        #
        # Without the residual, "correcting" printed identically whether the
        # camera moved 38 degrees or 0.2. Measured residuals of -5.9, +14.3 and
        # +6.3 against turn_to's 3.5 tolerance are either macro drift during the
        # walk or the turn not landing, and those need opposite fixes.
        got = ws.turn_to(want, log=log)
        if got is None:
            log(f"      t={t:.0f}s turn returned no heading — correction "
                "unverified")
        else:
            log(f"      t={t:.0f}s corrected to {got:.1f} (residual "
                f"{(want - got + 540) % 360 - 180:+.1f})")
    else:
        log(f"      t={t:.0f}s heading {have:.1f} vs recorded {want:.1f} "
            f"({err:+.1f}) — on profile")


def attempt(log=print, shots=None):
    """One attempt. `shots` is a directory to record diagnostics into.

    EVERY attempt is recorded, not just the ones that work. The first run of a
    six-attempt batch missed and there was nothing to look at afterwards,
    because only successes were being saved — which makes the one attempt that
    actually needs explaining the one that leaves no evidence.
    """
    if not ensure_stream.ensure(log=log):
        raise RuntimeError("no stream")
    spawn = inject_reset.reset(log=lambda m: None)
    time.sleep(1.5)
    if shots:
        compass.fast_capture().save(os.path.join(shots, "a_spawn.jpg"), quality=85)

    # SPLIT THE MACRO AND RE-AIM IN THE MIDDLE.
    #
    # Replaying sixty seconds of input in one go lets yaw drift accumulate the
    # whole way, and it shows up exactly where the person who plays this said it
    # does — the reticle sits slightly off the jukebox, and off the dealer by
    # the end. The compass measures yaw exactly, so the drift can simply be
    # removed partway: stop, turn to the heading the recording had at that
    # instant, and carry on. Costs about a second and starts the critical final
    # approach from a known aim rather than an accumulated one.
    mid_h = None
    t_prev = 0.0
    for t_cp in CHECKPOINTS:
        macro_replay.replay(DEMO, t0=t_prev, t1=t_cp, log=lambda m: None)
        t_prev = t_cp
        if t_cp == SPLIT_T:
            mid = compass.fast_capture()
            mid_h = compass.read_bearing(mid)
            if shots:
                mid.save(os.path.join(shots, "b_mid.jpg"), quality=85)
        if t_cp < END_T:
            _correct_heading(t_cp, log=log)

    time.sleep(0.8)
    img = compass.fast_capture()
    if not tp.at_table(img):
        # The macro lands at the table but sometimes a step short and to the
        # left, with the dealer and the cards plainly in view and no prompt.
        # Both failures in a twelve-run batch looked exactly like this, with the
        # end heading within two degrees of a successful run — so it is
        # proximity, not aim, and a few small steps fix it. Bounded tightly:
        # this is a nudge, not a search, and wandering off the spot the macro
        # established is worse than missing.
        # WHICH WAY IS IT WRONG? Nudging forward when the character has already
        # overshot pushes it further past the table. That decision used to be
        # made from the dealer template score and could not be: it reads
        # 0.21-0.31 whether or not she is in frame. _nudge() now concedes on a
        # MEASUREMENT instead — if steps stop moving even after crabbing, it is
        # against geometry, not behind an NPC, and it hands back for the retrace.
        #
        # NUDGE FIRST EITHER WAY, then fall through to _back_off below.
        #
        # This used to branch on `ahead` and log "retracing first" — but inside
        # that else, `ahead < DEALER_AHEAD` is necessarily true, so the ternary
        # always picked _nudge and _back_off was unreachable. The message was
        # describing something the code never did.
        #
        # Collapsed rather than repaired, because the outer `if not at_table`
        # below ALREADY falls back to _back_off, so nudge-then-retrace is the
        # behaviour either way — and the score cannot carry the decision: the
        # dealer template measured 0.21-0.31 across a whole approach on
        # 2026-08-31, under the 0.41 bar even where she was plainly in frame.
        ahead, _, _ = jukebox.find(compass.fast_capture(), DEALER)
        log(f"      not at the table yet (dealer {ahead:.3f}); nudging")
        img = _nudge(shots=shots, log=log)
        if not tp.at_table(img):
            # THE OTHER failure mode: overshooting past the table, ending at the
            # next table along with the dealer behind the character.
            #
            # The obvious fix — sweep for the dealer and walk to her — does not
            # work. Adding thirteen templates from every angle raised the match
            # score everywhere rather than sharpening it: a known success scores
            # 0.439 and a known overshoot 0.378, which is not a margin worth
            # steering on, and each sweep costs eighteen seconds.
            #
            # But the geometry is known without any vision at all. The final
            # approach runs east, so overshooting means too far east, and the
            # correction is simply to walk back the way it came.
            img = _back_off(shots=shots, log=log)
    ar.clear()
    # JUDGE THE RESULT ON A FRAME TAKEN AFTER THE STICKS STOP.
    #
    # `img` above was captured while the walk was still running, so it shows
    # where the character WAS PASSING THROUGH, not where it came to rest.
    # Measured 2026-08-31, twice: c_end.jpg showed the table dead ahead with
    # the "Baseball Cards - Play ($50)" prompt up, the route reported TABLE,
    # and the orchestrator's very first read a second later saw a window with
    # the dealer off at the right edge — same heading, drifted position. Six
    # unrecognized screens and a dead cycle, from a route that "succeeded".
    #
    # ar.clear() only stops NEW input; whatever was in flight still lands. So
    # WAIT FOR THE VIEW TO GO STILL rather than sleeping a guessed duration.
    #
    # A fixed 1.5s was not enough. Measured 2026-08-31 across three cycles:
    # c_end scored a genuine table prompt (correlation +0.32, +0.37 against a
    # 0.15 bar) and the orchestrator's first read moments later found the
    # character jammed against a wall, correlation +0.009. Something keeps
    # moving it after the clear — the listener's own watchdog is 5s
    # (INJECT_TIMEOUT_MS), which is longer than any sleep worth hardcoding.
    #
    # Waiting on stillness covers whatever the cause turns out to be, and
    # returns immediately in the normal case where the clear did land.
    img = _wait_until_still(log=log)
    if shots:
        img.save(os.path.join(shots, "c_end.jpg"), quality=85)
    # NAME WHERE THIS ENDED. places.identify() is offline, costs no API call,
    # and answers the question every failed route raises — "where did it stop?"
    # — which on 2026-09-01 had to be answered by hand, by eye, from saved
    # frames. It abstains rather than guessing, so `None` here means the spot is
    # not one of the labelled rooms, which is itself worth knowing.
    try:
        import places
        room, room_score, room_margin = places.identify(img)
        log(f"      ended in {room or 'an unlabelled place'} "
            f"(score {room_score:.3f}, margin {room_margin:.3f})")
    except Exception as e:
        log(f"      could not identify the end position: {type(e).__name__}: {e}")

    # WHICH GATE REJECTED, not just "ink 0.0000". at_table() has three
    # independent guards — contrast, ink and stroke correlation — and every
    # rejection printed the same line. Measured 2026-09-01 on four failed
    # attempts: two were rejected on CONTRAST (std 3.29, 2.71) and two on INK
    # (std 9.54, 8.67), which are different failures wanting different fixes,
    # and the log could not tell them apart.
    _std = float(tp._raw_patch(img).std())
    _ink, _score = tp.ink(img), tp.score(img)
    if not tp.at_table(img):
        if _std < tp.MIN_CONTRAST:
            why = f"CONTRAST (std {_std:.2f} < {tp.MIN_CONTRAST})"
        elif _ink < tp.INK_MIN:
            why = f"INK ({_ink:.4f} < {tp.INK_MIN})"
        elif _score < tp.MATCH_MIN:
            why = f"SHAPE (score {_score:+.3f} < {tp.MATCH_MIN})"
        else:
            why = "an unknown gate"
        log(f"      not at the table: rejected on {why}")

    return (tp.at_table(img), _ink, _score, img,
            {"spawn": spawn, "mid_heading": mid_h, "std": _std,
             "end_heading": compass.read_bearing(img)})


# MEASURED, not assumed. Taken from the circle recording: across frames where
# the dealer is confidently detected and the heading is known, one full frame
# width spans about 102 degrees. The code previously assumed 70, so every
# centring turn under-corrected by roughly 45% — which is precisely the drift
# the person playing this noticed, the reticle never quite landing on her.
FOV_DEGREES = 102.0
CENTRE_TOL = 0.008
CENTRE_TRIES = 3
NUDGE_STEPS = 12
NUDGE_SEC = 0.16
NUDGE_SPEED = 0.30
# Consecutive steps that move nothing even after crabbing before the
# nudge concedes it is against geometry rather than behind someone.
PINNED_STEPS = 2
# What a crab has to move before it counts as having got us out. Sits between
# the jiggle band (2.5-3.0, measured while wedged) and real movement (16-59
# walking, 34.8 on a genuine escape), so it separates the two without being
# near either.
ESCAPED_CHANGE = 8.0
# How long to let in-flight movement land after ar.clear() before deciding
# whether the route arrived. The injection watchdog is 5s, but a cleared
# stick stops promptly; this only has to outlast the character coasting.
# Long enough to outlast the listener's 5s release watchdog.
STILL_TIMEOUT_SEC = 8.0
# TWO template sets for the same character, because they answer different
# questions. The wide crop includes the table and window and is good at "is she
# somewhere in this frame". Its CENTRE, though, is the middle of that whole
# scene rather than the middle of her, so aiming at it puts the reticle beside
# her — the aim test reported "CENTRED" while the reticle was visibly off. The
# tight crop is her head and torso only, so its centre is the thing to aim at.
DEALER = "test_fixtures/dealer"            # detection: is she in view at all
DEALER_AIM = "test_fixtures/dealer_tight"  # aiming: where exactly is she
WANDA = "test_fixtures/wanda_prompt"
WANDA_SEEN = 0.55
# How many times to try crabbing past Wanda before walking through
# instead. Measured: unbounded, it consumed all twelve nudge steps.
WANDA_GOAROUNDS = 3
# The final approach runs east; the table is at roughly this bearing from the
# point where the macro ends.
TABLE_BEARING = 86.0
# Above this the dealer is genuinely somewhere in front. Measured: a known
# success scores 0.439 against her and a known overshoot 0.378.
DEALER_AHEAD = 0.41


def centre_on(template_dir, tries=CENTRE_TRIES, log=print):
    """Put the reticle on a landmark using the measured camera geometry."""
    """Put the reticle on a landmark by measuring its offset and turning that far.

    Iterates rather than turning once. A single correction is only as good as
    the FOV estimate and the template's idea of where the object's centre is;
    re-measuring after turning converges regardless, and stops as soon as the
    landmark is centred within tolerance.

    Returns the final horizontal offset, or None if the landmark was not seen.
    """
    # SAY WHAT IT DID, both ways. This turned the camera on every nudge step and
    # logged nothing at all — neither when it aimed nor when it declined to —
    # so an aim that never happened and one that landed perfectly produced the
    # same (empty) output. Measured 2026-09-01: the dealer template scores
    # 0.31-0.50, straddling this 0.35 gate, and a route ended facing WEST when
    # it wanted EAST. Whether this function walked the camera round chasing a
    # marginal match was unanswerable from the log.
    last = None
    started = None
    for i in range(tries):
        img = compass.fast_capture()
        score, x, _ = jukebox.find(img, template_dir)
        h = compass.read_bearing(img)
        if started is None:
            started = h
        if score < 0.35 or h is None:
            log(f"      centre_on({os.path.basename(template_dir)}): "
                f"score {score:.3f}{' (< 0.35)' if score < 0.35 else ''}"
                f"{' , no compass' if h is None else ''} — NOT aiming")
            return last
        last = x - 0.5
        if abs(last) <= CENTRE_TOL:
            log(f"      centre_on({os.path.basename(template_dir)}): centred "
                f"(score {score:.3f}, offset {last:+.3f}) after {i} turn(s)")
            return last
        want = (h + aim.angle_for_offset(last)) % 360
        log(f"      centre_on({os.path.basename(template_dir)}): score "
            f"{score:.3f} offset {last:+.3f} — turning {h:.1f} -> {want:.1f} "
            f"({(want - h + 540) % 360 - 180:+.1f} deg)")
        # perspective, not linear — see aim.angle_for_offset
        ws.turn_to(want, log=lambda m: None, tolerance=0.5, max_steps=5)
        time.sleep(0.20)
    if started is not None:
        now = compass.read_bearing(compass.fast_capture())
        if now is not None:
            log(f"      centre_on({os.path.basename(template_dir)}): gave up "
                f"after {tries} tries; camera moved "
                f"{(now - started + 540) % 360 - 180:+.1f} deg overall")
    return last


def _wait_until_still(log=print, timeout=STILL_TIMEOUT_SEC):
    """Block until consecutive frames stop changing, then return the last one.

    Uses ws.STUCK_CHANGE as the bar for "nothing is moving" — the same
    threshold the step loops use, measured from the same runs: walking moves
    the frame 16-59, a stationary character 0.5-2.3.
    """
    import numpy as np
    prev = None
    t0 = time.time()
    while time.time() - t0 < timeout:
        img = compass.fast_capture()
        cur = np.asarray(img.convert("L"), dtype=float)
        if prev is not None:
            if float(np.abs(cur - prev).mean()) < ws.STUCK_CHANGE:
                return img
        prev = cur
        time.sleep(0.4)
    log(f"      still moving {timeout:.0f}s after clear — judging anyway")
    return compass.fast_capture()


def _step_forward(log=print):
    """One nudge-sized step, crabbing free if it did not actually move.

    walk_forward() RETURNS the view change and both step loops used to discard
    it, so a step that walked into an NPC was indistinguishable from one that
    worked — the nudge would spend its whole budget shoving into somebody and
    then report a miss.

    Measured on the blocked run of 2026-08-31: normal walking moves the frame
    16-59, and every sample across the 45 seconds the character spent stuck
    behind an NPC read 0.5-2.3. ws.STUCK_CHANGE is 2.5, which separates those
    without a new constant, and ws.unstick() already knows the remedy: crab
    left, then right, then hard left, sliding along whatever is in the way.

    WHY IT IS GATED ON A COMMANDED STEP, and is not a general "the screen is
    frozen" rule: standing still legitimately looks identical. On that same run
    a real 12-second pause with nothing in the way read 0.8-4.4 — inside the
    stuck band. Judging only the movement of a step we just asked for removes
    that entire class of false positive, and needs no NPC detector at all.
    """
    moved = ws.walk_forward(NUDGE_SPEED, NUDGE_SEC)
    if moved < ws.STUCK_CHANGE:
        log(f"      step moved {moved:.1f} (< {ws.STUCK_CHANGE}) — "
            "something is in the way, crabbing free")
        # Report what the CRAB achieved, not the blocked step. A caller needs
        # to know whether we are still pinned after trying to get free — an
        # NPC steps aside, a wall does not.
        #
        # ...but only count it as FREED if it actually went somewhere.
        # ws.unstick() calls itself successful at ws.STUCK_CHANGE (2.5), which
        # is the bar for "this step was not completely dead" — far too low to
        # mean escaped. Measured 2026-09-01 across a full pinned nudge: every
        # crab landed 2.5-3.0 while normal walking moves the frame 16-59 and a
        # genuine escape measured 34.8. At 2.6 the counter below reset on every
        # step, so the nudge spent all twelve steps twitching against a wall
        # and never reached the retrace that would have fixed it.
        freed = ws.unstick(NUDGE_SPEED, NUDGE_SEC, log=log)
        moved = max(moved, freed if freed >= ESCAPED_CHANGE else 0.0)
    return moved


def _nudge(shots=None, log=print):
    """Aim at the dealer, then close the distance a small step at a time.

    REFUSES WANDA. She wanders, she is a mouse in a dark dress like the dealer,
    and the dealer templates harvested from every angle match her well enough to
    steer at. One run walked straight into her and stopped there. Her PROMPT is
    unambiguous though — "Wanda Fuller [] Talk" — so when it appears the nudge
    backs off and looks elsewhere instead of closing on the wrong character.
    """
    pinned = 0
    wanda_tries = 0
    for i in range(NUDGE_STEPS):
        img = compass.fast_capture()
        if tp.at_table(img):
            return img
        if tp.score_against(img, WANDA) >= WANDA_SEEN:
            # Wanda is standing in the approach. Backing away alone just loses
            # the position — one run reversed into a wall facing nothing. GO
            # AROUND her instead: face the table's bearing, crab sideways past
            # her, and carry on. The table lies east of here, which is known
            # from the route without needing to see it.
            # BOUNDED. Measured 2026-09-01: this fired on all twelve steps of
            # one nudge — detect Wanda, crab past her, `continue`, detect her
            # again — and the attempt ended at ink 0.0163, its closest approach,
            # having spent every remaining step sidestepping on the spot.
            #
            # If the crab has not shaken her after WANDA_GOAROUNDS tries it is
            # not working, and the steps are worth more spent walking: stop
            # treating her as blocking and let the normal nudge run. She is a
            # soft obstacle — the character can walk past her — so the failure
            # mode of ignoring her is far cheaper than burning the budget.
            wanda_tries += 1
            if wanda_tries > WANDA_GOAROUNDS:
                log(f"      Wanda still there after {WANDA_GOAROUNDS} "
                    "go-arounds — ignoring her and nudging through")
            else:
                log(f"      Wanda in the way; going around "
                    f"({wanda_tries}/{WANDA_GOAROUNDS})")
                ws.turn_to(TABLE_BEARING, log=lambda m: None)
                ar.send([f"left_x {ar.to_axis(0.85)}", f"left_y {ar.to_axis(-0.25)}",
                         "right_x 0", "right_y 0"])
                time.sleep(0.75)
                ar.send(["left_x 0", "left_y 0"])
                time.sleep(0.25)
                ws.turn_to(TABLE_BEARING, log=lambda m: None)
                continue
        centre_on(DEALER_AIM, log=log)
        if _step_forward(log) < ws.STUCK_CHANGE:
            # Crabbing did not free us either, so this is not an NPC that will
            # step aside — it is geometry. Pushing forward into it is the WRONG
            # correction: measured 2026-09-01, every failing route ended pinned
            # against the window wall EAST of the table, i.e. having walked
            # past it, and more forward steps only held it there.
            #
            # Give up the nudge and let the caller fall through to _back_off(),
            # which retraces along the approach line. This is the decision the
            # original code tried to make from the dealer template score, and
            # could not: that score reads 0.21-0.31 whether or not she is in
            # frame. "Can I still move forward?" is measurable; "can I see her"
            # is not.
            pinned += 1
            if pinned >= PINNED_STEPS:
                log(f"      pinned after {pinned} steps — overshot, "
                    "handing back to retrace")
                return compass.fast_capture()
        else:
            pinned = 0
        time.sleep(0.22)
    return compass.fast_capture()


TARGET_STREAK = 25


RECOVER_SWEEP = 30.0
RECOVER_IN_VIEW = 0.42
RECOVER_STEPS = 8


BACK_STEPS = 10


def _back_off(shots=None, log=print):
    """Walk back along the approach line, checking the prompt each step."""
    # A SINGLE unreadable compass frame used to abort the whole retrace, in
    # silence, and `h` was never used again afterwards anyway. The compass is
    # measurably unreadable on ~6% of world frames (it fails where the scene is
    # bright, which includes the bar this route ends in), so this threw away
    # the last-ditch recovery on a reading it did not need.
    h = ws.read_heading()
    if h is None:
        log("      retrace: no compass reading — continuing anyway, the "
            "retrace walks backwards and does not need a bearing")
    # MEASURE AND SAY SO, like the nudge does. This used to take all ten steps
    # in silence without ever checking they moved the character — so a retrace
    # that was itself wedged looked identical to one that walked back and found
    # nothing. On 2026-09-01 the nudge correctly conceded "overshot, handing
    # back to retrace" and the retrace then reported nothing whatsoever; there
    # was no way to tell which of the two had happened.
    import numpy as np
    stuck = 0
    for i in range(BACK_STEPS):
        img = compass.fast_capture()
        if tp.at_table(img):
            log(f"      retrace reached the table after {i} step(s)")
            return img
        before = np.asarray(img.convert("L"), dtype=float)
        # reverse: push the stick backwards, camera unchanged, so the character
        # retraces the approach rather than turning around and losing the aim
        ar.send([f"left_y {ar.to_axis(NUDGE_SPEED)}", "left_x 0",
                 "right_x 0", "right_y 0"])
        time.sleep(NUDGE_SEC)
        ar.send(["left_x 0", "left_y 0"])
        time.sleep(0.22)
        after = np.asarray(compass.fast_capture().convert("L"), dtype=float)
        moved = float(np.abs(after - before).mean())
        # ESCAPED_CHANGE, not STUCK_CHANGE — the same leniency that let the
        # nudge twitch away all twelve of its steps. A retrace step is the same
        # size as a nudge step, so when the way is clear it moves the frame
        # 16-59; anything under 8 is scraping, and at the 2.5 bar a scrape of
        # 2.6 reset the counter and bought another nine dead steps. Measured
        # live 2026-09-01: retrace steps of 1.2 / 2.0 / 2.3 with the counter
        # never once reaching 2/2.
        if moved < ESCAPED_CHANGE:
            stuck += 1
            log(f"      retrace step {i} moved {moved:.1f} — going nowhere "
                f"({stuck}/{PINNED_STEPS})")
            if stuck >= PINNED_STEPS:
                log("      retrace is wedged too — stopping rather than "
                    "twitching out the remaining steps")
                break
        else:
            stuck = 0
    return compass.fast_capture()


def _recover(shots=None, log=print):
    """Look around for the dealer's table, then close on it. Bounded."""
    h0 = compass.read_bearing(compass.fast_capture())
    if h0 is None:
        return compass.fast_capture()
    best = (-2.0, None)
    for i in range(int(round(360.0 / RECOVER_SWEEP))):
        target = (h0 + i * RECOVER_SWEEP) % 360
        ws.turn_to(target, log=lambda m: None)
        time.sleep(0.30)
        score, x, _ = jukebox.find(compass.fast_capture(), DEALER)
        if score > best[0]:
            best = (score, target)
    if best[0] < RECOVER_IN_VIEW:
        ws.turn_to(h0, log=lambda m: None)
        return compass.fast_capture()
    ws.turn_to(best[1], log=lambda m: None)
    for i in range(RECOVER_STEPS):
        img = compass.fast_capture()
        if tp.at_table(img):
            return img
        centre_on(DEALER_AIM, log=log)
        _step_forward(log)
        time.sleep(0.22)
    return compass.fast_capture()


def main(n=1, log=print, shot_root="/tmp/go_shots", stop_on_fail=True):
    """Run attempts, HALTING on the first miss unless told otherwise.

    Continuing past a failure wastes time and buries the evidence: by the time a
    batch of thirty finishes, the interesting attempt is twenty runs back and
    the game has been reset over it many times. Stopping keeps the failure fresh
    and its frames on disk, which is the only way the cause gets found.
    """
    streak = best = wins = 0
    for i in range(1, n + 1):
        shots = os.path.join(shot_root, f"attempt{i:02d}")
        os.makedirs(shots, exist_ok=True)
        info = {}
        try:
            # PASS THE LOG THROUGH. This used to be `log=lambda m: None`, which
            # discarded every message from inside the attempt — the heading
            # corrections, the crab-free messages, the pinned-and-retracing
            # decision. Running interactively that is merely quiet; running
            # unattended through run_cycles it is blinding, and it produced a
            # false conclusion on 2026-09-01: "no crabbing messages, so nothing
            # was stuck" was read off a log that could not have contained them.
            #
            # A missed attempt is the one that needs explaining, and this is
            # where its explanation was going.
            ok, ink, sc, img, info = attempt(log=log, shots=shots)
        except Exception as exc:
            log(f"  attempt {i}: FAILED ({exc})")
            ok, ink, sc = False, 0.0, 0.0
        wins += ok
        streak = streak + 1 if ok else 0
        best = max(best, streak)
        sp = info.get("spawn")
        mh = info.get("mid_heading")
        eh = info.get("end_heading")
        fmt = lambda v: "--" if v is None else f"{v:6.1f}"
        if not ok and stop_on_fail:
            log(f"  [{i:2}/{n}] MISSED  ink {ink:.4f}  end {fmt(eh)}  |  "
                f"{wins} ok before this  |  STOPPING for diagnosis "
                f"(frames in {shots})", flush=True)
            return wins, best
        pct = 100.0 * wins / i
        need = "" if best >= TARGET_STREAK else f", need {TARGET_STREAK}"
        log(f"  [{i:2}/{n}] {'TABLE ' if ok else 'missed'}  "
            f"ink {ink:.4f}  end {fmt(eh)}  |  "
            f"{wins} ok / {i - wins} missed ({pct:.0f}%)  |  "
            f"streak {streak}, best {best}{need}", flush=True)
    log(f"\n  {wins}/{n} reached the table ({100.0 * wins / max(n, 1):.0f}%); "
        f"longest streak {best} of {TARGET_STREAK} needed"
        f"{'  -- PASSED' if best >= TARGET_STREAK else ''}", flush=True)
    return wins, best


if __name__ == "__main__":
    os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
