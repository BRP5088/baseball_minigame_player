#!/usr/bin/env python3
"""Keep the PS5 awake with periodic, self-cancelling input.

    .venv/bin/python keep_awake.py &          # run alongside a session

WHY. The console sleeps when no input reaches it, and that has now cost two
runs: the 2026-09-01 overnight run four minutes in, and the 2026-09-03
leg-tolerance CONFIRMATION run, where every trial recorded depth 1 because the
picture had frozen — the harness read "cannot see" as "did not arrive". The
user has asked NOT to change the console's power setting, so the fix is to keep
giving it something to notice.

TWO THINGS THIS HAS TO GET RIGHT, and both are why it is not a one-liner:

1. IT MUST NOT MOVE THE CHARACTER. It nudges the CAMERA (right stick) and
   nothing else, then nudges back by the same amount, so the net heading change
   is ~0. The left stick is never touched, so position cannot drift.

   "~0" is bounded, not exact. The two halves are equal in stick-seconds, but
   the achieved rotations differ by the frame quantum (turn error here is an
   integer number of GAME FRAMES: 22.5 deg/s x 17.2ms = 0.39 deg) plus the few
   percent of run-to-run spread turn_curve measured. So each nudge can leave a
   fraction of a degree behind, and an idle night of them random-walks. The
   accumulated residual is NOT measured and no bound here is a measurement.
   What makes it tolerable is structural, not numerical: the gate below means
   this never runs during a walked leg, and every harness on this project
   begins a trial with a reset, whose spawn bearing has measured 86.9/87/87.
   A caller that walks from wherever the camera happens to be pointing, without
   a reset first, is outside that argument and must not assume it.

2. IT MUST NOT PERTURB A MEASUREMENT. A stray camera nudge in the middle of a
   walked leg would corrupt exactly the experiments this exists to protect. So
   it SKIPS its turn whenever another project script is running, and only pokes
   the console while the rig is genuinely idle.
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import turn_curve      # pure table, no console contact, safe to import here

# PS5 idle-sleep is minutes, not seconds; poking every 4 minutes is frequent
# enough with margin and rare enough to be invisible.
INTERVAL_SEC = 240.0

# HOW BIG THE NUDGE IS, AND WHY THESE TWO NUMBERS ARE NOT FREE CHOICES.
#
# They were 0.35 and 90ms, commented "above turn_curve.DEAD_BELOW (0.35) so it
# registers" and "~7 degrees at this magnitude". BOTH CLAIMS WERE FALSE, and
# false in the direction that hides a dead module:
#
#     0.35 > DEAD_BELOW (0.35)      is False — it sits ON the boundary
#     turn_curve.rate_for(0.35)     = 4.55 deg/s
#     4.55 deg/s x 0.090s           = 0.41 DEGREES, not ~7. Out by 17x.
#
# Seven degrees in 90ms needs 77.8 deg/s, i.e. magnitude ~0.90 — the top of the
# usable band. So the code asked for the smallest deflection the curve calls
# dead, held for the shortest time, while the comment described something
# seventeen times larger. That is the catalogue's #1 shape in a module whose
# whole job is to prevent a failure that has already invalidated a measurement.
#
# THE HOLD LENGTH IS PICKED TO MATCH THE MEASUREMENT, not the other way round.
# Every entry in turn_curve.MEASURED is an AVERAGE RATE OVER A 0.30s HOLD, so
# `rate x duration` is a READING at 0.30s and an EXTRAPOLATION at any other
# length — the shorter the hold, the more the acceleration transient dominates
# it. Holding for exactly 0.30s is therefore the one duration where this
# arithmetic is not a guess:
#
#     rate_for(0.60) = 22.5 deg/s   x 0.300s = 6.75 deg
#
# 0.60 clears DEAD_BELOW (0.35) with room, and stays well under USABLE_MAX
# (0.90) where turn_curve measured repeatability starting to fall apart. It is
# also what plan_turn would prefer on its own: a moderate stick held longer
# beats a hard stick held briefly, because the curve is flatter there.
NUDGE_MAG = 0.60
NUDGE_MS = 300

# Derived, never hand-written. The defect being fixed here was a hand-written
# number drifting away from the curve it claimed to come from; computing it
# means that cannot recur silently, and the log line below prints it, so the
# module states what it actually did instead of only that it did something.
NUDGE_DEG = turn_curve.rate_for(NUDGE_MAG) * (NUDGE_MS / 1000.0)

# WHAT IS STILL UNVERIFIED — READ THIS BEFORE TRUSTING THIS MODULE.
#
# NOTHING ABOVE ESTABLISHES THAT THE CONSOLE COUNTS THIS AS ACTIVITY. That is a
# property of the PS5's own idle timer. It cannot be measured offline and it has
# never been measured live, at 0.35 or at 0.60. The size of the nudge was fixed
# because the comment was wrong, NOT because 6.75 deg was shown to be enough.
#
# The most likely mechanism argues magnitude is irrelevant: chiaki's feedback
# sender deduplicates unchanged controller states, so ANY change emits an edge
# packet regardless of how big it is, and the console is probably counting
# packets rather than degrees. If that is right, 0.35 would have worked too.
# It is a hypothesis. It is not a measurement, and it must not be written up as
# one.
#
# What the change buys independent of that question: 0.41 deg is
# indistinguishable from the module doing nothing at all, so the old constants
# were UNFALSIFIABLE BY OBSERVATION. 6.75 deg moves the compass, which is what
# makes the live test below possible at all.
#
# THE LIVE TEST (~45 min, one person, no in-game money):
#   1. Wake the PS5, bring the stream up, leave the character standing still in
#      the world with nothing else driving the console.
#   2. Run this module alone and confirm the nudge ARRIVES: compass.read_bearing
#      beside the log line should show a ~6.8 deg swing and a return at each
#      poke. If it does not, the nudge is not reaching the game and no amount of
#      idle-timer reasoning matters.
#   3. Leave it for 40+ minutes — well past the timeout that killed the
#      2026-09-01 run four minutes in — and confirm the picture is still live
#      (a dead picture measures a frame delta of 0.00).
#   4. THE ARM THAT MAKES IT A TEST RATHER THAN A DEMO: repeat step 3 with
#      keep_awake NOT running, and confirm the console DOES sleep. Without that
#      control, a console that was never going to sleep looks exactly like a
#      working nudge — and on this project only an interventional comparison has
#      ever counted.

# Anything here means a real run owns the console; keep_awake stands down.
BUSY_PATTERNS = ("ab_leg_tolerance", "phase1_", "run_cycles", "go.py",
                 "Bretts_walk", "perform_brett_walk", "orchestrator")


def something_else_is_running():
    """True if another project script is driving the console."""
    try:
        out = subprocess.run(["pgrep", "-fl", "python"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        return True                    # cannot tell -> assume busy, stay quiet
    mine = str(os.getpid())
    for line in out.splitlines():
        if line.startswith(mine + " "):
            continue
        if any(p in line for p in BUSY_PATTERNS):
            return True
    return False


def nudge(log=print):
    """One self-cancelling camera movement. Returns True if it was sent.

    SELF-UNDOING IS THE WHOLE SAFETY ARGUMENT, so the reverse is in a `finally`
    rather than on the happy path. This fires unattended, every four minutes,
    for as long as a session lasts; a nudge that goes out and never comes back
    leaves the camera rotated by NUDGE_DEG, and a camera quietly off-heading
    corrupts exactly the runs this module exists to protect.

    It reverses only what actually went out. If the OUTWARD send itself raises
    — a missing FIFO, a dead chiaki — nothing was applied, and "undoing" it
    would rotate the camera NUDGE_DEG the OTHER way, turning a failed poke into
    a real disturbance. Hence the flag rather than a bare `finally`.

    The holds are TIMED (the third field), so chiaki releases the stick on its
    own steady_clock even if this process is killed between the two halves.
    That bounds the damage of a hard kill at one nudge of rotation instead of a
    stick stuck at deflection until the 5s inject watchdog.
    """
    if os.environ.get("BASEBALL_TEST_RUN"):
        return False
    import analog_replay as ar

    out = f"right_x {ar.to_axis(NUDGE_MAG)} {NUDGE_MS}"
    back = f"right_x {ar.to_axis(-NUDGE_MAG)} {NUDGE_MS}"
    centre_y = f"right_y 0 {NUDGE_MS}"      # pin the vertical: never look up
    settle = NUDGE_MS / 1000.0 + 0.25
    applied = False
    try:
        ar.send([out, centre_y])
        applied = True
        time.sleep(settle)
    finally:
        try:
            if applied:
                ar.send([back, centre_y])
                time.sleep(settle)
        finally:
            ar.send(["clear"])
    return True


def main(interval=INTERVAL_SEC, log=print):
    log(f"keep_awake: poking every {interval:.0f}s while the rig is idle")
    while True:
        if something_else_is_running():
            log("  a run owns the console — standing down this cycle")
        else:
            try:
                nudge(log=log)
                # Say the SIZE, not just that it happened. "nudged at 04:12:01"
                # reads identically whether the camera moved 6.8 degrees or
                # 0.41, which is how the old constants stayed wrong.
                log(f"  nudged +/-{NUDGE_DEG:.2f} deg (mag {NUDGE_MAG}, "
                    f"{NUDGE_MS}ms) at {time.strftime('%H:%M:%S')}")
            except Exception as e:
                log(f"  nudge failed ({type(e).__name__}: {e})")
        time.sleep(interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("keep_awake: stopped")
