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
# and must NOT match. The rule is a prefix/containment test on words of length >= 4, which
# 'WINER' passes against WINNER and 'PITCHER' fails against all three.
VOCAB = {"WINNER": "win", "LOSER": "loss", "DRAW": "draw"}


def _similar(seen: str, word: str) -> bool:
    """True if `seen` is `word`, or `word` with letters dropped, in order."""
    if len(seen) < 4:
        return False
    if seen == word or seen in word or word in seen:
        return True
    i = 0                                   # subsequence: WINER -> WINNER
    for ch in word:
        if i < len(seen) and seen[i] == ch:
            i += 1
    return i == len(seen) and len(seen) >= len(word) - 2


def match_word(texts):
    """(outcome, the text that matched) from OCR output, or (None, reason)."""
    seen = []
    for t, conf in texts:
        if conf is None or conf < MIN_CONF:
            continue
        clean = "".join(ch for ch in t.upper() if ch.isalpha())
        seen.append(clean)
        for word, outcome in VOCAB.items():
            if _similar(clean, word):
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
