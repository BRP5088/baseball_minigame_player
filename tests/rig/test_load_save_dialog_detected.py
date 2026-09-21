"""reset_env.load_save_dialog and its wiring into reset_environment (I-23).

WHY THIS EXISTS
---------------
reset_environment's commit step used to gate ONLY on a frame-DELTA against a
baseline taken right before the commit press. Live 2026-09-20
(overnight/run_live_20260920e.log), three retries all logged "no dialog yet"
and the function raised ResetError — against a frame
(test_fixtures/load_last_save_dialog_live_20260920.png) that shows the "Load
Last Save" confirmation dialog FULLY UP. Traced in reset_env.py: the bug was
not a stale baseline (ISSUES.md's first hypothesis) — it is that the retry
loop's LAST press was never polled again before the function gave up. See the
long comment above `_poll_dialog` inside reset_environment.

`load_save_dialog` (mirrors `give_up_dialog`, same box shape, same OCR
approach) fixes it two ways: it is asked before the very first press (so an
ALREADY-open dialog is never pressed again) and after every press including
the last one, and it counts on its own regardless of what the delta says.

Section 1 below is the reader alone, against the live fixture and the
negative population from agent_progress/issues/I-23/progress.md (656
1920x1080 fixtures scored, one true positive: the fixture itself). Section 2
threads it through reset_environment with a scripted screen, mirroring
test_reset_sequence.py's Game/run() style, for the specific shape ISSUES.md's
OTHER hypothesis describes: the dialog is already showing by the time this
section's own baseline is captured, so the delta between "before" and every
later frame is ~0.0 forever — a real console dialog that has landed and is
not animating gives a pure-delta gate nothing to see. Section 3 is the
control: force load_save_dialog False and confirm the SAME scripted run still
raises, so the fallback delta is not secretly the thing that saves it.
"""
import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import os
import sys
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

_pyautogui = types.ModuleType("pyautogui")
_pyautogui.keyDown = _pyautogui.keyUp = lambda *a, **k: None
_pyautogui.screenshot = lambda *a, **k: None
sys.modules.setdefault("pyautogui", _pyautogui)

import numpy as np
from PIL import Image

import reset_env

FIX = os.path.join(_ROOT, "test_fixtures")
DIALOG_FIXTURE = os.path.join(FIX, "load_last_save_dialog_live_20260920.png")

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# =========================================================================
# 1. THE READER ALONE: one positive, nine negatives across the screen
#    classes ISSUES.md named (pause without the dialog at both live
#    geometries, a bright pause-adjacent wall, the give_up dialog — a
#    DIFFERENT dark panel, same shape — a world/dealer-prompt frame, two ban
#    screens and two result screens).
# =========================================================================
if not os.path.exists(DIALOG_FIXTURE):
    fails.append(f"missing {DIALOG_FIXTURE} — this test must not silently "
                 "skip the one frame it exists to recognise")
else:
    got = reset_env.load_save_dialog(Image.open(DIALOG_FIXTURE))
    check(got is True,
          f"load_save_dialog on the live I-23 fixture returned {got!r}, "
          f"expected True")

NEGATIVES = [
    "pause_menu/gameplay_bright_wall.png",       # bright wall, pause-adjacent
    "pause_menu/load_last_save_selected.png",    # pause menu, "Load Last
                                                   # Save" HIGHLIGHTED in the
                                                   # ROW, no dialog — the
                                                   # adversarial one: the same
                                                   # three words are ON SCREEN
                                                   # (1867x1050, not 1920x1080)
    "give_up/give_up_dialog.jpg",                 # a DIFFERENT dark dialog
    "give_up/negative_gameplay_turn.jpg",         # world / gameplay turn
    "give_up/negative_ban_screen.jpg",            # ban screen
    "ban_grid/splash_banning_phase.png",          # ban screen, mid-animation
    "result_screens/winner_live_20260920.png",    # result screen, WINNER
    "result_screens/defeat_live_20260920.png",    # result screen, LOSER
    "table_prompt_live.jpg",                      # world, dealer prompt up
]

