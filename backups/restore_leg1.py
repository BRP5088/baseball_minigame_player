#!/usr/bin/env python3
"""Put leg 1 back to its original execution. See RESTORE_LEG1.md."""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = os.path.join(ROOT, "graph_walk.py")
s = open(p).read()
before = s

s = re.sub(r"LEG_SPEED_BY_LEG = \{.*?\n\}", "LEG_SPEED_BY_LEG = {}", s, flags=re.S)
s = re.sub(r'MERGE_STEPS_BY_LEG = \{\("office_corridor", "office_door"\)\}',
           "MERGE_STEPS_BY_LEG = set()", s)
if s == before:
    print("nothing to restore — leg 1 already original")
    sys.exit(0)
open(p, "w").write(s)
print("leg 1 restored: LEG_SPEED_BY_LEG = {}, MERGE_STEPS_BY_LEG = set()")
print("verify with:  grep -n 'LEG_SPEED_BY_LEG = \\|MERGE_STEPS_BY_LEG = ' graph_walk.py")
