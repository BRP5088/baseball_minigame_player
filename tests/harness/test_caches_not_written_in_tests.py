"""The offline suite must not write the rig's calibration files.

WHAT THIS GUARDS. `compass_scale.json` and `view_bounds.json` are read back by
LIVE runs: the scale cache decides degrees-per-pixel on the compass strip, and
the view cache moves the view centre and hence every bearing. Both were written
unconditionally, so an offline test wrote a production calibration file and the
next real run believed it.

It has happened twice. An offline analysis pass added a live geometry's key to a
worktree's copy, and on 2026-09-06 the ordinary suite added a key derived from
DEMO ARCHIVE frames at 1400x787 -- a geometry no live capture produces -- to the
file the rig uses. Nothing failed either time. Nothing ever does when a cache is
quietly wrong, which is the entire hazard: the run does not error, it just
measures the screen with somebody else's ruler.

WHAT IS AND IS NOT SUPPRESSED. Only the WRITE. The in-memory cache still fills
exactly as it would live, so a test exercises the same code path and the same
values; only persistence is skipped. Suppressing the read instead would change
what the tests measure, and suppressing the fill would make the tests measure a
different program.

MUTATION TEST (2026-09-06): removing either BASEBALL_TEST_RUN guard makes the
matching check below fail.
"""
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


os.environ.setdefault("BASEBALL_TEST_RUN", "1")   # the suite exports it; this file
# manipulates the flag itself below, so it must start from the same state standalone.
import compass
import input_controller as ic

CASES = (
    ("compass._save_scale_cache", compass, "_SCALE_CACHE_FILE", "_SCALE_CACHE",
     compass._save_scale_cache, (1920, 1080, 160, 0), 291.6),
    ("input_controller._save_view_cache", ic, "_VIEW_CACHE_FILE", "_VIEW_CACHE",
     ic._save_view_cache, (1920, 1080, 160, 0), (10, 20, 30, 40)),
)

for name, mod, filekey, cachekey, save, geom, value in CASES:
    d = tempfile.mkdtemp()
    real_path = getattr(mod, filekey)
    real_cache = dict(getattr(mod, cachekey))
    try:
        setattr(mod, filekey, os.path.join(d, "cache.json"))
        getattr(mod, cachekey)[geom] = value

        # 1. Under the test flag: no file appears.
        os.environ["BASEBALL_TEST_RUN"] = "1"
        save()
        check(f"{name} writes NOTHING under BASEBALL_TEST_RUN",
              not os.path.exists(getattr(mod, filekey)))

        # 2. ANTI-VACUITY. Without the flag it must still write -- otherwise
        # check 1 passes because the function is simply broken, and the rig
        # silently loses its calibration between runs.
        os.environ.pop("BASEBALL_TEST_RUN", None)
        save()
        wrote = os.path.exists(getattr(mod, filekey))
        check(f"{name} DOES still write when not a test run", wrote)
        if wrote:
            raw = json.load(open(getattr(mod, filekey)))
            flat = json.dumps(raw)
            check(f"{name}'s live write actually contains the new geometry",
                  "1920,1080,160,0" in flat)
    finally:
        os.environ["BASEBALL_TEST_RUN"] = "1"
        setattr(mod, filekey, real_path)
        getattr(mod, cachekey).clear()
        getattr(mod, cachekey).update(real_cache)
        shutil.rmtree(d, ignore_errors=True)

# 3. The real files on disk must be untouched by this very test.
for fn in ("compass_scale.json", "view_bounds.json"):
    p = os.path.join(_ROOT, fn)
    if os.path.exists(p):
        try:
            raw = json.load(open(p))
        except Exception as e:
            check(f"{fn} is still valid JSON after the suite ({e})", False)
            continue
        # A demo-archive geometry in the rig's cache is the exact pollution
        # this file exists to stop. Live captures are 1867x1050 or 1920x1080;
        # 1400x787 only ever comes from demos/.
        polluted = [k for k in json.dumps(raw).split('"') if k.startswith("1400,787")]
        check(f"{fn} carries no demo-archive geometry key"
              + (f" (found {polluted})" if polluted else ""), not polluted)

# --- 4. a forced write must be redirected first -----------------------------
# `force=True` is the escape hatch for the two tests that exercise persistence
# itself. It is also a way to reintroduce the exact bug: forcing a write while
# the module still points at the project's own file pollutes the rig again, and
# nothing would fail. So any test that forces must also redirect the path.
import ast

FORCED = {"_save_scale_cache": "_SCALE_CACHE_FILE",
          "_save_view_cache": "_VIEW_CACHE_FILE"}
_forcing = []
tests_root = os.path.join(_ROOT, "tests")
for dirpath, _dirnames, filenames in os.walk(tests_root):
    for fn in filenames:
        if not (fn.startswith("test_") and fn.endswith(".py")):
            continue
        full = os.path.join(dirpath, fn)
        try:
            tree = ast.parse(open(full).read(), full)
        except SyntaxError:
            continue
        forced_here, redirected = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr in FORCED:
                if any(k.arg == "force" and getattr(k.value, "value", False) is True
                       for k in node.keywords):
                    forced_here.add(node.func.attr)
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Attribute) and t.attr in FORCED.values():
                        redirected.add(t.attr)
        for call in sorted(forced_here):
            _forcing.append((fn, call, FORCED[call] in redirected))

for fn, call, redirected in _forcing:
    check(f"{fn} redirects {FORCED[call]} before calling {call}(force=True)"
          + ("" if redirected else " -- without it, that call writes the RIG's "
                                   "real calibration file"),
          redirected)

check("at least one test exercises the forced-write path, so rule 4 is not "
      f"vacuous (found {len(_forcing)})", len(_forcing) >= 2)

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