neg_checked = 0
for rel in NEGATIVES:
    p = os.path.join(FIX, rel)
    if not os.path.exists(p):
        fails.append(f"missing negative fixture {rel} — a check that cannot "
                     "run is not a check")
        continue
    img = Image.open(p)
    got = reset_env.load_save_dialog(img)
    neg_checked += 1
    check(got is False,
          f"{rel} ({img.size}): load_save_dialog returned True — a false "
          f"positive here would let reset_environment answer the confirm "
          f"dialog on the wrong screen")

check(neg_checked >= 8,
      f"only {neg_checked} negative fixtures were actually checked, need "
      f">= 8 (ISSUES.md I-23's requirement)")


# =========================================================================
# 2 & 3. WIRED INTO reset_environment: the confirm dialog is showing on
#    EVERY capture from the very start — i.e. it is already up before
#    reset_environment ever takes ITS OWN commit-step baseline, exactly
#    ISSUES.md's other hypothesis — and stays visually IDENTICAL (a real,
#    landed, non-animating dialog) until it is genuinely answered. So the
#    delta between any two samples is 0.0 for as long as nothing has
#    answered it: a pure-delta gate has nothing to see. `is_pause_screen`/
#    `selected_item` are state-driven fakes (as in test_reset_sequence.py's
#    Game), decoupled from the pixels, so navigation (steps 1-2, not what
#    this scenario is about) succeeds normally before the dialog is ever
#    looked at as PIXELS.
# =========================================================================
DIALOG_IMG = Image.open(DIALOG_FIXTURE).convert("RGB")
WORLD_IMG = Image.new("RGB", DIALOG_IMG.size, (220, 220, 220))  # bright,
                                                                  # nothing like
                                                                  # the dark
                                                                  # dialog frame


class Game:
    """The dialog is up from t=0 and stays up until a cross press LANDS —
    `press_lands` controls whether that can ever happen, so the control run
    can model "every press into it was dropped", which is what the real
    incident's log literally said three times."""

    def __init__(self, press_lands=True):
        self.press_lands = press_lands
        self.answered = False
        self.crosses = 0
        self.clock = 0.0

    # --- input_controller --------------------------------------------
    def has_focus(self):
        return True

    def frontmost_app(self):
        return "Terminal"

    def press(self, action, hold_seconds=0.05, post_delay=None):
        if action == "cross":
            self.crosses += 1
            if self.press_lands and not self.answered:
                self.answered = True

    def press_background(self, action, hold_seconds=0.05, post_delay=None):
        return True

    def chiaki_pid(self, refresh=False):
        return 4242

    # --- orchestrator / compass.fast_capture --------------------------
    def capture(self):
        return WORLD_IMG.copy() if self.answered else DIALOG_IMG.copy()

    # --- pause_menu (state-driven, not pixel-driven — see the header) --
    def is_pause_screen(self, img):
        return not self.answered

    def selected_item(self, img):
        return None if self.answered else "Load Last Save"

    # --- compass --------------------------------------------------------
    def read_bearing(self, img):
        return 97.4 if self.answered else None

    def sleep(self, seconds):
        self.clock += seconds


