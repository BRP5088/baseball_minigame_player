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

# --- 3. tokenisation: the result word can sit beside a SHORT neighbour and still be found
# I-54 CHANGED THIS: it used to read "THE WINNER" here. Section 6 below now refuses that
# input on purpose (a second REAL word, "THE", beside the vocab word) -- shown and reasoned
# about there rather than silently dropped. "A" is not a real word by that rule (under 3
# letters), so it still demonstrates the tokeniser finding a word beside other text.
got, detail = result_ocr.match_word([("A WINNER", 1.0)])
check(got == "win", f"'A WINNER' still finds WINNER as one of its tokens (got {got!r})")

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

# --- 6. I-54: OCR TRUNCATED A CARD NAME TO A LONE VOCAB WORD ----------------------------
# "JOHNNY DRAWERS" OCR'd with its trailing letters dropped reads "JOHNNY DRAW" -- and once
# split on the space, "DRAW" is not a substring of anything, it IS the whole vocab word.
# I-34's whole-token fix cannot see this: `_similar` is correctly being asked about "DRAW"
# alone. Live evidence: overnight/run_live_20260921t.log ~634 (main checkout, read-only):
# "[state] the templates missed this banner; OCR read it: 'JOHNNY DRAW'" -> a phantom draw
# logged mid-match (9 total), immediately followed by close_result refusing to press because
# a fresh read says is_result=False -- the match was still live, no banner had appeared.
#
# THE FIX: a candidate is refused when the OCR TEXT it came from also contains another
# alphabetic run of 3+ letters -- a real banner's text is the word alone (plus punctuation
# noise); a card name is two words. Checked PER OCR TEXT ENTRY, never pooled across the
# whole band crop -- the pooled form is what an earlier I-34 draft tried and reverted the
# same day, because the matchbox-ring lettering around the medallion is ALWAYS present
# SOMEWHERE in the crop, in its own separate detected text region.
got, detail = result_ocr.match_word([("JOHNNY DRAW", 1.0)])
check(got is None,
      f"the exact I-54 bug: a card name truncated by OCR to 'JOHNNY DRAW' must NOT score "
      f"a draw (got {got!r}, detail {detail!r})")

# the untruncated form stays refused too (I-34's own control, re-asserted here so a change
# to _similar/match_word cannot pass this file while breaking that one)
got, _ = result_ocr.match_word([("JOHNNY DRAWERS", 1.0)])
check(got is None, f"I-34 control, still refused (got {got!r})")

# a genuine banner, alone or with its own punctuation noise, is unaffected
for seen, want in (("DRAW", "draw"), ("DRAW!", "draw"), ("DRAWI", "draw")):
    got, _ = result_ocr.match_word([(seen, 1.0)])
    check(got == want,
          f"a real banner word must still read: {seen!r} -> {got!r} (wanted {want!r})")

# the mechanism generalises: ANY second real word (3+ letters) in the same OCR text refuses
# the match, even a filler like "THE" that is not itself a card name -- a real result
# banner's OCR text is the word alone. This is a DELIBERATE behaviour change from section 3
# above, which used to assert "THE WINNER" -> win; that assertion now reads "A WINNER"
# instead (a short filler that does not trip the guard), and the old input is re-asserted
# here as the new, correct answer -- shown and adjusted, per the ticket's own instruction,
# rather than silently dropped.
got, detail = result_ocr.match_word([("THE WINNER", 1.0)])
check(got is None,
      f"I-54: a second real word beside the vocab word refuses the match, even 'THE' "
      f"(got {got!r}, detail {detail!r})")

