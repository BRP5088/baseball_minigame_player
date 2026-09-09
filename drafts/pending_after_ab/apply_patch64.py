"""patch64: THE EVENT LOG -- when every capture, press, read and reveal episode happened and
WHICH dump frame it saw, so an agent can open the exact frame in a tools/record_stream.py
recording (join on `seq`) and judge the read. The user's ask, 2026-09-08 22:33: "do you have
it document when an action happens like OCR and where the crop is happening so agents later
on can determine if it was correct".

  * event_log.py: log_event(kind, **fields) appends {t, kind, seq, dump_mono_ns, ...} to
    BASEBALL_EVENT_LOG (read at CALL time, 10.18); a no-op when unset. log_regions() writes
    the crop tables once.
  * frame_dump.read_frame tags every image with info["dump_seq"] / ["dump_mono_ns"].
  * hooks: orchestrator.capture_screenshot_image and _fast_grab ("capture"); the ONE paid
    call site _BudgetedMessages.create ("vision": caller, images, the raw answer);
    _ocr_text ("ocr": caller, psm, text); input_controller.press ("press", before the
    test-run lockout so the offline suite can check it); reveal_watch's episode close
    ("reveal_episode" with the peak frame's seq); run_cycles.main writes the regions.
  * the smoke script sets BASEBALL_EVENT_LOG per run and stamps every log line with wall time.
Nothing here changes behaviour: every hook is a write to a file, guarded, and off by default.
Applies to: event_log.py (new), frame_dump.py, orchestrator.py, input_controller.py,
reveal_watch.py, run_cycles.py, drafts/pending_after_ab/scratch_saved/smoke_cycle.sh;
creates tests/harness/test_event_log.py.
"""
import ast, os, re, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
def rd(p): return open(os.path.join(ROOT, p)).read()
O, FD, IC, RW, RC = rd("orchestrator.py"), rd("frame_dump.py"), rd("input_controller.py"), rd("reveal_watch.py"), rd("run_cycles.py")
SM = rd("drafts/pending_after_ab/scratch_saved/smoke_cycle.sh")
assert not os.path.exists(os.path.join(ROOT, "event_log.py"))
assert not os.path.exists(os.path.join(ROOT, "tests", "harness", "test_event_log.py"))

EVENT_LOG = '''"""The per-run EVENT LOG: when each capture, press, read and reveal episode happened and
which dump frame it saw. Joined on `seq` with a tools/record_stream.py recording's
frames.jsonl, it lets an agent open the exact frame a read used.

Enabled by BASEBALL_EVENT_LOG=<path> (read at CALL time, CLAUDE.md 10.18); every call is
a no-op otherwise. Writes are appends of one JSON line; a failed write never raises.
"""
import json
import os
import time


def path(env=None):
    return (os.environ if env is None else env).get("BASEBALL_EVENT_LOG") or None


def _dump_seq():
    """The dump's current seq and monotonic stamp, or (None, None). Under
    BASEBALL_TEST_RUN frame_dump refuses the rig's file, so this is None there."""
    try:
        import frame_dump
        s = frame_dump.stats()
        return (s or {}).get("seq"), (s or {}).get("mono_ns")
    except Exception:
        return None, None


def log_event(kind, **fields):
    """Append one row. Returns True when a row was written."""
    p = path()
    if not p:
        return False
    seq, mono = _dump_seq()
    row = {"t": round(time.time(), 4), "kind": kind, "seq": seq, "dump_mono_ns": mono}
    row.update(fields)
    try:
        with open(p, "a") as f:
            f.write(json.dumps(row, default=str) + "\\n")
        return True
    except OSError:
        return False


def log_regions():
    """The crop tables, once per run: where every read looks, as fractions of the frame."""
    try:
        import orchestrator as o
        import table_prompt as tp
        return log_event("regions",
                         gameplay=o.GAMEPLAY_REGIONS_FRAC,
                         reveal_centre=list(o.REVEAL_CENTER_REGION),
                         ban_cols=o.BAN_GRID_COL_X_FRAC, ban_rows=o.BAN_GRID_ROW_Y_FRAC,
                         prompt_text_box=list(tp.TEXT_BOX),
                         settle_width=o.SETTLE_CALIBRATION_WIDTH,
                         screenshot_max_width=o.SCREENSHOT_MAX_WIDTH,
                         reveal_threshold=o.REVEAL_EDGE_THRESHOLD)
    except Exception as e:
        return log_event("regions", error=repr(e))


def caller_name(depth=2):
    import sys
    try:
        return sys._getframe(depth).f_code.co_name
    except Exception:
        return None
'''

# ---- frame_dump: tag the image with the seq ----------------------------------
a = "    return _to_image(hdr, payload)\n"
assert FD.count(a) == 1
FD2 = FD.replace(a, '''    img = _to_image(hdr, payload)
    if img is not None:
        # The join key with a recording and with the event log (patch64).
        img.info["dump_seq"] = hdr["seq"]
        img.info["dump_mono_ns"] = hdr["mono_ns"]
    return img
''', 1)

