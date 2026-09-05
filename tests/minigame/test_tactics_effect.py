"""tactics_effect must ABSTAIN rather than emit a p-value it cannot support."""
import json
import os
import os as _os
import subprocess
import sys
import tempfile

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
ROOT = _ROOT
sys.path.insert(0, ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import tactics_effect as te

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def write_log(rows):
    fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    for r in rows:
        fh.write(json.dumps(r) + "\n")
    fh.close()
    return fh.name


def row(kind, outcome):
    return {"phase": "batting", "our_power": 5, "our_tactics_kind": kind,
            "our_tactics_bonus": 1, "outcome": outcome}


# 3 speed rows against plenty of others: too few to judge, must abstain.
thin = ([row("speed_boost", "hit")] * 3
        + [row("swing_boost", "out")] * 20)
v = te.main(write_log(thin))
check("an arm below MIN_N abstains instead of reporting p",
      v["speed_boost"].get("verdict") == "insufficient data"
      and "p" not in v["speed_boost"])

# Enough rows on both sides: a p-value IS produced.
fat = ([row("speed_boost", "hit")] * 12
       + [row("swing_boost", "out")] * 12)
v = te.main(write_log(fat))
check("a well-populated arm does produce a p-value",
      isinstance(v["speed_boost"].get("p"), float))
check("and it detects a total split as unlikely",
      v["speed_boost"]["p"] < 0.05)

# A bonus with no kind is uncomputable, NOT 'no tactic' — the trap CLAUDE.md
# records: speed/fielding carry a bonus that adds no power, so treating an
# unknown kind as zero silently mixes them into the baseline.
mixed = ([{"our_power": 5, "our_tactics_bonus": 2, "outcome": "hit"}] * 30
         + [row("speed_boost", "hit")] * 12
         + [row("swing_boost", "out")] * 12)
v = te.main(write_log(mixed))
# The mutation this guards: `known = list(rows)`. It does NOT change the arm
# (those rows are not speed_boost), it silently swells the COMPARISON group —
# so assert on that side, which is where the contamination lands.
check("rows with no tactics_kind are excluded, not counted as baseline",
      v["speed_boost"]["n"] == 12
      and v["speed_boost"]["compared_against"] == 12)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
