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

import tempfile as _tf
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


def drive(readable_from, floor=0.0, max_wait=6.0, predicted_bases=None):
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
                                              baseline=object(),
                                              predicted_bases=predicted_bases)
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


# ---- 6. EVERY deal records one machine-readable row ----------------------------------
# THE PREDICTION HAS ONLY EVER BEEN PRINTED. bases_to_travel hands wait_for_hand_deal a
# number of base-movements to animate, the gate printed it, and NOTHING changed a delay --
# the user called this out and was right. No run has ever produced that line, so the
# dataset behind "more animation means a longer wait" is EMPTY, not thin.
#
# The coefficient still cannot be invented (CLAUDE.md 10.4: the archived releases are
# floor-censored, and no [deal] line on disk carries runner state to join against). What
# CAN be done offline is make the pair collectable, and that is what these pin.
def _deal_rows():
    return [o for o in orchestrator._OBSERVATIONS if o.get("event") == "deal_timing"]


orchestrator._OBSERVATIONS.clear()
released, _polls = drive(readable_from=3, max_wait=5.0, predicted_bases=7)
_r = _deal_rows()
check("a released deal records exactly one deal_timing row", len(_r) == 1, str(_r))
if _r:
    check("the row carries the PREDICTION, or there is nothing to regress on",
          _r[0].get("predicted_bases") == 7, str(_r[0]))
    check("...and the FLOOR-FREE settle time, which is the number to fit",
          _r[0].get("settled_at") is not None, str(_r[0]))
    check("...and the floor it was measured against, since the whole distribution "
          "moves when that constant changes",
          _r[0].get("floor") is not None, str(_r[0]))
    check("settled_at is not AFTER the release it precedes",
          _r[0]["settled_at"] <= _r[0]["waited"] + 1e-6, str(_r[0]))

# --- a capture that RAISES must not end the session --------------------------
# _grab_settle_regions and _mean_abs_delta were the only unwrapped calls in the
# poll loop, and the call site at orchestrator.py:7418 has no try -- so a grab
# raising on poll 3 escaped this function, reached run()'s outer finally, and
# STOPPED THE RUN. The timing row went with it, which is the one record that
# would have said why.
_saved = (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
          orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
          orchestrator._fast_grab, orchestrator.POST_PLAY_MIN_WAIT)
orchestrator._OBSERVATIONS.clear()
_n = {"i": 0}


def _dies(names):
    _n["i"] += 1
    if _n["i"] >= 3:
        raise RuntimeError("capture died")
    return {x: object() for x in names}


try:
    orchestrator._grab_settle_regions = _dies
    orchestrator._mean_abs_delta = lambda a, b: 999.0
    orchestrator._hand_signature = lambda img: ("x",)
    orchestrator._fast_grab = lambda: object()
    orchestrator.crop_gameplay_regions = lambda img: [("hand", object())]
    orchestrator.POST_PLAY_MIN_WAIT = 0.0
    _out = orchestrator.wait_for_hand_deal(max_wait=3.0, poll_interval=0.01,
                                           baseline=object())
    check(f"a raising capture reports instead of raising (got {_out})", _out is False)
    _r = _deal_rows()
    check("a raising capture still records its row — the row that explains the "
          "failure is exactly the one that must survive it",
          len(_r) == 1 and _r[0].get("outcome") == "error", str(_r))
except Exception as _e:
    check(f"a raising capture propagated out of the gate ({_e!r}) — at the real call "
          "site there is no try, so this ends the run", False)
finally:
    (orchestrator._grab_settle_regions, orchestrator._mean_abs_delta,
     orchestrator._hand_signature, orchestrator.crop_gameplay_regions,
     orchestrator._fast_grab, orchestrator.POST_PLAY_MIN_WAIT) = _saved
orchestrator._OBSERVATIONS.clear()

# --- the row must carry an X-AXIS, or the dataset is unusable ----------------
# predicted_bases was never passed by production -- the only call site is
# wait_for_hand_deal(baseline=pop_hand_baseline()) -- so every real row would have
# carried None and tools/deal_timing.py would refuse forever. The gate now pulls
# the BOUNDS off the stashed diamond itself, which is the number the moment
# actually supports (the margin that collapses them is not known until the reveal).
orchestrator._OBSERVATIONS.clear()
orchestrator.stash_deal_inputs(
    {"first": {"occupied": True, "speed": 2}, "second": {"occupied": False},
     "third": {"occupied": False}}, batter_speed=3, fielding=0)