# ---- orchestrator ---------------------------------------------------------------
a1 = 'import time\n'
assert O.count(a1) == 1
O2 = O.replace(a1, a1 + "import event_log\n", 1)
a2 = '''    import game_capture
    img = game_capture.grab()
    if img is None:
        focus_chiaki_window()
'''
assert O2.count(a2) == 1
O2 = O2.replace(a2, '''    import game_capture
    img = game_capture.grab()
    event_log.log_event("capture", where="capture_screenshot_image",
                        dump=img is not None, img_seq=(img.info.get("dump_seq") if img is not None else None))
    if img is None:
        focus_chiaki_window()
''', 1)
a3 = '''    import game_capture
    img = game_capture.grab(width=SETTLE_CALIBRATION_WIDTH)
    if img is not None:
        return img
'''
assert O2.count(a3) == 1
O2 = O2.replace(a3, '''    import game_capture
    img = game_capture.grab(width=SETTLE_CALIBRATION_WIDTH)
    event_log.log_event("capture", where="_fast_grab", dump=img is not None,
                        img_seq=(img.info.get("dump_seq") if img is not None else None))
    if img is not None:
        return img
''', 1)
a4 = '''    def create(self, *args, **kwargs):
        import api_budget
        api_budget.note_call()
        return self._inner.create(*args, **kwargs)
'''
assert O2.count(a4) == 1
O2 = O2.replace(a4, '''    def create(self, *args, **kwargs):
        import api_budget
        api_budget.note_call()
        resp = self._inner.create(*args, **kwargs)
        # THE EVENT LOG (patch64): the one place every paid read passes through. The
        # caller names the read kind; the raw answer is what the agent judges.
        try:
            n_img = sum(1 for m in kwargs.get("messages", []) if isinstance(m, dict)
                        for c in (m.get("content") if isinstance(m.get("content"), list) else [])
                        if isinstance(c, dict) and c.get("type") == "image")
            text = "".join(getattr(b, "text", "") for b in getattr(resp, "content", []) or [])
            event_log.log_event("vision", caller=event_log.caller_name(2), images=n_img,
                                answer=text[:4000], calls_used=api_budget.used())
        except Exception:
            pass
        return resp
''', 1)
# _ocr_text: wrap it rather than editing its returns -- the raw function keeps its body
# and docstring; the wrapper logs the caller and the text.
a_ocr = "def _ocr_text(image, psm, whitelist=None):\n"
assert O2.count(a_ocr) == 1
O2 = O2.replace(a_ocr, '''def _ocr_text(image, psm, whitelist=None):
    """The one word-mode OCR path, wrapped for the EVENT LOG (patch64): the caller
    names the read kind and the text is what the agent judges. See _ocr_text_raw."""
    _ocr_result = _ocr_text_raw(image, psm, whitelist)
    event_log.log_event("ocr", caller=event_log.caller_name(2), psm=psm, whitelist=whitelist,
                        size=(list(image.size) if hasattr(image, "size") else None),
                        text=(_ocr_result or "")[:200])
    return _ocr_result


def _ocr_text_raw(image, psm, whitelist=None):
''', 1)
rets = [1]

# ---- input_controller.press: log BEFORE the lockout ------------------------------
a5 = '''    would be silently ignored — the backoff would appear to work, print that it
    had raised the delay, and change nothing.
    """
'''
assert IC.count(a5) == 1
IC2 = IC.replace(a5, a5 + '''    # THE EVENT LOG (patch64), first, so the row exists whether or not the press
    # goes out (the test-run lockout below still holds every input path off).
    try:
        import event_log
        event_log.log_event("press", action=action, hold=hold_seconds, post_delay=post_delay)
    except Exception:
        pass
''', 1)

# ---- reveal_watch: the episode close ---------------------------------------------
a6 = "            self._episodes.append(o)\n            self._closed_count += 1\n"
assert RW.count(a6) == 1
RW2 = RW.replace(a6, a6 + '''            try:
                import event_log
                event_log.log_event("reveal_episode", t_first=o.t_first, t_peak=o.t_peak,
                                    t_last=o.t_last, peak=o.peak,
                                    peak_seq=(o.frame.info.get("dump_seq") if o.frame is not None else None))
            except Exception:
                pass
''', 1)

# ---- run_cycles: the regions once ------------------------------------------------
a7 = '    log(f"{cycles} cycles, API budget {api_budget.budget()} calls "\n'
assert RC.count(a7) == 1
RC2 = RC.replace(a7, '    import event_log\n    event_log.log_regions()\n' + a7, 1)

