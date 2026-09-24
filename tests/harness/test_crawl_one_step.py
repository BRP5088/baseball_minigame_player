"""tools/match_crawl.py's non-interactive entry (run_one_step / cli_main) drives
select_and_play/select_and_discard/press directly -- a FOURTH path to the console
beyond the three CLAUDE.md section 5 already enumerates. This exercises it end to
end against STUBBED capture and press functions, never the real console, and
separately proves the offline lockout fires when nobody stubs anything.

Check the neighbour's check() argument order first (CLAUDE.md "THE SUITE HAS NINE
DIFFERENT check() SIGNATURES, AND A REVERSED CALL ALWAYS PASSES"):
tests/harness/test_tools_spend_properly.py and test_every_test_sets_the_flag.py,
the two closest relatives in this directory, both use check(ok, msg) -- this file
matches them.
"""
import atexit
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))
os.environ["BASEBALL_TEST_RUN"] = "1"          # before any project import

import game_capture
import input_controller as ic
import tools.match_crawl as mc                 # noqa: E402 -- import order is the point

fails = []


def check(ok, msg):
    print(f"{'PASS' if ok else 'FAIL'}  {msg}")
    if not ok:
        fails.append(msg)


# A real 1920x1080 TURN-screen frame, not a hand crop -- run_one_step reads a WHOLE
# frame (crop_gameplay_regions cuts the hand/scoreboard/bases out of it), and this
# is the same fixture test_diamond_needs_a_turn_screen.py already uses as its TURN
# population, named rather than globbed (CLAUDE.md: never glob a directory a live
# run writes to).
FIXTURE = os.path.join(_ROOT, "test_fixtures", "give_up", "negative_gameplay_turn.jpg")


class Stubs:
    """Patches game_capture.grab / input_controller.press / select_and_play /
    select_and_discard for one `with` block, and counts every call. Also sets
    the opt-in CRAWL_DRIVE_IN_TESTS flag match_crawl.py's lockout checks for --
    it does NOT touch BASEBALL_TEST_RUN itself, so every other safety check in
    the process still sees it set.
    """

    def __init__(self, discard_ok=True, play_ok=True):
        from PIL import Image
        self.frame = Image.open(FIXTURE).convert("RGB")
        self.grab_calls = []
        self.press_calls = []
        self.play_calls = []
        self.discard_calls = []
        self.discard_ok = discard_ok
        self.play_ok = play_ok

    def _grab(self, *a, **kw):
        self.grab_calls.append((a, kw))
        return self.frame

    def _press(self, action, *a, **kw):
        self.press_calls.append(action)

    def _select_and_play(self, card_index, tactics_index=None, look=None, allow_blind=False):
        self.play_calls.append((card_index, tactics_index))
        return self.play_ok

    def _select_and_discard(self, card_index, look=None, discards_look=None):
        self.discard_calls.append(card_index)
        return self.discard_ok

    def __enter__(self):
        self._saved = (game_capture.grab, ic.press, ic.select_and_play,
                       ic.select_and_discard, mc.CRAWL_DRIVE_IN_TESTS)
        game_capture.grab = self._grab
        ic.press = self._press
        ic.select_and_play = self._select_and_play
        ic.select_and_discard = self._select_and_discard
        mc.CRAWL_DRIVE_IN_TESTS = True
        return self

    def __exit__(self, *exc):
        (game_capture.grab, ic.press, ic.select_and_play,
         ic.select_and_discard, mc.CRAWL_DRIVE_IN_TESTS) = self._saved


def _quiet(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*a, **kw)
    return result, buf.getvalue()


