"""READ THE RESULT BANNER WITH PaddleOCR -- the last resort before declaring a gap.

WHY THIS EXISTS. The template reader is fast (~1 ms) and right nearly always, but it is
matching a SHAPE, so every new rendering of a word is a new failure: over one night it missed
DRAW entirely (no class at all), then missed the LARGE FLAT form of WINNER/LOSER, then missed
the ARCHED form of DRAW at 0.671 against a 0.80 gate while the word sat crisp and legible on
a motionless screen. Each miss stalled a live run for 35 s or ended it.

Worse, each miss hid itself: templates were harvested BY TEMPLATE MATCHING, so the corpus
could only contain renderings that already matched, and the held-out census reported 0 errors
while an entire aspect bucket was missing (CLAUDE.md 31). Measured over the 73 harvested
draws, 67 sit in one aspect bucket; the frame that stalled the run sits in a bucket holding
exactly one sample.

OCR does not care about shape. Measured on the frames that defeated the templates:

    the arched DRAW the templates scored 0.671    ->  'DRAW!'  1.00
    flat DRAW x2                                  ->  'DRAW!'  1.00
    WINNER x2                                     ->  'WINNER' 0.90 / 'WINER' 0.87
    LOSER x2                                      ->  'LOSER'  1.00
    the quest log                                 ->  nothing
    a turn screen                                 ->  'PITCHER' (a card banner, not a result)

'WINER' is why the match is FUZZY and not equality: one dropped letter must not lose a match.

THE COST IS THE REASON IT IS LAST. A fresh paddle_venv subprocess loads the model every call:
measured 4.8 s and 6.2 s. That is far too slow for a per-poll check and perfectly acceptable
for the one frame per match where nothing else can answer -- which is exactly where it is
wired, and it replaces a 35 s stall.
"""
import atexit
import json
import os
import re
import select
import subprocess
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
PADDLE_PYTHON = os.environ.get(
    "PADDLE_VENV_PYTHON", os.path.join(_HERE, "paddle_venv", "bin", "python"))
PROBE = os.path.join(_HERE, "tools", "read_banner_paddle.py")

# The same band the template reader searches, so both are asked about the same pixels.
BAND = (0.28, 0.12, 0.72, 0.42)
TIMEOUT = 30.0
MIN_CONF = 0.55

# A CLOSED VOCABULARY OF THREE. Fuzzy, because OCR drops letters ('WINER' was observed at
# 0.87) -- but never so loose that a card banner counts: "PITCHER" appears on a turn screen
# and must NOT match. Matching is WHOLE-WORD ONLY (I-34, 2026-09-21): a player card OCR'd
# as "JOHNNY DRAWERS" on a live TURN frame -- not a result screen -- used to score a phantom
# draw, because the old rule was `word in seen or seen in word`, a bare substring test, and
# "DRAW" is a substring of "DRAWERS". A whole OCR TOKEN must now equal the vocab word, or be
# it with UP TO TWO letters dropped ('WINE' -> WINNER, OCR skipping two strokes -- see
# `_similar`'s docstring for why the tolerance is 2 and not the 1 an earlier comment here
# claimed) or one trailing character that is a '!' misread as a letter ('DRAWI' -> DRAW).
# "DRAWERS", "WINNERS" and "LOSERS" are each a real, different, LONGER word and must not
# match.
#
# A BELT-AND-BRACES CALL-SITE VETO ("refuse a match if the band has any other long alpha
# token") SHIPPED AND WAS REVERTED THE SAME DAY (I-34 skeptic, 2026-09-21). Viewing the
# actual `BAND` crop on every fixture in test_fixtures/result_screens/ shows the matchbox
# ring lettering (CAMEL BURN, SPARK-D, SAFETY MATCHES, SPIKE-D...) is ALWAYS present
# alongside the real word, on every class including the phantom-draw frame itself -- so
# the veto refused every genuine WINNER/LOSER/DRAW read, and a None here (not "unavailable",
# not "missing") reaches orchestrator.py:4256-4259's "the template answer is not trusted
# alone" branch, which repeats until MAX_STUCK_ATTEMPTS and ends the run UNSCORED on a real
# result screen -- the exact 35s-stall failure this whole module exists to prevent. Do not
# re-add a "no other token" rule without measuring the real BAND crop first.
VOCAB = {"WINNER": "win", "LOSER": "loss", "DRAW": "draw"}

