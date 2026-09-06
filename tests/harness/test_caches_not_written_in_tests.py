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

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
