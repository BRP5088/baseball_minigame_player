"""follow_verified must save the start pose on ARRIVAL, not only on failure.

Failure frames have been saved since 2026-09-04; successes never were. So when
4 failure frames measured 27-87px apart, there was nothing to compare that
spread against — and a spread without its control says nothing at all. The
claim "the failures cluster tightly, so start-pose variance is not the cause"
is unfalsifiable until the arrivals are measured the same way.

This guards the control group, not the navigation.
"""
import os
import os as _os
import sys
import tempfile
import types

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import graph_walk as gw

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class Img:
    """Stands in for a PIL image; records where it was written."""

    def __init__(self, saved):
        self.saved = saved

    def save(self, path, *a, **k):
        self.saved.append(path)

    def convert(self, *a):
        return self


def run(arrives):
    """Walk a one-node route that either arrives or does not; return files."""
    saved = []
    shots = tempfile.mkdtemp(prefix="ctl_")

    old_go = gw.go_to_node_verified
    old_rec = gw.RECORD_RELIABILITY
    gw.RECORD_RELIABILITY = False
    gw.go_to_node_verified = lambda *a, **k: arrives
    try:
        gw.follow_verified(
            object(), ["bar_jukebox"],
            capture=lambda: Img(saved),
            read_heading=lambda: 0.0,
            log=lambda *a: None,
            attempts=1, shots=shots,
        )
    except Exception as e:                    # the fake map is not a real one
        print(f"   (follow_verified raised {type(e).__name__}, continuing)")
    finally:
        gw.go_to_node_verified = old_go
        gw.RECORD_RELIABILITY = old_rec
    return saved


ok_files = run(True)
bad_files = run(False)

check("an ARRIVAL writes a control frame",
      any(os.sep + "success" + os.sep in f for f in ok_files))
check("an arrival's frame is NOT filed as a failure",
      not any("fail_" in os.path.basename(f) for f in ok_files))
check("a FAILURE still writes its frame",
      any("fail_" in os.path.basename(f) for f in bad_files))
check("a failure is NOT filed as a control",
      not any(os.sep + "success" + os.sep in f for f in bad_files))

print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