# ---- (a) --action look: reads, presses nothing ------------------------------
with Stubs() as s:
    session = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, session, ignore_errors=True)
    code, out = _quiet(mc.cli_main, ["--session", session, "--action", "look"])
    check(code == 0, f"(a) --action look exits 0 (got {code}); output:\n{out}")
    check(os.path.exists(os.path.join(session, "001_before.png")),
         "(a) 001_before.png written")
    check(os.path.exists(os.path.join(session, "001_before_annot.png")),
         "(a) 001_before_annot.png written")
    jpath = os.path.join(session, "001.json")
    check(os.path.exists(jpath), "(a) 001.json written")
    with open(jpath) as fh:
        r = json.load(fh)
    check("hand_rows" in r, "(a) json carries hand_rows")
    check("decision" in r, "(a) json carries the decision engine's proposal")
    check(not s.play_calls and not s.discard_calls and not s.press_calls,
         f"(a) look pressed nothing (play={s.play_calls} discard={s.discard_calls} "
         f"press={s.press_calls})")
    check(not os.path.exists(os.path.join(session, "001_after.png")),
         "(a) no after.png for a look-only step")


# ---- (b) --action d3 --dry: presses nothing, json says what it would send ---
with Stubs() as s:
    session = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, session, ignore_errors=True)
    code, out = _quiet(mc.cli_main, ["--session", session, "--action", "d3", "--dry"])
    check(code == 0, f"(b) --action d3 --dry exits 0 (got {code}); output:\n{out}")
    check(not s.discard_calls,
         f"(b) --dry pressed nothing (discard_calls={s.discard_calls})")
    with open(os.path.join(session, "001.json")) as fh:
        r = json.load(fh)
    check(r.get("dry") is True, f"(b) json marks dry=True (got {r.get('dry')!r})")
    check("select_and_discard(3)" in (r.get("acted") or ""),
         f"(b) json's acted names what it would send (acted={r.get('acted')!r})")
    check(not os.path.exists(os.path.join(session, "001_after.png")),
         "(b) no after.png for a dry run")


# ---- (c) --action d3: calls the stub with 3 exactly once, writes after + diff
with Stubs() as s:
    session = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, session, ignore_errors=True)
    code, out = _quiet(mc.cli_main, ["--session", session, "--action", "d3"])
    check(s.discard_calls == [3],
         f"(c) select_and_discard(3) called exactly once (got {s.discard_calls}); "
         f"output:\n{out}")
    check(code == 0, f"(c) a committed discard exits 0 (got {code})")
    check(os.path.exists(os.path.join(session, "001_after.png")), "(c) after.png written")
    check(os.path.exists(os.path.join(session, "001_after_annot.png")),
         "(c) after_annot.png written")
    with open(os.path.join(session, "001.json")) as fh:
        r = json.load(fh)
    check("diff" in r, f"(c) json carries a diff (keys: {sorted(r.keys())})")
    check(r.get("acted", "").endswith("COMMITTED"),
         f"(c) acted says COMMITTED (got {r.get('acted')!r})")


# ---- (c2) a REFUSED press (the stub declines) still writes json, no after ---
with Stubs(discard_ok=False) as s:
    session = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, session, ignore_errors=True)
    code, out = _quiet(mc.cli_main, ["--session", session, "--action", "d2"])
    check(code == 2, f"(c2) a refused action exits 2 (got {code})")
    check(s.discard_calls == [2], f"(c2) the stub was still called once ({s.discard_calls})")
    # A refused discard still ATTEMPTED a press (select_and_discard was called),
    # so the after-frame is still captured -- seeing "nothing changed" after a
    # refused press is exactly the diagnostic this tool exists to produce.
    check(os.path.exists(os.path.join(session, "001_after.png")),
         "(c2) after.png IS written even when the guard refused (a press was attempted)")
    with open(os.path.join(session, "001.json")) as fh:
        r = json.load(fh)
    check(bool(r.get("error") is None), "(c2) refusal is not reported as an error")


# ---- money guard: k start_match is refused, --allow-pay does not change that
with Stubs() as s:
    session = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, session, ignore_errors=True)
    code, out = _quiet(mc.cli_main, ["--session", session, "--action", "k start_match"])
    check(code == 2, f"(money) k start_match refuses (exit {code})")
    check(not s.press_calls, f"(money) start_match was never pressed ({s.press_calls})")
    code2, out2 = _quiet(mc.cli_main,
                         ["--session", session, "--action", "k start_match", "--allow-pay"])
    check(code2 == 2, f"(money) --allow-pay still refuses (exit {code2})")
    check(not s.press_calls, f"(money) still never pressed ({s.press_calls})")


