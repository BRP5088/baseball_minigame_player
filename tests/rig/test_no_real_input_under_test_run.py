"""NOTHING may reach a real input device while BASEBALL_TEST_RUN is set.

THE CLAIM THIS FILE EXISTS TO STOP BEING A CLAIM. can_use_background_input()'s
docstring said refusing under the flag "means a test run can never move the
character". It did not. It meant a test run could not use the BACKGROUND path,
and each caller then fell through to pyautogui, which types into whatever window
is FRONTMOST. On 2026-09-13 a mutation run of the offline suite sent "c"
(confirm_play/Triangle) into the user's own window with a paid match parked on
the console; the user reported the keystrokes before any log did.

Three separate paths reach the console and EACH needs its own lockout, because a
guard in one protects none of the others:

    input_controller  keyboard   press / hold_combo / walk_at -> pyautogui
                                 press_background            -> CGEventPostToPid
    analog_replay     sticks     send()                      -> the FIFO
    ensure_stream     recovery   _key()                      -> CGEventPostToPid

ensure_stream was found the same evening with NO lockout of any kind, and
resolving its own pid with a loose `pgrep -f chiaki-ng-build` that a /bin/sh
could win. Both halves are fixed; this pins them.

The structural half below is the point: it fails when a NEW emission site
appears anywhere, so the next one is a failing test rather than a keystroke in
someone's editor.
"""
import ast
import os
import sys
import types

