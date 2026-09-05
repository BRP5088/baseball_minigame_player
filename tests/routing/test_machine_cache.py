"""Geometry caches must be per-machine. Offline, no game, no screen.

WHY THIS EXISTS
---------------
The caches hold px-per-90-degrees and the view centre. Both are properties of
one computer's display and window placement, and applying one machine's
geometry to another's frames yields a bearing that LOOKS fine and is wrong —
the failure mode that cost this project most of a night (the macOS dock sat
inside the capture, moved the apparent view centre 28px, and biased every
heading by ~8.5 degrees while every internal consistency check passed).

The project is moved between computers, so the cache file travels. It must
therefore be keyed by machine: a new computer misses and measures its own
values, and the original's entries survive so moving back still works.
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)

import json
import os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

import compass
import input_controller as ic

fails = []
SCALE = compass._SCALE_CACHE_FILE
VIEW = ic._VIEW_CACHE_FILE
saved = {p: (open(p).read() if os.path.exists(p) else None) for p in (SCALE, VIEW)}

try:
    for p in (SCALE, VIEW):
        if os.path.exists(p):
            os.remove(p)

    real = ic.machine_id()
    if not real or "|" not in real:
        fails.append(f"machine_id() looks unusable: {real!r}")

    # --- machine A writes some geometry ------------------------------------
    compass._SCALE_CACHE.clear()
    compass._SCALE_CACHE[(2000, 1292, 166, 15)] = 295.0
    compass._save_scale_cache()
    ic._VIEW_CACHE.clear()
    ic._VIEW_CACHE[(2000, 1292)] = (0, 1942, 103, 1291)
    ic._save_view_cache()

    # --- machine B is a DIFFERENT computer ---------------------------------
    ic._MACHINE_ID = "other-laptop|arm64|3840x2160"

    if compass._load_scale_cache():
        fails.append("a different machine inherited the scale cache — its "
                     "bearings would be silently wrong, not missing")
    if ic._load_view_cache():
        fails.append("a different machine inherited the view-bounds cache")

    # machine B measures its own, and must not destroy machine A's
    compass._SCALE_CACHE.clear()
    compass._SCALE_CACHE[(3840, 2160, 320, 30)] = 560.0
    compass._save_scale_cache()
    ic._VIEW_CACHE.clear()
    ic._VIEW_CACHE[(3840, 2160)] = (0, 3800, 200, 2100)
    ic._save_view_cache()

    for path, label in ((SCALE, "scale"), (VIEW, "view")):
        with open(path) as fh:
            raw = json.load(fh)
        if real not in raw:
            fails.append(f"{label} cache: writing from machine B DELETED "
                         f"machine A's entry — moving the project back would "
                         f"silently re-measure everything")
        if "other-laptop|arm64|3840x2160" not in raw:
            fails.append(f"{label} cache: machine B's entry was not stored")

    # --- back on machine A: its own values are still there ------------------
    ic._MACHINE_ID = real
    if compass._load_scale_cache().get((2000, 1292, 166, 15)) != 295.0:
        fails.append("machine A lost its scale after machine B wrote")
    if ic._load_view_cache().get((2000, 1292)) != (0, 1942, 103, 1291):
        fails.append("machine A lost its view bounds after machine B wrote")

finally:
    ic._MACHINE_ID = None
    for p, content in saved.items():
        if content is None:
            if os.path.exists(p):
                os.remove(p)
        else:
            open(p, "w").write(content)

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  geometry caches are per-machine: a second computer misses rather than "
      "inheriting, both entries coexist, and neither overwrites the other")


# --- the cache file lives on a NAS now -------------------------------------
# A truncate-then-write loses EVERY machine's entry if the mount drops
# mid-write, not just the one being saved. Proven by checking that no moment
# exists where the file on disk is shorter than a complete document.
def _atomic_write_check():
    import compass, json, os, tempfile
    d = tempfile.mkdtemp()
    compass._SCALE_CACHE_FILE = os.path.join(d, "scale.json")
    compass._SCALE_CACHE = {(1728, 1117): 0.148}
    compass._save_scale_cache()
    first = json.load(open(compass._SCALE_CACHE_FILE))

    # simulate the mount dying partway through the NEXT save
    real_dump = json.dump
    def dying_dump(obj, fh, **kw):
        fh.write('{"partial": ')          # a torn write
        raise OSError("mount went away")
    json.dump = dying_dump
    try:
        compass._SCALE_CACHE = {(1728, 1117): 0.999}
        compass._save_scale_cache()       # swallowed by the except: pass
    finally:
        json.dump = real_dump

    survived = json.load(open(compass._SCALE_CACHE_FILE))
    assert survived == first, (
        "an interrupted save corrupted the cache — every machine's measured "
        f"geometry is gone, not just this one's (on disk: {survived!r})")
    leftovers = [f for f in os.listdir(d) if f.endswith(".tmp")]
    print(f"  interrupted save left the good cache intact"
          f"{' (stray .tmp remains, harmless)' if leftovers else ''}")


_atomic_write_check()
