"""I-40: a reload's wallet is a KNOWN CONSTANT (CLAUDE.md section 4: "Load Last
Save restores the wallet to $246"), and the local reader is not always right about
it. Live, 2026-09-21: right after a reload, `pause_menu.read_money` answered $286
for a wallet CLAUDE.md's own record says holds $246 -- a confident wrong read that
was trusted as `max_spend`, and the run spent past what the game's wallet actually
held before `start_match` failed five times with the record showing balance 36 and
a phantom $50 debit.

THIS FILE GUARDS TWO THINGS, NEITHER OF WHICH TOUCHES THE READER ITSELF:

  1. `run_cycles._reset_progress()` (through `_read_balance()`) must never hand
     `max_spend` a number that disagrees with the known reload constant --
     `RELOAD_WALLET`. A disagreeing read, or a read that raised, both become
     RELOAD_WALLET, and the disagreement is logged loudly rather than silently
     overridden (CLAUDE.md 10.1: a guard that fires and says nothing is
     indistinguishable from one that never fired).

  2. `orchestrator.record_money_read_frame()` keeps the frame a read was made on
     so the NEXT misread has a picture to look at -- copying `record_reveal_kind`'s
     shape exactly: never raises, writes nothing under BASEBALL_TEST_RUN unless a
     test hands it `out_dir`, and the answer (including a refusal, None) is in the
     filename so a census does not have to open every file to know what happened.

MUTANTS THIS IS BUILT TO CATCH: dropping the `bal != RELOAD_WALLET` branch in
`_read_balance()` (case i starts passing the bad read through); dropping
`record_money_read_frame`'s `_running_under_test()` guard (case iv starts writing
into the real corpus under the test flag); and moving the
`record_money_read_frame` call inside `read_balance_from_pause_menu` to BEFORE
the `MONEY_READ_TRIES` retry loop (case v starts keeping the frame under the
loop's first, possibly-None, answer instead of the one it actually settled on).
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(
        os.path.join(_ROOT, "requirements.txt")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
os.environ["BASEBALL_TEST_RUN"] = "1"

import tempfile

from PIL import Image

import api_budget                                                 # noqa: F401
import orchestrator as o
import pause_menu as pm_mod
import run_cycles as rc

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# CLAUDE.md sec 10.11: a test must not assert a constant against itself. (iv-e) below
# exercises the MECHANISM (the cap refuses, never prunes) entirely through
# o.MONEY_READ_MAX_FILES, so an accidental edit to the cap would sail through
# unnoticed -- pin the literal once, here.
check(f"MONEY_READ_MAX_FILES is still its pinned 200 (got {o.MONEY_READ_MAX_FILES})",
      o.MONEY_READ_MAX_FILES == 200)


# ---------------------------------------------------------------------------
# Part 1: _reset_progress() must always hand back RELOAD_WALLET when the read
# disagrees with it, or raised -- never the raw read.
# ---------------------------------------------------------------------------

_LOG = []
_orig_log = rc.log
rc.log = lambda msg, **kw: _LOG.append(str(msg))

_orig_read = o.read_balance_from_pause_menu
_orig_load = o.load_progress
_orig_save = o.save_progress
_SAVED = []
o.load_progress = lambda path: (3, 1, 0, None, False, False)
o.save_progress = lambda w, l, d, bal, path, **kw: _SAVED.append(bal)


def _reset_progress_with(read_fn):
    _LOG.clear()
    _SAVED.clear()
    o.read_balance_from_pause_menu = read_fn
    try:
        return rc._reset_progress()
    finally:
        o.read_balance_from_pause_menu = _orig_read


try:
    # --- (i) a read that DISAGREES with the known constant -----------------
    bal = _reset_progress_with(lambda: 286)
    check("(i) a $286 read after a reload is not trusted -- max_spend is "
          f"RELOAD_WALLET (${rc.RELOAD_WALLET}), got {bal}",
          bal == rc.RELOAD_WALLET)
    check("(i) save_progress recorded the GUARDED balance, not the raw 286",
          _SAVED == [rc.RELOAD_WALLET])
    _log_i = "\n".join(_LOG)
    check("(i) the disagreement is LOGGED LOUDLY, naming both numbers",
          "286" in _log_i and str(rc.RELOAD_WALLET) in _log_i
          and "DISAGREE" in _log_i.upper())

    # --- (ii) a read that AGREES: no disagreement line, same answer --------
    bal = _reset_progress_with(lambda: rc.RELOAD_WALLET)
    check("(ii) a read that agrees with RELOAD_WALLET is returned as-is",
          bal == rc.RELOAD_WALLET)
    _log_ii = "\n".join(_LOG)
    check("(ii) no disagreement is logged when the read agrees",
          "DISAGREE" not in _log_ii.upper())

    # --- (iii) a read that RAISES: same as a disagreement -------------------
    def _raises():
        raise RuntimeError("the pause menu would not open")
    bal = _reset_progress_with(_raises)
    check("(iii) a raised read falls back to RELOAD_WALLET, same as a "
          f"disagreement, got {bal}", bal == rc.RELOAD_WALLET)
    check("(iii) save_progress recorded RELOAD_WALLET, not left unset",
          _SAVED == [rc.RELOAD_WALLET])
finally:
    o.read_balance_from_pause_menu = _orig_read
    o.load_progress = _orig_load
    o.save_progress = _orig_save
    rc.log = _orig_log


# ---------------------------------------------------------------------------
# Part 2: record_money_read_frame -- the evidence keeper.
# ---------------------------------------------------------------------------

# --- (iv-a) under BASEBALL_TEST_RUN with no out_dir: writes NOTHING --------
check("(iv-a) CONTROL: the test flag is set",
      os.environ.get("BASEBALL_TEST_RUN") == "1")
_before = (sorted(os.listdir(o.MONEY_READ_DIR))
           if os.path.isdir(o.MONEY_READ_DIR) else None)
_frame = Image.new("RGB", (1920, 1080), (10, 20, 30))
r = o.record_money_read_frame(_frame, 46)
_after = (sorted(os.listdir(o.MONEY_READ_DIR))
          if os.path.isdir(o.MONEY_READ_DIR) else None)
check("(iv-a) returns None under the test flag with no out_dir", r is None)
check(f"(iv-a) the real corpus is untouched ({_before} -> {_after})",
      _before == _after)

# --- (iv-b) with out_dir: writes ONE file, named with the answer ----------
with tempfile.TemporaryDirectory() as d:
    r = o.record_money_read_frame(_frame, 46, out_dir=d)
    kept = sorted(os.listdir(d))
    check(f"(iv-b) out_dir bypasses the test-flag suppression, got {kept}",
          len(kept) == 1)
    check(f"(iv-b) the filename carries the answer (46): {kept}",
          bool(kept) and "46" in kept[0])
    check(f"(iv-b) record_money_read_frame's own return value matches: {r!r} vs {kept}",
          kept == ([r] if r else []))
    if kept:
        im = Image.open(os.path.join(d, kept[0]))
        check(f"(iv-b) the WHOLE frame is kept, not a crop ({im.size})",
              im.size == (1920, 1080))

# --- (iv-c) a REFUSAL (answer=None) still gets a frame, named accordingly --
with tempfile.TemporaryDirectory() as d:
    o.record_money_read_frame(_frame, None, out_dir=d)
    kept = sorted(os.listdir(d))
    check(f"(iv-c) a refusal (None) still keeps its frame, named with None: {kept}",
          len(kept) == 1 and "None" in kept[0])

# --- (iv-d) never raises, even handed a frame that explodes on use --------
class _Explodes:
    def __getattr__(self, k):
        raise RuntimeError("boom")


with tempfile.TemporaryDirectory() as d:
    r = o.record_money_read_frame(_Explodes(), 46, out_dir=d)
    check("(iv-d) a frame that raises on use costs the frame, not an exception "
          f"into the money path: {r!r}", r is None)
    check("(iv-d) nothing partial was left behind", not os.listdir(d))

# --- (iv-e) the cap REFUSES rather than prunes -----------------------------
with tempfile.TemporaryDirectory() as d:
    for i in range(o.MONEY_READ_MAX_FILES):
        open(os.path.join(d, f"1_{i}.png"), "w").close()
    r = o.record_money_read_frame(_frame, 46, out_dir=d)
    n = len(os.listdir(d))
    check(f"(iv-e) a full directory is REFUSED, not written into: returned "
          f"{r!r}, {n} files against a cap of {o.MONEY_READ_MAX_FILES}",
          r is None and n == o.MONEY_READ_MAX_FILES)
    check("(iv-e) the cap did not PRUNE the oldest file",
          os.path.exists(os.path.join(d, "1_0.png")))


# ---------------------------------------------------------------------------
# Part 3: the keeper is called AFTER the MONEY_READ_TRIES retry loop, with the
# loop's FINAL answer -- not wired in before the retries have run, which would
# file the frame under a wrong (or missing) answer while the real one was
# still one retry away.
# ---------------------------------------------------------------------------
_saved3 = (o.press, o.wait_for_screen_to_settle, o._fast_grab,
           pm_mod.is_pause_screen, pm_mod.read_money, o.read_ban_counter,
           o.record_money_read_frame)
_keeper_calls = []
_read_n = {"n": 0}
try:
    o.press = lambda k, *a, **kw: None
    o.wait_for_screen_to_settle = lambda *a, **k: True
    o._fast_grab = lambda: "FRAME"
    pm_mod.is_pause_screen = lambda img: True
    o.read_ban_counter = lambda img: None

    def _first_none_then_246(img, ocr=None):
        _read_n["n"] += 1
        return None if _read_n["n"] == 1 else 246
    pm_mod.read_money = _first_none_then_246

    def _keeper(frame, answer, out_dir=None):
        _keeper_calls.append(answer)
        return None
    o.record_money_read_frame = _keeper

    _got3 = o.read_balance_from_pause_menu()
    check(f"(v) the retry loop's final answer (246) reached "
          f"read_balance_from_pause_menu, got {_got3}", _got3 == 246)
    check(f"(v) the keeper was called EXACTLY ONCE, with the FINAL answer "
          f"(246), not the first (None): {_keeper_calls}",
          _keeper_calls == [246])
finally:
    (o.press, o.wait_for_screen_to_settle, o._fast_grab,
     pm_mod.is_pause_screen, pm_mod.read_money, o.read_ban_counter,
     o.record_money_read_frame) = _saved3


if FAILS:
    for f in FAILS:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(FAILS)} reload-wallet-guard failure(s)")
print("OK: I-40 -- a reload read that disagrees with the known $246 (or raises) "
      "never reaches max_spend, and every money read keeps its frame")
