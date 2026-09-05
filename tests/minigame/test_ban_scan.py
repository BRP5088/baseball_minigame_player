"""Behavioural tests for read_full_ban_collection() — offline, no game, no API.

WHY THIS EXISTS
---------------
QA round 1 (2026-08-25) found that `TRUST_ROSTER_ONLY`, the fully-local ban
path, and the tactics early-stop had ZERO behavioural coverage: flipping the
flag, deleting the fast path, or deleting the early stop each left all nine
then-existing test files green. `read_full_ban_collection()` was never executed
by any test at all — only its constants were inspected.

That is the same class of gap that let the C5 double-debit ship: the mechanism
was reasoned about, not exercised.

Everything here is faked at the boundary: `press` is a recorder, captures come
from real logged frames, and vision raises if called (so a test that expects a
local-only path FAILS rather than silently making an API call).
"""

import os as _os, sys as _sys
# Tests live in tests/ but the modules and fixtures they use sit at the
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# project root, so the root goes on sys.path and _ROOT anchors any path
# that used to be derived from __file__ back when this file lived there.
_sys.path.insert(0, _ROOT)


import os
import sys
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import glob

from PIL import Image

import orchestrator as o

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


FRAMES = sorted(glob.glob(os.path.join(_ROOT,
                                       "test_fixtures", "ban_scan", "*.jpg")))
if not FRAMES:
    # NOT a silent skip: orchestrator prunes screenshot_log/, so a green suite
    # with this file doing nothing is exactly the failure mode to avoid.
    raise SystemExit(
        "no reference frames in test_fixtures/ban_scan/ — ban-scan "
        "coverage would be silently disabled; restore the fixtures")

_REAL = Image.open(FRAMES[0]).convert("RGB")

# Module-level so the cache survives across every Rig() in this file — each
# block would otherwise pay the ~6.4s lock detection again for the same image.
_REAL_LOCK = o.detect_ban_grid_locked
_LOCK_CACHE = {}


class Rig:
    """Fakes every boundary read_full_ban_collection touches."""

    def __init__(self, frames=None, vision_raises=True, scroll_override=None):
        self.presses = []
        self.captures = 0
        self.vision_calls = 0
        self.ocr_calls = 0
        self.frames = frames or [_REAL]
        # None = healthy (scrollbar follows the press count). An int pins the
        # scrollbar to one level, simulating a dropped move_down.
        self.scroll_override = scroll_override
        self.downs = 0

    def _press(self, k, *a, **kw):
        self.presses.append(k)
        if k == "move_down":
            self.downs += 1
        elif k == "move_up":
            self.downs = max(0, self.downs - 1)

    def __enter__(self):
        self.saved = {}
        def cap(*a, **k):
            self.captures += 1
            return self.frames[min(self.captures - 1, len(self.frames) - 1)]
        def vision(*a, **k):
            self.vision_calls += 1
            raise AssertionError(
                "vision was called on a path that must be fully local")
        def ocr(c):
            self.ocr_calls += 1
            return None
        # Memoise lock detection per frame. The scan calls it once per scroll
        # iteration on the SAME fixture image, and each call runs two
        # MaxFilter(41) passes (~6.4s). That made this file take 181s and, since
        # test_no_side_effects re-runs every test in a subprocess, it dominated
        # the whole suite — which in turn made each QA mutation cycle minutes
        # long. Nothing here is testing the lock detector (test_ban_grid_locked
        # does that against known frames); this file tests the SCAN LOGIC around
        # it, so a memoised real result is the correct fixture, not a stub.
        _real_lock = _REAL_LOCK
        def lock(img):
            key = id(img)
            if key not in _LOCK_CACHE:
                _LOCK_CACHE[key] = _real_lock(img)
            return _LOCK_CACHE[key]

        # A HEALTHY scroll: the scrollbar agrees with the press count. The
        # fixture returns the same image at every depth, so without this the
        # real reader correctly reports a desync on every batch and the test
        # measures the desync path instead of the happy path.
        def scroll_level(img):
            if self.scroll_override is not None:
                return self.scroll_override, 500
            # Mirror the production formula exactly: presses advance by 2 per
            # batch and top_row = max(0, presses - 1). Anything else reports a
            # desync on every batch and the test measures the wrong path.
            return max(0, self.downs - 1), 500

        patches = {
            "read_ban_scroll_level": scroll_level,
            "detect_ban_grid_locked": lock,
            "capture_screenshot_image": cap,
            "read_ban_row_cards": vision,
            "ocr_ban_card_name": ocr,
            "press": self._press,
            "wait_for_screen_to_settle": lambda *a, **k: True,
        }
        for n, f in patches.items():
            if hasattr(o, n):
                self.saved[n] = getattr(o, n)
                setattr(o, n, f)
        o._cached_ban_collection = None
        return self

    def __exit__(self, *a):
        for n, f in self.saved.items():
            setattr(o, n, f)
        o._cached_ban_collection = None
        return False


