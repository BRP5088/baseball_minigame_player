"""A LOCAL STATE GAP used to leave no trace: `read_state_for_turn` raised
`ValueError(f"LOCAL STATE GAP: {gap} ...")` and nothing saved the frame the
gap was diagnosed from, so a stalled run's "Couldn't read the screen" print
(orchestrator.py's turn loop) named a gap nobody could look at.

`_save_state_gap` (orchestrator.py, just above `read_state_for_turn`) fixes
that: it writes the frame `local_game_state` already grabbed for this read
(`_LAST_GAP_FRAME`, no second capture) plus a why.json, to STATE_GAP_DIR --
same shape as `_save_dropped_hand`: opt-in under BASEBALL_TEST_RUN, capped
rather than pruned, and never raises into the turn loop.

This drives `_save_state_gap` itself, not a copy of its logic.
"""
import glob
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image

import orchestrator as o

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


# STATE_GAP_DIR anchors on orchestrator's __file__, same footgun DEAL_FRAME_DIR
# documents -- redirect it to a temp root for the whole file and restore in a
# finally, so a failure here can never touch the real diagnostics/.
_real_dir = o.STATE_GAP_DIR
o.STATE_GAP_DIR = tempfile.mkdtemp(prefix="state_gap_test_")
_saved_flag = o.STATE_GAP_FRAMES_IN_TESTS
_saved_cap = o.STATE_GAP_MAX_DIRS

try:
    o._LAST_GAP_FRAME = Image.new("RGB", (40, 20))

    # THE GUARD BLOCKS BY DEFAULT. Without STATE_GAP_FRAMES_IN_TESTS, a save
    # under BASEBALL_TEST_RUN must write nothing -- this is the control that
    # makes every check below mean something.
    before = set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*")))
    result = o._save_state_gap("control gap", turns_this_half=3)
    check(result is None, "CONTROL: under BASEBALL_TEST_RUN, no write without the opt-in")
    check(set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*"))) == before,
          "...and nothing landed on disk either")

    # ...and this test drives the path ON PURPOSE, so it opts in and restores.
    o.STATE_GAP_FRAMES_IN_TESTS = True
    o._OBSERVATIONS.append({"screen": "turn"})
    before = set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*")))
    out = o._save_state_gap("UNRECOGNISED SCREEN -- test", turns_this_half=7)
    new = set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*"))) - before
    check(len(new) == 1, f"a gap writes exactly one dir ({len(new)} written)")
    if new:
        d = new.pop()
        check(out == d, "...and _save_state_gap returns that directory")
        check(os.path.exists(os.path.join(d, "frame.png")), "...with frame.png in it")
        why_path = os.path.join(d, "why.json")
        check(os.path.exists(why_path), "...beside a why.json")
        if os.path.exists(why_path):
            with open(why_path) as fh:
                why = json.load(fh)
            check(why.get("gap") == "UNRECOGNISED SCREEN -- test",
                  "...naming the gap text")
            check(why.get("turns_this_half") == 7, "...and the round")
            check(bool(why.get("t")), "...and the time")
            check("turn" in (why.get("recent_screens") or []),
                  "...and the last few state names")

    # THE CAP HOLDS. One dir already exists from the write above; with the cap
    # set to that same count, the next gap must be refused, and nothing already
    # on disk may be touched (never delete, per the ticket).
    o.STATE_GAP_MAX_DIRS = len(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*")))
    existing_before = set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*")))
    refused = o._save_state_gap("cap test", turns_this_half=1)
    existing_after = set(glob.glob(os.path.join(o.STATE_GAP_DIR, "gap_*")))
    check(refused is None, "the cap refuses a new write once full")
    check(existing_after == existing_before,
          "...without touching anything already on disk")
    o.STATE_GAP_MAX_DIRS = _saved_cap

    # A FAILING SAVE MUST NEVER RAISE INTO THE TURN LOOP. Hand it a frame with
    # no .save() at all and confirm the call still returns cleanly.
    o._LAST_GAP_FRAME = object()
    try:
        result = o._save_state_gap("broken frame", turns_this_half=None)
        check(result is None, "a save that cannot write returns None, not a raise")
    except Exception as exc:
        check(False, f"a failing save must never raise into the turn loop ({exc!r})")

    # A None frame (no gap has been through local_game_state yet) is a no-op too.
    o._LAST_GAP_FRAME = None
    check(o._save_state_gap("no frame yet", turns_this_half=None) is None,
          "no stashed frame is also a no-op, never a raise")
finally:
    o.STATE_GAP_FRAMES_IN_TESTS = _saved_flag
    o.STATE_GAP_MAX_DIRS = _saved_cap
    o._LAST_GAP_FRAME = None
    shutil.rmtree(o.STATE_GAP_DIR, ignore_errors=True)
    o.STATE_GAP_DIR = _real_dir

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("ALL PASSED")
