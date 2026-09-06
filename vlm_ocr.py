"""Read a ban-grid card name with a vision model on the LAN.

WHERE THIS SITS, AND WHY IT IS NOT A REPLACEMENT. The ban reader is a ladder:

    1. tesseract, locally          20.8 ms/cell   63 of 110 correct, 0 wrong
    2. THIS, on the LAN           700    ms/cell   95 of 110 correct, 0 wrong
    3. the paid vision call        money

This slots in at step 2, reached ONLY when tesseract abstains. It never
overrides a confident local read, so the 63 cells that already resolve keep
resolving exactly as before and this change cannot regress them. What it
replaces is step 3: today an abstention costs a PAID vision call against a hard
budget, and every one of those is real money.

MEASURED 2026-09-06 on the same 110 real ban-grid cells the shipped test uses,
scored the same way against KNOWN_BAN_ROSTER:

    shipped reader, its own crop      63 correct   0 WRONG   47 abstained
    shipped reader, tightened crop    32 correct   0 WRONG   78 abstained
    qwen2.5vl:7b, tightened crop      95 correct   0 WRONG   15 abstained

THE CROP MATTERS AND IT IS NOT SHARED. `get_ban_grid_card_crop` returns a window
holding the bottom of the card ABOVE plus the target card, and a general vision
model reads whichever name is sharpest -- the neighbour's. Untightened it made
nine confident WRONG reads, every one a row-1 cell answering with a row-0 name.
Tightened, that goes to zero. The same tightening makes the SHIPPED reader
worse (63 -> 32), which is why each reader crops for itself and nothing here
touches the shared crop.

WRONG IS NOT ABSTAINED. This answer bans a physical card in a $50 match and
nothing downstream can detect a wrong one. So: the model's text must resolve to
EXACTLY ONE roster name or this abstains, a reply naming two cards abstains,
and every failure path -- host down, timeout, malformed JSON, model missing --
abstains rather than guessing. Zero wrong on 110 cells is not proof of zero
wrong in general.

IT MUST NEVER COST A RUN. Snoopy is a separate machine that can be asleep. Every
call is wrapped, `reachable()` is cached so a dead host costs one short timeout
per minute rather than one per cell, and any failure falls through to exactly
the behaviour that shipped before this file existed.
"""
import base64
import io
import json
import os
import re
import time
import urllib.error
import urllib.request

HOST = os.environ.get("BASEBALL_VLM_HOST", "http://snoopy:11434")
MODEL = os.environ.get("BASEBALL_VLM_MODEL", "qwen2.5vl:7b")

# Set BASEBALL_VLM=0 to turn the whole step off without editing code.
ENABLED = os.environ.get("BASEBALL_VLM", "1") != "0"

REACH_TIMEOUT = 2.0     # a dead host must cost ~nothing
READ_TIMEOUT = 30.0     # a warm read is 0.7s; this only bounds a stall
RECHECK_SEC = 60.0      # how long a reachability answer is trusted

# The bottom fraction of a ban-grid crop that holds ONE card. See the module
# docstring: the shared crop contains two, and the neighbour is what produced
# every wrong read in the first pass.
BOTTOM_FRAC = 0.62

PROMPT = ("This is a cropped baseball card from a video game. Read the "
          "player's NAME exactly as printed. Reply with ONLY the name and "
          "nothing else. If you cannot read it clearly, reply with exactly: "
          "UNREADABLE")

_reachable = None
_checked_at = 0.0
_last_error = None


def _norm(t):
    """Upper case, punctuation stripped, whitespace collapsed."""
    t = re.sub(r"[^A-Za-z0-9 ]+", " ", str(t))
    return re.sub(r"\s+", " ", t).strip().upper()


def _in_offline_test():
    """The offline suite must not touch the network.

    A test that reaches a host it does not control is not offline, and its
    result depends on whether a machine in another room is awake. Tests that
    exercise this module stub `_post` instead.
    """
    return (os.environ.get("BASEBALL_TEST_RUN")
            and os.environ.get("BASEBALL_VLM_ALLOW_IN_TESTS") != "1")


def _post(path, payload, timeout):
    """One HTTP call. Split out so a test can substitute it."""
    req = urllib.request.Request(
        HOST.rstrip("/") + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return json.loads(fh.read())


def reachable(force=False):
    """Is the host up AND does it have the model? Cached for RECHECK_SEC.

    CACHED BECAUSE A DEAD HOST IS THE EXPENSIVE CASE. Without this a sleeping
    Snoopy costs one 2s timeout per CELL, which on a ten-cell grid is twenty
    seconds of a match spent discovering the same thing ten times.

    Checks for the MODEL, not just the port: a running Ollama without
    qwen2.5vl would answer every read with a 404 and abstain on all of them,
    which looks exactly like a model that cannot read.
    """
    global _reachable, _checked_at, _last_error
    if not ENABLED or _in_offline_test():
        return False
    now = time.time()
    if not force and _reachable is not None and now - _checked_at < RECHECK_SEC:
        return _reachable
    _checked_at = now
    try:
        tags = _post("/api/tags", None, REACH_TIMEOUT)
        names = {m.get("name", "") for m in tags.get("models", [])}
        _reachable = MODEL in names
        _last_error = None if _reachable else f"{MODEL} not installed on {HOST}"
    except Exception as e:
        _reachable = False
        _last_error = f"{type(e).__name__}: {e}"
    return _reachable


def last_error():
    """Why the last reachability check said no, or None."""
    return _last_error


def _tighten(crop):
    w, h = crop.size
    return crop.crop((0, int(h * (1.0 - BOTTOM_FRAC)), w, h))


def read_card_text(card_img):
    """The model's raw reading of one ban-grid card, or None.

    Returns TEXT, not a roster card. Resolving text to a card is the caller's
    job and belongs next to the roster, so that this module cannot quietly
    become a second, differently-behaved matcher.
    """
    if not reachable():
        return None
    try:
        buf = io.BytesIO()
        _tighten(card_img).convert("RGB").save(buf, "PNG")
        r = _post("/api/generate", {
            "model": MODEL,
            "prompt": PROMPT,
            "images": [base64.b64encode(buf.getvalue()).decode()],
            "stream": False,
            # temperature 0: this reads a printed name, and a sampled answer
            # would make the same card resolve differently between runs.
            "options": {"temperature": 0, "num_predict": 40},
        }, READ_TIMEOUT)
        text = (r.get("response") or "").strip()
        return None if _norm(text) in ("", "UNREADABLE") else text
    except Exception:
        # A network blip must look exactly like an abstention, never like a
        # reading. The caller then does what it did before this file existed.
        return None


def resolve_against(text, roster_names):
    """The one roster name `text` contains, or None if not exactly one.

    A reply naming TWO cards is an ABSTENTION, not a pick. The crops can carry
    a sliver of the neighbouring card, and choosing between two names by
    position would be guessing on a path that spends $50.
    """
    if not text:
        return None
    n = _norm(text)
    named = [r for r in roster_names if _norm(r) and _norm(r) in n]
    return named[0] if len(named) == 1 else None