# --- 1. With TRUST_ROSTER_ONLY the scan is FULLY LOCAL --------------------
# vision raises, so any API call fails this outright.
with Rig() as rig:
    coll = o.read_full_ban_collection(max_presses=6, use_cache=False,
                                      trust_roster=True)
check(rig.vision_calls == 0,
      f"trust_roster made {rig.vision_calls} vision call(s) — the whole point "
      "is that this path never reaches the API")
check(rig.ocr_calls == 0,
      f"trust_roster ran {rig.ocr_calls} name OCR(s) — position lookup is the "
      "whole answer; name OCR is pure cost here")
check(len(coll) >= 3,
      f"trust_roster returned {len(coll)} cards from a real ban frame — too few "
      "to choose 3 bans")
check(all(isinstance(c[2], type(next(iter(o.KNOWN_BAN_ROSTER.values()))))
          for c in coll),
      "collection entries are not PlayerCards")

# --- 2. The flag genuinely switches paths --------------------------------
# NOTE the subtlety this test exists to pin down: on a real frame the roster
# covers 100% of visible positions, so the pre-existing full-coverage
# short-circuit ALREADY skips vision even with trust_roster=False. The flag is
# only distinguishable where coverage is PARTIAL — which is exactly where the
# old code fell through to vision and the new code skips the position instead.
# A first version of this test asserted "flag off reaches vision" and failed
# for that reason, not because the flag was broken.
_saved_roster = dict(o.KNOWN_BAN_ROSTER)
try:
    for _k in [k for k in list(o.KNOWN_BAN_ROSTER) if k[0] == 0][:2]:
        del o.KNOWN_BAN_ROSTER[_k]        # force partial coverage at top_row 0
    with Rig() as rig_off:
        try:
            o.read_full_ban_collection(max_presses=2, use_cache=False,
                                       trust_roster=False)
        except AssertionError:
            pass                          # vision raised = it was reached
        off_vision, off_ocr = rig_off.vision_calls, rig_off.ocr_calls
    with Rig() as rig_on:
        o.read_full_ban_collection(max_presses=2, use_cache=False,
                                   trust_roster=True)
        on_vision, on_ocr = rig_on.vision_calls, rig_on.ocr_calls
finally:
    o.KNOWN_BAN_ROSTER.clear()
    o.KNOWN_BAN_ROSTER.update(_saved_roster)

check(off_ocr > 0,
      f"with trust_roster=False and a roster gap, name OCR ran {off_ocr} times "
      "— expected the local-name fallback to be attempted")
check(on_ocr == 0 and on_vision == 0,
      f"with trust_roster=True a roster gap still cost {on_ocr} OCR(s) and "
      f"{on_vision} vision call(s) — uncatalogued positions must simply be "
      "skipped as ban candidates")
check((off_ocr, off_vision) != (on_ocr, on_vision),
      "both flag settings behaved identically — one of the two modes is dead "
      "code and the rollback switch does nothing")

# --- 3. A short scan must not poison the process cache (QA1-F6) ----------
# A mid-animation frame reads every cell as locked -> [] -> cached -> every
# later call in the process is served the empty list, including the caller's
# own retry loop. One bad frame cost the match fee and ended the session.
_blank = Image.new("RGB", _REAL.size, (10, 10, 10))
with Rig(frames=[_blank]) as rig:
    bad = o.read_full_ban_collection(max_presses=2, use_cache=True,
                                     trust_roster=True)
    check(len(bad) < 3, f"fixture error: blank frame yielded {len(bad)} cards")
    check(o._cached_ban_collection is None,
          f"a {len(bad)}-card scan was cached — a single bad frame now poisons "
          "every later scan in this process, and the retry loop cannot recover "
          "because it is served the same bad result")

# --- 4. The cursor is returned to the top ---------------------------------
# The scan scrolls down to read; select_bans_and_start_full() then navigates
# from an assumed (0,0). If the unwind is wrong, every ban lands on the wrong
# card — silently, since the positions still "exist".
with Rig() as rig:
    o.read_full_ban_collection(max_presses=6, use_cache=False, trust_roster=True)