def _run(game, force_content_false):
    """Install fakes for a Game and run reset_environment end to end.
    Returns (result, error)."""
    ic = types.ModuleType("input_controller")
    ic.has_focus, ic.frontmost_app, ic.press = (
        game.has_focus, game.frontmost_app, game.press)
    ic.press_background = game.press_background
    ic.chiaki_pid = game.chiaki_pid
    ic.press_path_counts = lambda: (0, 0, 0)
    ic.press_path_summary = lambda: "  [input] (fake)"

    es = types.ModuleType("ensure_stream")
    es._front_chiaki = lambda: None
    es._dismiss_mac_crash_dialog = lambda log=print: None
    sys.modules["ensure_stream"] = es

    orch = types.ModuleType("orchestrator")
    orch.capture_screenshot_image = game.capture
    sys.modules["orchestrator"] = orch

    pmenu = types.ModuleType("pause_menu")
    pmenu.is_pause_screen, pmenu.selected_item = (
        game.is_pause_screen, game.selected_item)
    sys.modules["pause_menu"] = pmenu

    comp = types.ModuleType("compass")
    comp.read_bearing = game.read_bearing
    comp.describe = lambda d: f"{d:.0f} deg"
    comp.fast_capture = game.capture
    sys.modules["compass"] = comp

    sys.modules["input_controller"] = ic
    # A FAKE CLOCK, not the real one — time.sleep advances it and time.time
    # reads it, so the polling loop inside reset_environment (up to
    # CONFIRM_WAIT_SEC of real-looking waiting per press) completes instantly
    # instead of busy-spinning for several real seconds per press. Same
    # technique as test_reset_sequence.py's Game.
    reset_env.time = types.SimpleNamespace(sleep=game.sleep,
                                           time=lambda: game.clock)
    _real_give_up = reset_env.give_up_dialog
    _real_load_save = reset_env.load_save_dialog
    reset_env.give_up_dialog = lambda img: False
    if force_content_false:
        reset_env.load_save_dialog = lambda img: False

    result, error = None, None
    try:
        result = reset_env.reset_environment(log=lambda *a: None)
    except reset_env.ResetError as exc:
        error = str(exc)
    except Exception as exc:                       # noqa: BLE001
        fails.append(f"scripted run: raised {type(exc).__name__} ({exc}) "
                     f"instead of ResetError")
    finally:
        reset_env.give_up_dialog = _real_give_up
        reset_env.load_save_dialog = _real_load_save
    return result, error


# --- 2. The real reader wired in: it must complete, not raise -----------
game = Game(press_lands=True)
res, err = _run(game, force_content_false=False)
check(err is None,
      f"with load_save_dialog live, a dialog that was already up before "
      f"the commit baseline was taken still raised {err!r} — this is "
      f"exactly the I-23 shape and the content reader exists to catch it")
check(res == 97.4, f"succeeded but returned {res!r}, expected the spawn "
                   f"bearing 97.4")
check(game.crosses == 1,
      f"pressed cross {game.crosses} time(s); expected exactly 1 (the "
      f"explicit YES press) — the (a) pre-press check exists so the commit "
      f"step itself never presses into a dialog it already sees is up")

# --- 3. CONTROL: force the content reader False; delta alone must fail --
# Every press into the dialog is DROPPED (press_lands=False) — modelling the
# real incident's own log line, "the commit press did not land", rather than
# assuming a press that never gets checked would have worked anyway.
game2 = Game(press_lands=False)
res2, err2 = _run(game2, force_content_false=True)
check(err2 is not None,
      f"control: with load_save_dialog forced False, the SAME scripted "
      f"dialog-already-up scenario returned {res2!r} instead of raising — "
      f"which would mean the delta fallback was silently doing the work "
      f"the content reader is supposed to be doing")
if err2 is not None:
    check("no confirmation dialog" in err2.lower(),
          f"control raised, but not the expected message: {err2!r}")


# =========================================================================
# 4. THE AFTER-PRESS CONTENT FALLBACK, SPECIFICALLY — not the pre-press
#    check (sections 2-3 above never let the dialog become visible-but-
#    undetected-by-delta AFTER a press; the dialog was either already up at
#    img0, or never resolved at all). This scenario is not visible at img0
#    (load_save_dialog(img0) correctly reads False, so branch (a) does NOT
#    fire) but appears after the first commit press with a delta far too
#    small to notice — the dialog panel's TITLE TEXT is the only thing that
#    changed, and that crop is a small fraction of a 1920x1080 frame.
# =========================================================================
_w, _h = DIALOG_IMG.size
_bx0, _by0, _bx1, _by1 = reset_env.LOAD_SAVE_BOX
_box_px = (int(_w * _bx0), int(_h * _by0), int(_w * _bx1), int(_h * _by1))
# Sample the panel's own fill just above the title band (inside the dark
# panel, no text) and paint over the title with it — same panel, no words.
_fill_patch = DIALOG_IMG.crop((_box_px[0], _box_px[1] - 20, _box_px[0] + 50,
                               _box_px[1] - 5))
