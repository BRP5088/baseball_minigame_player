"""patch64: the event log writes when enabled, never when disabled, and every hook is wired."""
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
