"""Open-loop walk: a fixed list of key presses, replayed from a fixed save.

WHY THIS INSTEAD OF CLOSED-LOOP CONTROL
---------------------------------------
Reading the on-screen compass costs ~9s live and ~79s on a saved frame, so a
control loop that consults it every iteration turns a 7-second walk into an
8-minute one — and it still failed, because the bearing is occasionally a
misread and the turn actuator's gain shifts with display mode.

But the save reload is deterministic: the same spawn position and the same
spawn bearing (measured 87-91 degrees over many resets, identical to the
degree). If the world starts identical and the inputs are identical, the
outcome is identical. No sensing required in the path at all.

Sensing then moves to where it belongs: ONE check at the end to confirm we
arrived, rather than a measurement before every press.
"""
import time

STEP = tuple           # (action, hold_seconds, pause_after)


def run(seq, press, log=None):
    """Execute a sequence of (action, hold_seconds, pause_after) steps."""
    for i, (action, hold, pause) in enumerate(seq, 1):
        press(action, hold_seconds=hold, post_delay=0.0)
        if log:
            log(f"    {i:2}. {action} hold={hold:.2f} pause={pause:.2f}")
        if pause:
            time.sleep(pause)


# Derived from the demonstrated route. Turn amounts are open-loop, so they are
# expressed in HOLD SECONDS rather than degrees; they get tuned against where
# the walk actually ends up, not against a compass reading.
CANDIDATE = [
    ("look_left",  0.80, 0.6),    # spawn ~89 -> face down the hallway (~270)
    ("walk_up",    1.60, 0.4),
    ("look_right", 0.40, 0.6),    # -> face the stairs (~5)
    ("walk_up",    3.30, 0.4),
    ("walk_up",    1.80, 0.4),    # through the L&B door, past the bar
    ("look_right", 0.35, 0.6),    # -> face the card table (~85)
]
