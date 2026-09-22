"""I-55: a result commit must leave evidence, not just a trophy count.

Three draws landed 2026-09-21 with nothing behind them: `overnight/
run_live_20260921r.log` ~555-556 ("Draw logged (8 total)" after a poll that
distrusted the template), `run_live_20260921t.log` ~634-636 (a PHANTOM draw
from a truncated card name, I-54) and `run_live_20260921u.log` ~724-725 ("Draw
logged (9 total)" with no `[state]` line at all). HANDOFF_NOW.md's LATER list
already asked for this fix; `record_result_frame` (orchestrator.py, beside
`record_reveal_kind` / `record_refused_select`) is it.

`state_json` -- what run() actually has at the commit site -- carries only
your_score/opp_score/result_outcome/result_won for a "result" screen; the
template scores per word and the OCR fallback's answer are computed inside
`local_game_state` and never survive the return trip. So `record_result_frame`
threads the four fields it CAN thread and re-derives the two it cannot from a
fresh capture, saying so in both the print line and why.json.

This file drives run() END TO END through `_run_harness.Harness`, the same
harness test_run_debit_and_scoring.py uses -- Harness bypasses
`local_game_state` by scripting `read_state_for_turn` directly, so the only
consumer of `_fast_grab` during a Harness-driven run is this keeper. Cases C
and E call `record_result_frame` directly, the same way test_tactics_select_
fallback.py's cases D/E call `record_refused_select` directly, so as not to
fight the harness's own `_fast_grab` patch.

`check(name, cond)` is deliberately NAME-FIRST here, unlike `_run_harness`'s
own COND-FIRST `check` (CLAUDE.md's nine-signatures trap) -- so this file does
not import that helper, to avoid two different orders of the same-looking call
in one test run.
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
# ...and this file's OWN directory, so `_run_harness` imports whether the file
# is run directly, from the project root, or re-executed in a subprocess by
# tests/harness/test_no_side_effects.py.
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import contextlib
import io
import json
import os
import tempfile

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
# Set before ANY project import: it is what holds every input path off.
os.environ["BASEBALL_TEST_RUN"] = "1"

# _run_harness FIRST among the project imports: it redirects the diagnostics
# dir, the match log and the deal log at a temp dir and only THEN imports
# orchestrator.
from _run_harness import Harness, RESULT_DRAW, RESULT_WIN, _PLAYED
import orchestrator as o
import local_state
from PIL import Image

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


class _RaisingFrame:
    """A frame object whose every attribute access raises -- record_reveal_kind's
    own `_Explodes` shape, reused here for the same reason: proving a save
    failure costs nothing but the frame."""
    def __getattr__(self, k):
        raise RuntimeError("boom: simulated frame failure")


# --- A: a WIN commit prints the evidence line and writes frame + why.json ---
with tempfile.TemporaryDirectory() as d:
    os.environ[o.RESULT_FRAME_DIR_ENV] = d
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            final = Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN]
                            ).run(target_wins=99)
    finally:
        os.environ.pop(o.RESULT_FRAME_DIR_ENV, None)
    out = buf.getvalue()
    check("(A) the win was still scored", final["wins"] == 1)
    check("(A) the evidence line names the decision path",
          "[result] win decided from state_json" in out)
    check("(A) the evidence line threads your_score/opp_score from state_json",
          "your_score=7" in out and "opp_score=3" in out)
    check("(A) the evidence line carries the re-derived template scores",
          "re-derived template scores" in out)
    check("(A) the evidence line says OCR was consulted",
          "re-derived OCR" in out)
    pngs = sorted(f for f in os.listdir(d) if f.endswith(".png"))
    whys = sorted(f for f in os.listdir(d) if f.endswith(".why.json"))
    check(f"(A) exactly one frame was written, got {pngs}",
          len(pngs) == 1 and pngs[0].startswith("win_"))
    check(f"(A) exactly one why.json was written, got {whys}",
          len(whys) == 1 and whys[0].startswith("win_"))
    if whys:
        with open(os.path.join(d, whys[0])) as fh:
            why = json.load(fh)
        check("(A) why.json carries the state_json numbers",
              why.get("from_state_json", {}).get("your_score") == 7
              and why.get("from_state_json", {}).get("opp_score") == 3)
        check("(A) why.json carries the re-derived template scores",
              "re_derived_template_scores" in why)
        check("(A) why.json carries the re-derived OCR fields",
              "re_derived_ocr_outcome" in why and "re_derived_ocr_detail" in why)
        check("(A) why.json says the re-derivation is not the decision frame",
              "not the frame the original decision was made on" in why.get("note", ""))


# --- B: a DRAW commit decided by the card reader names that path -----------
_real_read_result = local_state.read_result
local_state.read_result = lambda full: {
    "is_result": True, "outcome": "draw",
    "scores": {"WINNER": 0.10, "LOSER": 0.15, "DRAW": 0.50},
    "why": "result CARD read 'DRAW' -> draw (no arched banner; best template 0.500)",
}
try:
    with tempfile.TemporaryDirectory() as d:
        os.environ[o.RESULT_FRAME_DIR_ENV] = d
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                final = Harness(["match_start_prompt"] + _PLAYED
                                + [dict(RESULT_DRAW, result_outcome="draw")]
                                ).run(target_wins=99)
        finally:
            os.environ.pop(o.RESULT_FRAME_DIR_ENV, None)
        out = buf.getvalue()
        check("(B) the draw was still scored", final["draws"] == 1)
        check("(B) the evidence line names the CARD reader's path",
              "CARD" in out)
        whys = sorted(f for f in os.listdir(d) if f.endswith(".why.json"))
        if whys:
            with open(os.path.join(d, whys[0])) as fh:
                why = json.load(fh)
            check("(B) why.json's re-derived why names the CARD path",
                  "CARD" in (why.get("re_derived_template_why") or ""))
finally:
    local_state.read_result = _real_read_result


# --- C: under BASEBALL_TEST_RUN, nothing is written (capture stubbed to work) -
_real_fast_grab_c = o._fast_grab
_grab_calls = []
o._fast_grab = lambda: (_grab_calls.append(1), Image.new("RGB", (1920, 1080)))[1]
_real_dir_c = o.RESULT_FRAME_DIR
try:
    with tempfile.TemporaryDirectory() as watch:
        o.RESULT_FRAME_DIR = watch
        os.environ.pop(o.RESULT_FRAME_DIR_ENV, None)
        check("(C) CONTROL: the test flag is set",
              os.environ.get("BASEBALL_TEST_RUN") == "1")
        got = o.record_result_frame("win", {"your_score": 1, "opp_score": 0,
                                             "result_outcome": "win",
                                             "result_won": True})
        check("(C) returns None under the test flag", got is None)
        check("(C) writes nothing to the temp root",
              not any(_os.listdir(watch)) if _os.path.isdir(watch) else True)
        check("(C) the guard fires BEFORE capture, not because capture failed",
              _grab_calls == [])
finally:
    o._fast_grab = _real_fast_grab_c
    o.RESULT_FRAME_DIR = _real_dir_c


# --- D: a raising PIL save does not raise into run() ------------------------
_real_convert = Image.Image.convert
Image.Image.convert = lambda self, *a, **k: (_ for _ in ()).throw(
    RuntimeError("boom: simulated PIL save failure"))
try:
    with tempfile.TemporaryDirectory() as d:
        os.environ[o.RESULT_FRAME_DIR_ENV] = d
        try:
            final = Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN]
                            ).run(target_wins=99)
        finally:
            os.environ.pop(o.RESULT_FRAME_DIR_ENV, None)
        check("(D) a raising PIL convert did not raise into run() -- win still scored",
              final["wins"] == 1)
        check("(D) nothing was written when the save raised",
              not any(_os.listdir(d)) if _os.path.isdir(d) else True)
finally:
    Image.Image.convert = _real_convert


# --- E: the cap refuses at 200, out loud, and does not prune ----------------
_real_fast_grab_e = o._fast_grab
o._fast_grab = lambda: Image.new("RGB", (1920, 1080))
try:
    with tempfile.TemporaryDirectory() as d:
        for i in range(o.RESULT_FRAME_MAX_FILES):
            open(_os.path.join(d, f"win_{i}.png"), "w").close()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = o.record_result_frame("win", {"your_score": 1, "opp_score": 0,
                                                 "result_outcome": "win",
                                                 "result_won": True}, out_dir=d)
        _n_pngs = len([f for f in _os.listdir(d) if f.endswith(".png")])
        check(f"(E) a full corpus was written to anyway: returned {got!r}, "
              f"{_n_pngs} pngs against a cap of {o.RESULT_FRAME_MAX_FILES}",
              got is None and _n_pngs == o.RESULT_FRAME_MAX_FILES)
        check("(E) the refusal was printed, not silent",
              "[result]" in buf.getvalue() and str(o.RESULT_FRAME_MAX_FILES) in buf.getvalue())
        check("(E) no why.json was written for the refused frame",
              not any(f.endswith(".why.json") for f in _os.listdir(d)))
        # And it must not be a PRUNE: the oldest frame must survive.
        check("(E) the cap did not prune an existing frame",
              _os.path.exists(_os.path.join(d, "win_0.png")))
finally:
    o._fast_grab = _real_fast_grab_e


print("OK: I-55 -- a result commit prints the evidence line (state_json threaded, "
      "template scores and OCR re-derived and labelled as such), keeps the frame + "
      "why.json it was decided near, names the CARD reader's path when that is what "
      "answered, writes nothing under BASEBALL_TEST_RUN without its seam, a raising "
      "save costs the frame but never the commit, and the 200-file cap refuses out "
      "loud instead of pruning")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} result-commit-evidence failure(s)")