_ROOT = os.path.dirname(os.path.abspath(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

fails = []


def check(ok, msg):
    print(("  ok   " if ok else "  FAIL ") + msg)
    if not ok:
        fails.append(msg)


# ---------------------------------------------------------------- behavioural
import input_controller as ic
import analog_replay as ar

# A pyautogui that RECORDS instead of typing. If any guard is missing, the call
# lands here and the count is non-zero -- which is exactly what the real module
# would have done to the user's frontmost window.
_typed = []
_fake_gui = types.SimpleNamespace(
    keyDown=lambda k: _typed.append(("down", k)),
    keyUp=lambda k: _typed.append(("up", k)),
    press=lambda *a, **k: _typed.append(("press", a)),
    PAUSE=0.0)
_saved_gui, ic.pyautogui = ic.pyautogui, _fake_gui
_saved_focus = ic.FOCUS_PRESS_IN_TESTS
ic.FOCUS_PRESS_IN_TESTS = False          # the shipped default; tests opt IN, never out
try:
    check(ic.can_use_background_input() is False,
          "can_use_background_input() must refuse under the flag (the Quartz path)")
    check(ic.focus_input_allowed("cross") is False,
          "focus_input_allowed() must refuse under the flag (the pyautogui path)")

    _typed.clear()
    ic.press("cross", hold_seconds=0.0, post_delay=0.0)
    check(not _typed, f"press() reached the real keyboard under the flag: {_typed}")

    _typed.clear()
    ic.hold_combo(["walk_up", "walk_right"], 0.0)
    check(not _typed, f"hold_combo() reached the real keyboard under the flag: {_typed}")

    _typed.clear()
    _spent = ic.walk_at(20.0, 0.05)      # 20 deg: the BLENDED branch, which had no guard
    check(not _typed, f"walk_at() reached the real keyboard under the flag: {_typed}")
    check(_spent == 0.0,
          f"walk_at() reported {_spent}s travelled while refusing to move — a caller "
          "cannot tell a refused walk from a walked one (10.1)")

    # --- THE TARGETED PATH, which this file declared locked and never tested ---
    # press_background() and _bg_hold_keys() post CGEventPostToPid directly and
    # never call can_use_background_input() -- the gate lived only at the CALL
    # SITES. Reproduced with a PS5 connected and a match on screen:
    #     can_use_background_input() = False
    #     press_background('look_right') -> True, posted to pid 83980 twice
    # and THIS FILE printed "all three input paths are locked out" while it was
    # true, because EXPECTED listed both functions as known sites without ever
    # calling them. A census that asserts a site EXISTS is not a census that
    # asserts it is GUARDED.
    _posted = []
    sys.modules["Quartz"] = types.SimpleNamespace(
        CGEventPostToPid=lambda pid, ev: _posted.append(pid),
        CGEventCreateKeyboardEvent=lambda a, b, c: object())
    _posted.clear()
    _r = ic.press_background("look_right", hold_seconds=0.0, post_delay=0.0)
    check(not _posted and _r is False,
          f"press_background() posted to {_posted} and returned {_r} under the flag — "
          "those go straight to the running game's pid")
    _posted.clear()
    _r = ic._bg_hold_keys(["w"], 0.0)
    check(not _posted and _r is False,
          f"_bg_hold_keys() posted to {_posted} and returned {_r} under the flag — its "
          "own docstring calls it the single route every public input funnels through")

    # ...and the control: with the opt-in set, the path is REACHABLE. Without this the
    # four checks above would pass just as well on a press() that did nothing at all.
    # CONTROLS, one per guarded function. With only press() controlled, mutants that
    # turned hold_combo() and walk_at() into no-ops SURVIVED: `check(not _typed)` is
    # satisfied just as well by a function that does nothing, and walk_at's BLENDED
    # branch is the one that had no lockout at all -- the reason this file exists.
    ic.FOCUS_PRESS_IN_TESTS = True
    _typed.clear()
    ic.press("cross", hold_seconds=0.0, post_delay=0.0)
    check(len(_typed) == 2,
          f"CONTROL press(): with the opt-in the keys must still flow, got {_typed} — "
          "if this fails the press() check above proves nothing")
    _typed.clear()
    ic.hold_combo(["walk_up", "walk_right"], 0.0)
    check(len(_typed) >= 2,
          f"CONTROL hold_combo(): with the opt-in it must still emit, got {_typed} — "
          "otherwise a no-opped hold_combo passes the lockout check")
    _typed.clear()
    _ctl = ic.walk_at(20.0, 0.05)
    check(_typed and _ctl > 0,
          f"CONTROL walk_at() BLENDED branch: with the opt-in it must still emit and "
          f"report travel, got keys={len(_typed)} spent={_ctl} — otherwise a no-opped "
          "walk_at passes, and the blended branch is the one that was unguarded")
    ic.FOCUS_PRESS_IN_TESTS = False
finally:
    ic.pyautogui = _saved_gui
    ic.FOCUS_PRESS_IN_TESTS = _saved_focus

# --- the stick path ---------------------------------------------------------
_opened = []
_saved_open, ar.open_stream = ar.open_stream, lambda *a, **k: _opened.append(1)
try:
    ar.send(["left_y -32767"])
    check(not _opened, "analog_replay.send() opened the FIFO under the flag")
finally:
    ar.open_stream = _saved_open

# --- the recovery path ------------------------------------------------------
# ensure_stream._key does `import Quartz` INSIDE the function, so a fake in
# sys.modules is what it will pick up.
_posted = []
sys.modules["Quartz"] = types.SimpleNamespace(
    CGEventPostToPid=lambda pid, ev: _posted.append(pid),
    CGEventCreateKeyboardEvent=lambda a, b, c: object())
import ensure_stream
ensure_stream._key(12345, 36, after=0.0)
check(not _posted, f"ensure_stream._key() posted a real key event under the flag: {_posted}")

# --- and its pid must come from the resolver that checks IDENTITY ------------
# BEHAVIOURAL, not a source substring. The first version of this check asserted
# "pgrep" was absent from the source and failed on the docstring that EXPLAINS the
# bug -- a source-substring check is how mutants survive on this project. So spawn
# the decoy that actually reproduced it and watch what _pid() picks.
import subprocess as _sp, time as _t
_decoy = _sp.Popen(["/bin/sh", "-c", "sleep 5; : chiaki-ng-build"])
try:
    _t.sleep(0.4)
    _picked = ensure_stream._pid()
finally:
    _decoy.kill()
    _decoy.wait()
# A POSITIVE CONTROL FIRST. `_picked != _decoy.pid` is a bare negative, so a
# _pid() that returns None passes it -- and a None pid makes _key() early-return,
# turning the whole recovery ladder into a silent no-op (10.1) on the very path
# OPEN-23 was about. Assert the delegation contract instead of only the negative.
check(_picked == ic.chiaki_pid(),
      f"ensure_stream._pid() returned {_picked} but input_controller.chiaki_pid() says "
      f"{ic.chiaki_pid()} — it is resolving the pid itself again instead of delegating")
check(_picked != _decoy.pid,
      f"ensure_stream._pid() returned {_picked}, a /bin/sh whose argv merely CONTAINS "
      f"'chiaki-ng-build' — _key() posts straight to whatever this returns, so the "
      f"recovery ladder would type into that shell and report that nothing moved")

# ------------------------------------------------------------------ structural
# EVERY emission site, by (module, enclosing function). A new one changes this set
# and fails the test.
#
# THE FIRST VERSION OF THIS CENSUS MISSED SEVEN OF EIGHT REALISTIC NEW-EMITTER
# FORMS, proved by planting each one and watching the file still exit 0:
#
#   pyautogui.press(k)            `press` was not in EMITTERS -- the most idiomatic call
#   Quartz.CGEventPost(tap, ev)   not in EMITTERS, and it is a SYSTEM-WIDE tap
#   module-level pyautogui.keyDown  sites() only walked FunctionDef bodies
#   from pyautogui import keyDown  the call node is ast.Name, not ast.Attribute
#   getattr(pyautogui, "keyDown") the call node is ast.Call
#   an emitter in preflight.py    not on the 9-name scan list
#   an emitter in tools/          tools/ and overnight/ were unscanned
#
# The scan list was 9 hand-kept names against 120+ modules, and only two of them
# contribute a site -- so seven entries could have been typos with nothing failing.
# That is CLAUDE.md's own keep_awake lesson: a guard whose trigger is a hand-kept
# list of NAMES rots silently, because nothing fails when a new name is missing.
# It now walks every project module and derives the list.
EXPECTED = {
    ("input_controller.py", "press"),
    ("input_controller.py", "hold_combo"),
    ("input_controller.py", "walk_at"),
    ("input_controller.py", "_bg_hold_keys"),
    ("input_controller.py", "press_background"),
    ("ensure_stream.py", "_key"),
}
EMITTERS = {
    # pyautogui
    "keyDown", "keyUp", "press", "write", "typewrite", "hotkey",
    "click", "mouseDown", "mouseUp", "dragTo", "moveTo", "scroll",
    # Quartz -- PostToPid is targeted, CGEventPost is a SYSTEM-WIDE tap
    "CGEventPostToPid", "CGEventPost",
}
# THE RECEIVER MATTERS, not just the attribute. A bare name match cannot tell
# `pyautogui.press(k)` from this project's OWN `ic.press(...)`, and "write" matches
# every file write in the tree -- the first version of this list reported 900+
# sites across PIL. So the emitting MODULE is resolved per file from its imports.
INPUT_LIBS = {"pyautogui", "Quartz", "pynput"}
# The injection FIFO. A keystroke census cannot see `open(FIFO,"w").write("buttons
# 4096")`, and inject_reset.py wrote raw button masks to a HARDCODED
# /tmp/chiaki_input for the life of the project, ignoring CHIAKI_INJECT_INPUT --
# so every test that carefully redirected the pipe still had THAT writer aimed at
# the live one.
#
# WRITERS vs READERS, because naming the FIFO is not the hazard. tools/doctor.py
# names it to ask os.path.exists() and never opens it; CLAUDE.md's own summary of
# doctor is "MOVES NOTHING", and a check that cannot tell a presence test from a
# button mask would either flag it forever or be switched off.
FIFO_WRITERS = {"analog_replay.py", "inject_reset.py"}
FIFO_READERS = {"doctor.py"}


def _lib_bindings(tree):
    """Names in THIS module that refer to an input library, plus emitters imported bare.

    Covers `import pyautogui`, `import pyautogui as pg`, `from Quartz import X`,
    and `from pyautogui import keyDown` -- the last of which produces a BARE call
    that an attribute-only matcher cannot see.
    """
    mods, bare = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] in INPUT_LIBS:
                    mods.add(a.asname or a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            if (n.module or "").split(".")[0] in INPUT_LIBS:
                for a in n.names:
                    if a.name in EMITTERS:
                        bare.add(a.asname or a.name)
                    mods.add(a.asname or a.name)
    return mods, bare


def _emitter_name(node, mods, bare):
    """The emitter this Call invokes, through all four call shapes, or None."""
    f = node.func
    if (isinstance(f, ast.Attribute) and f.attr in EMITTERS
            and isinstance(f.value, ast.Name) and f.value.id in mods):
        return f.attr                                   # pyautogui.keyDown(k) / pg.press(k)
    if isinstance(f, ast.Name) and f.id in bare:
        return f.id                                     # keyDown(k), imported bare
    if (isinstance(f, ast.Call) and isinstance(f.func, ast.Name)
            and f.func.id == "getattr" and len(f.args) >= 2
            and isinstance(f.args[1], ast.Constant)
            and f.args[1].value in EMITTERS
            and isinstance(f.args[0], ast.Name) and f.args[0].id in mods):
        return f.args[1].value                           # getattr(pyautogui,"keyDown")(k)
    return None


def sites(path):
    """(basename, enclosing function or '<module>') for every emission call.

    Walks the WHOLE tree and attributes each call to its nearest enclosing
    function, so module level, class bodies, lambdas and comprehensions are all
    visible -- a planted module-level keyDown used to be invisible.
    """
    tree = ast.parse(open(path, encoding="utf-8").read())
    mods, bare = _lib_bindings(tree)
    if not mods and not bare:
        return set()
    owner = {}
    for fn in [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        for node in ast.walk(fn):
            owner[id(node)] = fn.name
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _emitter_name(node, mods, bare):
            out.add((os.path.basename(path), owner.get(id(node), "<module>")))
    return out


def project_modules():
    """Every project .py that could emit. DERIVED, never hand-kept."""
    skip = {".venv", "paddle_venv", ".claude", "agent_progress", "chiaki-ng-src",
            "chiaki-ng-build", "tests", "drafts", "__pycache__", "_obsolete",
            "tests_quarantine", "backups", "demos", "explore", "screenshot_log"}
    for dirpath, dirnames, filenames in os.walk(_ROOT):
        # A VIRTUALENV IS NOT PROJECT CODE. The first version walked into one and
        # reported 900+ "emission sites" across PIL. pyvenv.cfg marks a venv root;
        # site-packages marks its library.
        dirnames[:] = [d for d in dirnames
                       if d not in skip and not d.startswith(".")
                       and d != "site-packages"
                       and not os.path.exists(os.path.join(dirpath, d, "pyvenv.cfg"))]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


scanned, found = 0, set()
for p in project_modules():
    scanned += 1
    try:
        found |= sites(p)
    except SyntaxError:
        pass

check(100 <= scanned <= 400,
      f"scanned {scanned} project modules (want 100..400) — too few means the walk is "
      f"missing the tree, too many means it wandered into a virtualenv, "
      "so a new emitter could land anywhere in the gap")
check(found, "the scanner found NO emission sites at all — it is not scanning anything")
_new = found - EXPECTED
_gone = EXPECTED - found
check(not _new,
      f"NEW real-input emission site(s) {sorted(_new)} — add a BASEBALL_TEST_RUN "
      "lockout AND a behavioural check above, then list it in EXPECTED")
check(not _gone,
      f"expected emission site(s) {sorted(_gone)} vanished — if they were removed on "
      "purpose, drop them from EXPECTED; if renamed, the new name is unguarded")

# --- and the FIFO, which no keystroke census can see -------------------------
def _opens_for_writing(tree):
    """Builtin open(path, "w") OR the low-level os.open(path, O_WRONLY|...).

    analog_replay uses the second form on purpose -- O_WRONLY|O_NONBLOCK is how it
    refuses to block forever when no reader holds the pipe (its own comment) -- so a
    detector that knew only the builtin called the project's main stick writer a
    reader.
    """
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in {"O_WRONLY", "O_RDWR", "O_APPEND"}:
            return True
        if isinstance(n, ast.Name) and n.id in {"O_WRONLY", "O_RDWR", "O_APPEND"}:
            return True
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open":
            modes = [a for a in n.args[1:2]] + [k.value for k in n.keywords
                                                if k.arg == "mode"]
            for m in modes:
                if isinstance(m, ast.Constant) and isinstance(m.value, str) \
                        and ("w" in m.value or "a" in m.value):
                    return True
    return False


namers, writers = set(), set()
for _p in project_modules():
    try:
        _src = open(_p, encoding="utf-8").read()
    except Exception:
        continue
    if "CHIAKI_INJECT_INPUT" not in _src and "/tmp/chiaki_input" not in _src:
        continue
    namers.add(os.path.basename(_p))
    try:
        if _opens_for_writing(ast.parse(_src)):
            writers.add(os.path.basename(_p))
    except SyntaxError:
        writers.add(os.path.basename(_p))      # cannot prove it is safe

check(writers == FIFO_WRITERS,
      f"modules that name the injection FIFO AND open something for writing changed: "
      f"{sorted(writers)} vs {sorted(FIFO_WRITERS)}. A new writer sends button masks "
      "straight to the console; inject_reset.py did exactly that, unguarded.")
check(namers == FIFO_WRITERS | FIFO_READERS,
      f"modules naming the injection FIFO changed: {sorted(namers)} vs "
      f"{sorted(FIFO_WRITERS | FIFO_READERS)} — a new one is either a writer (guard it) "
      "or a reader (list it in FIFO_READERS so the writer check stays meaningful)")

print("\n" + ("FAILED: " + "; ".join(fails) if fails else
              "all three input paths are locked out under BASEBALL_TEST_RUN, "
              "the control proves the path is reachable, and the site census is exact"))
sys.exit(1 if fails else 0)
