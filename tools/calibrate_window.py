"""Arm the chiaki-window drift guard. Run ONCE, on a ban screen that reads correctly.

    .venv/bin/python -B tools/calibrate_window.py

THE GUARD THIS ARMS HAD NEVER FIRED. input_controller.window_drift() cannot
report drift until a reference exists, and save_window_reference() had ZERO
callers -- it was named only inside a preflight help string, so
window_reference.json was never written and the check could only ever say
"ok". What it guards, measured: a 58px displacement changed nothing, 110px
silently FLIPPED a ban-grid cell, banning a different card with no error.

Re-running this re-baselines to wherever the window is now, which silently
forgives real drift, so do not run it to make preflight quiet. Ported from
`Bretts_walk.py calibrate-window` when that entry point was deleted (2026-09-07).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def main():
    import input_controller as ic
    rect = ic.save_window_reference()
    if rect is None:
        print("the chiaki window is not open -- start the stream first")
        return 1
    print(f"calibrated: window at {tuple(int(v) for v in rect)}")
    print(f"preflight will now fail if it moves more than {ic.WINDOW_DRIFT_MAX_PT:.0f}pt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
