"""I-55: a result commit must leave evidence, not just a trophy count.

Three draws landed 2026-09-21 with nothing behind them: `overnight/
run_live_20260921r.log` ~555-556 ("Draw logged (8 total)" after a poll that
distrusted the template), `run_live_20260921t.log` ~634-636 (I-54's phantom
draw) and `run_live_20260921u.log` ~724-725 ("Draw logged (9 total)" with no
`[state]` line at all). HANDOFF_NOW.md's LATER list already asked for this fix.

FOLLOW-UP, SAME DAY. The first version of `record_result_frame` re-derived its
evidence from a FRESH capture taken at the commit site -- one or more polls
after `local_game_state` actually decided the outcome. A skeptic caught it
from its own sample print: a WIN's kept frame showed template scores of
{'winner': 0.0, 'loser': 0.0, 'draw': 0.0}, because by commit time the result
screen had already moved on. The fix threads what `local_game_state`'s
"result" branch already computed -- `result_scores`/`result_source`/
`result_card_word`/`result_ocr_words`/`result_frame_ns` -- through
`state_json`, and stashes the exact frame that branch read in the
module-level `_LAST_RESULT_FRAME`, paired with the same timestamp so a
mismatched global can never be mistaken for this decision's own picture.

This file tests BOTH layers directly:

  A, B, F   call `orchestrator.local_game_state()` itself, with
            `local_state.read_result` and `_fast_grab` SEEDED to known
            values, so the threaded fields and the stashed frame can be
            checked against exactly what was seeded -- not against whatever
            a live screen happens to show.
  C, D, E   drive `record_result_frame`'s own contract (the BASEBALL_TEST_RUN
            gate, resilience to a raising save, the 200-file cap), the same
            way the first version of this file did.

`check(name, cond)` is deliberately NAME-FIRST here, unlike `_run_harness`'s
own COND-FIRST `check` (CLAUDE.md's nine-signatures trap) -- so this file does
not import that helper, to avoid two different orders of the same-looking
call in one test run.
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
from _run_harness import Harness, RESULT_WIN, _PLAYED
import orchestrator as o
import local_state
import result_ocr
import table_prompt
from PIL import Image

failures = []


def check(name, cond):
    if not cond:
        failures.append(name)


# Two DISTINCT, reproducible frames. "decision" stands in for the picture
# local_game_state's result branch actually read; "fallback" stands in for
# whatever a LATER, unrelated capture would show, so a test that finds
# "fallback"'s bytes in the kept PNG has caught a re-derivation masquerading
# as the decision frame.
_DECISION_FRAME = Image.new("RGB", (1920, 1080), (17, 234, 91))
_FALLBACK_FRAME = Image.new("RGB", (1920, 1080), (200, 100, 50))


def _seed_and_read(scores, why, outcome, ocr=(None, "paddle venv missing at /nope"),
                   frame=_DECISION_FRAME):
    """Stub local_state.read_result + result_ocr.read_banner + _fast_grab, call
    local_game_state() once, and restore everything. Returns (state_json, gap)."""
    _real_read_result = local_state.read_result
    _real_read_banner = result_ocr.read_banner
    _real_fast_grab = o._fast_grab
    local_state.read_result = lambda full: {
        "is_result": True, "outcome": outcome, "scores": dict(scores), "why": why}
    result_ocr.read_banner = lambda full, *a, **k: ocr
    o._fast_grab = lambda: frame
    try:
        return o.local_game_state()
    finally:
        local_state.read_result = _real_read_result
        result_ocr.read_banner = _real_read_banner
        o._fast_grab = _real_fast_grab


# --- A: local_game_state THREADS what read_result produced, verbatim, and --
# --- record_result_frame prints those exact numbers, not a re-derivation ---
o._LAST_RESULT_FRAME = None
_KNOWN_SCORES = {"WINNER": 0.987, "LOSER": 0.012, "DRAW": 0.034}
_KNOWN_WHY = "WINNER -> win (0.987 against the next word at 0.034)"
st, gap = _seed_and_read(_KNOWN_SCORES, _KNOWN_WHY, "win")
check(f"(A) local_game_state read the seeded result cleanly, got gap={gap!r}",
      st is not None and gap is None)
if st is not None:
    check("(A) result_scores threaded VERBATIM from read_result",
          st.get("result_scores") == _KNOWN_SCORES)
    check(f"(A) result_source is 'template' (no CARD/OCR in the seeded why), got "
          f"{st.get('result_source')!r}", st.get("result_source") == "template")
    check("(A) result_frame_ns was stamped", isinstance(st.get("result_frame_ns"), int))
    check("(A) _LAST_RESULT_FRAME was stashed with the MATCHING timestamp",
          o._LAST_RESULT_FRAME is not None
          and o._LAST_RESULT_FRAME[1] == st.get("result_frame_ns")
          and o._LAST_RESULT_FRAME[0] is _DECISION_FRAME)

    with tempfile.TemporaryDirectory() as d:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fname = o.record_result_frame("win", st, out_dir=d)
        out = buf.getvalue()
        check(f"(A) record_result_frame wrote a file, got {fname!r}", fname is not None)
        check("(A) the printed line carries the SEEDED scores verbatim",
              str(_KNOWN_SCORES) in out)
        check("(A) the printed line names the template path", "path='template'" in out)
        check("(A) the printed line does NOT claim a re-derivation",
              "path='re-derived'" not in out and "RE-DERIVED capture" not in out)
        pngs = sorted(f for f in os.listdir(d) if f.endswith(".png"))
        whys = sorted(f for f in os.listdir(d) if f.endswith(".why.json"))
        check(f"(A) exactly one frame was written, got {pngs}",
              len(pngs) == 1 and pngs[0].startswith("win_"))
        if whys:
            with open(os.path.join(d, whys[0])) as fh:
                why_doc = json.load(fh)
            check("(A) why.json's scores match the seeded dict verbatim",
                  why_doc.get("scores") == _KNOWN_SCORES)
            check("(A) why.json names the decision frame, not a re-derivation",
                  "DECISION frame" in (why_doc.get("frame_provenance") or ""))


# --- B: a DRAW decided by the CARD reader names that path, word extracted --
o._LAST_RESULT_FRAME = None
_CARD_WHY = "result CARD read 'DRAW' -> draw (no arched banner; best template 0.500)"
st, gap = _seed_and_read({"WINNER": 0.10, "LOSER": 0.15, "DRAW": 0.50}, _CARD_WHY, "draw")
check(f"(B) local_game_state read the seeded card-path result, got gap={gap!r}",
      st is not None and gap is None)
if st is not None:
    check(f"(B) result_source is 'card', got {st.get('result_source')!r}",
          st.get("result_source") == "card")
    check(f"(B) result_card_word extracted 'DRAW' from the why string, got "
          f"{st.get('result_card_word')!r}", st.get("result_card_word") == "DRAW")
    with tempfile.TemporaryDirectory() as d:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            o.record_result_frame("draw", st, out_dir=d)
        out = buf.getvalue()
        check("(B) the printed line names the CARD path", "path='card'" in out)
        check("(B) the printed line carries the extracted card word",
              "card_word='DRAW'" in out)


# --- C: under BASEBALL_TEST_RUN, nothing is written (capture stubbed to work) -
_real_fast_grab_c = o._fast_grab
_grab_calls = []
o._fast_grab = lambda: (_grab_calls.append(1), Image.new("RGB", (1920, 1080)))[1]
_real_dir_c = o.RESULT_FRAME_DIR
o._LAST_RESULT_FRAME = None
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
o._LAST_RESULT_FRAME = None
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
o._LAST_RESULT_FRAME = None
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


# --- F: the kept PNG is BYTE-IDENTICAL to the frame the result branch read -
# Seed local_game_state with _DECISION_FRAME, then -- BEFORE calling
# record_result_frame -- swap the live capture over to a DIFFERENT frame, the
# way a real screen would have moved on by commit time. A keeper that
# re-captures instead of using the stashed decision frame will save
# _FALLBACK_FRAME's bytes here, and this check will catch it.
o._LAST_RESULT_FRAME = None
st, gap = _seed_and_read(_KNOWN_SCORES, _KNOWN_WHY, "win", frame=_DECISION_FRAME)
check(f"(F) local_game_state read the seeded result cleanly, got gap={gap!r}",
      st is not None and gap is None)
if st is not None:
    _real_fast_grab_f = o._fast_grab
    o._fast_grab = lambda: _FALLBACK_FRAME   # the screen has "moved on"
    try:
        with tempfile.TemporaryDirectory() as d:
            fname = o.record_result_frame("win", st, out_dir=d)
            check(f"(F) record_result_frame wrote a file, got {fname!r}", fname is not None)
            if fname:
                kept = Image.open(os.path.join(d, fname)).convert("RGB")
                check("(F) the kept PNG is byte-identical to the DECISION frame",
                      kept.tobytes() == _DECISION_FRAME.convert("RGB").tobytes())
                check("(F) the kept PNG is NOT the later fallback capture",
                      kept.tobytes() != _FALLBACK_FRAME.convert("RGB").tobytes())
    finally:
        o._fast_grab = _real_fast_grab_f


# --- G: a genuine ns MISMATCH must NOT keep a substitute frame as authoritative
# Skeptic finding (agent_progress/issues/I-55/skeptic.md, mutant 1): loosening
# `stashed[1] == wanted_ns` to just `stashed is not None` survived the shipped
# suite. Reproduces the skeptic's own probe: read result A, then read a SECOND,
# different result B (overwriting `_LAST_RESULT_FRAME` with B's frame), then
# commit on A's now-STALE state_json. The correct behaviour is to notice the ns
# no longer matches the stash and fall back to an HONEST re-derivation on
# whatever the screen shows NOW -- never silently keep B's picture stamped with
# A's numbers.
_MISMATCH_FRAME_A = Image.new("RGB", (1920, 1080), (5, 5, 200))
_MISMATCH_FRAME_B = Image.new("RGB", (1920, 1080), (200, 5, 5))
_MISMATCH_FRAME_NOW = Image.new("RGB", (1920, 1080), (5, 200, 5))
o._LAST_RESULT_FRAME = None
st_a, gap_a = _seed_and_read({"WINNER": 0.99, "LOSER": 0.01, "DRAW": 0.01},
                             "WINNER -> win (0.99 against the next word at 0.01)",
                             "win", frame=_MISMATCH_FRAME_A)
check(f"(G) result A read cleanly, got gap={gap_a!r}", st_a is not None and gap_a is None)
if st_a is not None:
    _ns_a = st_a.get("result_frame_ns")
    # Overwrite the stash with a SECOND, different result -- the way the next
    # poll in run()'s own loop would, before a delayed commit on A ever fires.
    st_b, gap_b = _seed_and_read({"WINNER": 0.01, "LOSER": 0.99, "DRAW": 0.01},
                                 "LOSER -> loss (0.99 against the next word at 0.01)",
                                 "loss", frame=_MISMATCH_FRAME_B)
    check(f"(G) result B read cleanly, got gap={gap_b!r}", st_b is not None and gap_b is None)
    check("(G) CONTROL: the stash now holds B's frame, not A's",
          o._LAST_RESULT_FRAME is not None and o._LAST_RESULT_FRAME[0] is _MISMATCH_FRAME_B)
    check("(G) CONTROL: A's own ns does not match the (now B) stash",
          _ns_a != o._LAST_RESULT_FRAME[1])

    _real_fast_grab_g = o._fast_grab
    o._fast_grab = lambda: _MISMATCH_FRAME_NOW   # "the screen" at commit time
    try:
        with tempfile.TemporaryDirectory() as d:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                fname = o.record_result_frame("win", st_a, out_dir=d)
            out = buf.getvalue()
            check(f"(G) record_result_frame wrote a file, got {fname!r}", fname is not None)
            check("(G) the printed line takes the RE-DERIVED path, not the decision frame",
                  "path='re-derived'" in out and "DECISION frame" not in out)
            check("(G) the printed line says the stash did not match",
                  "did not match the stashed frame" in out)
            if fname:
                kept = Image.open(os.path.join(d, fname)).convert("RGB")
                check("(G) the kept PNG is the FRESH capture, not A's own decision frame",
                      kept.tobytes() == _MISMATCH_FRAME_NOW.convert("RGB").tobytes())
                check("(G) the kept PNG is NOT B's stashed frame stamped with A's numbers",
                      kept.tobytes() != _MISMATCH_FRAME_B.convert("RGB").tobytes())
    finally:
        o._fast_grab = _real_fast_grab_g


# --- H: the SECOND return site (the OCR-only fallback) threads too -----------
# Skeptic finding (mutant 2): `_seed_and_read`'s stub always answers
# `is_result: True`, so the MAIN branch fires every time and the second return
# site -- reached when the template bank never scores `is_result` at all and
# `local_hand_cards` also fails, so `result_ocr.read_banner` is the last resort
# (orchestrator.py, "the templates missed this banner; OCR read it") -- was
# never exercised. Reverting THAT dict back to its pre-I-55 four-key shape
# survived the shipped suite. Ban/prompt/hand are stubbed to fall through
# deterministically, independent of what a blank test frame happens to look
# like to the real readers.
_OCR_FALLBACK_FRAME = Image.new("RGB", (1920, 1080), (90, 40, 160))
o._LAST_RESULT_FRAME = None
_real_read_result_h = local_state.read_result
_real_read_banner_h = result_ocr.read_banner
_real_fast_grab_h = o._fast_grab
_real_crop_h = o.crop_gameplay_regions
_real_ban_h = o.read_ban_counter
_real_hpr_h = o.homeplate_runner_present
_real_hand_h = o.local_hand_cards
_real_at_table_h = table_prompt.at_table
_PARTIAL_SCORES = {"WINNER": 0.31, "LOSER": 0.28, "DRAW": 0.30}
local_state.read_result = lambda full: {
    "is_result": False, "outcome": None, "scores": dict(_PARTIAL_SCORES),
    "why": "no result word found (best 0.31 < 0.8; card band read '')"}
result_ocr.read_banner = lambda full, *a, **k: ("draw", "DRAW!")
o._fast_grab = lambda: _OCR_FALLBACK_FRAME
o.crop_gameplay_regions = lambda full: [("hand", full)]
o.read_ban_counter = lambda full: None
o.homeplate_runner_present = lambda crops: False
o.local_hand_cards = lambda hand_img, phase=None, homeplate_runner=False: (
    None, "stubbed: no discs found")
table_prompt.at_table = lambda full: False
try:
    st_h, gap_h = o.local_game_state()
finally:
    local_state.read_result = _real_read_result_h
    result_ocr.read_banner = _real_read_banner_h
    o._fast_grab = _real_fast_grab_h
    o.crop_gameplay_regions = _real_crop_h
    o.read_ban_counter = _real_ban_h
    o.homeplate_runner_present = _real_hpr_h
    o.local_hand_cards = _real_hand_h
    table_prompt.at_table = _real_at_table_h
check(f"(H) local_game_state reached the OCR-fallback branch, got gap={gap_h!r} "
      f"st={st_h!r}", st_h is not None and gap_h is None)
if st_h is not None:
    check(f"(H) result_outcome is 'draw' (from OCR, not the templates), got "
          f"{st_h.get('result_outcome')!r}", st_h.get("result_outcome") == "draw")
    check(f"(H) result_source is 'ocr' at this site, got {st_h.get('result_source')!r}",
          st_h.get("result_source") == "ocr")
    check(f"(H) result_ocr_words carries the OCR detail, got {st_h.get('result_ocr_words')!r}",
          st_h.get("result_ocr_words") == "DRAW!")
    check("(H) result_scores threads the ORIGINAL read_result's partial scores "
          f"(this site never re-asks read_result), got {st_h.get('result_scores')!r}",
          st_h.get("result_scores") == _PARTIAL_SCORES)
    check("(H) result_card_word is None (OCR path, not CARD)",
          st_h.get("result_card_word") is None)
    check("(H) result_frame_ns was stamped", isinstance(st_h.get("result_frame_ns"), int))
    check("(H) _LAST_RESULT_FRAME was stashed at THIS site too, matching ns",
          o._LAST_RESULT_FRAME is not None
          and o._LAST_RESULT_FRAME[1] == st_h.get("result_frame_ns")
          and o._LAST_RESULT_FRAME[0] is _OCR_FALLBACK_FRAME)

    with tempfile.TemporaryDirectory() as d:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fname = o.record_result_frame("draw", st_h, out_dir=d)
        out = buf.getvalue()
        check(f"(H) record_result_frame wrote a file, got {fname!r}", fname is not None)
        check("(H) the evidence line names the ocr path at the second return site",
              "path='ocr'" in out)
        check("(H) the evidence line carries the OCR words from the second site",
              "ocr_words='DRAW!'" in out)
        check("(H) the evidence line does NOT claim a re-derivation",
              "path='re-derived'" not in out)


# --- I: the FALLBACK path's provenance text says so, explicitly --------------
# Skeptic finding (mutant 3): the only test touching the provenance string
# checked that the DECISION-frame path's own print avoids "re-derived" (case
# A) -- never the converse, that a genuine FALLBACK run's print and why.json
# actually SAY "re-derived". Replacing the fallback's provenance text with the
# literal "the DECISION frame" survived the shipped suite. No threaded fields
# at all here (no result_frame_ns, `_LAST_RESULT_FRAME` is None) -- the
# simplest way to force the fallback branch.
o._LAST_RESULT_FRAME = None
_real_fast_grab_i = o._fast_grab
o._fast_grab = lambda: Image.new("RGB", (1920, 1080), (10, 10, 10))
try:
    with tempfile.TemporaryDirectory() as d:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            fname = o.record_result_frame("loss", {"your_score": 2, "opp_score": 9,
                                                    "result_outcome": "loss",
                                                    "result_won": False}, out_dir=d)
        out = buf.getvalue()
        check(f"(I) record_result_frame wrote a file, got {fname!r}", fname is not None)
        check("(I) the printed line says re-derived", "path='re-derived'" in out)
        check("(I) the printed line does NOT claim the decision frame",
              "DECISION frame" not in out)
        whys = [f for f in os.listdir(d) if f.endswith(".why.json")]
        if whys:
            with open(os.path.join(d, whys[0])) as fh:
                why_doc = json.load(fh)
            _prov = why_doc.get("frame_provenance") or ""
            check("(I) why.json's provenance says RE-DERIVED", "RE-DERIVED" in _prov)
            check("(I) why.json's provenance does NOT claim the decision frame",
                  "DECISION frame" not in _prov)
finally:
    o._fast_grab = _real_fast_grab_i


# --- A control kept from the first version: a WIN commit through run() ------
# still scores and still calls the keeper -- confirms run()'s own call site
# passes state_json through rather than something ad hoc.
o._LAST_RESULT_FRAME = None
with tempfile.TemporaryDirectory() as d:
    os.environ[o.RESULT_FRAME_DIR_ENV] = d
    try:
        final = Harness(["match_start_prompt"] + _PLAYED + [RESULT_WIN]
                        ).run(target_wins=99)
    finally:
        os.environ.pop(o.RESULT_FRAME_DIR_ENV, None)
    check("(control) a WIN commit through run() still scores", final["wins"] == 1)
    pngs = [f for f in os.listdir(d) if f.endswith(".png")]
    check(f"(control) run()'s own commit site still calls the keeper, got {pngs}",
          len(pngs) == 1)


print("OK: I-55 -- local_game_state threads the template scores, source, card word, "
      "OCR words and a matching frame timestamp verbatim; record_result_frame prefers "
      "that exact decision frame over any later re-capture (byte-identical, case F), "
      "names the CARD path when that is what answered, writes nothing under "
      "BASEBALL_TEST_RUN without its seam, a raising save costs the frame but never "
      "the commit, the 200-file cap refuses out loud instead of pruning, and run()'s "
      "own commit site still wires the keeper in")

if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} result-commit-evidence failure(s)")