_TOKEN_RE = re.compile(r"[A-Za-z]+")
_EXCLAIM_NOISE = "IL"    # OCR sometimes renders a trailing '!' as one of these letters


def _similar(seen: str, word: str) -> bool:
    """True if the WHOLE token `seen` is `word` -- exactly, with UP TO TWO letters
    dropped in order ('WINE' -> WINNER, two strokes skipped), or with one trailing
    '!'-as-a-letter noise char ('DRAWI' -> DRAW). A `seen` that is LONGER than `word`
    for any other reason is a different word ('DRAWERS', 'WINNERS', 'LOSERS') and must
    not match, however much of `word` it contains -- containment used to count here and
    matched a card name (I-34).

    THE TWO-DROP TOLERANCE IS REAL AND WAS UNDER-STATED HERE UNTIL THE I-34 SKEPTIC READ
    THE CODE (2026-09-21): `len(seen) >= len(word) - 2` allows seen to be TWO shorter than
    word, not one -- WINNER accepts WINE, INNER, WIER and 13 more 4-letter subsequences.
    The floor `len(seen) < 4` caps how much of that tolerance any given word can actually
    use: DRAW (4 letters) gets ZERO drops (a 3-letter seen never clears the floor), LOSER
    (5) gets ONE (a 3-letter seen still can't clear it), and only WINNER (6) reaches the
    full two. Pre-existing behaviour, not a regression; documented rather than tightened,
    because tightening a reader on the money path is itself an unmeasured change (CLAUDE.md
    10.32) and this tolerance has been live and correct since result_ocr.py's first commit.
    """
    if len(seen) < 4:
        return False
    if seen == word:
        return True
    if len(seen) == len(word) + 1 and seen[:-1] == word and seen[-1] in _EXCLAIM_NOISE:
        return True
    if len(seen) >= len(word):
        return False
    i = 0                                   # subsequence: WINE -> WINNER (up to 2 drops)
    for ch in word:
        if i < len(seen) and seen[i] == ch:
            i += 1
    return i == len(seen) and len(seen) >= len(word) - 2


def match_word(texts):
    """(outcome, the text that matched) from OCR output, or (None, reason).

    Two kinds of candidate token are tried per OCR text, both checked WHOLE, never as a
    containment: the individual runs split on non-letter boundaries ("JOHNNY DRAWERS" ->
    JOHNNY, DRAWERS -- never concatenated into one string a substring test could hit), and
    the text's letters joined into ONE string with every non-letter (space, digit,
    punctuation) dropped ("W I N N E R" -> WINNER, "L0SER" -> LSER, "DRA W" -> DRAW) -- the
    OLD reader's only candidate, kept because OCR sometimes splits or digit-corrupts a
    single word (I-34 skeptic finding 4). Neither can reopen I-34: a joined card name like
    "JOHNNYDRAWERS" or a lone "DRAWERS" is LONGER than every vocab word, so `_similar`
    refuses it exactly as it refuses the split tokens -- verified below in
    `tests/minigame/test_result_ocr_whole_word.py`.

    I-54: THE WHOLE-TOKEN FIX DOES NOT CATCH A TRUNCATED CARD NAME. OCR sometimes drops a
    card name's trailing letters rather than running them together -- "JOHNNY DRAWERS" read
    as "JOHNNY DRAW" -- and the truncated form's second half is no longer a substring, it
    IS the vocab word once split on the space. `_similar` cannot refuse it; it is being
    asked about "DRAW" alone and "DRAW" alone is correct to accept.

    So a candidate token is refused when the OCR TEXT IT CAME FROM also contains another
    alphabetic run of 3+ letters -- a real banner's OCR text is the word alone, plus
    trailing punctuation noise ("DRAW!", "DRAWI"), never a second word, while a card name is
    two. This is checked PER OCR TEXT ENTRY (`t`), never pooled across the whole band crop.
    That distinction is load-bearing: an I-34 draft tried the pooled form ("refuse a match
    if the band has any other long alphabetic token") and it was reverted the same day --
    the matchbox-ring lettering around the medallion (CAMEL BURN, SPARK-D, SAFETY MATCHES,
    SPIKE-D...) is ALWAYS present somewhere in the crop, on every class including the
    phantom-draw frame itself, so a whole-band veto refused every genuine read. But that
    lettering is PaddleOCR's OWN separate detected text region -- `tools/read_banner_
    paddle.py` returns one `texts` entry per detected line (`rec_texts`/`rec_scores`
    zipped), not one entry for the whole crop -- so a card name's two words landing in ONE
    entry is what the per-entry version catches, without ever seeing the matchbox text at
    all. Verified against real PaddleOCR output (agent_progress/issues/I-54/progress.md):
    0 false positives added or removed across 185 reveal-card frames and the three live
    WINNER/DRAW/LOSER fixtures that already read.

    No confidence floor from the template reader is added here -- CLAUDE.md 10.32: no such
    floor has been measured, and inventing one on the money path is exactly the mistake this
    file's own history warns against.
    """
    seen = []
    for t, conf in texts:
        if conf is None or conf < MIN_CONF:
            continue
        candidates = _TOKEN_RE.findall(t.upper())
        significant = [c for c in candidates if len(c) >= 3]
        joined = "".join(candidates)
        if joined and joined not in candidates:
            candidates = candidates + [joined]
        if len(significant) > 1:
            # a second real word in the same OCR text -- a card name, not a banner.
            seen.extend(candidates)
            continue
        for tok in candidates:
            seen.append(tok)
            for word, outcome in VOCAB.items():
                if _similar(tok, word):
                    return outcome, t
    return None, f"no result word in {seen!r}" if seen else "no text found"


