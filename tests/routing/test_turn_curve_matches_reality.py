"""Guard turn_curve's table against drifting away from measured reality.

MEASURED is 0.30s-hold averages; VERIFIED_1S is an independent live check at a
different hold length. They should agree within a few percent across the band
the system actually uses. If someone "corrects" the table from a steady-state
number, this fails.
"""
import os
import os as _os
import sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import turn_curve as tc

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


TOL = 0.08          # 8%: the measured spread is 3.9-5.6%, so this is not slack

for mag, measured in tc.VERIFIED_1S:
    if mag > 0.90:
        # Outside the usable band, so mag_for never returns it — but the entry
        # still anchors the top of the interpolation, so guard it loosely
        # rather than skipping it entirely. Skipping is how a "corrected"
        # 1.00 entry slipped past unnoticed.
        err = abs(tc.rate_for(mag) - measured) / measured
        check(f"rate_for({mag:.2f}) is not wildly off ({tc.rate_for(mag):.1f} "
              f"vs {measured:.2f}, {err:.1%})", err <= 0.12)
        continue
    err = abs(tc.rate_for(mag) - measured) / measured
    check(f"rate_for({mag:.2f}) within {TOL:.0%} of the live measurement "
          f"({tc.rate_for(mag):.1f} vs {measured:.2f}, {err:.1%})", err <= TOL)

# The literal 0.90, NOT tc.USABLE_MAX: asserting against the constant makes the
# test self-referential — raise USABLE_MAX to 1.0 and the assertion raises with
# it and still passes, which is exactly what happened the first time this was
# mutation-tested.
USABLE_LIMIT = 0.90
check(f"USABLE_MAX is still {USABLE_LIMIT} (full stick measured 4.8x worse)",
      abs(tc.USABLE_MAX - USABLE_LIMIT) < 1e-9)

for want in (10, 75, 200, 500, 10_000):
    check(f"mag_for({want}) stays inside the usable band",
          tc.mag_for(want) <= USABLE_LIMIT + 1e-9)

# plan_turn is what turn_to actually calls.
for deg in (2, 15, 90, 180, 359):
    mag, secs = tc.plan_turn(deg)
    check(f"plan_turn({deg}) magnitude is usable ({mag:.2f})",
          mag <= USABLE_LIMIT + 1e-9)
    check(f"plan_turn({deg}) asks for a positive time ({secs:.2f}s)", secs > 0)

# MEASURED is a RECORD OF MEASUREMENTS, not a set of tunables. Pinning it
# exactly is the only guard that catches an edit which happens to stay inside a
# percentage tolerance — e.g. replacing the 1.00 entry's 0.30s-hold average
# (197.7) with a steady-state figure (220.5) is only 5.3% away from an
# independent check, so no reasonable tolerance rejects it, yet it silently
# changes what the table MEANS. Changing any of these requires a new
# measurement and a new comment saying how it was taken.
RECORDED = [
    (0.20, 0.4), (0.30, 1.6), (0.40, 7.5), (0.50, 16.2), (0.60, 22.5),
    (0.70, 37.3), (0.80, 58.2), (0.90, 74.8), (1.00, 197.7),
]
check("MEASURED still holds the values that were actually measured",
      tc.MEASURED == RECORDED)

# VERIFIED_1S is the INDEPENDENT check. Editing it to agree with MEASURED would
# make every tolerance check above pass trivially while destroying the only
# evidence that the table matches reality — a test that passes because the
# comparison was rigged is worse than no test.
check("VERIFIED_1S still holds the live 2026-09-03 measurements",
      tc.VERIFIED_1S == [(0.70, 35.49), (0.90, 72.01), (1.00, 209.45)])

# The two datasets measure DIFFERENT things and must stay separate.
check("MEASURED and VERIFIED_1S are distinct tables",
      tc.MEASURED != tc.VERIFIED_1S)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