released, _polls = drive(readable_from=3, max_wait=5.0)   # NO predicted_bases passed
_r = _deal_rows()
check("one row for one deal", len(_r) == 1, str(_r))
if _r:
    check("the row carries base-movement bounds, so the dataset has an x-axis",
          isinstance(_r[0].get("bases_lo"), int)
          and isinstance(_r[0].get("bases_hi"), int), str(_r[0]))
    check(f"bounds are ordered ({_r[0]['bases_lo']}..{_r[0]['bases_hi']})",
          _r[0]["bases_lo"] <= _r[0]["bases_hi"])
    check("the row carries a play_seq, so a diamond REUSED from a play whose gate "
          "never ran can be told from a fresh one",
          _r[0].get("play_seq") is not None, str(_r[0]))

# ...and a gate that runs with NO stash must not invent bounds.
orchestrator._OBSERVATIONS.clear()
orchestrator.pop_deal_inputs()                     # ensure empty
released, _polls = drive(readable_from=3, max_wait=5.0)
_r = _deal_rows()
check("with no diamond stashed the row says so rather than guessing",
      bool(_r) and _r[0].get("bases_lo") is None and _r[0].get("play_seq") is None,
      str(_r))

# A TIMEOUT MUST RECORD TOO, and this is the check that matters most. The slow turns are
# exactly the ones a bases-loaded home run produces -- the high end of the predictor. A
# dataset that silently drops them is biased precisely where the effect is supposed to
# live, and would read as "no effect" however strong the effect actually was.
orchestrator._OBSERVATIONS.clear()
released, _polls = drive(readable_from=10 ** 9, max_wait=0.3, predicted_bases=10)
_r = _deal_rows()
check("a TIMED-OUT deal records a row too (the slow turns are the informative ones)",
      len(_r) == 1 and _r[0].get("outcome") == "timeout", str(_r))
if _r:
    check("and the timeout row still carries its prediction",
          _r[0].get("predicted_bases") == 10, str(_r[0]))
orchestrator._OBSERVATIONS.clear()

# ---- 7. the dataset sink cannot contaminate the project root -------------------------
# It DID, the hour it was written: test_reveal_peak.py drives this same gate and does not
# redirect BASEBALL_DEAL_LOG, so deal_timing.jsonl appeared beside match_log.jsonl. The
# stamp made those rows removable; the file should not have existed at all. Two rules now,
# and each is checked, because "tests remember to redirect" is the assumption that failed.
_root_default = os.path.join(_ROOT, orchestrator.DEAL_LOG_FILE)
_had = os.path.exists(_root_default)

_saved_env = os.environ.pop("BASEBALL_DEAL_LOG", None)
try:
    check("under test with NO redirect, the sink refuses to name a path",
          orchestrator._deal_log_path() is None,
          repr(orchestrator._deal_log_path()))
    orchestrator.log_deal_timing({"outcome": "probe"})
    check("...and writing produced no file in the project root",
          os.path.exists(_root_default) == _had)

    # ...while an EXPLICIT redirect still writes, or this rule would silently disable the
    # dataset everywhere and read exactly like a working sink (10.1).
    _tmp = _tf.mkstemp(suffix=".jsonl")[1]
    os.environ["BASEBALL_DEAL_LOG"] = _tmp
    check("an explicit redirect is honoured at CALL time, not import time",
          orchestrator._deal_log_path() == _tmp)
    orchestrator.log_deal_timing({"outcome": "probe", "predicted_bases": 4})
    _lines = [l for l in open(_tmp).read().splitlines() if l.strip()]
    check("a redirected row is actually written", len(_lines) == 1, str(_lines))
    if _lines:
        import json as _json
        _row = _json.loads(_lines[0])
        check("and is stamped _synthetic so it can never be mistaken for real data",
              _row.get("_synthetic") is True, str(_row))
        check("and carries the prediction through the sink",
              _row.get("predicted_bases") == 4, str(_row))
    os.unlink(_tmp)
finally:
    if _saved_env is None:
        os.environ.pop("BASEBALL_DEAL_LOG", None)
    else:
        os.environ["BASEBALL_DEAL_LOG"] = _saved_env

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
