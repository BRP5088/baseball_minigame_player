"""The route to the street, found by stepping and looking rather than guessing.

Every leg here was walked one step at a time with the frame inspected after
each, so the landmarks are confirmed rather than inferred. Contrast with the
earlier recorded-demo routes: those were derived from timings and never
survived replay, because they assumed the office door was an obstacle to be
walked around. It is not — it is the WAYPOINT. Walk to it, then turn right,
and the stairwell is in view.

Frame delta after each 0.7s step tells movement from blockage: sustained travel
reads 15-34, jammed reads 0.8-2.0. That signal is reliable for "did I move";
it is NOT reliable for choosing WHICH way to go (walking at a lit lamp scores
60 while covering no ground), so direction comes from the landmark, never from
the delta.
"""

# (absolute bearing, mode, amount, what you should see at the end)
#
# "until_blocked" is the important one. A TIMED leg cannot reproduce a
# position: replaying the west leg for its measured 1.4s left the character
# short of the door, so the turn happened from the wrong spot and the whole
# route diverged. Walking until it JAMS against the door is repeatable —
# being pressed against geometry is a fixed place, and a stopwatch is not.
TO_BAR = [
    (270.0, "until_blocked", 5.0,
     "jammed against the office door, panelled, with a handle"),
    (8.0, "timed", 1.8,
     "out of the building, standing AT the L&B storefront"),
    (285.0, "until_blocked", 7.0,
     "inside the bar: menu board (Brie Shot / Feta Mug), till, barman"),
]

# The last leg ANCHORS AGAINST THE BUILDING rather than aiming at the door.
# A fixed 305 for 2.8s worked once and then failed, because the position on
# the street varies a little each run (the jam point and the north leg both
# have slack) and the entrance is a narrow target. Walking west INTO the
# facade until it jams makes the building itself the reference, so the doorway
# is entered from a repeatable place instead of a guessed heading.

# 1.8s on the north leg stops AT the storefront. 2.8s walks PAST it, on up the
# street toward the BAR sign and the pharmacy, which is where every earlier
# attempt ended up. The entrance faces 305 from that spot and is not visible
# until you stop in the right place and look left.
NORTH_LEG_OVERSHOOTS_AT = 2.8

# Walking past 2.8s on the second leg overshoots L&B and carries on up the
# street — BAR sign, pharmacy, parked cars. Measured at 4.2s.
OVERSHOOT_SEC = 4.2

SPAWN_NOTE = "spawn heading varies 57-91 across resets; read it, never assume"

# --- INSIDE THE BAR: not yet solved -----------------------------------------
# TO_BAR above is verified and reproducible. Getting from the bar to the card
# table is NOT. What is known, all confirmed by looking:
#
#   * the bar interior has a counter, till, bottles, a menu board reading
#     "Brie Shot 2c / Feta Mug 4c / Brie Bottle 15c", a dartboard and a
#     HIGH SCORE sign. Wanda Fuller stands near the entrance and her body
#     COVERS THE COMPASS when you stand close — the bearing reads unreadable
#     and it looks like a lost heading. Step back and it returns.
#   * 123 from just inside leads back OUT to the street (hydrant, manhole).
#   * 185 from the Wanda corner leads to an exterior stone stairwell.
#   * the demo describes a curtained archway into a dining room, then east to
#     the table. The curtains appeared at ~169 in a scan taken from just
#     inside the entrance — that is the lead worth following next, from that
#     exact spot rather than after drifting.
#
# NEXT: replay TO_BAR, do not move, scan 150-200 for the curtains, and take
# the archway from there.
NEXT_LEAD = 169.0

# in_lb_interior remains UNDETECTABLE, now confirmed two ways. Eight brightness
# and texture statistics all overlapped with the detective's own office, and a
# text approach — OCR for the bar's menu board ("Brie Shot", "Feta Mug") and
# its HIGH SCORE sign — read nothing at any threshold, because that lettering
# is small and stylised. at_baseball_table works precisely because the
# interaction prompt is large crisp white text; nothing else in the bar is.
