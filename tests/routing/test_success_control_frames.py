"""follow_verified must save the START pose on ARRIVAL, and the leg END on both.

Failure frames have been saved since 2026-09-04; successes never were. So when
4 failure frames measured 27-87px apart, there was nothing to compare that
spread against — and a spread without its control says nothing at all. The
claim "the failures cluster tightly, so start-pose variance is not the cause"
is unfalsifiable until the arrivals are measured the same way.

This guards the control group, not the navigation.
"""
import atexit
import os
import os as _os
import shutil
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

    def __init__(self, saved, tag="BEFORE"):
        self.saved = saved
        self.tag = tag
    def save(self, path, *a, **k):
        self.saved.append((path, self.tag))

    def convert(self, *a):
        return self


def run(arrives):
    """Walk a one-node route that either arrives or does not; return files."""
    saved = []
    shots = tempfile.mkdtemp(prefix="ctl_")
    atexit.register(shutil.rmtree, shots, ignore_errors=True)

    old_go = gw.go_to_node_verified
    old_rec = gw.RECORD_RELIABILITY
    gw.RECORD_RELIABILITY = False
    def fake_go(m, node, **kw):
        # A real arrival or failure publishes the frame the leg ended on.
        gw._LAST_LEG_END[node] = Img(saved, tag="LEG-END")
        return arrives
    gw.go_to_node_verified = fake_go
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
def stems(files):
    return {os.path.basename(f).rsplit("_", 1)[0]: tag for f, tag in files}
ok, bad = stems(ok_files), stems(bad_files)
check("an ARRIVAL writes a control frame",
      any(os.sep + "success" + os.sep in f for f, _ in ok_files))
check("...the START pose, from the frame taken before the attempt",
      ok.get("start_bar_jukebox") == "BEFORE")
check("...AND the leg's END frame, the twin of fail_<node>",
      ok.get("ok_bar_jukebox") == "LEG-END")
check("an arrival's frame is NOT filed as a failure",
      not any("fail_" in os.path.basename(f) for f, _ in ok_files))
check("a FAILURE still writes its frame",
      any("fail_" in os.path.basename(f) for f, _ in bad_files))
check("...from the leg's END, not the start",
      bad.get("fail_bar_jukebox") == "LEG-END")
check("...and its START pose beside it, so the control has both groups",
      bad.get("start_bar_jukebox") == "BEFORE")
check("a failure is NOT filed as a control",
      not any(os.sep + "success" + os.sep in f for f, _ in bad_files))


print("\nall green" if not FAILS else f"\n{len(FAILS)} FAILED")
sys.exit(1 if FAILS else 0)
