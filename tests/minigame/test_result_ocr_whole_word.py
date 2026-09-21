"""I-34: `result_ocr.match_word` matched a result word as a SUBSTRING of a longer word.

THE BUG, live, overnight/run_live_20260921j.log ~262-268 (main checkout, read-only):
`local_state.read_result_card`'s OWN whole-word fix (I-30, "\\b{k}\\b") only covers the
TEMPLATE reader's last-resort card path. `result_ocr.match_word` is a SEPARATE matcher --
the orchestrator's OWN last-resort OCR path, wired in at orchestrator.py ~4335-4340 -- and
it used `word in seen or seen in word`, a bare substring test. A player card OCR'd as
"JOHNNY DRAWERS" on a live TURN frame scored DRAW as a substring of DRAWERS, and run()
logged a draw for a match that was still in progress.

THE FIX: `_similar` now requires the WHOLE OCR token to equal the vocab word, with only
two OCR-noise exceptions -- one dropped letter (WINER -> WINNER) or one trailing letter
standing in for a misread '!' (DRAWI -> DRAW) -- and `match_word` tokenises each OCR text
on non-letter boundaries first, so "JOHNNY DRAWERS" is checked as two whole tokens, never
concatenated into one string a substring test could hit.

A second, independent layer (`_match_word_strict`, wired into `read_banner`) refuses a
match outright if the band's OCR texts carry any OTHER alphabetic token longer than 2
letters that doesn't itself look like a result word -- a real banner shows the word alone;
a reveal or a turn frame shows a player name or other prose beside it. UNMEASURED against
real result frames: `paddle_venv` does not exist in this worktree, and a live run
(run_cycles) was in the main checkout when this shipped, so running PaddleOCR against
`test_fixtures/result_screens/` was not attempted (CLAUDE.md 10.13/13a -- CPU-bound work
must not run alongside a live navigation, and the fixtures live only in the main checkout).
It ships anyway because its failure direction is safe: it can only turn an ACCEPTED match
into a REFUSAL, never the reverse, so the worst case is one extra poll
(`local_game_state` falls through to "UNRECOGNISED SCREEN"), never a wrong score.
"""
import os as _os, sys as _sys

_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import os
os.environ["BASEBALL_TEST_RUN"] = "1"

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

for seen, word in (("DRAWERS", "DRAW"), ("WINNERS", "WINNER"), ("LOSERS", "LOSER")):
    got, _ = result_ocr.match_word([(seen, 1.0)])
    check(got is None, f"{seen!r} is a real, different, LONGER word than {word} -- must "
          f"not match (got {got!r})")

# --- 2. the vocabulary still reads normally, including the OCR-noise tolerances ---------
for seen, want in (("WINNER", "win"), ("WINER", "win"),       # one dropped letter
                   ("LOSER", "loss"),
                   ("DRAW", "draw"), ("DRAW!", "draw"),        # a real '!' is stripped
                   ("DRAWI", "draw"),                          # '!' OCR'd as a letter
                   ("PITCHER", None), ("BATTER", None),        # card banners, untouched
                   ("BANNEDCARDS", None), ("", None)):
    got, _ = result_ocr.match_word([(seen, 1.0)])
    check(got == want, f"vocabulary unchanged: {seen!r} -> {got!r} (wanted {want!r})")

# --- 3. tokenisation: the result word can sit beside other words and still be found -----
got, detail = result_ocr.match_word([("THE WINNER", 1.0)])
check(got == "win", f"'THE WINNER' still finds WINNER as one of its tokens (got {got!r})")

# --- 4. the strict, belt-and-braces call-site rule (read_banner's real path) ------------
# It must REFUSE the same 'THE WINNER' text -- 'THE' is a 3-letter alphabetic token that
# is not itself a result word, so a real banner (the word alone) is distinguishable from
# a sentence that happens to contain one.
got, detail = result_ocr._match_word_strict([("THE WINNER", 1.0)])
check(got is None,
      f"strict: 'THE WINNER' has an extraneous token ('THE') and must be refused "
      f"(got {got!r}, detail {detail!r})")

got, detail = result_ocr._match_word_strict([("WINNER", 1.0)])
check(got == "win", f"strict: the word ALONE in the band is accepted (got {got!r})")

got, detail = result_ocr._match_word_strict([("DRAW!", 1.0)])
check(got == "draw",
      f"strict: a real banner's own '!' is stripped before the OTHER-token check runs, "
      f"so it is not mistaken for an extraneous token (got {got!r})")

got, detail = result_ocr._match_word_strict([("JOHNNY DRAWERS", 1.0)])
check(got is None,
      f"strict is not needed for the reported bug (match_word already refuses it) but "
      f"must not accept it either (got {got!r})")

# a short (<=2 letter) extra token must NOT trip the strict rule -- e.g. a stray 'X' from
# a close button or a border artifact
got, detail = result_ocr._match_word_strict([("WINNER", 1.0), ("X", 1.0)])
check(got == "win",
      f"strict: a short extraneous token (<=2 letters) does not veto a real banner "
      f"(got {got!r})")

if fails:
    print(f"\n{len(fails)} FAILED")
    raise SystemExit(1)
print("\nall green")
