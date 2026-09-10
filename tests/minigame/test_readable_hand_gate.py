"""The deal gate releases on a HAND THAT READS, not on a delta edge.

WHAT IT REPLACES. The old rule returned on the first poll where the hand had STARTED
changing and a hand-picked 6-second floor had passed -- motion having begun, not motion
having ended, which is how a mid-deal screenshot gets taken. Measured over 514 recorded
turns: the first read of a turn lands a median 11.96 s after the play, while on turns that
need a retry the read that finally WORKS lands at 17.59 s. Nothing differs between those
two except that the deal finished in between, so a quarter of all turns were spending a
paid API call to wait.

WHY NOT "WAIT FOR QUIET". Measured and refused. A SETTLED HAND reads a frame-to-frame
delta of ~4.6 while an EMPTY TABLE reads ~2.5 -- the empty table is QUIETER than the hand.
So quiet cannot separate "the cards have landed" from "there are no cards", which is the
mistake being fixed, and no threshold on that quantity works (CLAUDE.md 10.4).

Asking the reader instead invents no constant at all.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import orchestrator                                                     # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


check("the gate is on", orchestrator.USE_READABLE_HAND_GATE is True)
# Pinned as a literal: comparing against the constant it guards passes forever (10.11).
check("it needs TWO clean reads, not one", orchestrator.READABLE_POLLS == 2,
      str(orchestrator.READABLE_POLLS))


def drive(readable_from, floor=0.0, max_wait=6.0):
    """Run the real gate with everything around it stubbed. `readable_from` is the poll
    index at which local_hand_cards starts returning a hand. Returns (released, polls)."""
    calls = {"n": 0}

    def fake_grab_settle(names):
        calls["n"] += 1
        return {n: object() for n in names}

    def fake_delta(a, b):
        return 999.0                       # the edge is always seen, so only the new rule decides

    def fake_sig(img):
        # THE GATE NOW ASKS FOR A SIGNATURE, not for a complete hand: it releases when the
        # hand STOPS CHANGING. Requiring completeness cost 280 SECONDS of timeouts over one
        # 46-play run, and the hand memory makes an incomplete hand usable anyway.
        # Before `readable_from` the signature changes every poll; after it, it is steady.
        return ("steady",) if calls["n"] >= readable_from else ("moving", calls["n"])

    saved = (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
             orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
             orchestrator._fast_grab, orchestrator.POST_PLAY_MIN_WAIT)
    try:
        orchestrator._grab_settle_regions = fake_grab_settle
        orchestrator._mean_abs_delta = fake_delta
        orchestrator._hand_signature = fake_sig
        orchestrator._fast_grab = lambda: object()
        orchestrator.crop_gameplay_regions = lambda img: [("hand", object())]
        orchestrator.POST_PLAY_MIN_WAIT = floor
        out = orchestrator.wait_for_hand_deal(max_wait=max_wait, poll_interval=0.01,
                                              baseline=object())
        return out, calls["n"]
    finally:
        (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
         orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
         orchestrator._fast_grab, orchestrator.POST_PLAY_MIN_WAIT) = saved


# ---- 1. it does NOT release while the hand is unreadable -----------------------------
# This is the whole point: the old gate released here, on the edge alone.
released, polls = drive(readable_from=10 ** 9, max_wait=0.5)
check("an unreadable hand never releases the gate", released is False, f"{polls} polls")

# ---- 2. it releases once the hand reads, and NOT on the first clean poll -------------
released, polls = drive(readable_from=3, max_wait=5.0)
check("a readable hand releases it", released is True, f"after {polls} polls")
check("and not until it has read clean TWICE",
      polls >= 4, f"released on poll {polls}, first clean was poll 3")

# ---- 3. ONE clean frame in the middle of an animation must not release it ------------
# A frame caught mid-deal can still parse; that is exactly what READABLE_POLLS = 2 is for.
state = {"n": 0}


def flicker(img):
    state["n"] += 1
    return ({"x": 1} if state["n"] == 2 else None), None


saved = (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
         orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
         orchestrator._fast_grab, orchestrator.POST_PLAY_MIN_WAIT)
try:
    orchestrator._grab_settle_regions = lambda names: {n: object() for n in names}
    orchestrator._mean_abs_delta = lambda a, b: 999.0
    _n = {"i": 0}
    def flicker_sig(img):
        _n["i"] += 1
        return ("steady",) if _n["i"] in (2, 3) else ("moving", _n["i"])
    orchestrator._hand_signature = flicker_sig
    orchestrator._fast_grab = lambda: object()
    orchestrator.crop_gameplay_regions = lambda img: [("hand", object())]
    orchestrator.POST_PLAY_MIN_WAIT = 0.0
    out = orchestrator.wait_for_hand_deal(max_wait=0.6, poll_interval=0.01,
                                          baseline=object())
finally:
    (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
     orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
     orchestrator._fast_grab, orchestrator.POST_PLAY_MIN_WAIT) = saved
check("a single clean frame mid-animation does NOT release it", out is False, str(out))

# ---- 3b. TWO clean frames that are NOT CONSECUTIVE must not release it either -------
# The streak has to RESET on an unreadable poll. Without this case a mutant that only ever
# increments `good` passes the whole file, because every other case here has at most one
# clean frame -- so "clean twice" and "clean twice IN A ROW" are indistinguishable.
state2 = {"n": 0}


def spaced(img):
    state2["n"] += 1
    return ({"x": 1} if state2["n"] in (2, 6) else None), None


saved = (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
         orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
         orchestrator._fast_grab, orchestrator.POST_PLAY_MIN_WAIT)
try:
    orchestrator._grab_settle_regions = lambda names: {n: object() for n in names}
    orchestrator._mean_abs_delta = lambda a, b: 999.0
    _m = {"i": 0}
    def spaced_sig(img):
        _m["i"] += 1
        return ("steady",) if _m["i"] in (2, 6) else ("moving", _m["i"])
    orchestrator._hand_signature = spaced_sig
    orchestrator._fast_grab = lambda: object()
    orchestrator.crop_gameplay_regions = lambda img: [("hand", object())]
    orchestrator.POST_PLAY_MIN_WAIT = 0.0
    out = orchestrator.wait_for_hand_deal(max_wait=0.25, poll_interval=0.01,
                                          baseline=object())
finally:
    (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
     orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
     orchestrator._fast_grab, orchestrator.POST_PLAY_MIN_WAIT) = saved
check("two clean frames with a bad one between them do NOT release it",
      out is False, f"{out} (clean on polls 2 and 6, unreadable between)")

# ---- 4. it must never raise into the turn loop --------------------------------------
saved = (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
         orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
         orchestrator._fast_grab, orchestrator.POST_PLAY_MIN_WAIT)
try:
    orchestrator._grab_settle_regions = lambda names: {n: object() for n in names}
    orchestrator._mean_abs_delta = lambda a, b: 999.0
    def boom(img):
        raise RuntimeError("reader exploded")
    orchestrator._hand_signature = boom
    orchestrator._fast_grab = lambda: object()
    orchestrator.crop_gameplay_regions = lambda img: [("hand", object())]
    orchestrator.POST_PLAY_MIN_WAIT = 0.0
    out = orchestrator.wait_for_hand_deal(max_wait=0.3, poll_interval=0.01,
                                          baseline=object())
    check("a reader that raises does not take the turn loop with it", out is False)
except Exception as exc:
    check("a reader that raises does not take the turn loop with it", False, repr(exc))
finally:
    (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
     orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
     orchestrator._fast_grab, orchestrator.POST_PLAY_MIN_WAIT) = saved

# ---- 5. THE OLD BEHAVIOUR IS STILL THERE, and the flag really switches it ------------
orchestrator.USE_READABLE_HAND_GATE = False
try:
    released, polls = drive(readable_from=10 ** 9, max_wait=0.5)
    check("with the flag off, the edge alone releases it again (nothing was ripped out)",
          released is True, f"{polls} polls")
finally:
    orchestrator.USE_READABLE_HAND_GATE = True

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
