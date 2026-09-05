"""A cached chiaki pid must not outlive the process it names.

Nothing in the codebase calls chiaki_pid(refresh=True), so the first resolved
pid was trusted for the life of the run. restart_chiaki.sh kill -9s chiaki, so
after any restart CGEventPostToPid addressed a dead process: it delivers
nothing, raises nothing, and _bg_hold_keys still returns True. Every press
reports success while no input reaches the game.

That is the "stock build was running" failure of 2026-08-31 one layer down —
and harder to see, because there the binary was visibly wrong.
"""
import os
import os as _os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import input_controller as ic

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


_real_kill = os.kill
_real_run = ic.subprocess.run
resolved = []


class _Out:
    def __init__(self, text):
        self.stdout = text


def _fake_run(*a, **k):
    resolved.append(a)
    return _Out("4242\n")


# --- a live cached pid is returned without re-resolving --------------------
ic._chiaki_pid = 1234
os.kill = lambda pid, sig: None                  # "process exists"
ic.subprocess.run = _fake_run
resolved.clear()
got = ic.chiaki_pid()
check(got == 1234, f"a live cached pid was replaced ({got}); re-resolving on "
                   "every press would spawn a pgrep per keystroke")
check(not resolved, "re-resolved despite the cached process being alive")

# --- a DEAD cached pid is discarded and re-resolved ------------------------
ic._chiaki_pid = 1234


def _dead(pid, sig):
    raise ProcessLookupError


os.kill = _dead
resolved.clear()
got = ic.chiaki_pid()
check(got == 4242,
      f"chiaki_pid returned {got} for a process that no longer exists — every "
      "CGEventPostToPid would target it, deliver nothing, and report success")
check(len(resolved) == 1, "a dead pid must trigger exactly one re-resolve")

# --- alive but not ours to signal is still alive ---------------------------
ic._chiaki_pid = 777


def _perm(pid, sig):
    raise PermissionError


os.kill = _perm
resolved.clear()
got = ic.chiaki_pid()
check(got == 777,
      f"PermissionError means the process EXISTS but is not ours to signal; "
      f"treating it as dead returned {got} and would thrash pgrep")

os.kill = _real_kill
ic.subprocess.run = _real_run
ic._chiaki_pid = None

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  chiaki pid: live cache reused, dead cache re-resolved, "
      "not-ours-to-signal treated as alive")
