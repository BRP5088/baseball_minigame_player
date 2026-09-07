"""window_drift() must be ABLE to fail, and preflight must be able to block.

THE BUG THIS GUARDS. save_window_reference() had ZERO callers — the only
mention of it anywhere was inside a preflight help STRING — so
window_reference.json was never written, _load_window_reference() always
returned None, and window_drift() always took its `reference is None` branch
and reported ok=True. The guard could not fail, on any machine, ever.

What it guards, from preflight's own comment: "a 58px displacement changed
nothing, 110px silently FLIPPED a ban-grid cell — banning a different card,
with no error raised." That is the wrong card banned in a $50 match.

The catalogue shape: an unarmed guard and a satisfied guard have identical
output. `Bretts_walk.py calibrate-window` now arms it.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import input_controller as ic

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


HERE = (100.0, 100.0, 1920.0, 1080.0)


def drift_with(rect, reference):
    """window_drift() against a faked window position."""
    old = ic.game_window_rect
    ic.game_window_rect = lambda: rect
    try:
        return ic.window_drift(reference=reference)
    finally:
        ic.game_window_rect = old


# --- the guard must PASS when nothing moved -------------------------------
ok, drift, _rect, _ref = drift_with(HERE, HERE)
check("an unmoved window is ok", ok is True and drift == 0)

# --- and it must FAIL when the window moved past the limit ----------------
# 110px is the measured displacement that flipped a ban-grid cell.
moved = (HERE[0] + 110, HERE[1], HERE[2], HERE[3])
ok, drift, _rect, _ref = drift_with(moved, HERE)
check("a 110pt displacement is REJECTED", ok is False)
check("and the drift is reported, not swallowed", drift == 110)

# The limit must sit below the damage threshold. Pinned as a literal: reading
# WINDOW_DRIFT_MAX_PT on both sides would pass for any value.
check("the limit is below the 110pt that flipped a cell",
      ic.WINDOW_DRIFT_MAX_PT < 110)

# --- a small displacement is tolerated (58px changed nothing, measured) ---
small = (HERE[0] + 5, HERE[1], HERE[2], HERE[3])
ok, _d, _r, _ref = drift_with(small, HERE)
check("a 5pt displacement is tolerated", ok is True)

# --- no reference is 'ok' but must be DISTINGUISHABLE from a good check ---
ok, drift, _rect, ref = drift_with(HERE, None)
_saved = ic._load_window_reference()
check("with no reference the drift is None, not 0.0",
      drift is None and (ok is True or _saved is not None))

# --- a missing window must be REJECTED, not treated as fine ---------------
ok, _d, rect, _ref = drift_with(None, HERE)
check("a window that cannot be found is REJECTED", ok is False and rect is None)

# --- the arming path must exist and be reachable --------------------------
check("save_window_reference exists", callable(ic.save_window_reference))
sys.path.insert(0, os.path.join(_ROOT, "tools"))
import calibrate_window
_calls = []
_saved_srw = ic.save_window_reference
ic.save_window_reference = lambda: _calls.append(1) or (0, 0, 100, 100)
try:
    rc = calibrate_window.main()
finally:
    ic.save_window_reference = _saved_srw
check("tools/calibrate_window.py arms it by CALLING save_window_reference, "
      "so it is not just a docstring", _calls == [1] and rc == 0)

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
