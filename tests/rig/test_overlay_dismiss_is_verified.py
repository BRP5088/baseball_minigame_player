"""ensure_stream._dismiss_overlay_if_blocking must VERIFY the dismiss (I-05a).

THE BUG. It sent ONE ps_button press and returned True unconditionally --
never looking again to see whether the press actually worked. Evidence
2026-09-20: a parked match, the PS5 auto-slept, `run_one_match.py` burned
"Couldn't read the screen" polls against chiaki's own host list (capture
1867x1050, looks_like_ui True), `ensure_live()` then woke the console and
returned True while the PS5 Control Center was STILL up on top of it -- the
one unverified press had not cleared it. A second press, by hand, did.

THE FIX. Look after every press (a fresh capture, judged by the SAME reader
set orchestrator's own liveness gate uses -- see ensure_stream._game_visible's
docstring for why it is that set and not a bigger one) and return True only
once a game reader actually answers. Bounded at two presses: ps_button is a
TOGGLE (CLAUDE.md section 1), so a blind third press could reopen whatever the
first two closed.

METHOD. `compass.fast_capture`, `_pid` and `_key` are swapped for fakes so
this needs no rig, no chiaki, no PS5. Each capture in the scripted sequence is
a LABEL ("overlay" or "game"); `_game_visible` is also swapped so the label
IS the answer, rather than re-deriving it from real pixels (that discrimination
-- looks_like_ui, read_bearing, is_pause_screen, at_table, load_save_dialog --
is what test_streaming_rejects_chiaki_ui.py and test_run_gates_on_liveness.py
pin against real fixtures; this file is about the PRESS-AND-VERIFY loop, not
about reading a screen).
"""
import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import sys

import compass
import ensure_stream as es

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def run(labels):
    """Drive _dismiss_overlay_if_blocking against a scripted LABEL sequence.

    Each successive compass.fast_capture() call yields the next label; once
    only one remains it repeats forever, which is what lets a single-element
    list stand for "never changes" (used for the overlay-forever case) while
    a longer list models a transition partway through.

    Returns (result, press_count).
    """
    seq = list(labels)
    presses = {"n": 0}

    real_capture = compass.fast_capture
    real_visible, real_pid, real_key = es._game_visible, es._pid, es._key

    def fake_capture():
        if len(seq) > 1:
            return seq.pop(0)
        return seq[0] if seq else "game"

    compass.fast_capture = fake_capture
    es._game_visible = lambda label: label == "game"
    es._pid = lambda: 4242
    es._key = lambda pid, code, after=1.2: presses.__setitem__("n", presses["n"] + 1)
    try:
        result = es._dismiss_overlay_if_blocking(log=lambda *a: None)
    finally:
        compass.fast_capture = real_capture
        es._game_visible, es._pid, es._key = real_visible, real_pid, real_key
    return result, presses["n"]


# --- game from the very first look: nothing to dismiss ---------------------
ok, n = run(["game"])
check("game from the start: zero presses", n == 0)
check("game from the start: reports True (a game reader already answers)",
      ok is True)

# --- overlay, then game after ONE press -------------------------------------
ok, n = run(["overlay", "game"])
check("overlay,game: exactly one press", n == 1)
check("overlay,game: reports True once the game reader answers", ok is True)

# --- overlay, overlay, then game after TWO presses --------------------------
ok, n = run(["overlay", "overlay", "game"])
check("overlay,overlay,game: exactly two presses", n == 2)
check("overlay,overlay,game: reports True", ok is True)

# --- overlay forever: CONTROL. Bounded, and honestly reports failure -------
ok, n = run(["overlay"])
check("overlay forever: bounded at exactly two presses (never a blind third)",
      n == 2)
check("overlay forever: reports False -- the budget ran out, still blocked",
      ok is False)

# =============================================================================
# HOLE 3 (skeptic, 2026-09-21): _game_visible could not tell "no reader
# answered" from "every reader RAISED" -- all nine sat in a bare
# `except Exception: pass`. A broken numpy/cv2/tesseract makes every one of
# them throw, _game_visible returns False on every frame, and that reads as a
# real overlay: two blind ps_button presses at a live match, then a stopped
# run. Fixed by counting readers that actually RAN and answering True (fail
# open) when that count is zero. This drives the REAL _game_visible (not the
# fake used above) with every underlying reader stubbed to raise.
# =============================================================================
import orchestrator as _orch
import pause_menu as _pm
import table_prompt as _tp
import reset_env as _re
import local_hand as _lh
import local_state as _ls


def _boom(*a, **k):
    raise RuntimeError("boom -- simulating a broken reader")


def _run_all_readers_raise():
    """Stub every reader _game_visible calls to raise, call the REAL
    function, and restore everything in a finally."""
    saved = {
        (compass, "read_bearing"): compass.read_bearing,
        (_pm, "is_pause_screen"): _pm.is_pause_screen,
        (_tp, "at_table"): _tp.at_table,
        (_re, "load_save_dialog"): _re.load_save_dialog,
        (_orch, "read_ban_counter"): _orch.read_ban_counter,
        (_orch, "crop_gameplay_regions"): _orch.crop_gameplay_regions,
        (_lh, "read_hand"): _lh.read_hand,
        (_ls, "read_result"): _ls.read_result,
        (_ls, "read_result_card"): _ls.read_result_card,
        (_orch, "center_card_edge_fraction"): _orch.center_card_edge_fraction,
    }
    for mod, name in saved:
        setattr(mod, name, _boom)
    try:
        from PIL import Image
        dummy = Image.new("RGB", (1920, 1080), (40, 40, 40))
        return es._game_visible(dummy)
    finally:
        for (mod, name), fn in saved.items():
            setattr(mod, name, fn)


ok = _run_all_readers_raise()
check("every reader raises: _game_visible answers True (fail open), not "
      "False (which would read as a blocked overlay and fire two blind "
      "ps_button presses at a live match)", ok is True)

print(f"\n{len(FAILS)} FAIL" if FAILS else "\nall green")
sys.exit(1 if FAILS else 0)