# ---- the smoke script: the env and a wall-clock stamp on every line --------------
a8 = "export BASEBALL_API_BUDGET=200\n"
assert SM.count(a8) == 1
SM2 = SM.replace(a8, a8 + '''mkdir -p overnight/events
export BASEBALL_EVENT_LOG="$PWD/overnight/events/cycle_$(date +%Y%m%d_%H%M).jsonl"
echo "== event log: $BASEBALL_EVENT_LOG"
''', 1)
a9 = "PYTHONUNBUFFERED=1 .venv/bin/python -B run_cycles.py 1 2>&1 | tee overnight/smoke_cycle.log\n"
assert SM2.count(a9) == 1
SM2 = SM2.replace(a9, "PYTHONUNBUFFERED=1 .venv/bin/python -B run_cycles.py 1 2>&1 | .venv/bin/python -u -c 'import sys,time\nfor l in sys.stdin: sys.stdout.write(f\"{time.time():.3f} {l}\"); sys.stdout.flush()' | tee overnight/smoke_cycle.log\n", 1)

TEST = r'''"""patch64: the event log writes when enabled, never when disabled, and every hook is wired."""
import os, sys, json, tempfile
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")
fails = []
def check(c, m): (print("PASS", m) if c else (fails.append(m), print("FAIL", m)))
import event_log
os.environ.pop("BASEBALL_EVENT_LOG", None)
check(event_log.log_event("x", a=1) is False, "disabled: log_event returns False with the env unset")
d = tempfile.mkdtemp(); p = os.path.join(d, "ev.jsonl")
os.environ["BASEBALL_EVENT_LOG"] = p
try:
    check(event_log.log_event("capture", where="t") is True, "enabled: a row is written")
    row = json.loads(open(p).read().splitlines()[-1])
    check(row["kind"] == "capture" and row["where"] == "t" and "t" in row and "seq" in row, "the row carries kind, fields, t and seq")
    # press logs BEFORE the lockout: under BASEBALL_TEST_RUN nothing is sent, the row still lands
    import input_controller as ic
    n0 = len(open(p).read().splitlines())
    try:
        ic.press("cross")
    except Exception:
        pass
    rows = [json.loads(l) for l in open(p).read().splitlines()[n0:]]
    check(any(r["kind"] == "press" and r["action"] == "cross" for r in rows), "press() logs a 'press' row before the test-run lockout")
    # the regions row
    check(event_log.log_regions() is True, "log_regions writes")
    reg = json.loads(open(p).read().splitlines()[-1])
    check(reg["kind"] == "regions" and "gameplay" in reg and "reveal_centre" in reg and "prompt_text_box" in reg, "the regions row carries the crop tables")
    # the hooks are wired (source), with anti-vacuity on the anchors
    src = open(os.path.join(_ROOT, "orchestrator.py")).read()
    check(src.count('event_log.log_event("capture"') == 2, "both capture entry points log")
    check('event_log.log_event("vision"' in src and "answer=text[:4000]" in src, "the paid call site logs the raw answer")
    check('event_log.log_event("ocr"' in src, "_ocr_text logs its text")
    check('event_log.log_event("reveal_episode"' in open(os.path.join(_ROOT, "reveal_watch.py")).read(), "the watcher logs each closed episode with its peak seq")
    check('event_log.log_regions()' in open(os.path.join(_ROOT, "run_cycles.py")).read(), "run_cycles writes the regions once")
    check('img.info["dump_seq"] = hdr["seq"]' in open(os.path.join(_ROOT, "frame_dump.py")).read(), "frame_dump tags images with the dump seq")
    sm = open(os.path.join(_ROOT, "drafts/pending_after_ab/scratch_saved/smoke_cycle.sh")).read()
    check("BASEBALL_EVENT_LOG=" in sm and "time.time():.3f" in sm, "the smoke script sets the log path and stamps every line")
finally:
    os.environ.pop("BASEBALL_EVENT_LOG", None)
if fails:
    print(f"\n{len(fails)} FAILED"); sys.exit(1)
print("\nall green")
'''
for s in (O2, FD2, IC2, RW2, RC2): ast.parse(s)
ast.parse(EVENT_LOG); ast.parse(TEST)
assert O2.count('event_log.log_event("capture"') == 2 and O2.count('event_log.log_event("vision"') == 1
assert O2.count('event_log.log_event("ocr"') >= 1
def wr(p, s): open(os.path.join(ROOT, p), "w").write(s)
wr("event_log.py", EVENT_LOG); wr("frame_dump.py", FD2); wr("orchestrator.py", O2); wr("input_controller.py", IC2)
wr("reveal_watch.py", RW2); wr("run_cycles.py", RC2); wr("drafts/pending_after_ab/scratch_saved/smoke_cycle.sh", SM2)
wr("tests/harness/test_event_log.py", TEST)
print("patch64 applied to", ROOT, "-- _ocr_text returns wrapped:", len(rets))
