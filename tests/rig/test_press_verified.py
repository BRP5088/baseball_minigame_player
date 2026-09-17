"""press_verified looks after every press, and never presses while it cannot see.

WHY IT EXISTS. Measured on a live ban screen 2026-09-17, with every press confirmed
against chiaki's own instrumented log before being scored (n=60): 50 moved, 10 IGNORED
by the game, ZERO lost in delivery. The console receives about one press in six and
declines to act on it. No delay, event source or faster retry can prevent that -- four
such hypotheses were measured and refuted -- so the only remedy is to look, and press
again if it did not take.

THE SAFETY PROPERTY IS THE HARD ONE, AND IT PULLS AGAINST THE OBVIOUS FIX. Several of
these actions are TOGGLES: select_card bans a card and pressing it again UN-bans it. So
a retry issued because the reader went blind is strictly worse than no retry -- it can
undo the press that worked, and the caller is told it failed. Hence: blind before the
first press means do not press at all; blind after a press means stop immediately.

A test that only proved "it retries" would miss all of that, so most of what follows is
about refusing.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import input_controller as ic

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


class Rig:
    """Stands in for the screen. `script` says what observe() sees after each press."""
    def __init__(self, start, script):
        self.state, self.script, self.presses = start, list(script), 0

    def press(self, action, *a, **k):
        self.presses += 1
        if self.script:
            nxt = self.script.pop(0)
            if nxt is not ...:
                self.state = nxt

    def observe(self):
        return self.state


def run(start, script, **kw):
    rig = Rig(start, script)
    old = ic.press
    ic.press = rig.press
    try:
        ok, sent = ic.press_verified("select_card", rig.observe, settle=0, **kw)
    finally:
        ic.press = old
    return ok, sent, rig


# --- the happy path -------------------------------------------------------
ok, sent, rig = run((0, 0), [(0, 1)])
check(ok and sent == 1, f"a press that lands is one press, reported ok ({ok}, {sent})")

# --- the game ignores it, then takes it -----------------------------------
ok, sent, rig = run((0, 0), [..., ..., (0, 1)])
check(ok and sent == 3, f"two ignored presses then success = 3 presses, ok ({ok}, {sent})")

# --- ignored every time ---------------------------------------------------
# This one follows the constant ON PURPOSE: it tests the BEHAVIOUR (does it stop at
# the budget), not the budget's value, and the value is pinned as a literal below.
ok, sent, rig = run((0, 0), [...] * ic.PRESS_VERIFY_TRIES)
check(not ok and sent == ic.PRESS_VERIFY_TRIES,
      f"ignored every attempt: ok=False and it STOPS at the budget ({ok}, {sent})")
check(sent == ic.PRESS_VERIFY_TRIES,
      f"it honours PRESS_VERIFY_TRIES={ic.PRESS_VERIFY_TRIES}, not an inline literal")

# --- BLIND BEFORE: must not press at all ----------------------------------
ok, sent, rig = run(None, [(0, 1)])
check(not ok and sent == 0,
      f"blind BEFORE the first press -> presses NOTHING ({ok}, {sent} presses)")

# --- BLIND AFTER: must stop, never double-toggle --------------------------
ok, sent, rig = run((0, 0), [None, (0, 1)])
check(not ok and sent == 1,
      f"blind AFTER a press -> stops at 1 press, no double-toggle risk ({ok}, {sent})")
check(rig.presses == 1,
      f"CONTROL: exactly one real press reached the rig ({rig.presses})")

# --- the budget is configurable and respected -----------------------------
ok, sent, _ = run((0, 0), [...] * 7, tries=7)
check(not ok and sent == 7, f"tries=7 sends 7 ({ok}, {sent})")
ok, sent, _ = run((0, 0), [...], tries=1)
check(not ok and sent == 1, f"tries=1 sends 1 ({ok}, {sent})")

# --- it compares against the BASELINE, not against "not None" -------------
# A press that changes the state and changes it BACK must not read as success.
ok, sent, _ = run((0, 0), [(0, 1)])
check(ok, "a real change is success")
ok, sent, _ = run((0, 0), [(0, 0)])
check(not ok and sent == ic.PRESS_VERIFY_TRIES,
      f"a state that is EQUAL to the baseline is NOT success ({ok}, {sent})")

# --- the constants are measured, and pinned as literals (10.11) -----------
# DERIVED, and the literal is pinned here so a change has to be argued (10.11).
# Measured n=1000 on a live ban screen, every press confirmed delivered to chiaki:
# 15.20% ignored by the GAME, 0 lost in delivery -- and the ignores CLUSTER,
# P(ignore|previous ignored)=0.250 against 0.135 after a good press, longest run 4.
# So the retries are NOT independent trials and 0.152*0.25**(n-1) is the real tail:
#     tries=3  0.950%   (an independence assumption claimed 0.47% -- twice as good)
#     tries=4  0.237%
#     tries=5  0.059%   <- and it covers the longest run actually observed
check(ic.PRESS_VERIFY_TRIES == 5,
      f"PRESS_VERIFY_TRIES is 5 — 0.059% residual against a CLUSTERED 15.2% ignore "
      f"rate, and covers the longest observed run of 4 (got {ic.PRESS_VERIFY_TRIES})")
check(ic.BAN_NAV_MAX_STEPS == 22,
      f"BAN_NAV_MAX_STEPS is 22 — 99.92% of 12-move targets reached; at the shipped "
      f"14 it was 64.36%, i.e. a far ban silently missing 1 time in 3 "
      f"(got {ic.BAN_NAV_MAX_STEPS})")

print()
if fails:
    print(f"{len(fails)} FAILED")
    sys.exit(1)
print("all good")