downs = rig.presses.count("move_down")
ups = rig.presses.count("move_up")
check(downs == ups,
      f"scan pressed {downs} move_down but {ups} move_up — the cursor is left "
      f"{downs - ups} row(s) from the top, and select_bans_and_start_full() "
      "assumes it starts at (0, 0), so every ban would target the wrong row")

# --- The PRODUCTION default must be exercised ----------------------------
# QA2-2: every call above passes trust_roster= explicitly, so flipping
# TRUST_ROSTER_ONLY changed nothing in any test — the default binding was never
# reached. Call it the way run() does: with no argument at all.
#
# ...but calling it with no argument is not enough on its own. The fixture
# frame has FULL roster coverage, and the pre-existing full-coverage
# short-circuit already skips vision even with trust_roster=False — this
# file's own §2 comment says exactly that: "the flag is only distinguishable
# where coverage is PARTIAL". So this block reproduced the one condition that
# cannot tell the two paths apart, and mutating the default binding to
# `trust_roster = False` survived (QA, 2026-08-26).
#
# Force PARTIAL coverage by removing one catalogued card that the fixture
# actually shows, so an uncatalogued position is visible. With the flag on it
# is skipped locally (0 vision); with the flag off it would be sent to vision.
_victim_pos = sorted(o.KNOWN_BAN_ROSTER)[0]
_victim = o.KNOWN_BAN_ROSTER.pop(_victim_pos)
try:
    with Rig() as rig_default:
        o.read_full_ban_collection(max_presses=4, use_cache=False)
        default_vision, default_ocr = rig_default.vision_calls, rig_default.ocr_calls
finally:
    o.KNOWN_BAN_ROSTER[_victim_pos] = _victim
check(o.TRUST_ROSTER_ONLY is True,
      "TRUST_ROSTER_ONLY is not True — the assertions below describe the "
      "local-only default and no longer apply")
check(default_vision == 0 and default_ocr == 0,
      f"with an UNCATALOGUED position visible, the default (no trust_roster "
      f"argument) made {default_vision} vision call(s) and {default_ocr} "
      "OCR(s). TRUST_ROSTER_ONLY is not reaching read_full_ban_collection, so "
      "production behaves differently from every test in this file — and this "
      "is now measured under partial coverage, the only condition that can "
      "tell the two paths apart.")

# --- Missing fixtures must FAIL, not silently pass -----------------------
# QA2-7: this file used to SystemExit(0) when screenshot_log/ had no matching
# frames — and orchestrator prunes screenshot_log. The suite would have gone
# green with this entire file doing nothing.
check(len(FRAMES) >= 1,
      "no reference ban frames found — this file must fail loudly rather than "
      "skip, or pruning screenshot_log/ silently disables all ban-scan coverage")

# --- 5. A dropped keystroke must not mislabel the rows -------------------
# `top_row = presses_so_far - 1` counts keystrokes SENT, not scrolling that
# HAPPENED. With one move_down dropped, every subsequent row is mislabelled and
# the scan catalogues a card at the wrong position — replayed against real
# frames that means a LOCKED card the player does not own becomes a ban
# candidate. The scrollbar is the only independent witness.
o._OBSERVATIONS.clear()      # earlier rigs in this process left records
with Rig(scroll_override=0) as rig_stuck:
    _stuck_rows = o.read_full_ban_collection(max_presses=6, use_cache=False,
                                             trust_roster=True)
_desync = [x for x in o._OBSERVATIONS if x.get("event") == "ban_scroll_desync"]
check(_desync,
      "the scrollbar was pinned at level 0 while the press count advanced, and "
      "no desync was recorded — the scan is trusting the press count, which "
      "cannot see a dropped keystroke")
if _desync:
    check(_desync[0].get("scrollbar_row") == 0,
          f"desync record has the wrong rows: {_desync[0]}")

# ...and the scan must ACT on it, not merely report it. Both assertions above
# only inspect the record_observation call, which sits ABOVE the correction —
# so `top_row = _lvl` could be deleted entirely and the warning still fired
# while the scan carried on with the wrong rows (QA, 2026-08-26). With the
# scrollbar pinned at 0, every catalogued row must BE 0; under the mutant they
# come back 0,1,2,3... and a locked card the player does not own becomes a ban
# candidate, which is the cardinal failure of this screen.
# The viewport shows TWO rows at a time (top_row and top_row+1), so a
# scrollbar pinned at 0 legitimately yields rows {0, 1}. The mutant, driven by
# the advancing press count, climbs to max_presses. So the discriminator is
# the CEILING, not equality with [0].
_rows_seen = sorted({r for r, _c, _card in _stuck_rows})
check(not _rows_seen or max(_rows_seen) <= 1,
      f"the scrollbar was pinned at level 0 but the scan catalogued rows "
      f"{_rows_seen} — it recorded the desync and then used the press count "
      "anyway, so cards are filed at positions they do not occupy")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} ban-scan failure(s)")

