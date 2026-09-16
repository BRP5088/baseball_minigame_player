"""The gameplay check must be resolution-independent and reject overlays.

Two bugs this guards, both found live:

  * RETICLE_XY_FRAC pointed at plain background in the game-window capture, so
    in_gameplay() returned False on real gameplay.
  * The box sizes were absolute pixels, so the ring sampled a different area
    depending on capture width.

And one design point: brightness alone cannot separate gameplay from the PS5
home overlay (their ranges overlap), so the check is on the reticle's SHAPE.
"""

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import
_os.chdir(_ROOT)

import glob

from PIL import Image

import input_controller as ic

# FIXTURES, NOT demos/. demos/ is GITIGNORED, so these frames do not exist on a
# fresh clone and this file could not run at all for anyone else. The copies in
# test_fixtures/walk_frames/ ARE the every-20th sample this line used to take,
# so the stride is gone -- applying it again would leave 2 frames.
frames = sorted(glob.glob("test_fixtures/walk_frames/f_*.jpg"))
assert frames, "no walk frames to test against"

# every frame of a walk is gameplay, at every capture width this codebase uses
for f in frames[:6]:
    src = Image.open(f)
    for w in (1400, 1920, 2000):
        im = src.resize((w, int(src.height * w / src.width)))
        assert ic.in_gameplay(im), (
            f"{_os.path.basename(f)} at {w}px read as NOT gameplay "
            f"(dotness {ic.reticle_dotness(im):.1f}) — the check is not "
            "resolution-independent")

# AND THE SCREENS THAT MUST BE REJECTED — COMMITTED, NAMED, AND MANDATORY.
#
# This half used to loop over "/tmp/reconnect_state.png" and "/tmp/wake_state.png", guarded
# by `if os.path.exists(p)`. NOTHING IN THE REPOSITORY CREATES THOSE FILES, so the body
# never ran, and the line below still printed "pause and overlay screens rejected" every
# time. The test asserted, in its own output, a thing it had never checked -- and CLAUDE.md
# forbids /tmp for anything that matters precisely because it is emptied.
#
# These are real frames in the repo. Every one must be rejected: in_gameplay() gates where
# INPUT is sent, so accepting a menu means keystrokes land on a menu.
NEGATIVES = [
    _os.path.join("test_fixtures", "screens", "ban_screen__0.jpg"),
    _os.path.join("test_fixtures", "ban_screen", "ban_0of3_1920x1080.jpg"),
    _os.path.join("test_fixtures", "give_up", "negative_ban_screen.jpg"),
    _os.path.join("test_fixtures", "give_up", "negative_gameplay_turn.jpg"),
    # chiaki's OWN window, not the game at all: if this reads as gameplay the rig would
    # send input to the client while the console shows nothing (CLAUDE.md section 3 records
    # streaming() answering True on exactly this frame with the console asleep).
    _os.path.join("test_fixtures", "not_streaming", "hostlist_standby.png"),
]
missing = [p for p in NEGATIVES if not _os.path.exists(p)]
assert not missing, (
    f"negative fixtures are missing: {missing}. This half is MANDATORY — a skipped "
    "negative is how this file spent months claiming to reject overlays it never saw.")

for p in NEGATIVES:
    im = Image.open(p).convert("RGB")
    assert not ic.in_gameplay(im), (
        f"{p} accepted as gameplay (dotness {ic.reticle_dotness(im):.1f}) — in_gameplay() "
        "gates where INPUT is sent, so this would put keystrokes into a menu")
    # and at the other capture widths, for the same reason the positives are resized
    for w in (1400, 2000):
        small = im.resize((w, int(im.height * w / im.width)))
        assert not ic.in_gameplay(small), (
            f"{p} accepted as gameplay at {w}px (dotness "
            f"{ic.reticle_dotness(small):.1f}) — the rejection is not scale-free")

print(f"OK: gameplay detected at 1400/1920/2000px across {len(frames[:6])} frames; "
      f"{len(NEGATIVES)} non-gameplay screens rejected at three widths each")
