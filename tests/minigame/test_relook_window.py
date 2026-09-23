"""I-63: a blind slot's ONE re-look before refusing wasn't enough.

Every one of the 28 live matches leading up to this ticket lost its play
refusals to exactly one shape: `_clear_strays`' `_new_blind` guard
(input_controller.py, around the "read unreadable ... re-looking once before
refusing" print) took a single re-look after SELECT_RETRY_CONFIRM_SEC and
refused if the stray slot was still `None`. Measured against every
overnight/run_live_*.log (agent_progress/issues/I-63/measure.py): that one
re-look recovered only 5/12 live events, but every one of the 22
refused_select_<ns> rescue frames already on disk -- each read moments after
a refusal, with no deliberate extra wait -- read the SAME slot clean. The
blindness was clearing, just not within the one look this code allowed.

The fix bounds the SAME re-look to `_STRAY_RELOOK_MAX_ATTEMPTS` (2) attempts,
each after the existing SELECT_RETRY_CONFIRM_SEC settle -- LOOKING ONLY, no
extra presses -- and still refuses if every attempt in the window comes back
blind. This drives the real `_verified_select_and_play_inner` (not a stub of
it), the same seam agent_progress/i56-replay/replay.py uses, so a mutant that
presses inside the loop or drops the bound is caught end to end, not just at
`_clear_strays`' own boundary.

Uses the same check(cond, msg) shape as tests/minigame/test_verified_selection.py
and the sibling stray-guard tests (`grep -n "def check" tests/minigame/*.py`
before writing this one).
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import input_controller as ic  # noqa: E402

fails = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        fails.append(msg)


N = ic.MAX_HAND_SIZE
KINDS = ["player", "player", "tactics", "player", "player"]
BASELINE_YS = [200, 160, 150, 165, 220]
# The target (slot 1) select and the stray's baseline/blind shape are the
# cycle19 match4 incident's own values (run_live_20260922e.log:813-826,
# agent_progress/i56-replay/progress.md) -- real instrument readings, not
# invented ones. Only WHEN slot 2 clears is scripted per case below.
STRAY_SLOT = 2


class _CursorSelLike(list):
    """Mirrors orchestrator._CursorSel: a plain list plus `.kinds`."""

    def __init__(self, items, kinds):
        super().__init__(items)
        self.kinds = kinds


class Screen:
    """Target slot 1 selects on the first press, cleanly. The stray at
    STRAY_SLOT reads blind for the first `blind_looks` look() calls taken
    AFTER the select lands, then reads clean forever after -- or forever if
    `blind_looks` is None. That count includes every look() call in the
    real call chain, not just `_clear_strays`' own -- see
    _CLEAR_STRAYS_FIRST_LOOK below for where its first read actually falls.
    """

    def __init__(self, blind_looks):
        self.blind_looks = blind_looks
        self.cur = 0
        self.selected = set()
        self.press_log = []  # every press(), as (key, cur BEFORE the press)
        # index into press_log the instant slot 1 (the target) lands selected.
        # `_clear_strays` runs strictly AFTER the select, so nothing in
        # press_log from this index on is the walk-to-target -- it can only
        # be the re-look loop, which must press NOTHING (LOOKING ONLY).
        self.landed_at = None
        self.confirmed = False
        self.post_select_looks = 0

    def press(self, key, **kw):
        self.press_log.append((key, self.cur))
        if key == "select_card":
            if self.cur in self.selected:
                self.selected.discard(self.cur)
            else:
                self.selected.add(self.cur)
                if self.cur == 1 and self.landed_at is None:
                    self.landed_at = len(self.press_log)
        elif key == "confirm_play":
            self.confirmed = True
        elif key == "move_right":
            self.cur = min(N - 1, self.cur + 1)
        elif key == "move_left":
            self.cur = max(0, self.cur - 1)

    @property
    def select_targets(self):
        return [cur for key, cur in self.press_log if key == "select_card"]

    @property
    def presses_after_landing(self):
        """Everything `_clear_strays` (and only `_clear_strays`) could have
        pressed -- must be empty on every case below (LOOKING ONLY)."""
        if self.landed_at is None:
            return list(self.press_log)
        return self.press_log[self.landed_at:]

    def look(self):
        glow = [0.0] * N
        if not self.selected:
            glow[self.cur] = 25.0  # above CUR_TRUSTED_GLOW_MIN
            return glow, list(BASELINE_YS), N, _CursorSelLike([], KINDS)
        if self.confirmed:
            return glow, [], 0, _CursorSelLike([], KINDS)
        self.post_select_looks += 1
        still_blind = self.blind_looks is None or self.post_select_looks <= self.blind_looks
        ys = [201, 114, None if still_blind else 135, 166, 211]
        return glow, ys, N, _CursorSelLike(sorted(self.selected), KINDS)


def run(blind_looks):
    screen = Screen(blind_looks)
    real_press, real_sleep = ic.press, ic.time.sleep
    slept = []
    ic.press = screen.press
    ic.time.sleep = lambda d: slept.append(d)
    try:
        ok = ic._verified_select_and_play_inner(1, None, screen.look)
    finally:
        ic.press = real_press
        ic.time.sleep = real_sleep
    return ok, screen, slept


T_MAX = ic._STRAY_RELOOK_MAX_ATTEMPTS * ic.SELECT_RETRY_CONFIRM_SEC


def relook_sleeps(slept):
    """Only the re-look loop's own sleeps -- `_select_verified`'s settle and
    the reveal-wait elsewhere in the same call also go through `ic.time.sleep`
    (measured live: 0.4/0.6/0.45/0.25s), so isolate SELECT_RETRY_CONFIRM_SEC
    itself, the same way the sibling stray-guard tests compare against it."""
    return [s for s in slept if abs(s - ic.SELECT_RETRY_CONFIRM_SEC) < 1e-9]


# `Screen.look()` counts every look() call after the target selects, which
# includes MORE than just `_clear_strays`' own reads -- `_select_verified`'s
# own confirmation look (it checks `target in sel`, built from
# `self.selected` directly, so it succeeds regardless of `ys[STRAY_SLOT]`,
# but still counts as a look) happens first. Measured directly rather than
# assumed (an earlier draft of this test guessed 2 and got a FAIL showing
# `_clear_strays`' own first read never saw a blind slot at all): with
# card_index=1, tactics_index=None, `_clear_strays`' own first read is
# post-select look #3.
_CLEAR_STRAYS_FIRST_LOOK = 3

# =============================================================================
print("(a) the stray clears on `_clear_strays`' FIRST re-look -- commits, "
      "never touches the stray slot, spends less than the full window")
# =============================================================================
ok, screen, slept = run(blind_looks=_CLEAR_STRAYS_FIRST_LOOK)
check(ok is True, f"a stray that clears inside the bounded window must not "
      f"block the commit; got {ok!r}")
check(screen.confirmed and screen.selected == {1},
      f"slot 1 must be the only thing committed; confirmed={screen.confirmed} "
      f"selected={screen.selected!r}")
check(STRAY_SLOT not in screen.select_targets,
      f"the stray slot must NEVER be pressed, recovered or not; "
      f"select_targets={screen.select_targets!r}")
check(screen.presses_after_landing == [("confirm_play", 1)],
      f"LOOKING ONLY through the re-look window -- the only press once the "
      f"target has landed is the eventual confirm_play; got "
      f"{screen.presses_after_landing!r}")
_rl = relook_sleeps(slept)
check(len(_rl) == 1 and sum(_rl) < T_MAX,
      f"recovering on the first re-look must spend LESS than the full "
      f"{T_MAX}s window ({ic._STRAY_RELOOK_MAX_ATTEMPTS} x "
      f"{ic.SELECT_RETRY_CONFIRM_SEC}s), not the whole bound; got {_rl!r} "
      f"(all sleeps: {slept!r})")

# =============================================================================
print("(b) the stray clears only on the LAST re-look the bound allows -- "
      "still commits, using the full window")
# =============================================================================
ok, screen, slept = run(blind_looks=_CLEAR_STRAYS_FIRST_LOOK
                         + ic._STRAY_RELOOK_MAX_ATTEMPTS - 1)
check(ok is True, f"a stray that clears on the final allowed attempt must "
      f"still commit; got {ok!r}")
check(STRAY_SLOT not in screen.select_targets,
      f"the stray slot must NEVER be pressed; select_targets="
      f"{screen.select_targets!r}")
check(screen.presses_after_landing == [("confirm_play", 1)],
      f"LOOKING ONLY through the re-look window; got "
      f"{screen.presses_after_landing!r}")
_rl = relook_sleeps(slept)
check(len(_rl) == ic._STRAY_RELOOK_MAX_ATTEMPTS and abs(sum(_rl) - T_MAX) < 1e-9,
      f"using every attempt in the bound must spend exactly the full "
      f"{T_MAX}s window; got {_rl!r} (all sleeps: {slept!r})")

# =============================================================================
print("(c) the stray NEVER clears -- refuses after spending the full bounded "
      "window, zero extra presses, nothing committed")
# =============================================================================
ok, screen, slept = run(blind_looks=None)
check(ok is False, f"a stray that stays blind through the whole bounded "
      f"window must refuse; got {ok!r}")
check(not screen.confirmed, f"a refused attempt must never confirm_play; "
      f"confirmed={screen.confirmed}")
check(STRAY_SLOT not in screen.select_targets,
      f"the stray slot must NEVER be pressed even when it never clears; "
      f"select_targets={screen.select_targets!r}")
check(screen.presses_after_landing == [],
      f"LOOKING ONLY, even on the refusal path -- a refusal never reaches "
      f"confirm_play either; got {screen.presses_after_landing!r}")
_rl = relook_sleeps(slept)
check(len(_rl) == ic._STRAY_RELOOK_MAX_ATTEMPTS and abs(sum(_rl) - T_MAX) < 1e-9,
      f"a permanent blind must spend the FULL bounded window, no more, no "
      f"less; expected {ic._STRAY_RELOOK_MAX_ATTEMPTS} sleeps totalling "
      f"{T_MAX}s, got {_rl!r} (all sleeps: {slept!r})")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  a stray that clears inside the bounded re-look window commits "
      "(early or on the last attempt), a stray that never clears refuses "
      "after spending exactly the bounded window, and the non-target slot "
      "is never pressed either way")
