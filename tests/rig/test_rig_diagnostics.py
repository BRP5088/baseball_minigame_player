"""The rig must say when it CANNOT SEE, instead of answering as if it could.

WHY THIS EXISTS
---------------
Every bug in CLAUDE.md's diagnosis catalogue has one shape: the code did
nothing, and doing nothing looked exactly like working. This file guards six
places in the rig layer where that shape had reappeared — each one a fallback,
a guard or an `except` that produced a NORMAL-LOOKING answer from a failure,
with nothing in the log to separate the two.

The rule the catalogue gives is: ask what would be in the log if this step had
never run at all, and if the answer is "the same thing", fix the silence first.
So these checks assert on the LOG, not on the return value — the return values
are deliberately unchanged, because the point of every fix here is that
behaviour must not move.

The specific confusions guarded, and what a reader would otherwise conclude:

  ensure_stream.is_frozen  a capture that RAISES returns False, which
                           ensure_live reads as "the picture is updating".
                           streaming() can satisfy ensure() from a heartbeat
                           alone, so a broken capture plus a live console
                           returned "live, updating picture". CANNOT SEE
                           recorded as FINE — the error that cost a whole A/B.
  ensure_stream.streaming  four routes to True, and "the console replied" is a
                           different state from "the game is on screen". The
                           PS5 overlay covers the picture while heartbeats
                           continue.
  compass                  the fast glyph reader fails into the pytesseract
                           sweep, which is CORRECT and 8x slower (31ms ->
                           261ms). Nothing looks broken; the run is just slow,
                           and a reader blames the console or the network.
  places.identify_orb      "no references loaded" and "no keypoints in this
                           frame" both surface as `abstained (0.000/0.000)`,
                           the same string as a genuine abstention, which
                           readers are taught to read as "unmapped ground".
  analog_replay.send       a stray BASEBALL_TEST_RUN discards every stick
                           command; walk_forward still returns a small number,
                           so it reads as wedged geometry or a sleeping
                           console rather than as a shell variable.
  input_controller         three delivery paths, and the log never said which
                           carried a press. The third steals focus and types
                           into the FRONTMOST window.

WHAT IS DELIBERATELY NOT HERE. Some silence in these modules is documented and
intended — _focus_window_windows ("a raise here would abort a run over a
transient SetForegroundWindow refusal") and compass's `except _TurnAborted`
(guarded_press already printed the reason). Adding a message to either would
be noise, so neither is asserted on.
"""
import contextlib
import io
import os
import os as _os
import sys
import types

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
os.environ["BASEBALL_TEST_RUN"] = "1"
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


