"""jukebox.MATCH_MIN is UNCALIBRATED, and no value would calibrate it.

THE DEFECT. The line read `MATCH_MIN = 0.30  # calibrated below; see
tests/test_jukebox.py`. That file has never existed, anywhere in the tree,
under any of the test subdirectories — so a tuned-looking constant on a module
six production modules import carried a comment asserting evidence that was
never collected. This file is the measurement that comment promised, and it
reports a NEGATIVE result.

WHAT IT MEASURED. 766 archived frames scored through jukebox.find() against
test_fixtures/jukebox/: the whole corpus lies between 0.468 and 0.888, so 0.30
sits BELOW EVERY FRAME EVER CAPTURED HERE and visible() cannot return False.
A load screen, an outdoor street and an unlit corridor all pass it.

Then 22 of those frames were labelled by OPENING them and looking for the
jukebox. The populations overlap so heavily that no cut separates them:

    jukebox IN the frame    n= 9   0.583 .. 0.766
    jukebox NOT in it       n=13   0.523 .. 0.656

A stretch of bar counter scores 0.656 and an outdoor street 0.616, both above
frames where the jukebox fills a third of the screen. AUC 0.590 vs 0.500 for a
coin flip. This is the RETICLE_MIN_CONTRAST outcome — "no threshold on this
quantity can separate these populations" — and the right response was to say so
rather than to swap in a second unsupported number.

WHY THE ANCHORS ARE PINNED AS LITERALS. Comparing MATCH_MIN to itself passes
for any value, which is how the original drifted unnoticed. Every number below
is a measurement, so if the matcher changes these fail FIRST and the whole
calibration note in jukebox.py has to be re-derived before the constant is
touched. That is the intended behaviour, not a brittle test.

IF THE SEPARATION CHECK EVER FAILS, that is GOOD NEWS and not a regression: it
means the scorer was improved to the point where the populations no longer
overlap, and a real threshold can finally be measured into the gap. Re-derive
it, rewrite the comment in jukebox.py, and pin the new value here.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image
import jukebox as jb

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


_D = "demos/walk3_full_20260828_050731/"

# GROUND TRUTH. Every one of these was opened and looked at; the note says what
# is in it. Committed frames only — a missing anchor is a failure, not a skip.
POSITIVES = [   # the jukebox ("Pop-Elina" marquee, domed glass front) IS here
    ("places/bar_jukebox/live_00.jpg",          "jukebox centre-left, mid distance"),
    (_D + "f_0054.28.jpg",                      "jukebox left of centre, close"),
    (_D + "f_0054.11.jpg",                      "jukebox left, close"),
    ("places/bar_jukebox/route_0052.76.jpg",    "jukebox centre-left"),
    (_D + "f_0052.76.jpg",                      "jukebox centre-left"),
    (_D + "f_0052.42.jpg",                      "jukebox centre"),
    (_D + "f_0053.44.jpg",                      "jukebox centre-left"),
    (_D + "f_0054.45.jpg",                      "jukebox far left"),
    (_D + "f_0053.94.jpg",                      "jukebox centre-left"),
]
NEGATIVES = [   # no jukebox anywhere in the frame
    ("overnight/failframes/fail_bar_jukebox_1788563811.jpg",
                                                "bar counter, SPIKE-D machine"),
    ("route_frames/leg4_barentry__b.png",       "bar entry, two mice"),
    (_D + "f_0044.82.jpg",                      "bar counter / pool table"),
    (_D + "f_0045.32.jpg",                      "bar counter / pool table"),
    (_D + "f_0035.01.jpg",                      "OUTDOOR STREET, 'LITTLE BIG' storefront"),
    (_D + "f_0044.14.jpg",                      "bar counter"),
    (_D + "f_0013.86.jpg",                      "office corridor, panelled door"),
    (_D + "f_0013.52.jpg",                      "office corridor, panelled door"),
    (_D + "f_0040.42.jpg",                      "bar interior, mirrors"),
    (_D + "f_0047.69.jpg",                      "bar counter, stools"),
    (_D + "f_0050.05.jpg",                      "bar room, chandelier"),
    (_D + "f_0026.37.jpg",                      "dark stairwell"),
    (_D + "f_0055.29.jpg",                      "turned away from it, window"),
]

# The two frames the templates were CUT FROM. They self-match at 0.85-0.89 and
# are excluded from every statistic below: a template scoring highly on its own
# source frame is arithmetic, not evidence. Leaving them in would have lifted
# the positive range to 0.888 and made the overlap look smaller than it is.
SELF_MATCH = ["test_fixtures/jukebox/jukebox_live.jpg",
              "test_fixtures/jukebox/view_close.jpg"]

_missing = [p for p, _ in POSITIVES + NEGATIVES
            if not os.path.exists(os.path.join(_ROOT, p))]
if _missing:
    for p in _missing:
        print(f"FAIL missing anchor frame {p}")
    print("this test cannot run, and a test that cannot run must not "
          "report success")
    sys.exit(1)


def score(rel):
    return float(jb.find(Image.open(os.path.join(_ROOT, rel)))[0])


pos = [(score(p), p, note) for p, note in POSITIVES]
neg = [(score(p), p, note) for p, note in NEGATIVES]

print("\n  jukebox IN the frame:")
for s, p, note in sorted(pos, reverse=True):
    print(f"    {s:.4f}  {os.path.basename(p):24s} {note}")
print("  jukebox NOT in the frame:")
for s, p, note in sorted(neg, reverse=True):
    print(f"    {s:.4f}  {os.path.basename(p):24s} {note}")

ps = [s for s, _, _ in pos]
ns = [s for s, _, _ in neg]
print(f"\n  positives {min(ps):.3f}..{max(ps):.3f} (n={len(ps)})   "
      f"negatives {min(ns):.3f}..{max(ns):.3f} (n={len(ns)})")


# --- 1. the scorer itself, pinned so a change to it cannot pass silently -----
# Four anchors spanning the range. Tolerance is 0.02: find() is deterministic
# (pure numpy, no sampling), so this is slack for a library change, not noise.
ANCHORS = [
    ("places/bar_jukebox/live_00.jpg", 0.766, "clearest positive"),
    (_D + "f_0054.28.jpg",             0.677, "close positive"),
    ("overnight/failframes/fail_bar_jukebox_1788563811.jpg",
                                       0.656, "HIGHEST negative — bar counter"),
    (_D + "f_0035.01.jpg",             0.616, "outdoor street, no bar at all"),
]
for rel, want, note in ANCHORS:
    got = score(rel)
    check(f"{os.path.basename(rel)} scores {want:.3f} ({note}) — got {got:.4f}",
          abs(got - want) <= 0.02)


# --- 2. THE RESULT: the populations overlap, so nothing separates them -------
worst_neg = max(ns)
best_pos = max(ps)
beaten = [s for s in ps if s <= worst_neg]

check("a frame with NO jukebox outscores a frame with one "
      f"(worst negative {worst_neg:.3f} >= lowest positive {min(ps):.3f})",
      worst_neg >= min(ps))
check(f"the overlap swallows most of the positives ({len(beaten)} of "
      f"{len(ps)} sit at or below the worst negative)", len(beaten) >= 5)
# Stated so the negative result is not overstated: the score is NOT pure noise.
# The two closest views (0.766, 0.677) do clear every negative. It is the other
# seven — the jukebox plainly in frame, just not filling it — that the negatives
# outrank, and a detector is no use if it only fires when already on top of the
# thing it is meant to find.
check("the best positive does clear every negative, so the score carries SOME "
      "signal — the failure is that only the two closest views do",
      best_pos > worst_neg)

# WHY THE SELF-MATCH FRAMES ARE HELD OUT, checked rather than asserted: both
# outscore every genuine positive, so leaving them in would have quietly raised
# the positive range to 0.888 and made the overlap look narrower than it is.
_self = [(score(p), p) for p in SELF_MATCH
         if os.path.exists(os.path.join(_ROOT, p))]
check(f"the {len(_self)} template SOURCE frames outscore every genuine "
      f"positive ({', '.join(f'{s:.3f}' for s, _ in sorted(_self))}), which is "
      "why they are excluded from the statistics above",
      len(_self) == 2 and min(s for s, _ in _self) > best_pos)

# Best cut anywhere on the sweep, so "no threshold works" is a MEASUREMENT and
# not a figure of speech. Balanced accuracy, i.e. what the best possible value
# of MATCH_MIN would actually buy.
best = max(
    (0.5 * (sum(1 for v in ps if v >= t) / len(ps)
            + 1 - sum(1 for v in ns if v >= t) / len(ns)), t)
    for t in sorted(set(ps + ns)))
auc = (sum((a > b) + 0.5 * (a == b) for a in ps for b in ns)
       / float(len(ps) * len(ns)))
print(f"\n  best balanced accuracy {best[0]:.3f} at threshold {best[1]:.3f};  "
      f"AUC {auc:.3f} (0.5 = coin flip)")
check("no threshold reaches 0.80 balanced accuracy — this quantity cannot "
      f"carry the decision (best {best[0]:.3f})", best[0] < 0.80)
check(f"AUC stays near chance (got {auc:.3f}, chance 0.500)", auc < 0.70)

# POSITIVE CONTROL. Without this, the two checks above would also pass if the
# arithmetic were wired to report failure unconditionally — the degenerate case
# that made the break/rescue test in map_propose useless. Feed the SAME code a
# cleanly separable pair and it must report separation.
_sep_ps, _sep_ns = [0.90, 0.85, 0.80], [0.30, 0.25, 0.20]
_sep_best = max(
    (0.5 * (sum(1 for v in _sep_ps if v >= t) / len(_sep_ps)
            + 1 - sum(1 for v in _sep_ns if v >= t) / len(_sep_ns)), t)
    for t in sorted(set(_sep_ps + _sep_ns)))
_sep_auc = (sum((a > b) + 0.5 * (a == b) for a in _sep_ps for b in _sep_ns)
            / float(len(_sep_ps) * len(_sep_ns)))
check("POSITIVE CONTROL: separable populations DO score 1.0 / AUC 1.0, so the "
      "two checks above can distinguish overlap from separation",
      _sep_best[0] == 1.0 and _sep_auc == 1.0)


# --- 3. the shipped constant decides nothing ---------------------------------
# 0.468 is the MINIMUM of all 766 frames scored on 2026-09-04, pinned as a
# literal. `MATCH_MIN < 0.468` therefore says something falsifiable about the
# world; `MATCH_MIN < MATCH_MIN` would not.
CORPUS_MIN = 0.468
check(f"MATCH_MIN ({jb.MATCH_MIN}) sits below the whole measured corpus "
      f"({CORPUS_MIN}), so visible() can never return False",
      jb.MATCH_MIN < CORPUS_MIN)

# Pinned EXACTLY, because the comment's position is that 0.30 is the historical
# value left deliberately untouched — not a number anyone may nudge. Without
# this, MATCH_MIN could drift anywhere below 0.468 and nothing would notice,
# which is the drift that produced the original defect. Changing it in EITHER
# direction should require editing this line and the comment together.
check("MATCH_MIN is still the historical 0.30 (uncalibrated, deliberately "
      "unchanged — see the comment in jukebox.py before moving it)",
      jb.MATCH_MIN == 0.30)

_street = os.path.join(_ROOT, _D + "f_0035.01.jpg")
check("visible() calls an OUTDOOR STREET a jukebox at the shipped default — "
      "this is the defect, pinned so it cannot be 'fixed' by picking another "
      "unmeasured number (read the comment in jukebox.py first)",
      jb.visible(Image.open(_street)) is True)

# The one thing the threshold IS good for: an explicit argument still works, so
# callers that measured their own cut are unaffected by any of the above.
check("an explicit threshold argument overrides the default",
      jb.visible(Image.open(_street), threshold=0.99) is False)

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
