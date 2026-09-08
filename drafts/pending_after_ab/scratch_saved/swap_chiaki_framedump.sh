#!/bin/bash
# Install the frame-dump build of chiaki and PROVE it works. RUN THIS BY HAND,
# AT A BATCH BOUNDARY. It restarts chiaki, so it kills the stream for ~15s.
#
# It refuses to run while overnight/chain_trials.py is alive, because a restart
# mid-trial does not fail loudly: the child keeps walking, every capture starts
# raising, and the trial is scored as a routing failure.
#
#   bash scratchpad/swap_chiaki_framedump.sh
#
# WHAT IT DOES, in order:
#   1. refuse if a batch is running
#   2. refuse unless drafts/pending_after_ab/apply_patch49.py has been applied
#      (frame_dump.py present and restart_chiaki.sh exporting CHIAKI_FRAME_DUMP)
#      -- installing the binary without the reader gains nothing, and installing
#      the reader without the binary is what the fallback is for
#   3. restart_chiaki.sh with the new build as SRC (it kills chiaki, copies,
#      re-signs, relaunches with both env vars)
#   4. wait for the stream
#   5. check the dump: 1920x1080, seq INCREASING over 2s, compass.read_bearing
#      reads a bearing FROM IT, and -- the thing nobody can assume -- compare a
#      dump frame against a SIMULTANEOUS screen grab, because cv2 converts
#      NV12 as BT.601 while a PS5 stream is usually BT.709 and nobody has
#      measured what that costs on this game's art
#   6. PASS / FAIL
#
# IF IT FAILS: the old build is still at chiaki-ng-build/ in git-ignored land,
# but restart_chiaki.sh has already overwritten it. To go back, rebuild from a
# checkout without the framedump edits, or just set USE_FRAME_DUMP = False in
# compass.py -- the screen path is untouched and still works.
set -u
ROOT="/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
SRC="$ROOT/chiaki-ng-src/build/gui/chiaki.app/Contents/MacOS/chiaki"
PY="$ROOT/.venv/bin/python"

fail() { echo "FAIL: $*"; exit 1; }

# ---- 1. no live batch -----------------------------------------------------
if pgrep -f "chain_trials.py" > /dev/null; then
    echo "REFUSING: overnight/chain_trials.py is running."
    pgrep -fl "chain_trials.py" | sed 's/^/    /'
    echo "Restarting chiaki mid-trial does not fail loudly -- the child keeps"
    echo "walking, every capture raises, and the trial is scored as a routing"
    echo "failure. Wait for the batch to finish."
    exit 1
fi
echo "ok   no chain_trials.py running"

# ---- 2. the Python half must already be applied ---------------------------
[ -f "$SRC" ] || fail "no new build at $SRC (build it: cmake --build build --target chiaki)"
[ -f "$ROOT/frame_dump.py" ] || fail "frame_dump.py is missing -- apply drafts/pending_after_ab/apply_patch49.py first"
grep -q CHIAKI_FRAME_DUMP "$ROOT/restart_chiaki.sh" \
    || fail "restart_chiaki.sh does not export CHIAKI_FRAME_DUMP -- apply patch49 first"
nm -U "$SRC" | grep -qi FrameDumpStart \
    || fail "$SRC has no FrameDumpStart symbol; it is not the frame-dump build"
echo "ok   patch49 applied, and the build carries FrameDumpStart"

# ---- 3. install and relaunch ----------------------------------------------
echo "--- restart_chiaki.sh ---"
bash "$ROOT/restart_chiaki.sh" "$SRC" || fail "restart_chiaki.sh exited nonzero"
echo "--- /tmp/chiaki_run.log, frame dump lines ---"
grep -i "framedump\|frame dump" /tmp/chiaki_run.log || echo "    (none yet)"

# ---- 4. wait for the stream ----------------------------------------------
echo "--- waiting for the stream (up to 90s) ---"
"$PY" -B - <<'PYEOF' || fail "the stream did not come up"
import sys, time
sys.path.insert(0, "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball")
import ensure_stream
t0 = time.time()
while time.time() - t0 < 90:
    try:
        if ensure_stream.streaming():
            print("    streaming after %.0fs" % (time.time() - t0)); sys.exit(0)
    except Exception as e:
        print("    ", type(e).__name__, e)
    time.sleep(3)
print("    still not streaming after 90s"); sys.exit(1)
PYEOF

