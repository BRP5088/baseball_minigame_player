"""The LAN vision model is an extra rung, and it must never cost a match.

WHAT IT IS. `ocr_ban_card_name` is a ladder: tesseract locally (20.8 ms/cell),
then a vision model on another machine (700 ms/cell), then the PAID vision call.
The middle rung is reached ONLY when both local passes abstain, so every cell
that resolved before still resolves identically and what it displaces is money.

Measured 2026-09-06 over the same 110 real ban-grid cells, end to end through
`ocr_ban_card_name`:

    vision model OFF   63 correct   0 WRONG   47 abstained    2.3s
    vision model ON    97 correct   0 WRONG   13 abstained   47.5s

WHY EVERY CHECK HERE IS ABOUT REFUSING. This answer bans a physical card in a
$50 match and nothing downstream can detect a wrong one. Snoopy is a separate
machine that can be asleep, unplugged, or running a different model, and NONE of
those may turn into a guess or an exception inside a match. So the failure paths
get more tests than the success path.

OFFLINE BY CONSTRUCTION. `BASEBALL_TEST_RUN` disables the network path outright,
and every test here substitutes `vlm_ocr._post`. A test that reaches a host it
does not control is not offline: its result would depend on whether a machine in
another room happens to be awake.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"
os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

from PIL import Image

import vlm_ocr

ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        ok = False


def reset():
    vlm_ocr._reachable = None
    vlm_ocr._checked_at = 0.0


# --- 1. the offline suite must not reach the network ------------------------
calls = []


def exploding_post(path, payload, timeout):
    calls.append(path)
    raise AssertionError("the offline suite reached the network")


vlm_ocr._post = exploding_post
reset()
check("BASEBALL_TEST_RUN disables the network path outright",
      vlm_ocr.reachable() is False)
check("and nothing was sent", not calls)

# Everything below opts in explicitly, with a stub instead of a host.
os.environ["BASEBALL_VLM_ALLOW_IN_TESTS"] = "1"

MODEL = vlm_ocr.MODEL
CARD = Image.new("RGB", (260, 517), "white")


def stub(tags_models, response=None, raises=None):
    def _post(path, payload, timeout):
        if raises:
            raise raises
        if path == "/api/tags":
            return {"models": [{"name": n} for n in tags_models]}
        return {"response": response}
    vlm_ocr._post = _post
    reset()


# --- 2. the host is up and has the model ------------------------------------
stub([MODEL], response="CLAUDE EWER")
check("reachable when the host answers and has the model", vlm_ocr.reachable())
check("and it reads the card", vlm_ocr.read_card_text(CARD) == "CLAUDE EWER")

# --- 3. every failure path abstains, none of them raise ---------------------
stub([], response="CLAUDE EWER")
check("a host WITHOUT the model is not reachable -- otherwise every read 404s "
      "and looks like a model that cannot read", vlm_ocr.reachable() is False)
check("and reading returns None rather than raising",
      vlm_ocr.read_card_text(CARD) is None)

for label, exc in (("the host is asleep", OSError("connection refused")),
                   ("the read times out", TimeoutError("timed out")),
                   ("the reply is malformed", ValueError("bad json"))):
    stub([MODEL], raises=exc)
    check(f"{label} -> not reachable, no exception", vlm_ocr.reachable() is False)
    check(f"{label} -> read returns None", vlm_ocr.read_card_text(CARD) is None)

stub([MODEL], response="UNREADABLE")
check("an explicit UNREADABLE abstains", vlm_ocr.read_card_text(CARD) is None)
stub([MODEL], response="   ")
check("an empty reply abstains", vlm_ocr.read_card_text(CARD) is None)

# --- 4. a dead host is checked ONCE per minute, not once per cell -----------
# Ten cells x a 2s timeout is twenty seconds of a match spent rediscovering the
# same thing, which is why the answer is cached.
probes = []


def counting_post(path, payload, timeout):
    probes.append(path)
    raise OSError("down")


vlm_ocr._post = counting_post
reset()
for _ in range(10):
    vlm_ocr.read_card_text(CARD)
check(f"a dead host is probed once, not once per cell ({len(probes)} probe(s) "
      f"for 10 cells)", len(probes) == 1)

# --- 5. resolving text to a card refuses anything ambiguous ----------------
ROSTER = ["Claude Ewer", "Johnny Drawers", "Mama Jody Gain", "William Lee-Gains"]
check("an exact name resolves",
      vlm_ocr.resolve_against("CLAUDE EWER", ROSTER) == "Claude Ewer")
check("case and punctuation do not matter",
      vlm_ocr.resolve_against('claude  ewer.', ROSTER) == "Claude Ewer")
check("a reply naming TWO cards abstains -- the crop can carry a sliver of "
      "the neighbour, and picking one would be a guess",
      vlm_ocr.resolve_against("MAMA JODY GAIN\nWILLIAM LEE-GAINS", ROSTER) is None)
check("a name not on the roster abstains",
      vlm_ocr.resolve_against("SOMEBODY ELSE", ROSTER) is None)
check("no text abstains", vlm_ocr.resolve_against(None, ROSTER) is None)

# --- 6. the crop is tightened to ONE card ----------------------------------
# Untightened, the model read the neighbour's name and made nine confident
# WRONG calls, every one a row-1 cell answering with a row-0 name.
seen = {}


def crop_capturing_post(path, payload, timeout):
    if path == "/api/tags":
        return {"models": [{"name": MODEL}]}
    import base64, io
    seen["size"] = Image.open(io.BytesIO(
        base64.b64decode(payload["images"][0]))).size
    return {"response": "CLAUDE EWER"}


vlm_ocr._post = crop_capturing_post
reset()
vlm_ocr.read_card_text(CARD)
# The expected height is a LITERAL, not re-derived from BOTTOM_FRAC. A check
# computed from the constant it guards rises with it and passes forever
# (CLAUDE.md 10.11). 517 -> 321 is what the measured 0.62 window produces on a
# real ban-grid crop.
check(f"the image sent is the tightened crop, not the shared one "
      f"({seen.get('size')} from {CARD.size})",
      seen.get("size") == (260, 321))
check("and it is genuinely smaller than what the caller passed in",
      seen.get("size", (0, 999))[1] < CARD.size[1])
check("BOTTOM_FRAC is 0.62 -- the measured window that holds exactly one card",
      vlm_ocr.BOTTOM_FRAC == 0.62)

# --- 7. the ladder ordering: a confident local read is never overridden ----
import orchestrator as orc

vlm_called = []
_real_read = vlm_ocr.read_card_text
try:
    vlm_ocr.read_card_text = lambda img: vlm_called.append(1) or "JOHNNY DRAWERS"
    _real_ocr = orc._ocr_text
    try:
        # Make the LOCAL pass resolve confidently to a different card.
        orc._ocr_text = lambda *a, **k: "CLAUDE EWER"
        hit = orc.ocr_ban_card_name(CARD)
        check("a confident local read wins and the network is never touched",
              hit is not None and hit.name == "Claude Ewer" and not vlm_called)
        # Now make the local pass illegible, so the ladder must descend.
        orc._ocr_text = lambda *a, **k: "%%%%"
        hit = orc.ocr_ban_card_name(CARD)
        check("when the local pass abstains, the vision rung is reached",
              bool(vlm_called))
        check("and its answer resolves to the roster card",
              hit is not None and hit.name == "Johnny Drawers")
    finally:
        orc._ocr_text = _real_ocr
finally:
    vlm_ocr.read_card_text = _real_read

# --- 8. it can never raise into a match ------------------------------------
_real_read = vlm_ocr.read_card_text
try:
    def boom(img):
        raise RuntimeError("network on fire")
    vlm_ocr.read_card_text = boom
    _real_ocr = orc._ocr_text
    try:
        orc._ocr_text = lambda *a, **k: "%%%%"
        orc.ocr_ban_card_name(CARD)
        check("an exception in the vision rung is swallowed, not raised", True)
    except Exception as e:
        check(f"an exception in the vision rung is swallowed, not raised "
              f"({type(e).__name__})", False)
    finally:
        orc._ocr_text = _real_ocr
finally:
    vlm_ocr.read_card_text = _real_read

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
