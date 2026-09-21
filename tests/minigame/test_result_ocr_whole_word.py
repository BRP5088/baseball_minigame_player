"""I-34: `result_ocr.match_word` matched a result word as a SUBSTRING of a longer word.

THE BUG, live, overnight/run_live_20260921j.log ~262-268 (main checkout, read-only):
`local_state.read_result_card`'s OWN whole-word fix (I-30, "\\b{k}\\b") only covers the
TEMPLATE reader's last-resort card path. `result_ocr.match_word` is a SEPARATE matcher --
the orchestrator's OWN last-resort OCR path, wired in at orchestrator.py ~4335-4340 -- and
it used `word in seen or seen in word`, a bare substring test. A player card OCR'd as
"JOHNNY DRAWERS" on a live TURN frame scored DRAW as a substring of DRAWERS, and run()
logged a draw for a match that was still in progress.

THE FIX: `_similar` now requires a WHOLE OCR token to equal the vocab word, with two
OCR-noise tolerances -- up to TWO dropped letters ('WINE' -> WINNER; see `_similar`'s
docstring, the earlier "one dropped letter" wording undersold the real, pre-existing
tolerance) and one trailing letter standing in for a misread '!' ('DRAWI' -> DRAW) -- and
`match_word` tries two kinds of candidate per OCR text: the individual runs split on
non-letter boundaries ("JOHNNY DRAWERS" -> JOHNNY, DRAWERS, never concatenated into one
string a substring test could hit), and the text's letters joined into ONE string with
every space/digit/punctuation dropped ("W I N N E R" -> WINNER, "L0SER" -> LSER) -- the
OLD reader's only candidate, restored as an ADDITIONAL one so a word OCR splits across
spaces or digit-corrupts is still found. Neither candidate can reopen I-34: a joined name
like "JOHNNYDRAWERS" is LONGER than every vocab word, so `_similar` refuses it exactly as
it refuses the split tokens (checked below).

A CALL-SITE VETO ("refuse a match if the band has any other long alphabetic token") SHIPPED
THE SAME DAY AND WAS REVERTED (I-34 skeptic). Viewing the actual `BAND` crop on every
fixture in test_fixtures/result_screens/ (main checkout) shows the matchbox ring lettering
(CAMEL BURN, SPARK-D, SAFETY MATCHES, SPIKE-D...) is ALWAYS present alongside the real word,
on every class INCLUDING the phantom-draw frame itself -- so the veto refused every genuine
WINNER/LOSER/DRAW read. The claimed failure direction ("worst case is one extra poll") was
also wrong: a None from OCR here (not "unavailable", not "missing") reaches
orchestrator.py:4241-4259's "the template answer is not trusted alone" branch, which is
static on a real, unchanging result screen and so repeats every poll until
MAX_STUCK_ATTEMPTS (15) -- the run ends UNSCORED, which is exactly the 35s-stall failure
this whole module exists to prevent, not a cheap extra poll. `read_banner` now calls
`match_word` directly again; nothing at the call site filters its answer.
"""
import json
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
os.environ["BASEBALL_TEST_RUN"] = "1"

from PIL import Image
import result_ocr

fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


# --- 1. THE BUG ITSELF: a result word must not match as a substring of a longer word ----
got, detail = result_ocr.match_word([("JOHNNY DRAWERS", 1.0)])
check(got is None,
      f"the exact bug: a player card read 'JOHNNY DRAWERS' must NOT score a draw "
      f"(got {got!r}, detail {detail!r})")

got, _ = result_ocr.match_word([("JOHNNYDRAWERS", 1.0)])
check(got is None, "and the JOINED form (no space at all, exactly what the restored "
      f"joined-candidate mechanism produces from 'JOHNNY DRAWERS') must not reopen it "
      f"either (got {got!r})")

for seen, word in (("DRAWERS", "DRAW"), ("WINNERS", "WINNER"), ("LOSERS", "LOSER")):
    got, _ = result_ocr.match_word([(seen, 1.0)])
    check(got is None, f"{seen!r} is a real, different, LONGER word than {word} -- must "
          f"not match (got {got!r})")

got, _ = result_ocr.match_word([("PITCHERBATTER", 1.0)])
check(got is None, "a run-together non-vocab blob must not match either "
      f"(got {got!r})")

