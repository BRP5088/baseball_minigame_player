"""The compass scale cache is written once per geometry, not once per frame.

WHAT THIS GUARDS
----------------
compass.read_bearing derives `pitch` — px per 90 degrees — as
`float(np.median(spans))` from THIS frame's blob centres, then stored it with

    if _SCALE_CACHE.get(geom) != pitch:
        _SCALE_CACHE[geom] = pitch
        _save_scale_cache()

A float median re-derived per frame practically never equals the stored one, so
that condition was true almost every time. Measured 2026-09-05 over 26 archived
1920x1080 frames: **16 of 26 reads (62%) wrote the file**, all under ONE
geometry key, refining a value that ranged 289.50-292.50px — a 3.00px spread,
about 1%, median consecutive change 0.500px.

WHAT THE WRITE COSTS. This file first said "120ms median in the project
directory (n=20, max 324ms)". CORRECTED 2026-09-05 by an independent
re-measurement into the real project directory, n=60 under load average 18:
**median 9.0ms, mean 9.7ms, max 19.1ms, zero samples over a second**. An n=25
pass did show two ~5412ms samples, but a control loop of the same shape with
the file I/O removed shows those were whole-process stalls on a saturated
machine (CLAUDE.md 10.13), not the write. So the cut is worth ~0.4s of an 85.6s
trial, under 1% — real, free, and NOT a headline. This test guards the
BEHAVIOUR (one write per geometry), which is what actually has to hold; it
deliberately asserts nothing about the millisecond figure.

WHAT THE DISK COPY IS FOR. _load_scale_cache's own docstring: a frame showing
only ONE letter cannot establish the scale, so a fresh process would abstain on
every such frame; the scale belongs to the window, not the run, so it is kept
between runs. One good in-band value per geometry does that. The 150th does not.

NO THRESHOLD IS INVOLVED, deliberately. A moved or resized window produces a
DIFFERENT `geom` key, which is absent and so is written immediately — the two
cases are separated by identity, not by a number. The second check below is
exactly that branch.

Offline. No game, no screen; the cache file is redirected to a temp directory.
"""

import os as _os
import sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")
_os.environ["BASEBALL_TEST_RUN"] = "1"

import glob                       # noqa: E402
import tempfile                   # noqa: E402

from PIL import Image             # noqa: E402

import compass                    # noqa: E402

fails = []


def check(msg, ok):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


FRAMES = [p for p in sorted(glob.glob(_os.path.join(_ROOT, "places", "*", "*.jpg")))
          if Image.open(p).size == (1920, 1080)][:8]
if not FRAMES:
    print("FAIL no 1920x1080 world frame to test with")
    raise SystemExit(1)

writes = []
pitches = []
read_ok = 0

real_file = compass._SCALE_CACHE_FILE
real_save = compass._save_scale_cache
kept = dict(compass._SCALE_CACHE)
try:
    compass._SCALE_CACHE_FILE = _os.path.join(tempfile.mkdtemp(), "scale.json")
    compass._SCALE_CACHE.clear()

    def counted():
        writes.append(dict(compass._SCALE_CACHE))
        real_save()

    compass._save_scale_cache = counted

    for p in FRAMES:
        img = Image.open(p).convert("RGB")
        img.info["game_only"] = True
        b = compass.read_bearing(img)
        read_ok += b is not None
        pitches.append(tuple(sorted(compass._SCALE_CACHE.items())))

    first_pass = len(writes)
    keys = set(k for snap in writes for k in snap)

    # --- the branch that must still fire: a geometry never seen before -----
    # This is the whole safety argument. Drop the key and read the same frame:
    # an absent key must be written, or a moved window would never persist its
    # scale and a fresh process would abstain on every one-letter frame.
    before = len(writes)
    compass._SCALE_CACHE.clear()
    img = Image.open(FRAMES[0]).convert("RGB")
    img.info["game_only"] = True
    compass.read_bearing(img)
    new_key_writes = len(writes) - before
finally:
    compass._save_scale_cache = real_save
    compass._SCALE_CACHE_FILE = real_file
    compass._SCALE_CACHE.clear()
    compass._SCALE_CACHE.update(kept)

# --- anti-vacuity: the frames must actually exercise the write path --------
check(f"ANTI-VACUITY: the frames are readable ({read_ok}/{len(FRAMES)})",
      read_ok >= max(2, len(FRAMES) - 1))
distinct = len({snap for snap in pitches if snap})
check(f"ANTI-VACUITY: the measured pitch really does vary frame to frame "
      f"({distinct} distinct cached values across {len(FRAMES)} reads) — "
      f"otherwise 'one write' would be true for the wrong reason",
      distinct >= 2)

# --- the fix ---------------------------------------------------------------
check(f"one geometry is written to disk ONCE, not once per frame "
      f"({first_pass} write(s) over {len(FRAMES)} reads)",
      first_pass == 1)
check("and only one geometry key was involved", len(keys) == 1)

# --- the branch that must survive ------------------------------------------
check("a geometry the file has never seen IS written",
      new_key_writes == 1)

print()
if fails:
    print(f"{len(fails)} FAILED")
    for f in fails:
        print("  " + f)
    raise SystemExit(1)
print("all green")
