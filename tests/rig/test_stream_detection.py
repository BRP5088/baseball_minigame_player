"""`streaming()` must ask whether FRAMES ARE ARRIVING, not whether they parse.

It used to require read_bearing() to return a heading. That conflates two
questions: read_bearing has to identify a compass LETTER, which fails on bright
scenes — measured 2026-09-01 at ~6% of world frames, reliably inside the bar
the route ends in.

Twice that day an unattended run died with "stream did not come up within 150s"
while the game was running and plainly visible, because the sampled frame
happened to be one the letter reader could not parse.
"""
import os
import os as _os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.chdir(_ROOT)

import types

import compass
import ensure_stream

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


_real_find, _real_read, _real_pause = (compass.find_bar, compass.read_bearing,
                                       ensure_stream.pm.is_pause_screen)
ensure_stream.pm = types.SimpleNamespace(is_pause_screen=lambda img: False)

# THE HEARTBEAT IS STUBBED OFF for the frame cases below, and that is not
# incidental. These functions read the REAL chiaki log, so with the console
# actually connected every case here returned True through the heartbeat
# fallback and the frame logic was never exercised at all — the test passed or
# failed on whether a PS5 happened to be on, which is the opposite of a test.
_real_hb_since, _real_hb_seen = (ensure_stream._heartbeat_since_last_check,
                                 ensure_stream._heartbeat_seen)
ensure_stream._heartbeat_since_last_check = lambda *a, **k: False
ensure_stream._heartbeat_seen = lambda *a, **k: False

# The case that killed two runs: frames arriving, letters unreadable.
compass.find_bar = lambda img: (64, 223, 1322)
compass.read_bearing = lambda img: None
check(ensure_stream.streaming(object()) is True,
      "a world frame whose compass LETTERS cannot be read was reported as not "
      "streaming — this is the failure that aborted two unattended runs while "
      "the game was running fine")

# Normal case: both work.
compass.read_bearing = lambda img: 89.2
check(ensure_stream.streaming(object()) is True, "a readable world frame")

# Genuinely disconnected: chiaki's own host list has no compass strip at all.
compass.find_bar = lambda img: None
compass.read_bearing = lambda img: None
check(ensure_stream.streaming(object()) is False,
      "a disconnected host-list frame was reported as streaming — this "
      "function exists to detect exactly that state, and a false True means "
      "the run drives input into nothing")

# The pause screen is still streaming even with no strip.
ensure_stream.pm = types.SimpleNamespace(is_pause_screen=lambda img: True)
check(ensure_stream.streaming(object()) is True,
      "the pause menu is a streamed frame and must still count")

# ...and the fallback that the frame stubs above hide: no usable frame at all,
# but the console still answering. This is the case a bright room created twice
# on 2026-09-01, ending two runs while the game was visibly playing.
ensure_stream._heartbeat_seen = lambda *a, **k: True
ensure_stream.pm = types.SimpleNamespace(is_pause_screen=lambda img: False)
compass.find_bar = lambda img: None
compass.read_bearing = lambda img: None
check(ensure_stream.streaming(object()) is True,
      "an unreadable frame with the console still heartbeating was reported as "
      "down — the heartbeat is the console's own word and outranks pixels")
ensure_stream._heartbeat_seen = lambda *a, **k: False
ensure_stream.pm = types.SimpleNamespace(is_pause_screen=_real_pause)

# The non-blocking fast path outranks the picture entirely: if the console has
# answered since the last poll, no frame is even captured. This is the whole
# point of asking the console first — three separate frame readers have each
# reported a healthy stream as dead.
ensure_stream._heartbeat_since_last_check = lambda *a, **k: True
compass.find_bar = lambda img: (_ for _ in ()).throw(
    AssertionError("a frame was read even though the console had already "
                   "answered — the cheap, reliable check must short-circuit"))
check(ensure_stream.streaming(object()) is True,
      "a live heartbeat since the last poll was not enough on its own")
ensure_stream._heartbeat_since_last_check = lambda *a, **k: False
compass.find_bar = _real_find

ensure_stream._heartbeat_since_last_check = _real_hb_since
ensure_stream._heartbeat_seen = _real_hb_seen

compass.find_bar, compass.read_bearing = _real_find, _real_read
ensure_stream.pm = types.SimpleNamespace(is_pause_screen=_real_pause)

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  streaming(): true when frames arrive even if the compass cannot be "
      "read, false only when genuinely disconnected")
