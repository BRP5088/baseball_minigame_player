"""read_bearing must never hand back a confidently wrong heading.

WHAT WAS MEASURED (2026-09-05). Ground truth was built for 2571 of 3628
archived world frames -- demos/, explore/, world_log/ -- from three sources
that had to agree: two or more letters recognised over the FULL threshold
ladder, a pitch measured from the compass's own TICK LATTICE rather than from
the letters, and, where demos/*/input.json exists, the recorded controller.
Only the right stick turns the camera, so a run of frames over which the right
stick never leaves its deadzone MUST all read the same heading; 725 of 726
letter-truth frames inside such a run agreed with their run to within 3
degrees, which is corroboration from an instrument that knows nothing about
OCR. Frames whose truth could not be established were excluded, not guessed.
The labelled subset lives in test_fixtures/compass/labels.json.

    read_bearing as it stood     abstained on 427 of 2571 (16.6%)
                                 median |err| 0.176 deg over 2144 reads
                                 116 reads CONFIDENTLY WRONG by >20 degrees
                                 (every one of them by >46 degrees)

THE CAUSE, and it is a single one. All 116 came from a frame where exactly one
letter was ever recognised -- one in, one out of spacing_consistent. Split by
how many letters survived that check:

    1 letter      268 reads    116 confidently wrong    43.3%
    2 letters    1330 reads      0
    3 letters     546 reads      0

A lone letter cannot be cross-examined. Two of the three anchors below are not
even letters: a scenery blob at x=572 in a frame whose real letters stand at
499.5, 711.7 and 924.0 is read as 'S' or 'W', and with nothing to contradict it
the frame reports 233.0 or 324.0 where the truth is 84.8.

THE TICKS CANNOT SAVE THIS, which is why the fix is a refusal and not a
measurement. A letter swapped for the one opposite is exactly 180 degrees, a
whole number of 10-degree tick spacings, so the tick phase agrees with the
wrong answer as readily as with the right one.

WHY REFUSING IS AFFORDABLE NOW. Two letters used to be the only way to measure
the SCALE, and demanding them took the logged frames from 17/17 readable to
7/17 -- unaffordable. The tick lattice supplies the scale from marks nothing
has to recognise, so the only job left for a second letter is confirming the
first one's identity.

MEASURED OVER THE 2571 LABELLED FRAMES, warm scale cache, pytesseract fallback
disabled, four flags switched independently:

    arm                          abstain   reads   confidently wrong >20 deg
    baseline                      16.6%     2144     116   5.41% of reads
    +SIGNED_SPACING               16.6%     2144     116   byte-identical
    +USE_TICK_LATTICE             17.3%     2125      97
    +REQUIRE_TWO_LETTERS          27.0%     1877       0
    +POOL_THRESHOLDS (all four)    5.0%     2442       2   0.08% of reads

Both axes move the right way at once, which is the part worth checking if this
ever regresses: refusing an uncorroborated letter costs coverage, and going
back for the letter that would corroborate it more than pays that back. Of the
149 frames the shipped reader now abstains on where the baseline answered, 70
have established truth and the BASELINE WAS WRONG ON 62 OF THEM. Of the 471 it
now reads where the baseline abstained, 367 have truth and 366 are right.

At 1920x1080 -- the live capture geometry, 289 labelled frames -- the baseline
was already 0 confidently wrong at a 0.7% abstain rate, and this takes the
abstain rate to 0.0%. The 116 failures are all at the 1400x787 of the archived
demo recordings, which is 0.73x the linear resolution the live rig captures at.
Read that as a stress test, not as today's failure rate.

COST, measured interleaved in one process on 240 frames x 3 reps (arms measured
in separate processes could not be compared -- the machine load moved between
them): median 24.4ms -> 32.2ms per read, mean 25.3 -> 48.1. At ~52 reads a
trial that is under a second.

NOT PROMISED: perfection. Two reads out of 2442 are still wrong by 150 degrees,
both in demos/walk_20260827_214446, both from two SPURIOUS blobs that happen to
sit a plausible pitch apart and corroborate each other.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image

import compass

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


FIX = os.path.join(_ROOT, "test_fixtures", "compass")
LABELS = os.path.join(FIX, "labels.json")

# A missing corpus is a failure, not a skip. A test that cannot run must not
# report success -- the whole point of this file is that a confident answer
# with nothing behind it is worse than no answer.
if not os.path.exists(LABELS):
    print(f"FAIL missing labelled corpus {LABELS}")
    sys.exit(1)

CORPUS = json.load(open(LABELS))["frames"]
print(f"  labelled corpus: {len(CORPUS)} frames")


def err(a, b):
    return abs(compass.angular_error(a, b))


# --- 1. the property that matters ------------------------------------------
# Abstaining is allowed on any frame. Being WRONG is not. 2.0 degrees is well
# outside the 0.176 median the reader already achieves and well inside the 46.9
# degrees of the smallest measured failure, so it sits between the populations
# rather than inside either.
worst = 0.0
for f in CORPUS:
    img = Image.open(os.path.join(FIX, f["file"]))
    got = compass.read_bearing(img)
    if got is None:
        continue
    e = err(f["truth_deg"], got)
    worst = max(worst, e)
    check(f"{f['file']}: read {got:.2f} vs truth {f['truth_deg']:.2f} "
          f"(|err| {e:.2f})", e <= 2.0)
print(f"  worst error over frames that were read: {worst:.3f} deg")

# --- 2. the three anchors, pinned by the value they used to return ----------
# Named individually so that a regression says WHICH failure came back. The
# recorded values are what read_bearing actually returned on these frames
# before REQUIRE_TWO_LETTERS; each is the reading of a single unchecked blob.
ANCHORS = {
    "wrong_one_letter_180.jpg": (84.82, 264.92),
    "wrong_one_letter_scenery.jpg": (84.82, 233.00),
    "wrong_one_letter_quadrant.jpg": (84.82, 324.00),
}
for name, (truth_deg, was) in ANCHORS.items():
    got = compass.read_bearing(Image.open(os.path.join(FIX, name)))
    check(f"{name}: no longer returns the old {was:.2f} "
          f"(got {'None' if got is None else f'{got:.2f}'})",
          got is None or err(got, was) > 20.0)
    check(f"{name}: is either right or silent",
          got is None or err(got, truth_deg) <= 2.0)

# --- 3. the switches that do the work --------------------------------------
# MUTATION GUARDS. Each says which flag is holding which line, and every one of
# them must FAIL if the flag stops mattering -- otherwise this file is testing
# nothing. Restored immediately in a finally.
def with_flags(**flags):
    saved = {k: getattr(compass, k) for k in flags}
    for k, v in flags.items():
        setattr(compass, k, v)
    try:
        out = {}
        for name, (truth_deg, was) in ANCHORS.items():
            out[name] = compass.read_bearing(Image.open(os.path.join(FIX, name)))
        return out
    finally:
        for k, v in saved.items():
            setattr(compass, k, v)


def bad(out):
    return sum(1 for n, g in out.items()
               if g is not None and err(g, ANCHORS[n][0]) > 20.0)


# The corpus anchors are REAL regressions: with both guards off, the reader
# returns all three wrong bearings again.
off = with_flags(REQUIRE_TWO_LETTERS=False, POOL_THRESHOLDS=False)
check(f"with both guards off, all {len(ANCHORS)} wrong bearings come back "
      f"({bad(off)} did)", bad(off) == len(ANCHORS))

# EITHER guard alone is enough on these frames, which is the point: they attack
# the same failure from opposite directions. REQUIRE_TWO_LETTERS refuses an
# uncorroborated letter; POOL_THRESHOLDS goes and finds the letter that
# corroborates or contradicts it.
check("REQUIRE_TWO_LETTERS alone stops all three",
      bad(with_flags(REQUIRE_TWO_LETTERS=True, POOL_THRESHOLDS=False)) == 0)
check("POOL_THRESHOLDS alone stops all three",
      bad(with_flags(REQUIRE_TWO_LETTERS=False, POOL_THRESHOLDS=True)) == 0)

for flag in ("REQUIRE_TWO_LETTERS", "POOL_THRESHOLDS", "SIGNED_SPACING",
             "USE_TICK_LATTICE"):
    check(f"{flag} ships ON", getattr(compass, flag) is True)

# WHAT POOLING BUYS, and it is coverage rather than safety. The shipped ladder
# stops at the first threshold yielding two BLOBS; on these two frames the
# second letter separates only at 110, which BLOB_THRESHOLDS never reaches.
COVERAGE = {"abstains_but_readable_1920.jpg": 288.173,
            "abstains_but_readable_1920_b.jpg": 103.530}
for name, want in COVERAGE.items():
    got = compass.read_bearing(Image.open(os.path.join(FIX, name)))
    check(f"{name}: pooling recovers it ({got})",
          got is not None and err(got, want) <= 2.0)
saved = compass.POOL_THRESHOLDS
compass.POOL_THRESHOLDS = False
try:
    still = [n for n in COVERAGE
             if compass.read_bearing(Image.open(os.path.join(FIX, n))) is None]
    check(f"with POOL_THRESHOLDS off both go back to abstaining "
          f"({len(still)} of {len(COVERAGE)} did)", len(still) == len(COVERAGE))
finally:
    compass.POOL_THRESHOLDS = saved

check("threshold 110 is in the fine ladder and NOT in the shipped one -- "
      "that gap is what pooling closes",
      110 in compass.BLOB_THRESHOLDS_FINE
      and 110 not in compass.BLOB_THRESHOLDS)

# --- 4. the tick lattice reproduces the letters' own pitch ------------------
# MEASURED on this exact frame: the letters stand at S 615.0, W 906.4, N 1198.0,
# i.e. 291.5px per 90 degrees. The ticks are fitted from marks no recogniser
# ever sees. Both numbers are LITERALS: checking the lattice against
# PITCH_PX_PER_90 would pass for any value of either.
img = Image.open(os.path.join(FIX, "three_letters_1920.jpg"))
w, h = img.size
bar_y, _, _ = compass.find_bar(img)
band = max(14, int(h * 0.020))
vmid, vw = (w - 1) / 2.0, float(w - 1)
x0, x1 = int(vmid - vw * 0.235), int(vmid + vw * 0.235)
fit = compass.fit_tick_lattice(
    compass.tick_peaks(img.convert("L"), bar_y, x0, x1, band), w)
check("the tick lattice fits at all", fit is not None)
if fit is not None:
    d, c, inliers, rms = fit
    print(f"  tick spacing {d:.4f}px  rms {rms:.4f}px  {inliers} marks on it")
    check(f"9 tick spacings = {9 * d:.2f} reproduces the letters' 291.5px "
          f"per 90 deg to within 1%", abs(9 * d - 291.5) <= 2.915)
    check(f"the fit is sub-pixel (rms {rms:.3f} < 1.0)", rms < 1.0)
    # The letters sit HALF a spacing off the ticks: the ticks are the odd
    # multiples of 5 degrees. Measured offsets on this frame: 0.14, 0.03, 0.04.
    for cx in (615.0, 906.44, 1198.0):
        off = (cx - c - d / 2.0) % d
        off = min(off, d - off)
        check(f"letter at x={cx} sits on the half-lattice (off {off:.2f}px)",
              off < 1.0)
    # And the phase alone gives the heading modulo 10 degrees. Truth 286.389.
    phase = compass.tick_phase_deg(vmid, d, c)
    check(f"tick phase {phase:.3f} matches the truth 286.389 mod 10",
          abs(phase - 286.389 % 10.0) < 0.2)

# --- 5. the letters' ORDER is evidence -------------------------------------
# Bearing increases to the RIGHT along the bar, so 'W' then 'S' one pitch apart
# is impossible -- that pair needs three pitches. Comparing unsigned gaps
# accepted it. This hole has not yet cost a measured read (all 116 failures
# were single-letter frames, so the check was never reached) but it can only
# ever turn a read into an abstention, and it is cheap.
P = 207.0
check("W then S at one pitch is refused",
      compass.spacing_consistent([(713.5, "W"), (920.5, "S")], P) == [])
check("E then S at one pitch is accepted",
      len(compass.spacing_consistent([(713.5, "E"), (920.5, "S")], P)) == 2)
check("the order is what decides, not the argument order",
      len(compass.spacing_consistent([(920.5, "S"), (713.5, "E")], P)) == 2)
check("W then N across the wrap is accepted",
      len(compass.spacing_consistent([(290.0, "W"), (500.0, "N")], 210.0)) == 2)
check("N, E, S in order are all kept",
      len(compass.spacing_consistent(
          [(498.0, "N"), (710.0, "E"), (927.0, "S")], 212.5)) == 3)

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
