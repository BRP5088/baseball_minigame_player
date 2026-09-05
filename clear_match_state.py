"""Clear a stale 'match in progress' flag from a progress file.

    python3 clear_match_state.py progress_taylere.json

WHY THIS EXISTS
---------------
`match_in_progress` is persisted so a crash mid-match does not throw away a win
already paid for: a result screen is only scored for a match THIS process paid
for, so without the flag surviving a restart, a rerun would refuse the genuine
result, dismiss it, and lose it.

The cost of that correctness is a stale-state case. If the match is genuinely
over — finished by hand, save reloaded, console reset — the flag still claims a
paid match is running, and every rerun waits for a result that is never coming.
Nothing else clears it, so this exists rather than asking anyone to hand-edit
JSON at 2am. Written atomically, and it never touches wins/losses/balance.
"""

import json
import os
import sys

if len(sys.argv) != 2:
    print(__doc__)
    sys.exit(1)

path = sys.argv[1]
try:
    with open(path) as f:
        data = json.load(f)
except FileNotFoundError:
    print(f"{path} does not exist.")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"{path} is not readable JSON ({e}). Refusing to touch it.")
    sys.exit(1)

before = (bool(data.get("match_in_progress")), bool(data.get("bans_done_this_match")))
if not any(before):
    print(f"{path}: nothing to clear — both flags are already false.")
    sys.exit(0)

data["match_in_progress"] = False
data["bans_done_this_match"] = False
tmp = path + ".tmp"
with open(tmp, "w") as f:
    json.dump(data, f, indent=2)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, path)

print(f"{path}: match_in_progress={before[0]} bans_done_this_match={before[1]} "
      "-> both False.")
print(f"  unchanged: {data.get('wins')}W/{data.get('losses')}L/"
      f"{data.get('draws')}D, ${data.get('balance')}")
