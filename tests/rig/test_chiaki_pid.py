"""A cached chiaki pid must not outlive the process it names -- OR ITS IDENTITY.

Two failures, one cache. The first: nothing called chiaki_pid(refresh=True), so the first
resolved pid was trusted for the life of the run, and restart_chiaki.sh kill -9s chiaki --
after any restart CGEventPostToPid addressed a dead process, delivered nothing, raised
nothing, and _bg_hold_keys still returned True.

The second, 2026-09-13, is the same shape one question further out. `pgrep -f chiaki`
matched this session's own `/bin/zsh`, it sorted first, and the liveness guard PASSED --
a shell is alive. Every press went to a terminal for an afternoon and every press reported
success. So "is this pid alive" is not the contract; "is this pid CHIAKI" is, and this file
pins the newer one.

The cost that rule has to stay under is a `ps` per keystroke, which is why the identity
answer is cached for _IDENTITY_TTL_SEC and why that caching is pinned here too.
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
resolved = []          # pgrep invocations
identity = []          # `ps -o comm=` invocations
comm = ["chiaki"]      # what `ps` says this pid IS


class _Out:
    def __init__(self, text):
        self.stdout = text


def _fake_run(cmd, *a, **k):
    """Answer `ps -p N -o comm=` and `pgrep` separately.

    The earlier version of this file returned "4242" to EVERYTHING, so the identity check
    read the pid itself as the process name, decided it was not chiaki, and re-resolved --
    the test failed on a correct implementation.
    """
    if cmd and cmd[0] == "ps":
        identity.append(tuple(cmd))
        return _Out(comm[0] + "\n")
    resolved.append(tuple(cmd))
    return _Out("4242\n")


def _reset(pid, is_chiaki=True):
    ic._chiaki_pid = pid
    ic._identity_checked.update({"pid": None, "at": 0.0, "ok": False})
    comm[0] = "chiaki" if is_chiaki else "/bin/zsh"
    resolved.clear()
    identity.clear()


ic.subprocess.run = _fake_run

# --- a live cached pid that IS chiaki is returned without re-resolving -----
_reset(1234)
os.kill = lambda pid, sig: None                  # "process exists"
got = ic.chiaki_pid()
check(got == 1234, f"a live chiaki pid was replaced ({got}); re-resolving on "
                   "every press would spawn a pgrep per keystroke")
check(not resolved, "re-resolved despite the cached process being alive AND chiaki")

# --- ...and the identity answer is CACHED, not re-asked per press ----------
# The whole reason the old guard asked only about liveness was cost. If every press paid
# for a `ps`, this rule would be reverted the first time a turn felt slow.
before = len(identity)
for _ in range(20):
    ic.chiaki_pid()
check(len(identity) == before,
      f"20 further presses cost {len(identity) - before} extra `ps` lookups within "
      f"_IDENTITY_TTL_SEC ({ic._IDENTITY_TTL_SEC}s) — the identity answer is not cached")

# --- a live cached pid that is NOT chiaki is DISCARDED ---------------------
# This is the 2026-09-13 failure exactly: pid alive, liveness guard happy, and every
# CGEventPostToPid landing in a shell. Alive is not the property that matters.
_reset(1234, is_chiaki=False)
got = ic.chiaki_pid()
check(got == 4242,
      f"chiaki_pid kept {got}, a LIVE process that is not chiaki — that is the "
      "/bin/zsh an afternoon of presses went to, and it reported success every time")
check(len(resolved) == 1, "a wrong-identity pid must trigger exactly one re-resolve")

# --- a DEAD cached pid is discarded and re-resolved ------------------------
_reset(1234)


def _dead(pid, sig):
    raise ProcessLookupError


os.kill = _dead
got = ic.chiaki_pid()
check(got == 4242,
      f"chiaki_pid returned {got} for a process that no longer exists — every "
      "CGEventPostToPid would target it, deliver nothing, and report success")
check(len(resolved) == 1, "a dead pid must trigger exactly one re-resolve")

# --- alive but not ours to signal is still alive ---------------------------
_reset(777)


def _perm(pid, sig):
    raise PermissionError


os.kill = _perm
got = ic.chiaki_pid()
check(got == 777,
      f"PermissionError means the process EXISTS but is not ours to signal; "
      f"treating it as dead returned {got} and would thrash pgrep")

# --- a failed LOOKUP is not evidence of a wrong process -------------------
# `ps` can fail for reasons that have nothing to do with which program this is. Treating
# that as "not chiaki" would thrash pgrep on a perfectly good pid.
_reset(1234)
os.kill = lambda pid, sig: None


def _raises(cmd, *a, **k):
    if cmd and cmd[0] == "ps":
        raise OSError("ps unavailable")
    resolved.append(tuple(cmd))
    return _Out("4242\n")


ic.subprocess.run = _raises
got = ic.chiaki_pid()
check(got == 1234 and not resolved,
      f"a `ps` that could not RUN was read as 'not chiaki' and re-resolved (got {got})")

os.kill = _real_kill
ic.subprocess.run = _real_run
ic._chiaki_pid = None
ic._identity_checked.update({"pid": None, "at": 0.0, "ok": False})

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  chiaki pid: chiaki cache reused (identity cached), a live NON-chiaki pid "
      "discarded, dead cache re-resolved, not-ours-to-signal treated as alive")
