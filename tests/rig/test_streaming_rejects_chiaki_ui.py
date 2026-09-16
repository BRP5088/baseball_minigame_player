"""streaming() must not report UP while chiaki is showing its own window.

THE BUG (OPEN-18). `find_bar` answers "is there a horizontal light band here",
which is true of the game's compass strip AND of any application toolbar. So
`streaming()` returned True on chiaki's own host list. On 2026-09-06 the user
watched every failed reconnect print `[stream] up via find_bar` while the PS5
was in STANDBY and there was no stream at all, and an hour went into diagnosing
the compass instead of the rig. An unattended run in that state presses buttons
at a sleeping console until morning.

THE FIXTURE IS THE REAL THING. `test_fixtures/not_streaming/hostlist_standby.png`
is a live capture of the chiaki window showing `State: standby`, taken at the
rig's own 1867x1050 geometry. Until it existed this ticket could not be settled:
the negative population was a single frame nobody had kept, so no threshold
could be placed between two MEASURED populations (CLAUDE.md 10.4). Six captures
1.5s apart were byte-identical, so this is ONE distinct frame and the file says
so rather than pretending to be six.

THE DISCRIMINATOR IS NOT ABOUT THE COMPASS, deliberately. Qt draws flat fills --
large areas of one exact RGB value, and bands running the full width. H.264
never does; quantisation dithers even a dark room, so decoded video holds no
long exact runs. That is why the rule still holds on ban screens and gameplay,
where no compass exists and a compass-shaped test would reject a healthy stream.

MEASURED over 848 real streaming frames (demos, screenshot_log, explore,
overnight, places; 65 of them pause screens) against the live host list plus 70
non-game images find_bar fires on:

                          streaming: p50    p99     MAX  |  host list
    flatness                  0.0357  0.1131  0.2949  |  0.6678
    widest exact row run      0.1208  0.3917  0.6208  |  1.0000

Held out properly -- thresholds fitted on half the streaming frames, scored on
the other half -- gives ZERO false positives on 71 non-streaming frames and
1.2% false negatives.

WHY THE FALSE NEGATIVES ARE CHEAP, which is what makes this safe to ship.
Rejecting the find_bar branch does NOT return False. It falls through to
`_heartbeat_seen()`, the console's own word and strictly better evidence than
pixels, which returns on the first heartbeat it sees (~0.4s). So a real stream
whose frame happens to be flat still answers True, a moment later. The standby
host list has no session, therefore no heartbeat, and correctly comes back
False after the full wait -- a wait paid only on the path that was about to give
up anyway.
"""
import glob
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

from PIL import Image

import compass
import ensure_stream as es

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


HOSTLIST = os.path.join(_ROOT, "test_fixtures", "not_streaming",
                        "hostlist_standby.png")
check("the live standby host-list fixture exists -- without it this ticket "
      "cannot be settled at all", os.path.exists(HOSTLIST))
if not os.path.exists(HOSTLIST):
    print("\nFAILURES above")
    sys.exit(1)

host = Image.open(HOSTLIST)

# --- 1. the bug's exact preconditions still hold ----------------------------
# If find_bar ever stopped firing on this frame the guard below would pass for
# a reason that has nothing to do with what it checks.
check("find_bar still FIRES on the standby host list, which is the bug",
      compass.find_bar(host) is not None)
check("and read_bearing correctly abstains on it",
      compass.read_bearing(host) is None)

# --- 2. the discriminator ---------------------------------------------------
check("the host list is recognised as chiaki's own UI", es.looks_like_ui(host))

# --- 3. streaming() answers False, and ONLY because of the guard ------------
# Heartbeats are stubbed off so this is offline and instant. That is the state
# the bug lives in: no console replying, and a frame that fools find_bar.
_hb1, _hb2 = es._heartbeat_since_last_check, es._heartbeat_seen
try:
    es._heartbeat_since_last_check = lambda *a, **k: False
    es._heartbeat_seen = lambda *a, **k: False

    check("streaming() reports DOWN on the standby host list",
          es.streaming(host) is False)

    # THE CONTROL. Without the guard it must report UP -- otherwise something
    # else is producing the False above and this file is pinning the wrong
    # thing. This is the historical behaviour, reproduced exactly.
    _real = es.looks_like_ui
    try:
        es.looks_like_ui = lambda im: False
        check("and WITHOUT the guard it reports UP, via find_bar -- so the "
              "guard is what changed the answer",
              es.streaming(host) is True
              and "find_bar" in (es.last_route() or ""))
    finally:
        es.looks_like_ui = _real
finally:
    es._heartbeat_since_last_check = _hb1
    es._heartbeat_seen = _hb2

# --- 4. real streaming frames are NOT rejected ------------------------------
# Includes screenshot_log, which is match play: ban grids and gameplay, where
# no compass exists. A compass-shaped discriminator would fail here.
# FIXTURES, NOT four live directories. demos/, screenshot_log/ and explore/ are
# GITIGNORED and overnight/ is written by live runs -- so this population did not
# exist on a fresh clone AND it CHANGED under the test. CLAUDE.md records that
# exact failure: "the 2026-09-06 streak runs appended 165 leg-end frames there and
# G5's pinned profile went 15 -> 9 with no code change". A false-positive rate is
# only meaningful against a population that holds still.
#
# These are the same 260 frames the caps below used to take, copied with their
# source directory kept in the filename so provenance survives the flattening.
frames = sorted(glob.glob(os.path.join(_ROOT, "test_fixtures/streaming_real/*.jpg")))
check("there are enough real streaming frames to score against",
      len(frames) >= 150)

rejected = []
for f in frames:
    try:
        im = Image.open(f)
    except Exception:
        continue
    if es.looks_like_ui(im):
        rejected.append(f)

rate = len(rejected) / float(len(frames)) if frames else 1.0
# 5% is the ceiling, not the measurement: the measured rate is 0.35% over 848
# frames. A ceiling well above it leaves room for new fixtures without pinning
# a number that will drift, while still failing loudly if the gate starts
# eating real frames.
check(f"real streaming frames are accepted ({len(rejected)}/{len(frames)} "
      f"= {100*rate:.2f}% rejected, ceiling 5%)", rate <= 0.05)
for f in rejected[:5]:
    print(f"     rejected: {os.path.relpath(f, _ROOT)}")

# --- 5. the thresholds are pinned as LITERALS -------------------------------
# CLAUDE.md 10.11: a test that asserts against the constant it is guarding
# rises with it and passes forever.
check("UI_FLAT_FRAC is 0.25, between a streaming max of 0.2949 and the host "
      "list's 0.6678", es.UI_FLAT_FRAC == 0.25)
check("UI_ROW_RUN_FRAC is 0.50, between a streaming max of 0.6208 and the "
      "host list's 1.0000", es.UI_ROW_RUN_FRAC == 0.50)

# --- 6. it must never raise into a live run ---------------------------------
class Exploding:
    def convert(self, *a):
        raise RuntimeError("boom")


check("a frame it cannot read is treated as NOT ui, so a broken check can "
      "never call a live stream dead", es.looks_like_ui(Exploding()) is False)

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
