"""Per-leg single-execution outcome tally from archived overnight logs.READ-ONLY. For each 'leg A -> B' line, records what the NEXT 'arrived?' line
says (True / None=abstained), whether the leg reported BLOCKED, and which step.
'arrived? None' is an ABSTENTION by identify(), not proof of a miss (CLAUDE.md
8e). office_door has no reference by design so its 'arrived?' is never True.
"""
import os
import re
import sys
from collections import defaultdictROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGS = sys.argv[1:] or ["overnight/ab_leg1.log", "overnight/streak_postleg1.log",
                        "overnight/ab_attempts_open5.log"]leg_re = re.compile(r"leg (\S+) -> (\S+)")
arr_re = re.compile(r"arrived\? (\S+)")
arm_re = re.compile(r"arm=(\S+)")
blk_re = re.compile(r"BLOCKED on step (\d+)")
stepblk_re = re.compile(r"step (\d+) blocked but the scene is MOVING")
laststep_re = re.compile(r"step (\d+)/(\d+) bearing")for path in LOGS:
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        print(f"missing {path}")
        continue
    print(f"\n=== {path}")
    arm = "-"
    cur = None
    tally = defaultdict(lambda: defaultdict(int))
    blocked_at = defaultdict(list)
    for line in open(full, errors="replace"):
        s = line.strip()
        ma = arm_re.search(s)
        if ma and "LEG_SPEED_BY_LEG" in s:
            arm = ma.group(1)
        ml = leg_re.search(s)
        if ml and s.lstrip("| ").startswith("leg "):
            cur = (arm, ml.group(1), ml.group(2))
            tally[cur]["executions"] += 1
            continue
        if cur is None:
            continue
        mb = blk_re.search(s)
        if mb:
            tally[cur]["BLOCKED"] += 1
            blocked_at[cur].append(int(mb.group(1)))
        ms = stepblk_re.search(s)
        if ms:
            tally[cur]["step_blocked_events"] += 1
        mr = arr_re.search(s)
        if mr and "arrived?" in s:
            v = mr.group(1)
            tally[cur]["confirmed" if v == "True" else "abstained"] += 1
            cur = None
    for k in sorted(tally):
        t = tally[k]
        ex = t["executions"]
        print(f"  {k[0]:9s} {k[1]:16s} -> {k[2]:16s} exec {ex:3d}  "
              f"confirmed {t['confirmed']:3d}  abstained {t['abstained']:3d}  "
              f"BLOCKED {t['BLOCKED']:2d} at steps {blocked_at[k]}  "
              f"step-blocked events {t['step_blocked_events']}")
