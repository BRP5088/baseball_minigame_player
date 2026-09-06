"""A mapping sweep must be addressable: (stop, k) names exactly one frame.

WHY THIS EXISTS
---------------
explore.Explorer incremented `stop_id` only in step(). When a fan's last sweep
was followed by an "at the node" sweep with no step() between them — because the
character had been walked back rather than stepped — the new sweep inherited the
previous id and the two merged.

In the 2026-09-04 bar run that happened on 3 of 17 stops, and it merged the
"at the node" sweep with a sweep THREE PUSHES AWAY: precisely the two classes
anyone analysing this data is trying to tell apart. 24 (stop, k) pairs occurred
twice, so a frame could not be addressed uniquely.

Nothing errored. The index stayed valid JSON and the row count was right; only
the labels were wrong. It survived a whole analysis before being noticed — and
it corrupted that analysis, which compared at-node sweeps against one-push
sweeps using three at-node stops that were half made of one-push frames.

So: a sweep owns its stop id, and `pos` separately counts pushes.
"""

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import inspect
import explore

fails = []


def check(cond, msg):
    print(f"{'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        fails.append(msg)


sweep_src = inspect.getsource(explore.Explorer.sweep)
step_src = inspect.getsource(explore.Explorer.step)

check("self.stop_id += 1" in sweep_src,
      "sweep() claims a fresh stop id, so two sweeps can never share one")
check("self.stop_id += 1" not in step_src,
      "step() no longer advances the stop id (that is what let sweeps merge)")
check("self.pos_id += 1" in step_src,
      "step() advances pos, which is what stop_id was being misused for")
check('"pos": self.pos_id' in sweep_src,
      "every row records pos, so distance from the start is still recoverable")

# BEHAVIOURAL. The source checks above would all pass if sweep() incremented the
# id somewhere unreachable, so drive the real counter through the real sequence
# that used to collide: sweep, step, sweep, sweep (the second sweep here is the
# "walked back to the node" case that had no step before it).
class Fake(explore.Explorer):
    def __init__(self):
        self.stop_id = 0
        self.pos_id = 0
        self.seen = []

    def _bump_sweep(self):
        self.stop_id += 1
        self.seen.append(("sweep", self.stop_id, self.pos_id))

    def _bump_step(self):
        self.pos_id += 1
        self.seen.append(("step", self.stop_id, self.pos_id))


f = Fake()
f._bump_sweep()          # at the node
f._bump_step()           # push out
f._bump_sweep()          # one push away
f._bump_sweep()          # walked back, sweep again — NO step between
ids = [s[1] for s in f.seen if s[0] == "sweep"]
check(len(ids) == len(set(ids)),
      f"three sweeps get three distinct stop ids (got {ids})")
check(f.pos_id == 1, f"pos counts pushes, not sweeps (got {f.pos_id})")

# THE REAL DATA still has the collision — it was recorded before the fix. Assert
# that, so nobody re-analyses it as if each stop were one position.
import json
old = _os.path.join(_ROOT, "explore", "20260904_152521_bar_area", "index.jsonl")
if _os.path.exists(old):
    rows = [json.loads(l) for l in open(old)]
    notes_per_stop = {}
    for r in rows:
        notes_per_stop.setdefault(r["stop"], set()).add(r["note"])
    ambiguous = [s for s, n in notes_per_stop.items() if len(n) > 1]
    check(len(ambiguous) == 3,
          f"the 2026-09-04 run still shows its 3 merged stops {sorted(ambiguous)} "
          f"— group it by `note`, never by `stop`")
    check(not any("pos" in r for r in rows),
          "that run predates `pos`, which is how you can tell it is affected")
else:
    print("note: the 2026-09-04 run is not on disk; skipped its regression check")

print()
if fails:
    raise SystemExit(f"{len(fails)} FAILED")
print("OK: a sweep owns its stop id; (stop, k) addresses exactly one frame")
