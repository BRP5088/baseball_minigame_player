"""The mapping recorder must survive a bad frame and keep actions in the timeline.

WHY THIS EXISTS
---------------
A mapping walk is a LIVE pass that cannot be repeated identically, so the
recorder failing halfway costs the whole pass. And the graph's edge costs are
recovered offline by pairing walk commands with the frames around them, so a
command that does not reach the index may as well not have happened.

Both properties are the kind that look fine until the one run that matters.
"""
import json
import os
import os as _os
import shutil
import sys
import tempfile
import time
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

from PIL import Image

import world_log

fails = []


def check(c, m):
    if not c:
        fails.append(m)


# Fake the three modules the recorder reads, so nothing touches the screen.
grabs = {"n": 0, "fail_on": None}


def fake_capture():
    grabs["n"] += 1
    if grabs["fail_on"] is not None and grabs["n"] == grabs["fail_on"]:
        raise RuntimeError("simulated capture failure")
    return Image.new("RGB", (64, 36), (30, 30, 30))


sys.modules["compass"] = types.SimpleNamespace(
    fast_capture=fake_capture, read_bearing=lambda img: 90.0)
sys.modules["places"] = types.SimpleNamespace(
    identify=lambda img: ("bar_exit_corner", 0.71, 0.20))
sys.modules["table_prompt"] = types.SimpleNamespace(at_table=lambda img: False)

tmp = tempfile.mkdtemp(prefix="worldlog-test-")
try:
    # --- a failing grab must not kill the session --------------------------
    grabs["n"] = 0
    grabs["fail_on"] = 2
    rec = world_log.Recorder("unit", hz=25.0, root=tmp).start()
    rec.note("turn_to", bearing=90)
    time.sleep(0.5)
    rec.note("walk_forward", seconds=3.0)
    time.sleep(0.4)
    d = rec.stop()

    rows = world_log.load(d)
    frames = [r for r in rows if r["kind"] == "frame"]
    notes = [r for r in rows if r["kind"] == "note"]

    check(len(frames) >= 4,
          f"only {len(frames)} frames recorded over ~0.9s at 25Hz — the loop "
          "stopped early, which on a live walk loses the pass")
    check(any("error" in f for f in frames),
          "the simulated grab failure produced no row at all; a dropped frame "
          "must be VISIBLE in the index, not silently absent")
    check(len(frames) > sum(1 for f in frames if "error" in f),
          "every frame errored — the recorder did not recover from one bad grab")

    # --- actions must be in the SAME timeline as the frames ---------------
    check(len(notes) == 2, f"recorded {len(notes)} notes, expected 2")
    check([n["action"] for n in notes] == ["turn_to", "walk_forward"],
          f"notes came back as {[n['action'] for n in notes]}")
    check(notes[0]["bearing"] == 90 and notes[1]["seconds"] == 3.0,
          "note() dropped its fields; the leg's duration is unrecoverable "
          "without them")
    check(notes[0]["t"] < notes[1]["t"],
          "note timestamps are not ordered, so commands cannot be paired with "
          "the frames around them")
    check(any(f["t"] > notes[0]["t"] for f in frames),
          "no frame is timestamped after the first note — frames and notes are "
          "not on one clock, and legs are recovered by pairing them")

    # --- metadata that the offline graph build depends on -----------------
    good = [f for f in frames if "error" not in f]
    check(all(f.get("heading") == 90.0 for f in good),
          "heading missing from frame rows")
    check(all(f.get("place") == "bar_exit_corner" for f in good),
          "place guess missing from frame rows")
    check(all("file" in f for f in good), "frame rows have no filename")
    check(all(os.path.exists(os.path.join(d, f["file"])) for f in good),
          "an index row names a file that was never written")

    # --- a failure ESCAPING _capture_row must not kill the thread either --
    # The inner try/except covers grab and save. Anything else — a change to
    # the metadata block, a module reloaded underneath it — reaches the loop's
    # own handler, and if that handler is narrow the recorder dies silently
    # mid-walk and the pass is lost with no error in the index.
    rec2 = world_log.Recorder("boom", hz=25.0, root=tmp)
    _real_capture = rec2._capture_row
    calls = {"n": 0}

    def exploding():
        calls["n"] += 1
        if calls["n"] == 1:
            raise KeyError("something unforeseen inside _capture_row")
        return _real_capture()

    rec2._capture_row = exploding
    rec2.start()
    time.sleep(0.4)
    d2 = rec2.stop()
    rows2 = world_log.load(d2)
    check(any("error" in r for r in rows2),
          "an exception escaping _capture_row produced no error row — the "
          "recorder swallowed it, so a dead mapping walk looks like a quiet one")
    check(len(rows2) >= 3,
          f"only {len(rows2)} row(s) after an unforeseen exception — the "
          "recorder thread died instead of carrying on, losing the live pass")

    # --- load() must impose time order ------------------------------------
    # Notes come from the CALLER's thread and frames from the recorder's, so
    # the file can interleave out of order. Legs are recovered by reading
    # actions and frames in sequence, and an out-of-order stream pairs a walk
    # command with frames from before it.
    d3 = os.path.join(tmp, "ordering")
    os.makedirs(d3, exist_ok=True)
    with open(os.path.join(d3, "index.jsonl"), "w") as fh:
        for t in (2.0, 0.5, 1.0):
            fh.write(json.dumps({"kind": "note", "t": t, "action": f"a{t}"}) + "\n")
    got = [r["t"] for r in world_log.load(d3)]
    check(got == sorted(got),
          f"load() returned rows in file order {got}; two threads write this "
          "file, so it must be sorted by time or commands pair with the wrong "
          "frames")

    # --- it must write UNDER world_log, never into screenshot_log ---------
    check(world_log.SESSION_ROOT == "world_log",
          f"mapping frames default to {world_log.SESSION_ROOT!r}; they must be "
          "kept out of screenshot_log/, whose archives are all match play and "
          "which made a clustering pass return nothing but card art")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  world_log: survives a failed grab, keeps commands and frames on one "
      "clock, records heading/place per frame, and writes outside screenshot_log")