# --- 2. the vocabulary still reads normally, including the OCR-noise tolerances ---------
for seen, want in (("WINNER", "win"), ("WINER", "win"),       # one dropped letter
                   ("WINE", "win"),                           # TWO dropped letters
                   ("LOSER", "loss"),
                   ("DRAW", "draw"), ("DRAW!", "draw"),        # a real '!' is stripped
                   ("DRAWI", "draw"),                          # '!' OCR'd as a letter
                   ("PITCHER", None), ("BATTER", None),        # card banners, untouched
                   ("BANNEDCARDS", None), ("", None)):
    got, _ = result_ocr.match_word([(seen, 1.0)])
    check(got == want, f"vocabulary unchanged: {seen!r} -> {got!r} (wanted {want!r})")

# a THIRD dropped letter must still fail -- the tolerance is two, not unbounded
got, _ = result_ocr.match_word([("WIE", 1.0)])
check(got is None, f"three dropped letters (WIE for WINNER) must not match (got {got!r})")

# --- 3. tokenisation: the result word can sit beside other words and still be found -----
got, detail = result_ocr.match_word([("THE WINNER", 1.0)])
check(got == "win", f"'THE WINNER' still finds WINNER as one of its tokens (got {got!r})")

# --- 4. the RECALL REGRESSION the skeptic found and the joined-candidate fix for it ------
# The old reader joined every alpha char of a text into ONE string before matching, so it
# accepted a word OCR splits across spaces, or corrupts with a stray digit. Tokenising
# alone (I-34's first fix) lost this. The joined candidate restores it as an EXTRA
# candidate alongside the split tokens, without reopening containment.
for seen, want in (("W I N N E R", "win"),      # split across single-letter spaces
                   ("D R A W", "draw"),
                   ("DRA W", "draw"),           # split into two pieces, not all singles
                   ("L0SER", "loss")):          # a zero read for the O
    got, detail = result_ocr.match_word([(seen, 1.0)])
    check(got == want, f"recall regression: {seen!r} -> {got!r} (wanted {want!r}, "
          f"detail {detail!r})")

# --- 5. THE WIRING: read_banner must actually CALL match_word, not just have it nearby --
# match_word alone proves nothing about read_banner if the two are ever disconnected (the
# I-34 skeptic's mutant v: read_banner bypasses match_word). Drive read_banner end to end
# through a STUBBED worker -- no paddle_venv, no subprocess, no console -- by replacing the
# module's `_worker`/`_readline` so the JSON line a real PaddleOCR worker would print is
# handed back directly, and pointing PADDLE_PYTHON/PROBE at this file (which exists) so
# read_banner's own "is the venv there" checks pass.


class _FakeStdin:
    def write(self, s):
        pass

    def flush(self):
        pass


class _FakeProc:
    def __init__(self):
        self.stdin = _FakeStdin()
        self.stdout = object()   # never read for real -- _readline is stubbed below too

    def poll(self):
        return None


def _read_banner_via_stub(texts):
    """Drive the REAL result_ocr.read_banner with a fake worker that hands back `texts`,
    proving the wiring from read_banner through to match_word's verdict."""
    tmp_dir = "/tmp"
    path = os.path.join(tmp_dir, f"result_band_{os.getpid()}.png")
    line = json.dumps({path: texts})
    orig_worker, orig_readline = result_ocr._worker, result_ocr._readline
    orig_python, orig_probe = result_ocr.PADDLE_PYTHON, result_ocr.PROBE
    result_ocr._worker = lambda: _FakeProc()
    result_ocr._readline = lambda pipe, timeout: line
    result_ocr.PADDLE_PYTHON = __file__
    result_ocr.PROBE = __file__
    try:
        img = Image.new("RGB", (400, 200), (255, 255, 255))
        return result_ocr.read_banner(img, tmp_dir=tmp_dir)
    finally:
        result_ocr._worker, result_ocr._readline = orig_worker, orig_readline
        result_ocr.PADDLE_PYTHON, result_ocr.PROBE = orig_python, orig_probe


got, detail = _read_banner_via_stub([("JOHNNY DRAWERS", 1.0)])
check(got is None, f"wiring: read_banner given a stubbed 'JOHNNY DRAWERS' read must NOT "
      f"score a draw (got {got!r}, detail {detail!r})")

got, detail = _read_banner_via_stub([("DRAW!", 1.0)])
check(got == "draw", f"wiring: read_banner given a stubbed 'DRAW!' read must score a "
      f"draw (got {got!r}, detail {detail!r})")

if fails:
    print(f"\n{len(fails)} FAILED")
    raise SystemExit(1)
print("\nall green")
