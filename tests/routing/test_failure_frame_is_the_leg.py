"""A failure must be classified from the LEG'S frame, on every run.

Three defects, all found 2026-09-05, all of the same family — the output looked
like evidence and was not:

1. follow_verified classified `before`, a frame captured at the TOP of its own
   loop. That is the PREVIOUS node's successful arrival. Four frames saved that
   way on 2026-09-04 all identified as bar_pool_room at 506-734 matches while
   claiming to show the jukebox leg, so `failures_by_kind` was a re-encoding of
   WHICH node failed rather than why.

2. The classification sat inside `if shots:`. measure_streak.py calls
   consecutive_arrivals with no shots, so on the runs that actually score the
   25-consecutive requirement the census was silently EMPTY — while still being
   reported.

3. follow() saved the leg-end frame as a FIXED name, `at_<node>.jpg`. Every
   attempt and every trial overwrote it, so a 10-trial A/B finished holding one
   frame per node and the failures it was collected to explain had been
   overwritten by later successes.
"""

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import re
import graph_walk as gw
import failure_kind as fk

fails = []


def check(cond, msg):
    print(f"{'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        fails.append(msg)


# --- source-level: the shapes that made these invisible must not return ----
src = open(_os.path.join(_ROOT, "graph_walk.py"), encoding="utf-8").read()

check('f"at_{b}.jpg"' not in src,
      "follow() no longer saves the leg-end frame under a fixed name")
check(re.search(r'at_\{b\}_\{int\(time\.time\(\) \* 1000\)\}\.jpg', src) is not None,
      "follow()'s leg-end filename carries a timestamp")
check("_LAST_LEG_END[b] = img" in src,
      "follow() publishes the leg-end frame before recovery runs")
check("img = before if before is not None else capture()" not in src,
      "follow_verified no longer classifies `before` (the previous node)")

# --- behavioural: which image actually reaches classify() -----------------
class Frame:
    """Stands in for a PIL image. Identity is the whole point of the test."""
    def __init__(self, tag):
        self.tag = tag

    def convert(self, _mode):
        return self

    def save(self, *a, **k):
        pass


saved = {}
orig_classify = fk.classify
orig_gtnv = gw.go_to_node_verified
orig_live = gw.stream_is_live


def fake_classify(img, node, route, live=True):
    saved["tag"] = getattr(img, "tag", None)
    saved["calls"] = saved.get("calls", 0) + 1
    return "WEDGED", "stubbed"


def run_once(leg_end_tag, shots=None):
    """One failing node, with a known leg-end frame published by follow()."""
    saved.clear()
    gw._LAST_FAILURE_KINDS.clear()
    fk.classify = fake_classify
    gw.stream_is_live = lambda *a, **k: True

    def fake_gtnv(m, node, **kw):
        # This is what follow() does inside a real attempt.
        if leg_end_tag is not None:
            gw._LAST_LEG_END[node] = Frame(leg_end_tag)
        return False

    gw.go_to_node_verified = fake_gtnv
    try:
        return gw.follow_verified(
            None, ["target_node"],
            capture=lambda: Frame("AFTER-RECOVERY"),
            read_heading=lambda: 0.0, log=lambda *a: None, shots=shots)
    finally:
        fk.classify = orig_classify
        gw.go_to_node_verified = orig_gtnv
        gw.stream_is_live = orig_live
        gw._LAST_LEG_END.clear()


# The core claim: the leg's own frame is what gets classified, NOT the frame
# captured before the attempt and NOT the post-recovery view.
run_once("LEG-END")
check(saved.get("tag") == "LEG-END",
      f"classify() receives the leg-end frame (got {saved.get('tag')!r})")

# Without shots, `before` is never captured at all — the census must still run.
# This is the measure_streak.py case, and it was returning nothing.
run_once("LEG-END", shots=None)
check(saved.get("calls") == 1,
      "classification runs with shots=None (the measure_streak case)")
check(gw._LAST_FAILURE_KINDS == ["WEDGED"],
      f"the class is recorded with no shots (got {gw._LAST_FAILURE_KINDS})")

# If follow() published nothing, the fallback must be used AND declared, never
# silently substituted for the leg's frame.
run_once(None)
check(saved.get("tag") == "AFTER-RECOVERY",
      f"falls back to the current view when no leg-end frame exists "
      f"(got {saved.get('tag')!r})")

# A frame left behind by an earlier trial must never be classified as this one.
gw._LAST_LEG_END["target_node"] = Frame("STALE-FROM-LAST-TRIAL")
run_once("LEG-END")
check(saved.get("tag") == "LEG-END",
      f"a stale leg-end frame is dropped before the attempt "
      f"(got {saved.get('tag')!r})")

print()
if fails:
    raise SystemExit(f"{len(fails)} FAILED")
print("OK: failures are classified from the leg's own frame, shots or not")
