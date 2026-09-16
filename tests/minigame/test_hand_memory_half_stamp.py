"""The hand memory's HALF stamp must survive a play, and a null stamp is not a match.

Two defects that composed, both found by QA round 4 and both reproduced here.

  forget_hand_slot() calls _save_hand_memory() with NO phase on every play and
  every discard. The save wrote {"phase": null}, so the FIRST card spent erased
  the half stamp for the rest of the match.

  _load_hand_memory's guard read `not in (None, phase)`, so a null stamp was
  accepted for BOTH halves -- it waved through exactly the state the save had
  just created.

Seen on the live rig 2026-09-16: hand_memory.json on disk after a completed match
read {"phase": null, "slots": {"0": ..., "3": ...}}.

Why it matters: a new half deals a FRESH five. A batting slot remembered as
secondary 3 -- a batter's SPEED, which the role census says no pitcher has -- is
then served on a pitching turn, for a slot the reader cannot see and so cannot audit.
"""
import json
import os
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import orchestrator as o

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


class Mem:
    """Point the memory at a temp file and let saves actually write."""

    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix=f"handmem{os.getpid()}_")
        self.saved = (o.HAND_MEMORY_FILE, o._running_under_test,
                      o.MEMORY_IN_PROCESS_ONLY, dict(o._hand_memory),
                      o._hand_memory_loaded)
        o.HAND_MEMORY_FILE = os.path.join(self.d, "hand_memory.json")
        o._running_under_test = lambda: False   # the save refuses under a test run
        o.MEMORY_IN_PROCESS_ONLY = False
        o._hand_memory.clear()
        o._hand_memory_loaded = False
        return self

    def __exit__(self, *a):
        (o.HAND_MEMORY_FILE, o._running_under_test,
         o.MEMORY_IN_PROCESS_ONLY, mem, o._hand_memory_loaded) = self.saved
        o._hand_memory.clear()
        o._hand_memory.update(mem)

    def on_disk(self):
        with open(o.HAND_MEMORY_FILE) as fh:
            return json.load(fh)


ROWS = [{"digit": 7}, {"digit": 4}]


# ---- 1. A PHASE-LESS SAVE MUST NOT ERASE THE STAMP -------------------------
with Mem() as m:
    o._hand_memory[0] = {"power": "7", "secondary": 1}
    o._hand_memory[1] = {"power": "4", "secondary": 3}
    o._save_hand_memory(phase="batting")
    stamped = m.on_disk()["phase"]
    o.forget_hand_slot(1)                 # a play: saves with NO phase
    after = m.on_disk()["phase"]

check(stamped == "batting", f"a stamped save writes its phase: {stamped!r}")
check(after == "batting",
      f"after forget_hand_slot the stamp SURVIVES: {after!r} (was null before the fix)")

# ---- 2. A NULL STAMP IS NOT A MATCH FOR EITHER HALF ------------------------
with Mem() as m:
    with open(o.HAND_MEMORY_FILE, "w") as fh:
        json.dump({"phase": None,
                   "slots": {"0": {"power": "7", "secondary": 1}}}, fh)
    adopted_null = o._load_hand_memory(ROWS, phase="pitching")

check(adopted_null == 0,
      f"an UNSTAMPED file is refused when the half is known: adopted {adopted_null}")

# ---- 3. A WRONG stamp is refused (the case that already worked) ------------
with Mem() as m:
    with open(o.HAND_MEMORY_FILE, "w") as fh:
        json.dump({"phase": "batting",
                   "slots": {"0": {"power": "7", "secondary": 1}}}, fh)
    adopted_wrong = o._load_hand_memory(ROWS, phase="pitching")

check(adopted_wrong == 0,
      f"a BATTING file is refused on a pitching turn: adopted {adopted_wrong}")

# ---- 4. THE CONTROL. Without this the three checks above pass on a loader
#         that adopts nothing ever, which is the same bug wearing a fix's clothes.
with Mem() as m:
    with open(o.HAND_MEMORY_FILE, "w") as fh:
        json.dump({"phase": "batting",
                   "slots": {"0": {"power": "7", "secondary": 1}}}, fh)
    adopted_ok = o._load_hand_memory(ROWS, phase="batting")

check(adopted_ok > 0,
      f"CONTROL: a MATCHING stamp with corroborating rows IS adopted: {adopted_ok}")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