def _say(fn, *a, **kw):
    """(return value, everything it printed)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = fn(*a, **kw)
    return r, buf.getvalue()


# ===========================================================================
# 1. ensure_stream.is_frozen() — a failed capture is not "the picture is fine"
# ===========================================================================
import ensure_stream as es
# This file drives ensure_stream's ORCHESTRATION on purpose, against stubbed
# internals. The module refuses to run under BASEBALL_TEST_RUN since 2026-09-13 --
# the offline suite was reaching the LIVE rig, and one rung further is
# restart_chiaki.sh, i.e. kill -9 on the user's stream -- so opt in explicitly.
es.RIG_DRIVER_IN_TESTS = True



class _Img:
    def __init__(self, v, shape=(16, 16)):
        self.v, self.shape = v, shape

    def convert(self, mode):
        return self

    def __array__(self, dtype=None):
        import numpy as np
        return np.full(self.shape, self.v, dtype=dtype or float)


_real_es_time = es.time
es.time = types.SimpleNamespace(sleep=lambda s: None)
_real_compass_mod = sys.modules.get("compass")


def _boom():
    raise RuntimeError("grab failed")


sys.modules["compass"] = types.SimpleNamespace(fast_capture=_boom)
frozen, out = _say(es.is_frozen)
check(frozen is False,
      "BEHAVIOUR CHANGED: a failed grab must still answer 'not frozen'. Being "
      "unable to look is not evidence the picture stopped, and reporting "
      "frozen here would restart chiaki on a healthy stream.")
check(out.strip(),
      "is_frozen() swallowed a capture exception in SILENCE. ensure_live reads "
      "`ensure(log) and not is_frozen()`, and ensure() is satisfied by a "
      "heartbeat with no capture at all — so a broken capture plus a live "
      "console returns 'live, updating picture' and the log never says the rig "
      "could not see.")
check("RuntimeError" in out and "grab failed" in out,
      f"the message must name the exception that stopped the capture, or the "
      f"next reader has to guess which of NoGameWindow / mss / a resize it "
      f"was; got {out!r}")
check("NOT FROZEN" in out or "not frozen" in out,
      f"the message must say what is being ANSWERED, not just what failed — "
      f"the danger is the answer, not the exception; got {out!r}")
check("evidence" in out.lower() or "updating" in out.lower(),
      f"the message must say what a reader would otherwise wrongly conclude "
      f"(that the picture is updating); got {out!r}")

# A working capture must stay silent — a line on every healthy call would make
# the warning above worthless.
def _frames(seq):
    it = iter(seq)
    sys.modules["compass"] = types.SimpleNamespace(fast_capture=lambda: next(it))


_frames([_Img(50), _Img(70)])
live, out = _say(es.is_frozen)
check(live is False, "BEHAVIOUR CHANGED: a changing picture was called frozen")
check(out == "",
      f"is_frozen() printed on a perfectly healthy capture: {out!r}. A "
      "diagnostic that fires when nothing is wrong is noise, and the real one "
      "gets skimmed past.")

if _real_compass_mod is not None:
    sys.modules["compass"] = _real_compass_mod
else:
    sys.modules.pop("compass", None)
es.time = _real_es_time


# ===========================================================================
# 2. ensure_stream.streaming() — WHICH of the four routes answered
# ===========================================================================
# "up via heartbeat" means the console replied and says nothing about whether
# the game is on screen; "up via read_bearing" means the world is visible. The
# PS5 home overlay sits between those two states, which is the whole reason
# _dismiss_overlay_if_blocking exists.
_real_hb = es._heartbeat_since_last_check
_real_es_compass, _real_es_pm = es.compass, es.pm

es._heartbeat_since_last_check = lambda *a, **k: True
check(es.streaming() is True, "BEHAVIOUR CHANGED: a heartbeat must answer True")
hb_route = es.last_route()
check(hb_route is not None,
      "streaming() answered True via the heartbeat without recording the "
      "route, so ensure() can only log 'the stream is up' — which a reader "
      "takes as 'the game is visible'. It is not: the console can heartbeat "
      "with the PS5 overlay covering the picture.")
check("heartbeat" in (hb_route or "").lower(),
      f"the heartbeat route must be NAMED as a heartbeat; got {hb_route!r}")

es._heartbeat_since_last_check = lambda *a, **k: False
es.compass = types.SimpleNamespace(
    fast_capture=lambda: _Img(50),
    find_bar=lambda img, **k: None,
    read_bearing=lambda img: 89.2,
    NoGameWindow=RuntimeError)
es.pm = types.SimpleNamespace(is_pause_screen=lambda img: False)
check(es.streaming() is True,
      "BEHAVIOUR CHANGED: a readable compass must answer True")
bearing_route = es.last_route()
check(bearing_route != hb_route,
      f"streaming() reports the same route ({bearing_route!r}) for a heartbeat "
      "and for a readable compass. Those are different states — one says the "
      "console is alive, the other says the world is on screen — and a single "
      "label cannot tell an overlay-covered stream from a visible one.")
check("bearing" in (bearing_route or "").lower()
      or "compass" in (bearing_route or "").lower(),
      f"the compass route must be named; got {bearing_route!r}")

# The short-circuit ORDER must be unchanged: find_bar is checked first because
# it survives bright scenes that defeat read_bearing.
_asked = []
es.compass = types.SimpleNamespace(
    fast_capture=lambda: _Img(50),
    find_bar=lambda img, **k: (_asked.append("find_bar"), (64, 619, 1535))[1],
    read_bearing=lambda img: (_asked.append("read_bearing"), 89.2)[1],
    NoGameWindow=RuntimeError)
check(es.streaming() is True, "BEHAVIOUR CHANGED: find_bar must answer True")
check(_asked == ["find_bar"],
      f"BEHAVIOUR CHANGED: splitting the `or` chain to record the route must "
      f"not change what gets evaluated. find_bar answered, so read_bearing "
      f"must never have been called; calls were {_asked}")

# ensure() must print the route ONCE at the entry, not on every poll.
log_lines = []
check(es.ensure(log=log_lines.append) is True,
      "BEHAVIOUR CHANGED: ensure() must return True on a live stream")
joined = " ".join(log_lines)
check(log_lines,
      "ensure() returned True and logged NOTHING, so the log cannot "
      "distinguish 'the console replied' from 'the game is on screen'")
check(len(log_lines) == 1,
      f"ensure() logged {len(log_lines)} lines on the happy path: {log_lines}. "
      "streaming() is polled every few seconds; the route belongs at the entry "
      "ONCE or it becomes the log.")
check("find_bar" in joined,
      f"ensure()'s line must name the route that answered; got {joined!r}")

# ...and AT MOST once on the RECONNECT path, which polls streaming() every
# CONNECT_WAIT seconds for up to MAX_WAIT — around two dozen polls. A route
# line inside that loop is a route line every few seconds through the whole
# reconnect, which is the log a reader most needs readable.
_real_pid, _real_key, _real_time = es._pid, es._key, es.time
_real_hb_seen = es._heartbeat_seen
_polls = [0]


def _bar_after_a_while(img, **k):
    _polls[0] += 1
    return None if _polls[0] <= 5 else (64, 619, 1535)


es._heartbeat_since_last_check = lambda *a, **k: False
es._heartbeat_seen = lambda *a, **k: False       # or streaming() waits 25s
es.compass = types.SimpleNamespace(
    fast_capture=lambda: _Img(50),
    find_bar=_bar_after_a_while,
    read_bearing=lambda img: None,
    NoGameWindow=RuntimeError)
es.pm = types.SimpleNamespace(is_pause_screen=lambda img: False)
es._pid = lambda: 4242
es._key = lambda *a, **k: None
es.time = types.SimpleNamespace(sleep=lambda s: None, time=lambda: 0.0)
try:
    log_lines = []
    check(es.ensure(log=log_lines.append) is True,
          "BEHAVIOUR CHANGED: ensure() must return True once the stream comes "
          "back after a reconnect")
    check(_polls[0] > 3,
          f"the reconnect loop only polled {_polls[0]} times, so this check "
          "never exercised a repeated poll and proves nothing")
    joined = " ".join(log_lines)
    check(joined.count("up via") <= 1,
          f"ensure() logged the route {joined.count('up via')} times over "
          f"{_polls[0]} polls: {log_lines}. streaming() is polled every "
          f"{es.CONNECT_WAIT}s for up to {es.MAX_WAIT}s, so a route line "
          "inside that loop repeats through the entire reconnect.")
finally:
    es._pid, es._key, es.time = _real_pid, _real_key, _real_time
    es._heartbeat_seen = _real_hb_seen

es._heartbeat_since_last_check = _real_hb
es.compass, es.pm = _real_es_compass, _real_es_pm


# ===========================================================================
# 3. compass — the fast glyph reader must announce its 8x-slower fallback
# ===========================================================================
from PIL import Image

import compass
import ocr_glyphs

check(hasattr(compass, "_warn_once"),
      "compass has no _warn_once: read_bearing runs inside every turn's "
      "control loop (52 calls in one profiled trial), so a per-call warning "
      "would bury the log it is meant to make readable")

# once-per-process, on the helper itself
compass._warned.discard("probe")
_, first = _say(compass._warn_once, "probe", "hello")
_, second = _say(compass._warn_once, "probe", "hello")
check("hello" in first, "compass._warn_once printed nothing the first time")
check(second == "",
      f"compass._warn_once repeated itself: {second!r}. At read_bearing's call "
      "rate a repeating warning IS the log.")
compass._warned.discard("probe")

FRAME = os.path.join(_ROOT, "test_fixtures", "compass_glyphs", "frames",
                     "frame.jpg")
if not os.path.exists(FRAME):
    fails.append(f"{FRAME} is missing; the compass leg ran on nothing")
else:
    frame = Image.open(FRAME)
    _real_recognise = ocr_glyphs.recognise
    _real_pt = compass.pytesseract
    _cache = dict(compass._SCALE_CACHE)
    _reached = []

    def _explode(images, whitelist="NESW"):
        _reached.append(len(images))
        raise ImportError("tesserocr is not installed")

    try:
        ocr_glyphs.recognise = _explode
        # Keep the fallback sweep cheap: it is not what is under test, and the
        # real one spawns ~28 tesseract subprocesses.
        compass.pytesseract = types.SimpleNamespace(
            image_to_string=lambda *a, **k: "")
        compass._warned.discard("ocr_glyphs")
        compass._SCALE_CACHE.clear()
        _, out = _say(compass.read_bearing, frame)
        compass._SCALE_CACHE.clear()
        _, again = _say(compass.read_bearing, frame)
    finally:
        ocr_glyphs.recognise = _real_recognise
        compass.pytesseract = _real_pt
        compass._SCALE_CACHE.clear()
        compass._SCALE_CACHE.update(_cache)

    # Anti-vacuity: if read_bearing stopped routing through recognise, the two
    # reads below never touched the code this check is about.
    check(_reached,
          "compass.read_bearing never called ocr_glyphs.recognise on the "
          "fixture frame, so this whole leg asserted on a code path that did "
          "not run")
    check(out.strip(),
          "the fast glyph reader failed and compass said NOTHING. Every "
          "bearing read then goes down the pytesseract sweep, which is "
          "CORRECT and ~8x slower (31ms -> 261ms measured) — so nothing looks "
          "broken and a profiler-less reader blames the console, the network "
          "or the walk.")
    check("ImportError" in out and "tesserocr" in out,
          f"the message must name the failure that disabled the fast reader; "
          f"got {out!r}")
    check("31" in out or "261" in out or "8x" in out or "slow" in out.lower(),
          f"the message must say what the reader would otherwise wrongly "
          f"conclude — that the slowness has some other cause; got {out!r}")
    check(again == "",
          f"the warning repeated on the second read: {again!r}. read_bearing "
          "is called dozens of times per trial; this must be once per process.")


# ===========================================================================
# 4. places.identify_orb — two "cannot answer" returns that look like an
#    ordinary abstention
# ===========================================================================
import numpy as np

import places

check(hasattr(places, "_warn_once"), "places has no _warn_once helper")

# (a) no references at all — once per process, because it is a property of the
#     run: an empty places/ makes the WHOLE route abstain at EVERY node.
places._warned.discard("no-refs")
(room, m, r), out = _say(places.identify_orb, _Img(50), refs={})
check((room, m, r) == (None, 0, 0.0),
      f"BEHAVIOUR CHANGED: an empty reference set must still abstain as "
      f"(None, 0, 0.0); got {(room, m, r)!r}")
check(out.strip(),
      "identify_orb abstained with NO references loaded and said nothing. That "
      "surfaces as `unverified, abstained (0.000/0.000)` — byte-identical to a "
      "genuine abstention, which CLAUDE.md teaches readers to interpret as a "
      "gap in the reference set rather than a broken run. Nothing was compared "
      "at all.")
check("refer" in out.lower(),
      f"the message must say that the REFERENCES are missing, not merely that "
      f"the answer was None; got {out!r}")
_, again = _say(places.identify_orb, _Img(50), refs={})
check(again == "",
      f"the missing-references warning repeated: {again!r}. It is one fact "
      "about the run, and identify runs at every confirmation.")

# (b) a frame with no keypoints — per call, and cheap at confirmation cadence.
#     A blank/dead capture and a wedged-against-geometry frame both land here,
#     and both are a different diagnosis from "unmapped ground".
blank = Image.fromarray(np.zeros((240, 320, 3), dtype=np.uint8))
_, d = places.keypoints(blank)
if d is not None:
    fails.append("the blank fixture image yielded keypoints, so the "
                 "no-keypoints branch was never exercised")
else:
    fake_refs = {"portrait_room": [np.zeros((10, 32), dtype=np.uint8)]}
    (room, m, r), out = _say(places.identify_orb, blank, refs=fake_refs)
    check((room, m, r) == (None, 0, 0.0),
          f"BEHAVIOUR CHANGED: a frame with no keypoints must abstain as "
          f"(None, 0, 0.0); got {(room, m, r)!r}")
    check(out.strip(),
          "identify_orb abstained on a frame with NO keypoints in silence. "
          "That is the signature of a blank or dead capture, or of a character "
          "pressed flat against geometry — none of which is 'this location is "
          "unmapped', which is what the identical log line means everywhere "
          "else.")
    check("keypoint" in out.lower(),
          f"the message must say the FRAME had nothing in it; got {out!r}")
    # Per call on purpose: a second dead frame is a second event.
    _, again = _say(places.identify_orb, blank, refs=fake_refs)
    check(again.strip(),
          "the no-keypoints line is per-frame, not per-process: each dead "
          "capture is its own event and suppressing the second one hides a "
          "stream that died mid-route")


# ===========================================================================
# 5. analog_replay.send() — the test-run guard must not discard a live walk in
#    silence
# ===========================================================================
import analog_replay as ar

check(os.environ.get("BASEBALL_TEST_RUN"),
      "this file must run with BASEBALL_TEST_RUN set — that is the state under "
      "test. (test_injected_input.py deletes it partway through; do not model "
      "on that half of it.)")
check(hasattr(ar, "_warn_once"),
      "analog_replay has no _warn_once: send() runs 30-50 times a second for "
      "the length of every walk, so a per-call print would be the entire log")

ar._warned.discard("test-run")
_real_open = ar.open_stream
_opened = []
ar.open_stream = lambda: (_opened.append(1), _real_open())[1]
try:
    r, out = _say(ar.send, ["left_x 17694"])
    check(r is None and not _opened,
          "BEHAVIOUR CHANGED: under BASEBALL_TEST_RUN send() must discard the "
          "command without opening the FIFO — the offline suite drove the live "
          "console through exactly this gap once already")
    check(out.strip(),
          "send() discarded a stick command in silence. A stray exported "
          "BASEBALL_TEST_RUN makes an entire live walk a no-op while "
          "walk_forward still returns a small view-change number (standing "
          "still measures 0.91-6.41), which reads as wedged geometry or a "
          "sleeping console — so the diagnosis goes to the console and the "
          "cause is a shell variable.")
    check("BASEBALL_TEST_RUN" in out,
          f"the message must NAME the variable, since unsetting it is the whole "
          f"fix; got {out!r}")
    check("discard" in out.lower() or "no-op" in out.lower()
          or "nothing will move" in out.lower(),
          f"the message must say what is happening to the commands; got {out!r}")
    _, again = _say(ar.send, ["left_x 17694"])
    check(again == "",
          f"the guard warning repeated: {again!r}. At 30-50Hz this must be "
          "once per process.")
finally:
    ar.open_stream = _real_open


# ===========================================================================
# 6. input_controller.chiaki_pid — a failed lookup is not a dead process
# ===========================================================================
import input_controller as ic

_real_sub = ic.subprocess


class _Timeout(Exception):
    pass


def _pgrep_times_out(*a, **k):
    raise _Timeout("pgrep timed out after 5s")


ic.subprocess = types.SimpleNamespace(run=_pgrep_times_out)
try:
    pid, out = _say(ic.chiaki_pid, refresh=True)
finally:
    ic.subprocess = _real_sub
    ic._chiaki_pid = None
check(pid is None,
      "BEHAVIOUR CHANGED: a failed pgrep must still resolve to None")
check(out.strip(),
      "chiaki_pid() swallowed the pgrep failure with no message, while the "
      "ProcessLookupError branch directly above it prints — its own comment "
      "says 'input would otherwise vanish silently'. None here turns "
      "can_use_background_input() False, so every press for the rest of the "
      "run drops onto the focus-stealing pyautogui path.")
check("_Timeout" in out or "timed out" in out,
      f"the message must name the failure; got {out!r}")
check("focus" in out.lower() or "background" in out.lower(),
      f"the message must say what a reader would otherwise wrongly conclude — "
      f"that chiaki is gone, rather than that the LOOKUP failed and input has "
      f"silently changed path; got {out!r}")


# ===========================================================================
# 7. input_controller.press() — WHICH of the three paths carried the press
# ===========================================================================
class _Fake:
    def __init__(self):
        self.downs = []

    def keyDown(self, k):
        self.downs.append(k)

    def keyUp(self, k):
        pass


_saved = (ic.pyautogui, ic._inject_press, ic.can_use_background_input,
          ic._bg_hold_keys, ic.focus_chiaki_window, ic.ACTION_DELAY)
fake = _Fake()
ic.pyautogui = fake
# This file drives the focus+pyautogui fallback ON PURPOSE, against the fake above.
# press() refuses that path under BASEBALL_TEST_RUN since 2026-09-13 -- it typed "c"
# into the frontmost window during a mutation run -- so opt in explicitly.
_saved_focus_flag = ic.FOCUS_PRESS_IN_TESTS
ic.FOCUS_PRESS_IN_TESTS = True
ic.focus_chiaki_window = lambda: False
ic.ACTION_DELAY = 0.0
ic._press_via_inject = ic._press_via_background = ic._press_via_focus = 0
try:
    check("no presses" in ic.press_path_summary(),
          f"with no presses sent the summary should say so rather than report "
          f"a made-up split; got {ic.press_path_summary()!r}")

    ic._inject_press = lambda action, hold: True
    ic.can_use_background_input = lambda action=None: True
    ic._bg_hold_keys = lambda keys, hold: True
    ic.press("cross", hold_seconds=0.0, post_delay=0.0)
    check(ic.press_path_counts() == (1, 0, 0),
          f"a FIFO-injected press was not counted as one: "
          f"{ic.press_path_counts()}")

    ic._inject_press = lambda action, hold: False
    ic.press("cross", hold_seconds=0.0, post_delay=0.0)
    check(ic.press_path_counts() == (1, 1, 0),
          f"a background-Quartz press was not counted as one: "
          f"{ic.press_path_counts()}")

    # THE SILENT DROP. can_use_background_input() False skips the branch
    # entirely, so the announced _bg_hold_keys fallback never fires and the
    # focus-stealing path runs with no output at all.
    ic.can_use_background_input = lambda action=None: False
    _, out = _say(ic.press, "cross", hold_seconds=0.0, post_delay=0.0)
    check(fake.downs,
          "BEHAVIOUR CHANGED: with both targeted paths unavailable the press "
          "must still go out through pyautogui")
    check(ic.press_path_counts() == (1, 1, 1),
          f"the focus+pyautogui press was not counted: "
          f"{ic.press_path_counts()}. That path sends to the FRONTMOST window "
          "and is the one capable of typing into the user's own work; a run "
          "that had quietly moved onto it looked identical in the log to one "
          "delivering cleanly over the FIFO.")
    check(out == "",
          f"press() printed per press: {out!r}. It is the hottest button path "
          "in the system — every menu navigation, every card selection — so "
          "this must be counters plus ONE summary, never a line each.")

    summary = ic.press_path_summary()
    check("1" in summary and summary.count("1") >= 3,
          f"the summary must report all three counts; got {summary!r}")
    check("frontmost" in summary.lower(),
          f"the summary must say WHERE the focus+pyautogui presses went, since "
          f"that is the risk that distinguishes the paths; got {summary!r}")

    # It has to be printed where something already prints, or nobody sees it.
    # orchestrator prints focus_cache_summary() and nothing else here, and that
    # function has TWO branches — check both, or a mutant that drops the
    # delivery line from one of them survives.
    _fc, _fs = ic._focus_calls, ic._focus_skips
    try:
        ic._focus_calls, ic._focus_skips = 3, 7      # the ordinary branch
        check(summary in ic.focus_cache_summary(),
              f"press_path_summary() is not reported by focus_cache_summary(), "
              f"which is the ONLY place the input layer's per-run summary is "
              f"printed. A diagnostic no caller prints is the same silence it "
              f"was written to remove. focus_cache_summary() gave "
              f"{ic.focus_cache_summary()!r}")

        ic._focus_calls = ic._focus_skips = 0        # the "no presses" branch
        check(ic.press_path_summary() in ic.focus_cache_summary(),
              "focus_cache_summary()'s no-presses branch drops the delivery "
              "summary. FIFO presses never touch focus, so both focus counters "
              "stay 0 and 'no keypresses sent' is printed for a run that "
              "pressed hundreds of buttons.")
    finally:
        ic._focus_calls, ic._focus_skips = _fc, _fs
    ic._press_via_inject = ic._press_via_background = ic._press_via_focus = 0
finally:
    (ic.pyautogui, ic._inject_press, ic.can_use_background_input,
     ic._bg_hold_keys, ic.focus_chiaki_window, ic.ACTION_DELAY) = _saved
    ic.FOCUS_PRESS_IN_TESTS = _saved_focus_flag
    ic._press_via_inject = ic._press_via_background = ic._press_via_focus = 0


if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)
print("  rig diagnostics: a failed capture, a heartbeat-only stream, a dead "
      "fast OCR backend, an empty reference set, a keypoint-less frame, a "
      "swallowed test-run guard, a failed pgrep and the focus-stealing press "
      "path all announce themselves — once per process where the path is hot, "
      "and behaviour is unchanged in every case")
