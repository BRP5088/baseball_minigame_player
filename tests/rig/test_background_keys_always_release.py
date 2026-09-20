"""A key-DOWN on the targeted Quartz path must always get a key-UP attempt.

press_background() and _bg_hold_keys() post DOWN, sleep, then post UP. They
used to do it inside ONE `try/except Exception: return False` with no
`finally`, so anything that raised in between left the key PHYSICALLY HELD at
chiaki -- and therefore at the console -- while the function reported False.
A KeyboardInterrupt during the sleep was worse: `except Exception` cannot catch
a BaseException, so it propagated with the key still down.

This is the keyboard twin of the dropped release packet CLAUDE.md section 5
calls "the lurking catastrophe" on the stick path, and the exposure is not
exotic: press() routes EVERY button press through _bg_hold_keys, and
reset_env._probe_transports holds look_right for 0.3 s at a time. A held
Return is a held CROSS, which is the button that answers YES on "Give up?".

NOTHING IS POSTED ANYWHERE BY THIS FILE. Quartz is replaced in sys.modules
with a recorder before either function is called, and chiaki_pid is stubbed to
a pid that does not exist, so the two guards are independent.
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

import input_controller as ic

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


POSTS = []
RAISE_AT = [None]
NO_SUCH_PID = 999999


class _FakeQuartz(types.ModuleType):
    """Records posts. ONE-SHOT failure injection.

    Raising at a fixed post INDEX would also break the release attempt the
    fix adds, which measures "Quartz is permanently dead" -- a state nothing
    can recover from -- rather than the transient failure a finally exists
    for. Fire once, then behave.
    """

    @staticmethod
    def CGEventCreateKeyboardEvent(src, code, down):
        return ("event", code, down)

    @staticmethod
    def CGEventPostToPid(pid, ev):
        assert pid == NO_SUCH_PID, f"posted to an unexpected pid {pid!r}"
        if RAISE_AT[0] is not None and len(POSTS) == RAISE_AT[0]:
            RAISE_AT[0] = None
            raise RuntimeError("injected one-shot Quartz failure")
        POSTS.append(("DOWN" if ev[2] else "UP", ev[1]))


# Import happens above with the REAL Quartz -- pyautogui reads the display size
# at import time and dies on a stub. `import Quartz` inside the two functions
# resolves from sys.modules on every call, so swapping now still replaces what
# they see.
_real_quartz = sys.modules.get("Quartz")
sys.modules["Quartz"] = _FakeQuartz("Quartz")

_saved = (ic.targeted_input_allowed, ic.chiaki_pid, ic.ACTION_DELAY, ic.time.sleep)
# targeted_input_allowed() refuses under BASEBALL_TEST_RUN, which is the whole
# point of it (section 5) -- this file drives the code BEHIND that guard, with
# the pid stubbed to nothing so the lockout being open cannot matter.
ic.targeted_input_allowed = lambda what: True
ic.chiaki_pid = lambda *a, **k: NO_SUCH_PID
ic.ACTION_DELAY = 0.0


def run(fn, raise_at=None, interrupt=False):
    POSTS.clear()
    RAISE_AT[0] = raise_at
    if interrupt:
        def _boom(_s):
            raise KeyboardInterrupt("simulated Ctrl-C while the key is held")
        ic.time.sleep = _boom
    raised = None
    try:
        ret = fn()
    except BaseException as exc:                      # noqa: BLE001 - that is the test
        ret, raised = None, type(exc).__name__
    finally:
        ic.time.sleep = _saved[3]
    downs = [c for kind, c in POSTS if kind == "DOWN"]
    ups = [c for kind, c in POSTS if kind == "UP"]
    return ret, raised, [c for c in downs if c not in ups], list(POSTS)


# ---- positive control: the checks below must be able to SEE a stuck key ------
# Without this, a stub that silently posts nothing would make every
# "no key left down" assertion pass by finding no keys at all.
POSTS.clear()
_FakeQuartz.CGEventPostToPid(NO_SUCH_PID, ("event", 42, True))
_ctl_down = [c for kind, c in POSTS if kind == "DOWN"]
_ctl_up = [c for kind, c in POSTS if kind == "UP"]
check([c for c in _ctl_down if c not in _ctl_up] == [42],
      "CONTROL: the recorder must report an unmatched DOWN as a stuck key; "
      f"got POSTS={POSTS!r}. Every check below is vacuous if this fails.")

# ---- the clean paths still work, and still report True ----------------------
ret, raised, stuck, posts = run(lambda: ic.press_background("cross", 0.0))
check(ret is True, f"press_background clean: expected True, got {ret!r}")
check(stuck == [], f"press_background clean left keys down: {stuck!r}")
check(len(posts) == 2, f"press_background clean should post DOWN then UP; got {posts!r}")

ret, raised, stuck, posts = run(lambda: ic._bg_hold_keys(["w", "a"], 0.0))
check(ret is True, f"_bg_hold_keys clean: expected True, got {ret!r}")
check(stuck == [], f"_bg_hold_keys clean left keys down: {stuck!r}")
check([k for k, _ in posts] == ["DOWN", "DOWN", "UP", "UP"],
      f"_bg_hold_keys clean must release in reverse order; got {posts!r}")

# ---- THE BUG: a raise between DOWN and UP must not strand the key -----------
# A multi-key hold whose SECOND down post fails. Before the fix the first key
# stayed down forever; the function returned False and said nothing.
ret, raised, stuck, posts = run(lambda: ic._bg_hold_keys(["w", "a"], 0.0), raise_at=1)
check(stuck == [],
      "_bg_hold_keys: a raise on the second key-DOWN must still release the "
      f"first key. Keys left held at the console: {stuck!r} (posts={posts!r})")
check(ret is False,
      f"_bg_hold_keys must still answer False when a post raised; got {ret!r}")

# ---- THE REACHABLE ONE: Ctrl-C / SIGINT during the hold sleep ---------------
# `except Exception` cannot catch a BaseException, so this used to propagate
# with the key still down -- not even the `return False` ran. Every hold sleeps
# with a key held, so this window exists on every single press.
ret, raised, stuck, posts = run(lambda: ic._bg_hold_keys(["w"], 1.0), interrupt=True)
check(raised == "KeyboardInterrupt",
      f"the interrupt must still propagate, not be swallowed; got {raised!r}")
check(stuck == [],
      "_bg_hold_keys: a KeyboardInterrupt during the hold must release the key "
      f"on the way out. Keys left held: {stuck!r} (posts={posts!r})")

ret, raised, stuck, posts = run(lambda: ic.press_background("cross", 1.0), interrupt=True)
check(raised == "KeyboardInterrupt",
      f"press_background: the interrupt must propagate; got {raised!r}")
check(stuck == [],
      "press_background: a KeyboardInterrupt during the hold must release the "
      f"key -- a held Return is a held CROSS. Keys left held: {stuck!r}")

# ---- the release is ATTEMPTED even when it cannot succeed, and says so ------
# When the UP post is itself what fails there is nothing left to try. The fix
# does not pretend otherwise; what it must not do is stay SILENT about it
# (section 10.1), because a key held at the console with no log line is
# indistinguishable from a clean press.
import io                                                    # noqa: E402
import contextlib                                            # noqa: E402

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    ret, raised, stuck, posts = run(lambda: ic.press_background("cross", 0.0), raise_at=1)
out = buf.getvalue()
check(ret is False,
      f"press_background must answer False when the release failed; got {ret!r}")
check("RELEASE" in out.upper() and "36" in out,
      "a release that could not be posted must be announced loudly, naming the "
      f"keycode; got {out!r}")

ic.targeted_input_allowed, ic.chiaki_pid, ic.ACTION_DELAY, ic.time.sleep = _saved
if _real_quartz is not None:
    sys.modules["Quartz"] = _real_quartz
else:
    sys.modules.pop("Quartz", None)

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  targeted Quartz path: every key-DOWN gets a key-UP attempt, including "
      "through a raise and through a KeyboardInterrupt in the hold")
