"""A DISCARD IS A DEAL, and this path never treated it as one.

`wait_for_hand_deal` had exactly ONE live caller -- after a PLAY, inside run() --
so on a discard `reset_deal_frames()` never ran and the replacement card arrived
with nothing watching. That is the gap this guards, and it matters because of
what save_deal_frames' own comment already claims: the frames from while a card
is still IN FLIGHT, "before any neighbour could cover it", are the one record
that can say what an occluded card was.

A discard re-flows the whole fan, so it moves the OCCLUDER as well as the
discarded card. It is therefore the one moment an ALREADY-PRESENT unreadable
slot can become visible -- and it was the one moment unwatched.

THE CONDITION IS THE WHOLE TEST. Watching every discard would be a wait on every
qualifying hand for nothing; watching none is the bug. So the negative case --
a fully-readable hand must NOT wait -- is what makes the positive case mean
anything. Without it this file passes against a version that always waits.

This drives the SHIPPED play_one_turn, not a copy of its condition.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import orchestrator as o

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


def card(idx, power, secondary):
    return {"kind": "player", "name": None, "power": power,
            "secondary": secondary, "hand_index": idx}


def run_turn(hand, discard_ok=True):
    """Run the real play_one_turn. Returns (slot_thrown, times_it_watched).

    `discard_ok=False` makes select_and_discard REFUSE, which is what the live
    guard did on 2026-09-17 when an occluded slot made a lift unmeasurable.
    """
    thrown, watched = [], []
    saved = {n: getattr(o, n) for n in
             ("select_and_discard", "forget_hand_slot", "hand_cursor_look",
              "select_and_play", "record_observation", "_grab_settle_regions",
              "stash_hand_baseline", "capture_diamond_at_play",
              "wait_for_hand_deal")}
    try:
        o.select_and_discard = (lambda idx, **k:
                                (thrown.append(idx), discard_ok)[1] if discard_ok
                                else False)
        o.forget_hand_slot = lambda *a, **k: None
        o.hand_cursor_look = lambda *a, **k: None
        o.select_and_play = lambda *a, **k: True
        o.record_observation = lambda **k: None
        o._grab_settle_regions = lambda *a, **k: {"hand": None}
        o.stash_hand_baseline = lambda *a, **k: None
        o.capture_diamond_at_play = lambda *a, **k: None
        o.wait_for_hand_deal = lambda *a, **k: watched.append(1) or True
        o.play_one_turn({"hand": hand, "phase": "batting", "your_score": 0,
                         "opp_score": 0, "discards_left": 2, "runners": [],
                         "batters_used": None}, 0)
    finally:
        for n, v in saved.items():
            setattr(o, n, v)
    return (thrown[0] if thrown else None), len(watched)


# Every card weak, so should_redraw fires and the discard branch is reached.
# SLOT 1 IS ABSENT -- exactly what local_hand_cards does when a disc is occluded:
# it drops the card and keeps hand_index on the survivors.
blind_slot, blind_watch = run_turn([card(0, 4, 3), card(2, 4, 3),
                                    card(3, 4, 1), card(4, 5, 2)])
check(blind_slot is not None,
      f"a weak hand with slot 1 missing still discards (threw slot {blind_slot})")
check(blind_watch == 1,
      f"and it WATCHES the redeal ({blind_watch} call(s)) -- the one moment the "
      "occluded slot can be seen")

# THE NEGATIVE CASE, and it is what gives the positive one meaning. All five slots
# read, so there is nothing to learn from the redeal and nothing should be paid.
full_slot, full_watch = run_turn([card(0, 4, 3), card(1, 4, 1), card(2, 4, 3),
                                  card(3, 5, 2), card(4, 4, 2)])
check(full_slot is not None,
      f"a fully-readable weak hand also discards (threw slot {full_slot})")
check(full_watch == 0,
      f"but does NOT wait ({full_watch} call(s)) -- a healthy hand pays nothing, "
      "which is what stops this being a wait on every qualifying hand")

# A REFUSED DISCARD MUST NOT BE WATCHED. Nothing was thrown, so there is no deal --
# and watching one anyway appends a row to deal_timing.jsonl saying a deal took 20s
# and barely moved. That is a two-row dataset meant to be FITTED, and the row cannot
# be told apart from a genuinely slow deal. Observed live on this code's first run.
refused_slot, refused_watch = run_turn([card(0, 4, 3), card(2, 4, 3),
                                        card(3, 4, 1), card(4, 5, 2)],
                                       discard_ok=False)
check(refused_watch == 0,
      f"a REFUSED discard with a blind slot does NOT watch ({refused_watch} call(s)) "
      "-- no deal happened, so a timing row would be a phantom")

# CONTROL. Without this both checks above pass against a play_one_turn that never
# reaches the discard branch at all.
strong_slot, strong_watch = run_turn([card(0, 9, 2), card(2, 8, 1)])
check(strong_slot is None and strong_watch == 0,
      f"CONTROL: a STRONG hand neither discards nor waits (slot {strong_slot}, "
      f"{strong_watch} wait(s)) -- so the rows above read real discards")

# AND THE FRAME THE CALL WAS MADE ON IS KEPT. Separate directory from
# _save_refused_hand on purpose: that corpus is hands refused OUTRIGHT, has a
# contact-sheet tool and a test reading it, and a partially-read hand is a
# different population.
import glob
import tempfile
from PIL import Image

# THE GUARD BLOCKS BY DEFAULT, and this is the control: without it the check
# below would pass just as well with the guard missing entirely.
_b0 = set(glob.glob(os.path.join(o.DEAL_FRAME_DIR, "dropped_*")))
o._save_dropped_hand(Image.new("RGB", (40, 20)), "guard control", [1])
check(set(glob.glob(os.path.join(o.DEAL_FRAME_DIR, "dropped_*"))) == _b0,
      "CONTROL: under BASEBALL_TEST_RUN the frame is NOT written without the opt-in")

# ...and this test drives that path ON PURPOSE, so it opts in and restores.
before = set(glob.glob(os.path.join(o.DEAL_FRAME_DIR, "dropped_*")))
_saved_flag = o.DEAL_FRAMES_IN_TESTS
o.DEAL_FRAMES_IN_TESTS = True
try:
    o._save_dropped_hand(Image.new("RGB", (40, 20)), "test: slots [1] unreadable", [1])
finally:
    o.DEAL_FRAMES_IN_TESTS = _saved_flag
after = set(glob.glob(os.path.join(o.DEAL_FRAME_DIR, "dropped_*")))
new = after - before
check(len(new) == 1, f"_save_dropped_hand keeps the frame ({len(new)} dir written)")
if new:
    d = new.pop()
    check(os.path.exists(os.path.join(d, "hand.png")),
          "...and the frame itself is in it")
    check(os.path.exists(os.path.join(d, "why.json")),
          "...beside a why.json naming the dropped slots")
    import shutil
    shutil.rmtree(d, ignore_errors=True)

check(o._save_dropped_hand(None, "none", []) is None,
      "a None image is a no-op, never a raise into the turn loop")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