# ---------------------------------------------------------------------------------------
# THE PERSISTENT WORKER. The model load is the entire cost -- 4.8-6.2 s one-shot against a
# few hundred ms of inference -- so the process is started once and kept. It idles for the
# rest of the match, which costs memory and nothing else. Same shape ocr_glyphs already uses
# for tesseract (134 ms first call, 23 ms steady).
_proc = None
_lock = threading.Lock()
START_TIMEOUT = 60.0


def _shutdown():
    global _proc
    p, _proc = _proc, None
    if p and p.poll() is None:
        try:
            p.stdin.write("QUIT\n"); p.stdin.flush()
            p.wait(timeout=3)
        except Exception:
            p.kill()


atexit.register(_shutdown)


def _readline(pipe, timeout):
    """A line, or None on timeout. A worker still loading and a worker WEDGED look identical
    without this (CLAUDE.md 10.1), so every read is bounded and the caller is told which."""
    r, _, _ = select.select([pipe], [], [], timeout)
    return pipe.readline() if r else None


def _worker():
    """The live worker, starting it if needed. None if it cannot be started."""
    global _proc
    if _proc is not None and _proc.poll() is None:
        return _proc
    if not (os.path.isfile(PADDLE_PYTHON) and os.path.isfile(PROBE)):
        return None
    _proc = subprocess.Popen([PADDLE_PYTHON, "-u", PROBE],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
    line = _readline(_proc.stdout, START_TIMEOUT)
    if not line or line.strip() != "READY":
        _shutdown()
        return None
    return _proc


def start():
    """Warm the worker up front so the first real read is not the one that pays the load.
    Returns True if it is up. Safe to call more than once."""
    with _lock:
        return _worker() is not None


def read_banner(full_frame, tmp_dir="/tmp"):
    """(outcome, detail). outcome is 'win' | 'loss' | 'draw' | None.

    None ALWAYS means NOT READ -- a missing venv, a timeout, a crash, or no word found. It is
    never "no result screen", because the caller must not turn this reader's silence into a
    claim about the game.
    """
    if not os.path.isfile(PADDLE_PYTHON):
        return None, f"paddle venv missing at {PADDLE_PYTHON}"
    if not os.path.isfile(PROBE):
        return None, f"probe missing at {PROBE}"
    w, h = full_frame.size
    band = full_frame.convert("L").crop(
        (int(w * BAND[0]), int(h * BAND[1]), int(w * BAND[2]), int(h * BAND[3])))
    path = os.path.join(tmp_dir, f"result_band_{os.getpid()}.png")
    with _lock:
        try:
            band.save(path)
            p = _worker()
            if p is None:
                return None, "paddle worker would not start"
            p.stdin.write(path + "\n"); p.stdin.flush()
            line = _readline(p.stdout, TIMEOUT)
            if line is None:
                # A wedged worker must not wedge the turn loop. Kill it; the next call
                # starts a fresh one and pays the load again, which is the right trade.
                _shutdown()
                return None, f"paddle worker timed out after {TIMEOUT}s (restarted)"
            texts = json.loads(line).get(path, [])
            if isinstance(texts, str):
                return None, texts
            return match_word(texts)
        except Exception as e:
            _shutdown()
            return None, f"{type(e).__name__}: {e}"
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
