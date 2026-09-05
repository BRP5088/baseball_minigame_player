"""With no game window, capture must RAISE — never return the desktop.

WHY THIS EXISTS
---------------
fast_capture() used to fall back to mss.monitors[1] when it could not find the
game window — the exact behaviour its own docstring explains is wrong. On
2026-09-02, with chiaki not running at all, that returned the CLAUDE DESKTOP
WINDOW. Every detector then read it happily: streaming() answered True, the
picture measured as "updating", and a whole setup pass was spent analysing a
screenshot of the conversation instead of the game.

Wrong pixels are worse than no pixels, because nothing downstream can tell.
"""
import os
import os as _os
import sys
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import compass
import ensure_stream

fails = []


def check(c, m):
    if not c:
        fails.append(m)


import input_controller as ic
_real_rect = ic.game_window_rect
ic.game_window_rect = lambda: None
try:
    raised = None
    try:
        compass.fast_capture()
    except compass.NoGameWindow as e:
        raised = str(e)
    except Exception as e:
        raised = f"WRONG TYPE: {type(e).__name__}"
    check(raised is not None and "WRONG TYPE" not in raised,
          f"fast_capture returned pixels with no game window (got {raised!r}). "
          f"It used to hand back the desktop, and a session was spent reading "
          f"the Claude window as if it were the game.")
    check(raised and "chiaki" in raised.lower(),
          f"the error {raised!r} does not say what is wrong; an unattended run "
          f"is diagnosed from this string")

    # streaming() must treat it as "not streaming", not explode.
    try:
        got = ensure_stream.streaming()
        ok = got is False
    except Exception as e:
        ok = False
        fails.append(f"streaming() raised {type(e).__name__} with no game "
                     f"window; that state is exactly what it exists to report")
    check(ok, "streaming() did not answer False with no game window")

    # is_frozen() must not claim a frozen picture when there is no picture.
    try:
        check(ensure_stream.is_frozen() is False,
              "is_frozen() said True with no game window; there is nothing to "
              "be frozen, and a spurious True triggers a chiaki restart")
    except Exception as e:
        fails.append(f"is_frozen() raised {type(e).__name__} with no window")
finally:
    ic.game_window_rect = _real_rect

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  no game window: capture raises with a diagnostic message, streaming() "
      "answers False, is_frozen() does not fabricate a freeze")