_fill = tuple(int(v) for v in
             np.asarray(_fill_patch).reshape(-1, 3).mean(axis=0))
BEFORE_IMG = DIALOG_IMG.copy()
BEFORE_IMG.paste(Image.new("RGB", (_box_px[2] - _box_px[0], _box_px[3] - _box_px[1]), _fill),
                 (_box_px[0], _box_px[1]))

check(reset_env.load_save_dialog(BEFORE_IMG) is False,
      "BEFORE_IMG (title text blanked) must read False on its own, or this "
      "scenario is not testing what it claims to")
_delta_before_dialog = float(np.abs(
    np.asarray(BEFORE_IMG.convert("L"), dtype=float) -
    np.asarray(DIALOG_IMG.convert("L"), dtype=float)).mean())
check(_delta_before_dialog < 5.0,
      f"BEFORE_IMG vs DIALOG_IMG delta is {_delta_before_dialog:.2f}, too "
      f"close to CONFIRM_DELTA_MIN ({reset_env.CONFIRM_DELTA_MIN}) for this "
      f"scenario to isolate the content path cleanly (measured 0.25 when "
      f"this was built)")


class Game4:
    """capture() shows BEFORE_IMG until the first cross lands, then DIALOG_IMG
    forever — deliberately no further "world" transition, so this scenario
    tests only whether the COMMIT step (I-23's own concern) resolves, not
    the separate, already-tested YES-verification loop below it."""

    def __init__(self):
        self.pressed = 0
        self.clock = 0.0

    def has_focus(self):
        return True

    def frontmost_app(self):
        return "Terminal"

    def press(self, action, hold_seconds=0.05, post_delay=None):
        if action == "cross":
            self.pressed += 1

    def press_background(self, action, hold_seconds=0.05, post_delay=None):
        return True

    def chiaki_pid(self, refresh=False):
        return 4242

    def capture(self):
        return BEFORE_IMG.copy() if self.pressed == 0 else DIALOG_IMG.copy()

    def is_pause_screen(self, img):
        return self.pressed == 0

    def selected_item(self, img):
        return "Load Last Save" if self.pressed == 0 else None

    def read_bearing(self, img):
        return None   # never reached; this scenario is about the commit
                      # step only, and stops one way or the other before here

    def sleep(self, seconds):
        self.clock += seconds


# --- 4a. Content enabled: the commit step itself must resolve -----------
game4a = Game4()
_, err4a = _run(game4a, force_content_false=False)
check(err4a is not None and "no confirmation dialog" not in err4a.lower(),
      f"with load_save_dialog live, a dialog that appears AFTER the first "
      f"press with a delta too small to notice still raised "
      f"'no confirmation dialog appeared': {err4a!r} — the after-press "
      f"content fallback exists exactly for this case. (It still raises "
      f"SOME error here, from the separate YES-verification loop this "
      f"scenario deliberately does not model past the commit step — that "
      f"is expected and not what this check is about.)")

# --- 4b. CONTROL: content forced False — delta alone must raise, and with
#    the SPECIFIC "no confirmation dialog appeared" message this time,
#    because now the commit step itself is what fails.
game4b = Game4()
_, err4b = _run(game4b, force_content_false=True)
check(err4b is not None and "no confirmation dialog" in err4b.lower(),
      f"control: with load_save_dialog forced False, the same "
      f"delta-too-small-to-notice scenario did not raise "
      f"'no confirmation dialog appeared' ({err4b!r}) — the content "
      f"fallback inside _poll_dialog must be the thing resolving 4a, not "
      f"something else")


if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print(f"  load_save_dialog: True on the live I-23 fixture, False on "
      f"{neg_checked} other screens; wired into reset_environment it "
      f"completes a reset whose dialog was already up before the delta "
      f"baseline was taken, and the control (content reader forced False) "
      f"confirms the delta alone still cannot")