print(f"OK: ban scan — trust_roster is fully local (0 vision, 0 OCR, "
      f"{len(coll)} cards), the flag switches paths, short scans are not "
      f"cached, and the cursor unwinds ({downs} down / {ups} up)")


# --- read_ban_counter must actually READ (V1) ----------------------------
# QA 2026-08-26: `read_ban_counter` had NO behavioural test anywhere. Hard-wire
# it to `return 3` and the entire suite still passed — because
# test_run_state_machine.py patches the reader out
# (`"read_ban_counter": lambda *a, **k: self.ban_counter`), so the branch was
# covered and the reader never was.
#
# That is not academic. This function exists because three of five real ban
# sequences finished at 2/3 and the match started anyway. A reader stuck at 3
# restores exactly that blindness — and now prints "[ban] verified 3/3 bans
# placed" while lying, which is worse than the silence it replaced.
#
# Real frames, from the live ban screen of 2026-08-26 13:39. Two-sided by
# construction: it must read a SHORT count as short, and an unreadable frame as
# None. A reader that can only ever say "3" fails on four of these five.
import os as _os
from PIL import Image as _Image
from orchestrator import read_ban_counter as _rbc

# _ROOT, not dirname(__file__): the fixtures live at the PROJECT root, and this
# line was missed when the tests moved into tests/. It looked for
# tests/test_fixtures/ban_counter, never found it, and took the "must not
# silently skip" exit — so the read_ban_counter coverage this block exists to
# provide has been off since the move, reported as a missing fixture.
_FIX = _os.path.join(_ROOT, "test_fixtures", "ban_counter")
_CASES = [
    ("20260826_133925_665.jpg", 0),   # nothing banned yet
    ("20260826_133958_816.jpg", 1),
    ("20260826_134001_536.jpg", 2),   # SHORT — must not read as 3
    ("20260826_134004_720.jpg", 3),   # the only frame that is genuinely 3
    ("20260826_133957_697.jpg", None),  # mid-transition: must abstain
]

# THE GEOMETRY THE GAME ACTUALLY SENDS. Every frame above is a 2000x1292
# FULL-DISPLAY capture with the game letterboxed inside it; capture now grabs
# the 1920x1080 game WINDOW, where the same fractions land on blank notebook
# page. This block was fully green on 2026-09-01 while read_ban_counter
# returned None for every live frame, so a match started with 1 of 3 bans
# placed and nothing noticed. These two live in ban_scan/ because they are the
# same ban grids; they read 0/3.
_WINDOW_CASES = [("20260828_140309_081.jpg", 0), ("20260828_140315_271.jpg", 0)]

if not _os.path.isdir(_FIX):
    raise SystemExit(
        f"missing fixture dir {_FIX} — this test must not silently skip; that "
        "is how read_ban_counter went untested in the first place")

for _name, _expect in _CASES:
    _path = _os.path.join(_FIX, _name)
    assert _os.path.exists(_path), f"missing fixture {_name}"
    _got = _rbc(_Image.open(_path))
    assert _got == _expect, (
        f"{_name}: read {_got!r}, expected {_expect!r} — the counter reader is "
        "not reading the frame")

# Explicitly pin the property that a constant-returning reader would violate.
_vals = [_rbc(_Image.open(_os.path.join(_FIX, n))) for n, _ in _CASES]
assert len(set(_vals)) > 1, "the reader returns the same value for every frame"
assert None in _vals, "the reader never abstains, so it cannot be refusing anything"

_WFIX = _os.path.join(_ROOT, "test_fixtures", "ban_scan")
for _name, _expect in _WINDOW_CASES:
    _path = _os.path.join(_WFIX, _name)
    assert _os.path.exists(_path), f"missing window fixture {_name}"
    _im = _Image.open(_path)
    assert _im.size == (1920, 1080), (
        f"{_name} is {_im.size}, not a 1920x1080 window capture — this case "
        "exists precisely to pin the geometry the game sends")
    _got = _rbc(_im)
    assert _got == _expect, (
        f"{_name}: read {_got!r}, expected {_expect!r} — the counter cannot be "
        "read on WINDOW captures, which is every live frame. When this last "
        "broke, a paid match ran with 1 of 3 bans placed and nothing noticed.")

print(f"OK: read_ban_counter reads {len(_CASES)} real ban frames correctly "
      f"(0/1/2/3 and one refusal) and {len(_WINDOW_CASES)} window captures")
