"""reset_env.reset_environment() driven against a scripted screen. Fully offline.

NOTHING here reaches the PS5. input_controller, orchestrator, compass and
pause_menu are all replaced with fakes in sys.modules BEFORE reset_environment
runs — it imports those four inside its own function body, so the entries it
resolves are whatever sys.modules holds at call time. reset_env.time is
replaced too, so the 45s load wait costs nothing and the test can put the
compass back at a chosen moment.

WHY THIS EXISTS
---------------
reset_environment() is the one part of a session that used to need a human, and
it is the one part that commits an irreversible-ish action — reloading the save
— on a menu where one row below "Load Last Save" is "Load" (a save picker) and
two is "Quit to Main Menu", which drops out of the game and ends an unattended
run. Nothing on the path deletes data; both ways to misstep just silently
derail the night, which is exactly why nobody would notice.

The module's answer is that every step is VERIFIED, never assumed: navigation
reads the highlight back, the commit is gated on the screen actually changing,
and "loaded" means the compass reappeared rather than a sleep expiring. Those
three gates are only worth anything if they FAIL LOUDLY, so what is pinned here
is the raising, not the happy path:

    no chiaki focus        -> ResetError, and ZERO presses of anything
    pause never opens      -> ResetError naming which of the two causes it is
    highlight unreadable   -> ResetError, and NO blind dpad_down
    no confirmation dialog -> ResetError after ONE cross, never the second
    compass never returns  -> ResetError, and it gives up rather than hanging

and above all the interleaving invariant: every `cross` this function ever
sends must have been immediately preceded by a reading of "Load Last Save".
Counting crosses is not enough — two crosses on the wrong row is the accident.
So the fakes record presses and highlight-readings into ONE ordered log, and
the check walks it: for each cross, what did the code last believe was
selected? The adversarial cases (a D-pad that moves two rows per press, a
cursor parked on "Quit to Main Menu") exist to make that check bite.

The failure mode that actually bit this project is in the docstring of
reset_env.py: the `o` key stopped reaching the game while `look_right` and
`walk_left` kept working, so "is input reaching the game" and "is THIS key
reaching the game" are different questions. _diagnose_no_pause distinguishes
them with a probe press, and both of its branches are exercised below.
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
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import


import os
import sys
import tempfile
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

# Belt and braces: if any fake below is wrong and the REAL input_controller
# gets imported anyway, it must still not be able to press a key.
_pyautogui = types.ModuleType("pyautogui")
_pyautogui.keyDown = _pyautogui.keyUp = lambda *a, **k: None
_pyautogui.screenshot = lambda *a, **k: None
sys.modules.setdefault("pyautogui", _pyautogui)

from PIL import Image

import reset_env

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# The menu order reset_environment navigates by. Kept as a literal here rather
# than read from pause_menu, so that this file states the contract it depends
# on instead of agreeing with whatever the other module currently says.
MENU = ["Resume", "Load Last Save", "Load", "Quit to Main Menu"]
TARGET = "Load Last Save"

import pause_menu as _real_pm
check([n for n, _ in _real_pm.MENU_ITEMS] == MENU,
      f"pause_menu.MENU_ITEMS is {[n for n, _ in _real_pm.MENU_ITEMS]}, but "
      f"reset_env navigates assuming {MENU} — one of the two moved")

# Screen brightness per state. Distinct values so a stale frame is detectable:
# every fake below re-reads the image it was handed and complains if it is not
# the frame the game would be showing right now.
# Brightness levels chosen so the DELTAS BETWEEN THEM match what the real
# screens measure (2026-09-01), because deltas are the only thing the code
# under test looks at:
#
#     pause -> confirm (dialog appears)   ~78   -> 170 - 78 = 92
#     confirm -> loading (YES accepted)   29.26 -> 92 + 29 = 121
#
# The old values gave confirm -> loading a delta of 10, which is BELOW the
# pause screen's real idle noise (max 4.16) by less than a factor of three and
# below any workable gate. That made the rig demand a threshold no real screen
# could support, and it is why CONFIRM_DELTA_MIN was left at 2.0 — under the
# noise floor — where it silently passed on animation and cost a whole cycle.
LEVEL = {"gameplay": 60, "pause": 170, "confirm": 92, "loading": 121,
         "world": 80, "match": 45, "giveup": 150}


class Game:
    """A scripted PS5 screen. Every method is pure bookkeeping."""

    def __init__(self, **kw):
        self.state = "gameplay"
        self.cursor = 0
        self.focus = True
        self.pause_opens = True
        self.down_step = 1
        self.wrap = False
        self.sel_override = "keep"     # or None / a literal name
        self.confirm_drop = 78.0       # measured dialog-appearance delta
        # How many cross presses on the pause menu get DROPPED before one opens
        # the confirmation dialog. Measured live 2026-09-01 on three runs.
        self.drop_commits = 0
        # Seconds after the first OPTIONS press before the menu actually
        # renders. Measured live 2026-09-02: it appeared after the per-attempt
        # poll windows had closed, and the reset condemned it.
        self.menu_delay = 0.0
        self._menu_at = None
        self.probe_moves = 0.0         # brightness a look_right probe causes
        # TWO TRANSPORTS, because the bug was invisible while the fake had one.
        # press() models the FIFO/stick path; press_background() models the
        # Quartz keyboard path the pause key actually uses. A fake that cannot
        # tell them apart cannot fail on a diagnostic that confuses them.
        self.keyboard_dead = False
        self.bg_calls = []
        self.pid = 4242
        # In-world idle noise. reset_env's own comment measures it at 14-20,
        # and the old probe's threshold was 5.0 — under it. With this at 0 a
        # test cannot notice that, so scenarios set it deliberately.
        self.idle_noise = 0.0
        self.load_secs = 6.0
        self.bearing = 97.4
        self.events = []               # ordered ('press', a) / ('sel', v)
        self.captures = 0
        self.focus_checks = 0
        self.pause_checks = 0
        self.stale = []
        self.clock = 0.0
        self.nudge = 0.0
        self._world_at = None
        self.__dict__.update(kw)

    # --- the screen ------------------------------------------------------
    def level(self):
        if self._menu_at is not None and self.clock >= self._menu_at:
            self.state = "pause"
            self._menu_at = None
        base = LEVEL[self.state]
        if self.state == "confirm":
            base = LEVEL["pause"] - self.confirm_drop
        return int(round(base + self.nudge))

    def capture(self):
        self.captures += 1
        self.events.append(("cap", self.state))
        # Alternating idle noise, so two consecutive captures differ by
        # idle_noise even when nothing was pressed. That is what a NULL sample
        # has to see.
        v = self.level() + (self.idle_noise if self.captures % 2 else 0)
        v = max(0, min(255, int(round(v))))
        return Image.new("RGB", (64, 64), (v, v, v))

    def _fresh(self, img, who):
        got = img.convert("L").getpixel((0, 0))
        if abs(got - self.level()) > self.idle_noise:
            self.stale.append(f"{who} was handed a frame at level {got} while "
                              f"the screen shows {self.level()} — it is reusing "
                              f"a stale capture instead of taking a new one")

    # --- input_controller ------------------------------------------------
    def has_focus(self):
        self.focus_checks += 1
        return self.focus

    def frontmost_app(self):
        return "Terminal"

    def press(self, action, hold_seconds=0.05, post_delay=None):
        self.events.append(("press", action))
        if action == "toggle_pause":
            if self.pause_opens and self.state == "gameplay":
                if self.menu_delay:
                    if self._menu_at is None:
                        self._menu_at = self.clock + self.menu_delay
                else:
                    self.state = "pause"
            elif self.state == "match":
                # You cannot pause an active match (user, 2026-09-01) — OPTIONS
                # raises "Give up?" instead. Pressing it AGAIN just toggles that
                # dialog, which is how the real reset burned all its attempts.
                self.state = "giveup"
            elif self.state == "giveup":
                self.state = "match"
        elif action == "dpad_down":
            if self.state == "pause":
                n = self.cursor + self.down_step
                self.cursor = n % len(MENU) if self.wrap else min(n, len(MENU) - 1)
        elif action == "cross":
            if self.state == "giveup":
                self.state = "gameplay"      # YES quits the match to the world
            elif self.state == "pause":
                if self.drop_commits > 0:
                    self.drop_commits -= 1   # the press was lost
                else:
                    self.state = "confirm"
            elif self.state == "confirm":
                self.state = "loading"
                self._world_at = self.clock + self.load_secs
        elif action == "look_right":
            self.nudge += self.probe_moves
        elif action == "look_left":
            self.nudge -= self.probe_moves

    def press_background(self, action, hold_seconds=0.05, post_delay=None):
        """The Quartz keyboard transport. Returns whether it claims to have sent.

        When keyboard_dead it still RETURNS TRUE while moving nothing — which
        is the real failure mode: CGEventPostToPid reports nothing back, so a
        swallowed key is indistinguishable from a delivered one at the call
        site. Only the picture can tell.
        """
        self.bg_calls.append(action)
        self.events.append(("bg", action))
        if not self.keyboard_dead:
            if action == "look_right":
                self.nudge += self.probe_moves
            elif action == "look_left":
                self.nudge -= self.probe_moves
        return True

    def chiaki_pid(self, refresh=False):
        return self.pid

    # --- pause_menu ------------------------------------------------------
    def is_pause_screen(self, img):
        self.pause_checks += 1
        self._fresh(img, "is_pause_screen")
        return self.state == "pause"

    def selected_item(self, img):
        self._fresh(img, "selected_item")
        if self.state != "pause":
            val = None
        elif self.sel_override != "keep":
            val = self.sel_override
        else:
            val = MENU[self.cursor]
        self.events.append(("sel", val))
        return val

    # --- compass ---------------------------------------------------------
    def read_bearing(self, img):
        self._fresh(img, "read_bearing")
        if self.state == "loading" and self.clock >= self._world_at:
            self.state = "world"
        return self.bearing if self.state == "world" else None

    # --- clock -----------------------------------------------------------
    def sleep(self, seconds):
        self.clock += seconds

    # --- readouts --------------------------------------------------------
    def presses(self, action=None):
        p = [a for k, a in self.events if k == "press"]
        return p if action is None else [a for a in p if a == action]

    def crosses_believed(self):
        """What the code had last read as selected, at each cross it sent."""
        believed, last = [], "<nothing read>"
        for kind, val in self.events:
            if kind == "sel":
                last = val
            elif kind == "press" and val == "cross":
                believed.append(last)
        return believed


def run(label, **kw):
    """Install fakes for a fresh Game and run reset_environment against it."""
    game = Game(**kw)

    ic = types.ModuleType("input_controller")
    ic.has_focus, ic.frontmost_app, ic.press = (
        game.has_focus, game.frontmost_app, game.press)
    ic.press_background = game.press_background
    ic.chiaki_pid = game.chiaki_pid
    ic.press_path_counts = lambda: (0, len(game.bg_calls), 0)
    ic.press_path_summary = lambda: "  [input] (fake)"

    # The escalation imports ensure_stream lazily; record what it would do to
    # the real machine instead of doing it.
    es = types.ModuleType("ensure_stream")
    game.fronted = []
    game.crash_dismissed = []
    es._front_chiaki = lambda: game.fronted.append(True)
    es._dismiss_mac_crash_dialog = lambda log=print: game.crash_dismissed.append(True)
    sys.modules["ensure_stream"] = es
    orch = types.ModuleType("orchestrator")
    orch.capture_screenshot_image = game.capture
    pmenu = types.ModuleType("pause_menu")
    pmenu.is_pause_screen, pmenu.selected_item = (
        game.is_pause_screen, game.selected_item)
    comp = types.ModuleType("compass")
    comp.read_bearing = game.read_bearing
    comp.describe = lambda d: f"{d:.0f} deg"
    # reset_environment captures through compass.fast_capture (mss, ~111ms)
    # rather than orchestrator.capture_screenshot_image (~3058ms, and it
    # re-focuses the window on every call). The fake must expose it or the
    # whole sequence dies on an AttributeError before any scenario is tested —
    # which is exactly what happened, and the guard in test_no_side_effects
    # caught that this file had stopped running at all.
    comp.fast_capture = game.capture

    # The probe saves frames. Redirect them so an offline run never writes into
    # the project tree (tests/harness/test_no_side_effects.py would catch it,
    # and a diagnostic that pollutes the repo is its own defect).
    game.frame_dir = tempfile.mkdtemp(prefix=f"resetprobe_{os.getpid()}_")
    reset_env.PROBE_DIR = game.frame_dir

    sys.modules["input_controller"] = ic
    sys.modules["orchestrator"] = orch
    sys.modules["pause_menu"] = pmenu
    sys.modules["compass"] = comp
    reset_env.time = types.SimpleNamespace(sleep=game.sleep,
                                           time=lambda: game.clock)
    # give_up_dialog lives in reset_env itself and OCRs a real frame, so it is
    # patched here rather than faked through sys.modules.
    _real_give_up = reset_env.give_up_dialog
    reset_env.give_up_dialog = lambda img: game.state == "giveup"

    result, error = None, None
    game._restore_give_up = lambda: setattr(reset_env, "give_up_dialog", _real_give_up)
    try:
        result = reset_env.reset_environment(log=lambda *a: None)
    except reset_env.ResetError as exc:
        error = str(exc)
    except Exception as exc:                       # noqa: BLE001
        fails.append(f"{label}: raised {type(exc).__name__} ({exc}) instead of "
                     f"ResetError — an unattended caller only catches ResetError")

    # Non-vacuity: the fakes must actually have been the things it talked to.
    if game.captures == 0 and game.focus:
        fails.append(f"{label}: the fake orchestrator was never asked for a "
                     f"frame — the patch did not take and this scenario proved "
                     f"nothing")
    for s in game.stale:
        fails.append(f"{label}: {s}")
    return game, result, error


def must_raise(label, error, needle):
    check(error is not None,
          f"{label}: returned normally instead of raising ResetError")
    if error is not None:
        check(needle.lower() in error.lower(),
              f"{label}: raised, but the message ({error!r}) never mentions "
              f"{needle!r} — an unattended run is diagnosed from this string")


# =========================================================================
# 1. No focus: raise, and press absolutely nothing.
# =========================================================================
# Without focus every press below vanishes, so each later step would fail for a
# reason unrelated to the real cause. The check has to come first, and it has
# to come before any input.
g, res, err = run("no focus", focus=False)
must_raise("no focus", err, "frontmost")
check(g.presses() == [],
      f"no focus: pressed {g.presses()} anyway — those keys went to whatever "
      f"app IS in front")
check(g.captures == 0,
      f"no focus: took {g.captures} screenshot(s) before checking focus — the "
      f"focus gate is not the first thing that happens")
check(g.focus_checks >= 1, "no focus: has_focus was never called at all")

# =========================================================================
# 2. Pause menu never opens.
# =========================================================================
# Both branches of _diagnose_no_pause, because telling them apart is the whole
# reason it exists: one is fixable by the user, the other is not.
# THE PROBE MUST TOUCH THE TRANSPORT IT CONDEMNS. The old probe pressed
# look_right, which is in STICK_AXES and not BUTTON_BITS, so it went over the
# FIFO and never touched a key — and the message then blamed the 'o' key and
# keyboard focus. These scenarios exist because a fake with ONE transport
# cannot notice that; press() is the FIFO here and press_background() is the
# keyboard.
#
# idle_noise is set deliberately: reset_env documents in-world idle noise at
# 14-20 while the old gate was `moved > 5.0`, so a dead transport used to read
# as alive. Each verdict is paired against this scene's own null.

# A3 — NEITHER transport moves the picture.
g, res, err = run("probe: neither transport", pause_opens=False,
                  keyboard_dead=True, probe_moves=0.0, idle_noise=15.0)
must_raise("probe: neither transport", err, "neither transport")
check(len(g.presses("toggle_pause")) == 3,
      f"pause dead: pressed pause {len(g.presses('toggle_pause'))} times, "
      f"expected 3 (PAUSE_OPEN_ATTEMPTS) — it either gave up early or is "
      f"retrying without bound against a problem only the user can fix")
check("cross" not in g.presses(),
      "pause dead: sent a cross even though the menu never opened")
check(not g.fronted,
      "neither transport: fronted chiaki anyway — escalation must be gated on "
      "the one signature it can fix, not run on every failure")

# A1 — THE OBSERVED FAILURE: keyboard dead, FIFO alive.
g, res, err = run("probe: keyboard dead", pause_opens=False,
                  keyboard_dead=True, probe_moves=60.0, idle_noise=15.0)
must_raise("probe: keyboard dead", err, "keyboard transport")
check(g.bg_calls,
      "keyboard dead: press_background was never called — the probe never "
      "touched the transport it is about to blame, which is the whole bug")
check(g.presses("look_right") and g.presses("look_left"),
      f"probe branch: presses were {g.presses()} — the camera probe must both "
      f"turn and turn back, or a failed reset also leaves the view rotated")
check("look_left" in g.bg_calls,
      "keyboard dead: the keyboard probe turned the camera and never turned it "
      "back")
check(g.fronted and g.crash_dismissed,
      "keyboard dead: did not escalate — this is the one signature fronting "
      "chiaki can fix, and the old code only ADVISED the user to do it")
check(len(g.presses("toggle_pause")) == 4,
      f"keyboard dead: pressed pause {len(g.presses('toggle_pause'))} times; "
      f"expected 3 attempts plus exactly 1 retry after fronting")
check("focus" not in err.lower().split("candidates")[0],
      f"keyboard dead: asserted focus as the cause before listing candidates "
      f"— {err!r}")

# A2 — BOTH alive. This is the case the old code got exactly backwards: it
# would blame the 'o' key and focus while the key was in fact being delivered.
g, res, err = run("probe: both alive", pause_opens=False,
                  keyboard_dead=False, probe_moves=60.0, idle_noise=15.0)
must_raise("probe: both alive", err, "both input transports are alive")
check("keyboard focus" not in err.lower() and "'o' key" not in err.lower(),
      f"both alive: still blamed the keyboard/focus — {err!r}")
check(not g.fronted,
      "both alive: fronted chiaki even though the keyboard was delivering")

# A5 — NULL DISCIPLINE. The null must be a real capture..capture pair with no
# press between them, not the pre-press frame reused.
first_bg = next((i for i, (k, _) in enumerate(g.events) if k == "bg"), None)
check(first_bg is not None and first_bg >= 2
      and [k for k, _ in g.events[first_bg - 2:first_bg]] == ["cap", "cap"],
      f"null discipline: the two events before the keyboard probe were "
      f"{[k for k, _ in g.events[max(0, (first_bg or 2) - 2):first_bg]]}, not a "
      f"clean capture..capture pair — the control measured a scene that had "
      f"already been disturbed, so the null is not a null")

# A4 — POSITIVE CONTROL. A healthy reset must probe nothing, front nothing and
# write no frames. Without this the file would pass with the diagnostic firing
# on every reset.
g, res, err = run("probe: healthy reset never probes")
check(err is None, f"healthy reset raised {err!r}")
check(not g.bg_calls and not g.presses("look_right") and not g.fronted,
      f"healthy reset probed anyway: bg={g.bg_calls}, "
      f"look_right={g.presses('look_right')}, fronted={g.fronted} — the "
      f"diagnostic must cost nothing when nothing is wrong")
check(not os.listdir(g.frame_dir),
      f"healthy reset wrote frames into {g.frame_dir} — diagnostic output on "
      f"the success path is noise that hides the real failures")

# =========================================================================
# 3. Highlight unreadable -> refuse, do not press blindly.
# =========================================================================
# This is the gate that stops the whole class of accident. pause_menu abstains
# when it is not sure; reset_environment must treat that as a stop, not as
# permission to nudge the cursor and look again.
g, res, err = run("highlight unreadable", state="pause", sel_override=None)
must_raise("highlight unreadable", err, "refusing to press blindly")
check("dpad_down" not in g.presses(),
      "unreadable highlight: pressed dpad_down anyway — moving a cursor you "
      "cannot see is how it ends up on 'Quit to Main Menu'")
check("cross" not in g.presses(),
      "unreadable highlight: sent a cross with no idea what was selected")

# =========================================================================
# 4. It never presses cross on the wrong row. THE point of the module.
# =========================================================================
# 4a. A D-pad that moves two rows per press steps straight over the target.
g, res, err = run("dpad overshoots", state="pause", down_step=2)
must_raise("dpad overshoots", err, "never landed")
check(g.crosses_believed() == [],
      f"overshoot: sent cross while believing {g.crosses_believed()} was "
      f"selected — those rows are 'Load' and 'Quit to Main Menu'")
check(len(g.presses("dpad_down")) == 5,
      f"overshoot: pressed dpad_down {len(g.presses('dpad_down'))} times, "
      f"expected 5 — the navigation loop is not bounded where it was")

# 4b. Cursor parked on the row that ends the session, D-pad doing nothing.
g, res, err = run("stuck on quit", state="pause", cursor=3, down_step=0)
must_raise("stuck on quit", err, "never landed")
check("cross" not in g.presses(),
      "stuck on 'Quit to Main Menu': sent a cross — this is the press that "
      "drops out of the game and ends the night")

# 4c. Wrapping menu: it must navigate by READING, not by a fixed press count.
g, res, err = run("wraps around to target", state="pause", cursor=2, wrap=True)
check(err is None, f"wrap: raised {err!r} — from 'Load' the cursor reaches "
                   f"'Load Last Save' in three Downs and it should follow it")
check(len(g.presses("dpad_down")) == 3,
      f"wrap: pressed dpad_down {len(g.presses('dpad_down'))} times, expected "
      f"3 — it is counting presses rather than reading the highlight back")
check(g.crosses_believed() == [TARGET, TARGET],
      f"wrap: crosses landed while believing {g.crosses_believed()}")

# =========================================================================
# 5. The commit is gated on the dialog actually appearing.
# =========================================================================
# Two-sided, against brightness deltas chosen from the screen rather than from
# CONFIRM_DELTA_MIN, so the threshold cannot drift in either direction unseen.
g, res, err = run("dialog never appeared", state="pause", confirm_drop=1.0)
must_raise("dialog never appeared", err, "no confirmation dialog")
check(len(g.presses("cross")) == 1,
      f"no dialog: sent {len(g.presses('cross'))} crosses, expected exactly 1 "
      f"— the second cross is the YES, and sending it into a screen that never "
      f"changed is pressing into the unknown")

# 4.0 WAS asserted here as "a real dialog, barely". It is not: the pause screen
# idles at 1.68-4.16 (ten samples, 2026-09-01), so this case was pinning the
# gate open at exactly the noise level that made the reset fail three times in
# a row while reporting success. It is now the REJECTION case.
g, res, err = run("noise mistaken for a dialog", state="pause", confirm_drop=4.16)
must_raise("noise mistaken for a dialog", err, "no confirmation dialog")
check(len(g.presses("cross")) == 1,
      f"noise: sent {len(g.presses('cross'))} crosses, expected exactly 1 — a "
      f"4.16 delta is the screen animating, and sending YES into it is the bug "
      f"that wasted three reset attempts and a whole cycle")

# The smallest change actually observed for a REAL transition (YES accepted,
# dialog -> loading screen) was 29.26. The gate must still pass that.
g, res, err = run("faint but real dialog", state="pause", confirm_drop=25.0)
check(err is None,
      f"a 25.0 delta is well clear of the 4.16 noise floor but the run raised "
      f"{err!r} — the gate has tightened past what the screen delivers")
check(len(g.presses("cross")) == 2,
      f"faint dialog: sent {len(g.presses('cross'))} crosses, expected 2")

# =========================================================================
# 6. "Loaded" means the compass came back, and the wait is bounded.
# =========================================================================
# 36.0s is 80% of the 45s the module allows, written as a literal on purpose:
# derived from LOAD_TIMEOUT_SEC it would pass for any value of it.
g, res, err = run("world returns late", state="pause", load_secs=36.0)
check(err is None, f"a load finishing at 36s is inside the budget but the run "
                   f"raised {err!r} — it is giving up on slow but healthy loads")
check(res == 97.4, f"returned {res!r} instead of the spawn bearing 97.4 — "
                   f"callers replay a recorded walk from this number")
check(g.clock >= 36.0,
      f"claimed the world was back after {g.clock:.1f}s of waiting, but the "
      f"compass only returned at 36.0s — it is not actually waiting for it")

g, res, err = run("world never returns", state="pause",
                  load_secs=float("inf"))
must_raise("world never returns", err, "compass never reappeared")
check(g.clock <= 60.0,
      f"waited {g.clock:.0f}s before giving up — the bound is 45s, and an "
      f"unattended caller cannot be left hanging on a load that failed")
check(len(g.presses("cross")) == 2,
      f"never returned: sent {len(g.presses('cross'))} crosses, expected 2")

# =========================================================================
# 7. Happy path, end to end, from live gameplay.
# =========================================================================
# Starts OUTSIDE the menu so the open-the-pause loop is actually exercised —
# starting on the pause screen would satisfy it on iteration one and the loop
# under test would never run.
g, res, err = run("happy path")
check(err is None, f"happy path raised {err!r}")
check(res == 97.4, f"happy path returned {res!r}, expected the bearing 97.4")
check(len(g.presses("toggle_pause")) == 1,
      f"happy path pressed pause {len(g.presses('toggle_pause'))} times, "
      f"expected 1 — a second press would close the menu again")
check(len(g.presses("dpad_down")) == 1,
      f"happy path pressed dpad_down {len(g.presses('dpad_down'))} times, "
      f"expected 1 — Load Last Save is exactly one row below Resume")
check(len(g.presses("cross")) == 2,
      f"happy path sent {len(g.presses('cross'))} crosses, expected exactly 2 "
      f"(commit, then YES)")

# --- the invariant, over every scenario run above -------------------------
# Re-run the whole set and assert the one property that matters across all of
# them at once, so a future scenario cannot be added without it applying.
for label, kw in [("happy path", {}),
                  ("wrap", dict(state="pause", cursor=2, wrap=True)),
                  ("overshoot", dict(state="pause", down_step=2)),
                  ("stuck on quit", dict(state="pause", cursor=3, down_step=0)),
                  ("unreadable", dict(state="pause", sel_override=None)),
                  ("lies 'Load'", dict(state="pause", sel_override="Load")),
                  ("lies 'Quit'", dict(state="pause",
                                       sel_override="Quit to Main Menu")),
                  ("no dialog", dict(state="pause", confirm_drop=1.0)),
                  ("slow load", dict(state="pause", load_secs=36.0))]:
    g, res, err = run(label, **kw)
    bad = [b for b in g.crosses_believed() if b != TARGET]
    check(not bad,
          f"{label}: sent cross(es) while the last highlight it read was "
          f"{bad} — a cross on any row but {TARGET!r} is the accident this "
          f"whole module exists to prevent")

# =========================================================================
# 8. A match is in progress: OPTIONS opens "Give up?", not the pause menu.
# =========================================================================
# The reset used to press OPTIONS, see no pause menu, and raise "the pause menu
# will not open and NO input is reaching the game" — the opposite of the truth,
# because the press HAD worked and put the dialog up. Two runs died on that on
# 2026-09-01 with a healthy stream and working input.
g, res, err = run("match in progress", state="match")
check(err is None,
      f"a reset starting mid-match raised {err!r} — it must quit the match and "
      f"carry on; the reload discards the match anyway, so this costs nothing")
check(res == 97.4,
      f"returned {res!r} instead of the spawn bearing — the reset did not "
      f"complete from a mid-match start")
_seq = [a for _k, a in g.events if _k == "press"]
check("cross" in _seq and _seq.index("cross") < _seq.count("toggle_pause") + 99,
      f"never answered the Give up? dialog; pressed {_seq}")
check(_seq.count("toggle_pause") <= 2,
      f"pressed OPTIONS {_seq.count('toggle_pause')} times against a Give up? "
      f"dialog — pressing it again just toggles the dialog, which is exactly "
      f"how the real reset burned all three attempts")

# =========================================================================
# 10. The press that OPENS the dialog is retried, like the YES that follows.
# =========================================================================
# A dropped commit press failed three runs on 2026-09-01 with "no confirmation
# dialog appeared (delta 2.4 / 3.0)", while the very next manual cross opened it
# at delta 83.8 — the press was lost, not the detector wrong. The YES press had
# been retried since it first failed; this one never was.
g, res, err = run("commit press dropped once", state="pause", drop_commits=1)
check(err is None,
      f"one dropped commit press still killed the reset ({err!r}). It must be "
      f"retried, exactly as the YES press already is")
check(res == 97.4, f"returned {res!r} after recovering from a dropped press")
_crosses = [a for _k, a in g.events if _k == "press" and a == "cross"]
check(len(_crosses) == 3,
      f"sent {len(_crosses)} crosses for one dropped commit; expected 3 "
      f"(dropped commit, successful commit, YES)")

# ...but it must NOT keep pressing forever.
g, res, err = run("commit press never lands", state="pause", drop_commits=99)
must_raise("commit press never lands", err, "no confirmation dialog")
_crosses = [a for _k, a in g.events if _k == "press" and a == "cross"]
check(len(_crosses) <= 4,
      f"sent {len(_crosses)} crosses into a menu that never responded — the "
      f"retry must be bounded")


# =========================================================================
# 11. A menu that opens LATE must not be condemned.
# =========================================================================
# Measured live 2026-09-02: the reset raised "the pause menu will not open and
# NO input is reaching the game (probe delta 4.9)" while the menu was open —
# is_pause_screen() then read True on 15 consecutive samples. The probe cannot
# support that claim either: in-world idle noise alone measures 14-20, so 4.9
# says the screen was not in the world, not that input was dead.
g, res, err = run("menu opens late", state="gameplay", menu_delay=14.0)
check(err is None,
      f"a menu that rendered 14s in was condemned with {err!r}. That message "
      f"sent two separate investigations at the input path while input was "
      f"fine")
check(res == 97.4, f"returned {res!r} after the menu appeared late")

# ...but a menu that NEVER opens must still fail, and say so.
g, res, err = run("menu never opens", state="gameplay", pause_opens=False)
must_raise("menu never opens", err, "pause menu will not open")


# --- A BAN SCREEN MUST NOT BE NAVIGATED AS A MENU -----------------------------
# is_pause_screen cannot tell the pause book from the BAN book: over 10,239 frames,
# 1,122 of 1,140 ban frames clear PAGE_MIN_FRAC 0.80 (BAN 0.7101..0.8587 vs PAUSE
# 0.9263..0.9446), and MENU_TEXT_MIN_FRAC overlaps completely, so no threshold on
# that quantity separates two notebooks. reset_env used to break on that and then
# navigate it AS A MENU -- selected_item() names an entry on 19 of 1,140 ban frames,
# so up to five dpad_down presses land in a live ban screen. It never named 'Load
# Last Save' in those 1,140, so no `cross` followed; that is luck, not a guard.
#
# reset_env imports input_controller and pause_menu INSIDE the function, so they are
# locals -- the real modules are what must be patched, not attributes of reset_env.
import reset_env as _re2
import input_controller as _ic2
import pause_menu as _pm2
import orchestrator as _o2          # the FAKE this file installed in sys.modules

_pressed2 = []
_saved2 = (_pm2.is_pause_screen, _ic2.press, _re2.give_up_dialog,
           getattr(_o2, "read_ban_counter", None))
try:
    _pm2.is_pause_screen = lambda img: True     # the guard that admits a ban screen
    _o2.read_ban_counter = lambda img: 1        # ...but the ban counter answers
    _ic2.press = lambda k, *a, **kw: _pressed2.append(k)
    _re2.give_up_dialog = lambda img: False
    try:
        _re2.reset_environment(log=lambda *a: None)
        _ok2 = False
    except _re2.ResetError as _e2:
        _ok2 = "ban screen" in str(_e2)
    except Exception:
        _ok2 = False
    _nav2 = [k for k in _pressed2 if k in ("dpad_down", "move_down", "cross")]
    check(_ok2, "a ban screen must be REFUSED, not navigated as a menu — "
                "is_pause_screen admits both notebooks")
    check(not _nav2, f"menu navigation was pressed into a live ban screen: {_nav2}")
finally:
    (_pm2.is_pause_screen, _ic2.press, _re2.give_up_dialog) = _saved2[:3]
    if _saved2[3] is None:
        if hasattr(_o2, "read_ban_counter"):
            delattr(_o2, "read_ban_counter")
    else:
        _o2.read_ban_counter = _saved2[3]


if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  reset_environment raises ResetError (pressing nothing) with no focus, "
      "names which of the two input failures blocked the pause menu, refuses "
      "to move an unreadable cursor, stops after one cross when no dialog "
      "appears, gives up on a load that never lands and waits out one that "
      "does; across 9 scripted screens every cross it ever sent was preceded "
      "by a verified 'Load Last Save'")
