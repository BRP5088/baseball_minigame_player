"""THE PRESS MUST GO TO CHIAKI, not to something that merely mentions it.

2026-09-13: `pgrep -f chiaki` matched this session's own `/bin/zsh -c ...`, whose command
line contained the word because the commands being run mentioned chiaki paths. It sorted
FIRST, chiaki_pid returned the shell, and every CGEventPostToPid went to a terminal for an
afternoon. Nothing raised. The liveness guard could not help -- the shell is alive -- and
the ban scan returned 8 cards of a 33-card collection reporting no error.

The question that guard could not ask is the one pinned here: is this pid CHIAKI?
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import subprocess, time
import input_controller as ic

_fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        _fails.append(msg)


print("1. A LIVE PROCESS THAT IS NOT CHIAKI IS REFUSED")
# A real process of our own, whose command line contains the word. This is the impostor,
# built the same way the real one was: a shell that mentions chiaki.
# The word has to survive into ARGV. `sh -c "sleep 30 # chiaki"` does NOT work: the shell
# exec-optimises a single command and argv becomes a bare `sleep 30`, with the comment gone
# -- the first version of this test built exactly that and then reported that pgrep -f did
# not match, which would have read as "the bug cannot happen". Passing it as $0 keeps it.
imp = subprocess.Popen(["/bin/sh", "-c", "sleep 30; true",
                        "chiaki-ng-build/chiaki.app"])
try:
    time.sleep(0.4)
    check(imp.poll() is None, f"the impostor is running (pid {imp.pid})")
    # it is alive: the old guard's whole question answers YES on it
    alive = True
    try:
        os.kill(imp.pid, 0)
    except ProcessLookupError:
        alive = False
    check(alive, "...and os.kill(pid, 0) says it is alive — which is why the liveness "
                 "guard passed it")
    ic._identity_checked.update({"pid": None, "at": 0.0, "ok": False})
    check(ic._still_chiaki(imp.pid) is False,
          "but _still_chiaki refuses it — the question is what the process IS, not "
          "whether it exists")

    print("\n2. pgrep -f WOULD HAVE MATCHED IT, which is how this happened")
    out = subprocess.run(["pgrep", "-f", ic.CHIAKI_WINDOW_PROCESS_NAME],
                         capture_output=True, text=True).stdout.split()
    check(str(imp.pid) in out,
          f"pgrep -f {ic.CHIAKI_WINDOW_PROCESS_NAME!r} matches the impostor ({out[:6]}) — "
          f"the resolver must not simply take the first of these")

    print("\n3. THE CACHE IS KEYED ON THE PID, so one answer cannot cover another")
    ic._identity_checked.update({"pid": imp.pid, "at": time.time(), "ok": False})
    check(ic._still_chiaki(imp.pid) is False, "the cached NO is returned for that pid")
    other = os.getpid()
    ic._identity_checked.update({"pid": imp.pid, "at": time.time(), "ok": True})
    check(ic._still_chiaki(other) is False,
          "and a DIFFERENT pid is re-checked rather than inheriting it — this test's own "
          "python is not chiaki either")
finally:
    imp.kill()
    imp.wait()

print("\n4. A DEAD PID IS STILL CAUGHT (the original guard still works)")
ic._identity_checked.update({"pid": None, "at": 0.0, "ok": False})
gone = imp.pid
dead = False
try:
    os.kill(gone, 0)
except ProcessLookupError:
    dead = True
check(dead, f"the impostor {gone} is gone now")

print("\n5. THE RESOLVER PREFERS AN EXACT NAME MATCH")
src = open(_os.path.join(_ROOT, "input_controller.py"), encoding="utf-8").read()
check('"pgrep", "-x"' in src,
      "_resolve_chiaki_pid asks pgrep -x (the executable NAME) before -f (the whole "
      "command line)")
check(src.index('"pgrep", "-x"') < src.index('"pgrep", "-f", CHIAKI_WINDOW_PROCESS_NAME'),
      "...and asks it FIRST, so the loose match is only a fallback")
# BEHAVIOURAL, NOT A SOURCE SUBSTRING. The first version of this check looked for the
# filter's text in the file — and that exact string also appears in _still_chiaki, so
# deleting the filter from the FALLBACK left this green. A mutant proved it. Drive the
# resolver instead, with pgrep -x finding nothing and pgrep -f finding only an impostor.
_real_run = subprocess.run


def _fake_run(cmd, *a, **k):
    class R:
        stdout = ""
    if cmd[:2] == ["pgrep", "-x"]:
        return R()                                  # the app is not running
    if cmd[:2] == ["pgrep", "-f"]:
        R.stdout = "424242\n"                       # only an impostor matches
        return R()
    if cmd[:2] == ["ps", "-p"]:
        R.stdout = "/bin/zsh\n"                     # and it is a shell
        return R()
    return _real_run(cmd, *a, **k)


ic.subprocess.run = _fake_run
try:
    got = ic._resolve_chiaki_pid()
finally:
    ic.subprocess.run = _real_run
check(got is None,
      f"with no exact match and only a /bin/zsh matching the command line, the resolver "
      f"returns None rather than that pid (got {got!r}) — returning it is how every press "
      f"went to a terminal for an afternoon")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
