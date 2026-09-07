"""Harnesses report failure classes from LEG-END frames, split by provenance.

consecutive_arrivals split its census into `failures_by_kind_leg_end` and
`failures_from_fallback_frame` on 2026-09-06, and nothing read the split: every
harness kept recording `list(gw._LAST_FAILURE_KINDS)`, the MIXED per-trial list,
and printing it as "failures by class". A fallback frame -- taken before the
attempt, or after the recovery fan -- photographs a different moment, so a
class census built from it describes the fan, not the leg (OPEN-1). A correct
number nobody reads is this project's signature failure wearing a different
hat; this file makes the split the thing that is read.

Two halves. The UNIT half drives `_harness.census_kinds` on a stub with a known
mix and checks the split, the lockstep guard, and that `report_kinds` prints
the leg-end classes as the headline. The WIRING half parses each harness with
`ast` and asserts a real Call to `census_kinds` -- a Call node, not a substring,
with a positive control that a source without the call is rejected.
"""
import ast
import glob
import os
import sys
import types

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.append(os.path.join(_ROOT, "overnight"))
import _harness

ok = True
def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond: ok = False

# --- UNIT --------------------------------------------------------------------
LEG = "the leg's own end"
gw = types.SimpleNamespace(
    LEG_END_SOURCE=LEG,
    _LAST_FAILURE_KINDS=["overshot", "wedged", "overshot", "regressed"],
    _LAST_FAILURE_SOURCES=[LEG, "after recovery — shows the fan, not the leg", LEG,
                           "before the attempt (PREVIOUS node) — weak evidence"])
c = _harness.census_kinds(gw)
check("the mixed list is kept for continuity", c["kinds"] == ["overshot", "wedged", "overshot", "regressed"])
check("leg-end classes are exactly the LEG_END_SOURCE ones", c["kinds_leg_end"] == ["overshot", "overshot"])
check("fallback classes are exactly the others", c["kinds_fallback"] == ["wedged", "regressed"])
check("nothing is double-counted", len(c["kinds_leg_end"]) + len(c["kinds_fallback"]) == len(c["kinds"]))

broken = types.SimpleNamespace(LEG_END_SOURCE=LEG, _LAST_FAILURE_KINDS=["overshot", "wedged"],
                               _LAST_FAILURE_SOURCES=[LEG])
b = _harness.census_kinds(broken)
check("a broken lockstep attributes NOTHING rather than guessing",
      b["kinds_leg_end"] == [] and b["kinds_fallback"] == [] and b.get("kinds_unattributed") == 2)

empty = types.SimpleNamespace(LEG_END_SOURCE=LEG, _LAST_FAILURE_KINDS=[], _LAST_FAILURE_SOURCES=[])
e = _harness.census_kinds(empty)
check("an arriving trial yields empty lists, not a missing key",
      e["kinds_leg_end"] == [] and e["kinds_fallback"] == [] and "kinds_unattributed" not in e)

rows = [dict(c), dict(e), {"kinds": ["wedged"]}]          # third: a legacy row
lines = []
_harness.report_kinds(rows, out=lines.append)
check("the headline is the LEG-END tally", any("LEG-END" in l and "'overshot': 2" in l for l in lines))
check("fallback frames are shown separately, not folded in", any("FALLBACK" in l and "'wedged': 1" in l and "'regressed': 1" in l for l in lines))
check("a legacy mixed-only row is reported as not counted", any("legacy" in l and "not counted" in l for l in lines))
check("legacy mixed classes do NOT leak into the headline", not any("LEG-END" in l and "wedged" in l for l in lines))
check("tally_kinds over kinds_leg_end ignores fallback and legacy rows",
      _harness.tally_kinds(rows, "kinds_leg_end") == {"overshot": 2})

# --- WIRING ------------------------------------------------------------------
HARNESSES = ["measure_primitive.py", "ab_leg1.py", "streak_table.py", "ab_attempts.py"]

def calls_census(src):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
            if name == "census_kinds":
                return True
    return False

for h in HARNESSES:
    p = os.path.join(_ROOT, "overnight", h)
    src = open(p, encoding="utf-8").read()
    check(f"{h} records the census through census_kinds (a Call node, not a substring)", calls_census(src))
    check(f"{h} no longer records the mixed list directly", "list(gw._LAST_FAILURE_KINDS)" not in src)

# Positive control: the scanner must reject a source that only MENTIONS it.
check("the wiring scan rejects a source that mentions census_kinds without calling it",
      not calls_census("x = 'census_kinds'\n# _harness.census_kinds(gw) in a comment\n"))
check("and accepts one that calls it", calls_census("import _harness\nr = {**_harness.census_kinds(gw)}\n"))

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
