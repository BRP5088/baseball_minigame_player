"""I-30, skeptic follow-up: `_close_result_safely`'s fresh check must actually gate the press.

A skeptic reviewing commit 49af1ca found that `_close_result_safely` is behaviourally
safe end to end, but nothing in the suite pins the fresh-check LINE ITSELF: a mutant
that deletes it (reverting to an unconditional `press_verified("close_result", ...)`)
still passed all 12 files run for that commit, because every scenario in those files
either never reaches `_close_result_safely` with a stale read, or happens to behave the
same either way.

This file drives `_close_result_safely` DIRECTLY (not through the whole run() loop),
with `_result_screen_up` scripted call by call:

    call 1   the fresh check `_close_result_safely` itself makes right before deciding
             whether to press at all
    call 2   press_verified's own baseline `_look()` (only reached if call 1 was True)
    call 3   press_verified's post-press `_look()` (only reached if a press was sent)

REFUSAL: call 1 answers False (a fresh look already shows no result screen -- the
live shape: the misread had evaporated by press time). close_result must NOT be
pressed, and the log must say why.

CONTROL: call 1 and 2 answer True (a result screen is genuinely, freshly up), call 3
answers False (the press landed and closed it). Exactly one press, reported as a
landed press.

MUTATION: deleting the `if up is not True: ... return False, 0` guard makes
`_close_result_safely` call `press_verified` unconditionally. In the REFUSAL
scenario that means `press_verified`'s own baseline read is False (not None), which
`press_verified` treats as a valid non-blind baseline and presses INTO, retrying up
to PRESS_VERIFY_TRIES times hunting for a change that (in the live incident) could
never come. The refusal assertions below catch that directly.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

_os.environ["BASEBALL_TEST_RUN"] = "1"
_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import orchestrator as o                                                     # noqa: E402
import input_controller as ic                                                # noqa: E402

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


class _ScriptedRSU:
    """Stands in for orchestrator._result_screen_up. Returns each value in
    `sequence` in order, one per call; repeats the last value if called more
    times than the script has answers for (so an unexpectedly-extra call is
    visible in `calls` rather than raising)."""

    def __init__(self, sequence):
        self.sequence = list(sequence)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.sequence:
            self._last = self.sequence.pop(0)
        return self._last


def run_scenario(sequence):
    presses = []
    logs = []

    def fake_press(action, *a, **kw):
        presses.append(action)

    rsu = _ScriptedRSU(sequence)
    saved_rsu = o._result_screen_up
    saved_press = ic.press
    o._result_screen_up = rsu
    ic.press = fake_press
    try:
        ok, sent = o._close_result_safely(log=logs.append)
    finally:
        o._result_screen_up = saved_rsu
        ic.press = saved_press
    return ok, sent, presses, logs, rsu.calls


# --- REFUSAL: the fresh read is already False -- nothing to close ----------------
ok, sent, presses, logs, calls = run_scenario([False])
check(presses == [],
      f"close_result must NOT be pressed when the fresh read is already False; "
      f"pressed {presses}")
check(sent == 0, f"expected 0 presses sent, got {sent}")
check(ok is False, f"expected ok=False (nothing was closed), got {ok!r}")
check(any("refus" in m.lower() or "not press" in m.lower() for m in logs),
      f"the refusal must be logged, naming why; got log lines: {logs}")
check(calls == 1,
      f"a False fresh read must stop right there -- expected exactly 1 call to "
      f"_result_screen_up, got {calls} (a mutant without the gate would call "
      f"press_verified, which reads again and presses)")

# --- CONTROL: a genuinely fresh, still-up result screen gets closed in one press --
ok, sent, presses, logs, calls = run_scenario([True, True, False])
check(presses == ["close_result"],
      f"a genuinely fresh result screen must be closed with exactly ONE "
      f"close_result press; got {presses}")
check(sent == 1, f"expected exactly 1 press sent, got {sent}")
check(ok is True, f"expected ok=True (the press landed), got {ok!r}")
check(calls == 3,
      f"expected 3 reads (the fresh check, press_verified's before, and its "
      f"after); got {calls}")


for f in failures:
    print(f"FAIL: {f}")
print(f"{len(failures)} close_result stale-read failure(s)"
      if failures else "close_result stale-read refusal: all checks passed")
_sys.exit(1 if failures else 0)
