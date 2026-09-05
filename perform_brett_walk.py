#!/usr/bin/env python3
"""Write the walk here. Everything else is handled.

    .venv/bin/python perform_brett_walk.py

Every command and frame is recorded to world_log/<stamp>_brett/, so the walk
becomes something map_build.py can turn into graph legs. The path the bot
follows today came from a recording made from a DIFFERENT starting pose, which
is the reason the last two legs miss — a walk recorded from where the bot
actually stands is the fix.

WHAT YOU CAN CALL
=================
On a real controller: LEFT STICK moves the player, RIGHT STICK moves the
camera. Same split here.

MOVES THE PLAYER  (left stick)
    w.forward(2.0)     walk, in seconds
    w.back(0.5)
    w.right(0.4)       strafe sideways — does NOT turn
    w.left(0.4)

MOVES THE CAMERA  (right stick) — the player stays where it is
    w.turn(270)        closed loop: reads the compass and lands ON 270.
                       0=N 90=E 180=S 270=W. Errors do not accumulate.
    w.camera(0.4, x=0.5)
                       raw: hold the stick at magnitude x for 0.4s.
                       No compass. x: +right -left   y: +down -up
                       Magnitude is 0..1 (above that it clamps to full stick).

    Which one? turn() when you know WHERE you want to face — it is drift-free.
    camera() when you just want to nudge the view, or to look up/down, which
    turn() cannot do.

    Measured cost of raw: two identical camera(1.0, x=1.0) calls turned
    +208.6 and +201.0 degrees. 7.7 degrees apart, same command.

MOVES NEITHER
    w.press("box")     any button: cross moon box pyramid dpad_up ...
    w.jump()           cross (this DOES move the player — upward)
    w.wait(1.0)        stand still (an NPC in the way)
    w.look()           print where we are
    w.mark("bar_jukebox")
                       "this spot is <place>" — saves the frame as a reference
                       the localiser can recognise later. The one thing only
                       you can do, because you can see the screen.

THE THING THAT TRIPS EVERYONE UP
    forward() is CAMERA-RELATIVE. The player walks whichever way the camera
    faces, so turning the camera is how you choose the direction of the next
    forward(). That is why every route here is written turn-then-walk.

Bearings on the current route, for reference:
    portrait_room -> 287 (the corner)  ->  2 (the jukebox)  ->  90 (the table)
"""

import sys

from brett_walk import walk


def moves(w):
    # ------------------------------------------------------------------
    # EDIT FROM HERE. This is the current last-mile guess, which arrives
    # about 1 time in 6 — change the numbers and see what happens.
    # ------------------------------------------------------------------

    import analog_replay as ar

    ar.send([f"right_y {ar.to_axis(0.0)}",
            f"right_x {ar.to_axis(1.0)}",
            "left_x 0", "left_y 0"])
    import time
    time.sleep(1.0)
    # ar.send(["right_x 0", "right_y 0"])

    ar.clear()


    # w.turn(287)
    # w.forward(2.0)
    # w.look()

    # w.turn(2)
    # w.forward(3.3)
    # w.look()

    # w.turn(90)
    # w.forward(4.1)
    # w.look()

    # ------------------------------------------------------------------
    # TO HERE.
    # ------------------------------------------------------------------


    # w.stick(1.0, y=1.0)
    # w.camera(seconds=1.0, x=10.0, y=0.0)
    # w.look()


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "brett"
    with walk(name) as w:
        try:
            moves(w)
        except KeyboardInterrupt:
            print("\nstopped by hand")