# THE LENGTH FLOOR IS A DECIDED, KNOWN LIMIT, PINNED RATHER THAN LEFT IMPLICIT. A run under
# 3 letters ("JO", "A", "TH") does not count as a second real word, so it cannot trip the
# guard -- which is what lets "A WINNER" above still match. The same rule means a card name
# truncated on BOTH halves down to 2-letter fragments ("JO DRAW") is not caught by this fix;
# nothing observed (this file's own module docstring, the live incident) has ever shown OCR
# truncate a card's FIRST word that hard while leaving the second at a clean vocab length, so
# this is recorded as a known residual rather than chased with an arbitrary lower floor
# (CLAUDE.md 10.4: a threshold must sit between two MEASURED populations, and no population of
# 1-2 letter OCR fragments has been measured here).
got, detail = result_ocr.match_word([("JO DRAW", 1.0)])
check(got == "draw",
      f"I-54 known limit, decided and pinned: a 2-letter fragment does not count as a "
      f"second word, so 'JO DRAW' still reads as draw (got {got!r}, detail {detail!r})")

# the guard is scoped to ONE OCR text entry, never pooled across the whole band -- a second,
# SEPARATE text (e.g. matchbox-ring lettering elsewhere in the crop) must not block a
# lone-word entry. This is exactly the shape the reverted I-34 call-site veto got wrong;
# pinning it here catches a regression back to the pooled form.
got, detail = result_ocr.match_word([("CAMEL BURN", 0.95), ("DRAW!", 1.0)])
check(got == "draw",
      f"a second, SEPARATE OCR text entry must not block a lone-word entry elsewhere in "
      f"the same band (got {got!r}, detail {detail!r})")

# --- 7. I-54: THE NEGATIVE FIXTURE -- A REAL REVEAL FRAME WITH JOHNNY DRAWERS ON SCREEN --
# test_fixtures/reveal_kind_truth/auto/speed_boost_1790029528372177000.jpg (main checkout),
# the frame nearest the incident's own timestamp, copied to
# test_fixtures/result_screens/negative_johnny_drawers_20260921.jpg. Real PaddleOCR output
# on its BAND crop (agent_progress/issues/I-54/progress.md) -- Johnny Drawers' own card sits
# BELOW the BAND region, so its name is not what OCR reads here; the real crop instead holds
# two OTHER cards' banners. Pinned as a literal for the same reason I-34's own
# phantom_draw_20260920.png fixture is: raw OCR output is not reproducible offline without a
# live paddle_venv call (see that fixture's own comment in test_result_card_is_read.py).
NEG_FIX = os.path.join(_ROOT, "test_fixtures", "result_screens",
                       "negative_johnny_drawers_20260921.jpg")
check(os.path.exists(NEG_FIX), f"fixture missing: {NEG_FIX}")
NEG_TEXTS = [("PITCH FOCUS", 0.99), ("PITCHER", 0.98)]
got, detail = result_ocr.match_word(NEG_TEXTS)
check(got is None,
      f"the negative fixture's real OCR text must not score a result "
      f"(got {got!r}, detail {detail!r})")

# ...and through read_banner's FULL wiring, on the real fixture file, worker stubbed to the
# recorded real texts -- same pattern as I-34's own wiring test, same reason: deterministic,
# no paddle_venv needed to run it.
got, detail = _read_banner_via_stub(NEG_TEXTS)
check(got is None,
      f"wiring: read_banner on the negative fixture must not score a result "
      f"(got {got!r}, detail {detail!r})")

# --- 8. I-54: THE THREE LIVE RESULT FIXTURES STILL READ ----------------------------------
# Measured via real PaddleOCR (agent_progress/issues/I-54/progress.md), before AND after
# this fix -- identical both times, so the new guard costs nothing on a genuine banner.
LIVE_CASES = [("heldout_winner_a.jpg", "WINNER", "win"),
              ("heldout_loser_a.jpg", "LOSER", "loss"),
              ("heldout_draw_768.jpg", "DRAW!", "draw")]
for name, real_text, want in LIVE_CASES:
    p = os.path.join(_ROOT, "test_fixtures", "result_screens", name)
    check(os.path.exists(p), f"fixture missing: {p}")
    got, detail = _read_banner_via_stub([(real_text, 0.99)])
    check(got == want,
          f"{name}: the real OCR text {real_text!r} must still read as {want!r} "
          f"(got {got!r}, detail {detail!r})")

if fails:
    print(f"\n{len(fails)} FAILED")
    raise SystemExit(1)
print("\nall green")