# ---- 5. the checks --------------------------------------------------------
echo "--- checking the dump ---"
"$PY" -B - <<'PYEOF'
import os, sys, time
import numpy as np
ROOT = "/Users/bpatterson/Documents/Claude Cowork Personal/Auto Baseball"
sys.path.insert(0, ROOT)
# NEVER under BASEBALL_TEST_RUN: frame_dump refuses the default path there, and
# this check would then "pass" by measuring nothing.
os.environ.pop("BASEBALL_TEST_RUN", None)
import frame_dump, compass

ok = True
def check(label, cond, detail=""):
    global ok
    print(("  PASS " if cond else "  FAIL ") + label + (("  -- " + detail) if detail else ""))
    if not cond: ok = False

st = frame_dump.stats()
check("the dump exists and parses", st is not None,
      "" if st else "no readable header at %s -- did the launch log say 'frame dump'?"
      % frame_dump.dump_path())
if st is None:
    print("\nFAIL"); sys.exit(1)
print("  header:", {k: st[k] for k in ("path","width","height","pix_fmt","seq",
                                       "color_space","color_range","dropped")})
check("the frame is 1920x1080", (st["width"], st["height"]) == (1920, 1080),
      "%dx%d" % (st["width"], st["height"]))
check("the dump is FRESH", st["age_s"] <= frame_dump.MAX_AGE_S,
      "age %.0fms" % (st["age_s"] * 1000))

seq0 = st["seq"]
time.sleep(2.0)
st1 = frame_dump.stats()
check("seq INCREASES over 2s -- frames are still arriving",
      st1 is not None and st1["seq"] > seq0,
      "%s -> %s (%.1f dumps/s)" % (seq0, st1["seq"] if st1 else None,
                                   ((st1["seq"] - seq0) / 2.0) if st1 else 0))

img = frame_dump.read_frame()
check("read_frame returns a 1920x1080 image", img is not None and img.size == (1920, 1080),
      str(img.size) if img else "None")

# THE READ MUST BE CHEAP, or it is not an improvement on the 111ms screen grab.
t0 = time.perf_counter()
for _ in range(10):
    frame_dump.read_frame()
per_ms = (time.perf_counter() - t0) / 10 * 1000
check("a read costs well under the screen grab it replaces", per_ms < 40.0,
      "%.1f ms" % per_ms)

# fast_capture must now prefer it, and say so.
cap = compass.fast_capture()
check("compass.fast_capture is served BY THE DUMP", bool(cap.info.get("frame_dump")))
b = compass.read_bearing(cap)
check("compass.read_bearing reads a bearing from the dump frame", b is not None,
      "bearing %s" % (("%.1f" % b) if b is not None else "None -- may be a bright "
                      "scene (~6%% of world frames abstain), re-run before blaming this"))

# WHAT NOBODY HAS MEASURED: the dump is converted with cv2's BT.601 limited-range
# matrix, while the header above says which colorspace the decoder reported. If
# the two paths disagree materially, a detector calibrated on screen grabs will
# read differently off the dump. This measures it instead of assuming.
compass.USE_FRAME_DUMP = False
try:
    screen = compass.fast_capture()
finally:
    compass.USE_FRAME_DUMP = True
dump2 = compass.fast_capture()
if screen.size != dump2.size:
    print("  note  the screen path returns %s and the dump %s -- resized to compare"
          % (screen.size, dump2.size))
    screen = screen.resize(dump2.size)
a = np.asarray(screen, np.int16); c = np.asarray(dump2, np.int16)
d = np.abs(a - c)
print("  colour/geometry difference against a SIMULTANEOUS screen grab (the two "
      "frames are milliseconds apart, so motion inflates this):")
print("      median %.1f   p95 %.1f   max %d   levels per channel"
      % (np.median(d), np.percentile(d, 95), d.max()))
print("      grayscale median %.1f"
      % np.median(np.abs(a.mean(axis=2) - c.mean(axis=2))))
print("      (a median above ~10 is worth chasing: it would mean cv2's BT.601"
      "\n       conversion is wrong for this stream and a proper matrix is needed"
      "\n       in frame_dump._to_image. It is NOT a reason to move any detector"
      "\n       threshold.)")

print("\nPASS" if ok else "\nFAIL"); sys.exit(0 if ok else 1)
PYEOF
rc=$?
echo
if [ $rc -eq 0 ]; then
    echo "PASS  the frame dump is live. Captures no longer need chiaki's window"
    echo "      on the current Space, so the Mac is usable during a batch."
    echo "      tools/doctor.py now prints a 'frame dump' line; check it there too."
else
    echo "FAIL  see above. The screen path still works: compass.USE_FRAME_DUMP = False"
    echo "      restores exactly today's behaviour without touching the binary."
fi
exit $rc
