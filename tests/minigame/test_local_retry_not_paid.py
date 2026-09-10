"""A local reader failure must cost a RE-GRAB, not a paid call — and must leave a frame.

MEASURED ON THE FIRST LIVE RUN OF THE READABLE-HAND GATE, and this file exists because
that run went the WRONG WAY: 26 of 31 paid calls were read_game_state and the loop went
from 1.44 reads per turn (the 514-turn baseline) to 5.00.

The mechanism was mine. The all-or-nothing local hand build refused 16 hands; each refusal
raised out of validate_game_state; and the caller's retry is a WHOLE FRESH PAID CALL. So
the retry loop was pointed at the wrong thing — a local re-grab costs ~21 ms, a paid retry
costs a call and several seconds.

AND THE FAILURES WERE INVISIBLE. record_local_hand only fires after the PAID read
succeeds, so every refused frame was captured, rejected and discarded: all 6 frames that
run saved read COMPLETE, while 16 refusals left no trace at all. CLAUDE.md 10.1 — an early
return that writes nothing.
"""
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image                                                   # noqa: E402

import orchestrator                                                     # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


check("a re-grab budget exists and is more than one",
      orchestrator.LOCAL_HAND_REGRABS >= 2, str(orchestrator.LOCAL_HAND_REGRABS))

# ---- 1. A REFUSED FRAME IS KEPT -----------------------------------------------------
tmp = tempfile.mkdtemp(prefix="refused_")
saved_dir = orchestrator.REFUSED_HAND_DIR
try:
    orchestrator.REFUSED_HAND_DIR = tmp
    orchestrator._save_refused_hand(Image.new("RGB", (40, 20), (7, 7, 7)), "slot 1: kind unknown")
    pngs = [f for f in os.listdir(tmp) if f.endswith(".png")]
    check("the refused frame is written to disk", len(pngs) == 1, str(os.listdir(tmp)))
    why = os.path.join(tmp, "why.jsonl")
    check("and WHY it was refused is written beside it", os.path.exists(why))
    if os.path.exists(why):
        row = json.loads(open(why).read().splitlines()[0])
        check("...with the reason, not just a file", row.get("why") == "slot 1: kind unknown",
              str(row))
    # It must never raise into the turn loop, whatever it is handed.
    orchestrator._save_refused_hand(None, "x")
    orchestrator._save_refused_hand(object(), "x")
    check("the recorder swallows its own failures", True)
finally:
    orchestrator.REFUSED_HAND_DIR = saved_dir
    shutil.rmtree(tmp, ignore_errors=True)

# ---- 2. A LOCAL FAILURE RE-GRABS, AND SUCCEEDS WITHOUT A PAID CALL -------------------
def drive(succeed_on):
    """Run _retry_local_hand with local_hand_cards succeeding on the Nth re-grab.
    Returns (state, number of re-grabs made)."""
    calls = {"n": 0}

    def cards(img):
        calls["n"] += 1
        return ({"kind": "player"} if calls["n"] >= succeed_on else None), "slot 1: kind unknown"

    saved = (orchestrator.local_hand_cards, orchestrator.crop_gameplay_regions,
             orchestrator._fast_grab, orchestrator.LOCAL_HAND_REGRAB_SLEEP)
    try:
        orchestrator.local_hand_cards = cards
        orchestrator.crop_gameplay_regions = lambda img: [("hand", object())]
        orchestrator._fast_grab = lambda: object()
        orchestrator.LOCAL_HAND_REGRAB_SLEEP = 0.0
        st = {"hand": [], "_hand_unread": "slot 1: kind unknown"}
        orchestrator._retry_local_hand(st)
        return st, calls["n"]
    finally:
        (orchestrator.local_hand_cards, orchestrator.crop_gameplay_regions,
         orchestrator._fast_grab, orchestrator.LOCAL_HAND_REGRAB_SLEEP) = saved


st, n = drive(succeed_on=2)
check("a hand that reads on the 2nd re-grab is used", st.get("hand"), str(st.get("hand")))
check("...and the unread marker is cleared, so validate does not raise",
      "_hand_unread" not in st, str(sorted(st)))
check("...and it stopped re-grabbing once it succeeded", n == 2, f"{n} re-grabs")

# THE VETO: it must give up rather than spin, and must leave the marker so the paid path
# still takes over. A silent give-up that looked like success would be the same bug again.
st, n = drive(succeed_on=10 ** 9)
check("a hand that never reads leaves the unread marker set",
      st.get("_hand_unread") and not st.get("hand"), str(sorted(st)))
check("...and it re-grabs a BOUNDED number of times",
      n == orchestrator.LOCAL_HAND_REGRABS, f"{n} of {orchestrator.LOCAL_HAND_REGRABS}")

# ---- 3. IT DOES NOTHING WHEN THE PAID MODEL OWNS THE CARDS ---------------------------
saved_flag = orchestrator.PAID_READS_CARDS
try:
    orchestrator.PAID_READS_CARDS = True
    st, n = drive(succeed_on=1)
    check("with PAID_READS_CARDS on, the local retry stays out of the way", n == 0, f"{n}")
finally:
    orchestrator.PAID_READS_CARDS = saved_flag

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
