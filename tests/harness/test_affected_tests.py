"""`--affected` must never quietly narrow the suite down to nothing useful.

The whole value of an affected-tests mode is that a green run still means
something. The failure it invites is the catalogue's usual shape: the selection
silently misses the test that would have caught the change, the run is fast and
green, and nothing says a thing.

So the checks here are about what must ALWAYS be selected, not about keeping the
selection small.
"""

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import affected_tests as at

fails = []


def check(cond, msg):
    print(f"{'ok  ' if cond else 'FAIL'} {msg}")
    if not cond:
        fails.append(msg)


MODS = at._project_modules()
TESTS = at.test_files()

check(len(TESTS) > 50, f"found the test files ({len(TESTS)})")
check("graph_walk" in MODS and "orchestrator" in MODS,
      "root modules resolve by bare name")

# 1. A NON-.py CHANGE MUST SELECT EVERYTHING.
# Import edges cannot see a fixture, a JSON file or a shell script. Narrowing on
# one is how a fast green run stops meaning anything.
for path in ["world_map.json", "test_fixtures/ban_scan/grid.png",
             "run_tests.sh", "requirements.txt"]:
    sel, _ = at.select([path], MODS, TESTS)
    check(sel == set(TESTS), f"{path} selects the whole suite ({len(sel)})")

# 2. A CHANGED TEST RUNS ITSELF.
one = "tests/harness/test_no_undefined_names.py"
sel, _ = at.select([one], MODS, TESTS)
check(one in sel, "a changed test file selects itself")

# 3. A CHANGED MODULE SELECTS ITS DIRECT IMPORTERS.
# Pinned by construction rather than by a literal count: ask the closure which
# tests reach the module, then require the selection to contain all of them.
for mod in ["turn_curve.py", "api_budget.py", "places.py"]:
    name = mod[:-3]
    expect = {t for t in TESTS
              if name in at.closure(_os.path.join(_ROOT, t), MODS)}
    sel, _ = at.select([mod], MODS, TESTS)
    check(expect and expect <= sel,
          f"{mod} selects all {len(expect)} tests that reach it")

# 4. TRANSITIVE, NOT JUST DIRECT.
# A test importing graph_walk must be selected when places.py changes, because
# graph_walk imports places. Direct-import-only matching would miss this and is
# the single most likely way this tool goes quietly wrong.
gw = at.closure(_os.path.join(_ROOT, "graph_walk.py"), MODS)
check("places" in gw, "graph_walk reaches places (transitive edge exists)")
importers = [t for t in TESTS
             if "graph_walk" in at.closure(_os.path.join(_ROOT, t), MODS)]
sel, _ = at.select(["places.py"], MODS, TESTS)
check(importers and all(t in sel for t in importers),
      f"places.py selects the {len(importers)} tests that only import "
      f"graph_walk")

# 4b. MODULES OUTSIDE THE ROOT COUNT TOO.
# Found for real: three tests import overnight/_harness.py by bare name, and the
# first version of _project_modules() only walked the root and tests/, so a
# change to that file selected ZERO tests — while the run went green. Pinned by
# grepping for the import rather than by a count, so it tracks the real callers.
import re as _re
_h_importers = [t for t in TESTS
                if _re.search(r"^\s*(import|from)\s+_harness\b",
                              open(_os.path.join(_ROOT, t)).read(), _re.M)]
check(len(_h_importers) >= 3,
      f"found the tests that import _harness ({len(_h_importers)})")
sel, _ = at.select(["overnight/_harness.py"], MODS, TESTS)
check(all(t in sel for t in _h_importers),
      f"overnight/_harness.py selects all {len(_h_importers)} of its importers")

# 5. SELECTION MUST ACTUALLY DISCRIMINATE.
# If every module selected everything the mode would be pointless, and a bug
# that made select() return all tests would otherwise pass checks 1-4 silently.
sel, _ = at.select(["turn_curve.py"], MODS, TESTS)
check(0 < len(sel) < len(TESTS),
      f"turn_curve.py selects a strict subset ({len(sel)} of {len(TESTS)})")

# 6. A MODULE NO TEST IMPORTS MUST SAY SO, not return an empty set silently.
sel, reasons = at.select(["definitely_not_a_real_module.py"], MODS, TESTS)
check(any("NO TEST IMPORTS IT" in r for r in reasons),
      "an unimported module is reported, not silently skipped")

# 7. UNPARSEABLE FILES MUST NOT NARROW THE RUN.
# _imports returns None on a syntax error; closure must treat that as "reaches
# nothing known" without crashing the selection for every other test.
import tempfile
with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
    fh.write("def broken( :\n")
    bad = fh.name
try:
    check(at._imports(bad) is None, "a syntax error yields None, not a crash")
    check(at.closure(bad, MODS) == set(), "an unparseable file reaches nothing")
finally:
    _os.unlink(bad)

print()
if fails:
    raise SystemExit(f"{len(fails)} FAILED")
print(f"OK: affected-test selection cannot silently narrow the suite")