# ---- (d) BASEBALL_TEST_RUN set, nothing stubbed: refuses before any capture -
_calls = []
_saved_grab = game_capture.grab


def _sentinel(*a, **kw):
    _calls.append(1)
    raise AssertionError("a stubbed capture must not be reached")


game_capture.grab = _sentinel
_saved_flag = mc.CRAWL_DRIVE_IN_TESTS
mc.CRAWL_DRIVE_IN_TESTS = False              # the control: no opt-in this time
try:
    session = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, session, ignore_errors=True)
    code, out = _quiet(mc.cli_main, ["--session", session, "--action", "look"])
    check(code == 1, f"(d) refuses with exit 1 when nothing is stubbed (got {code})")
    check(_calls == [], f"(d) the sentinel capture was never reached (calls={_calls})")
    check("BASEBALL_TEST_RUN" in out, f"(d) the refusal names the flag; output:\n{out}")
finally:
    game_capture.grab = _saved_grab
    mc.CRAWL_DRIVE_IN_TESTS = _saved_flag


# ---- (e) --summary prints one line per recorded step -------------------------
with Stubs() as s:
    session = tempfile.mkdtemp()
    atexit.register(shutil.rmtree, session, ignore_errors=True)
    mc.cli_main(["--session", session, "--action", "look"])
    mc.cli_main(["--session", session, "--action", "s"])
    code, out = _quiet(mc.cli_main, ["--summary", session])
    lines = [l for l in out.splitlines() if l.strip()]
    check(code == 0, f"(e) --summary exits 0 (got {code})")
    check(len(lines) == 2, f"(e) one line per recorded step (got {len(lines)}: {lines})")


# (f) THE GUARD SITS INSIDE look() AND apply_action(), NOT ONLY AT THE ENTRY POINTS.
# QA round 3's finder stripped look()'s own _refuse_if_test_run() call and every
# check above still passed, because they all reach look() through run_one_step,
# whose own refusal fires first. These two call the functions DIRECTLY with the
# opt-in off and a capture/press that would raise if reached: a stripped guard
# lets the sentinel fire, so the mutant cannot survive this section.
_saved_flag = mc.CRAWL_DRIVE_IN_TESTS
mc.CRAWL_DRIVE_IN_TESTS = False
_saved_grab = game_capture.grab
_saved_fast = getattr(mc.o, "_fast_grab", None)
def _sentinel_direct(*a, **k):
    raise AssertionError("capture/press reached past the guard")
try:
    game_capture.grab = _sentinel_direct
    mc.o._fast_grab = _sentinel_direct
    os.environ["BASEBALL_TEST_RUN"] = "1"
    try:
        mc.look(1)
        check(False, "(f) look() called directly under BASEBALL_TEST_RUN must refuse")
    except RuntimeError as e:
        check("REFUSING" in str(e), f"(f) look() refuses with the lockout message (got {e!r})")
    except AssertionError as e:
        check(False, f"(f) look() reached the capture: {e}")
    try:
        mc.apply_action("d3", {}, None)
        check(False, "(f) apply_action() called directly under BASEBALL_TEST_RUN must refuse")
    except RuntimeError as e:
        check("REFUSING" in str(e), f"(f) apply_action() refuses with the lockout message (got {e!r})")
    except AssertionError as e:
        check(False, f"(f) apply_action() reached a press: {e}")
finally:
    game_capture.grab = _saved_grab
    if _saved_fast is not None:
        mc.o._fast_grab = _saved_fast
    mc.CRAWL_DRIVE_IN_TESTS = _saved_flag


print()
if fails:
    print(f"{len(fails)} FAILED")
    raise SystemExit(1)
print("all checks passed")
