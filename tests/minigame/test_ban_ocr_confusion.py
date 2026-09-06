"""Ban-card name-banner OCR: the confusion table, and the gates that make
abstention the default. No API calls, no console input — real cached frames
plus pure-function probes.

WHAT THIS GUARDS THAT tests/test_ocr_ban_card.py CANNOT
------------------------------------------------------
That file scores 18 known cards pass/abstain and caps abstentions. Its own N23
note records the trap: a LOOSER matcher scores BETTER there, because fewer
abstentions is silently rewarded. Since the confusion-aware second pass landed
it reads 18/18 with zero abstentions, so its outcome section can no longer tell
a real improvement from a loosening at all.

So the property is asserted from both sides here, over a corpus five times
larger:
  * 110 cells across 11 real ban-grid frames — 0 may resolve to the WRONG card,
    and at least 63 must still resolve (a floor, so nobody "fixes" an
    abstention by cranking strictness until the local path resolves nothing).
  * a NEGATIVE set of strings that MUST be refused, every one of them either
    lifted verbatim from a real frame or measured to sit just under a gate.
    This is the half that fails when the matcher is loosened.

A wrong card here is not a bad log line: it fills roster_hits, suppresses the
vision read that would have corrected it, and bans the wrong physical card in a
$50 match (QA_FINDINGS_R2.md N1). An abstention costs one vision call.

WHY THIS FILE WAS QUARANTINED AS A HANG, AND WHAT IT ACTUALLY WAS
-----------------------------------------------------------------
Quarantined 2026-09-03 for producing "zero output and never finishing" at 180s
buffered and 100s under `python -u`, diagnosed from that silence as "stuck at
import or module-level setup". It was neither. Measured 2026-09-04:

    import orchestrator                          1.6 - 2.0 s
    the 110-cell corpus loop (section 2)        18.6 s serial, 169 ms/cell
    every pure-function / stubbed section        0.06 s combined
    130 real pytesseract calls, whole file      37 - 41 s serial

`ocr_ban_card_name` calls `pytesseract.image_to_string`, which SHELLS OUT: a
process spawn plus a fresh eng.traineddata load per cell (`tesseract --version`
alone measures 77ms, 27% of a 282ms call). Under the load this was first run
beside, spawn cost is what degrades — ocr_glyphs.py records 5380ms vs 1160ms
for the same 40 crops on this machine, ~4.6x — which puts the serial file over
180s while producing NOTHING, because THE FILE'S FIRST print STATEMENT SAT
AFTER ALL 110 CELLS. "No output yet" was a property of where the prints were,
not of where the interpreter was. That is the CLAUDE.md pattern exactly: a slow
step and a hung step had identical output, so the silence got read as a stack
trace it never was.

Both halves of that are fixed here and both must stay:
  * EVERY phase prints as it completes, flushed. A future stall names the phase
    it is in on the line before it.
  * the corpus OCRs SERIALLY, in process. It used to run through an 8-worker
    thread pool (14.97s -> 2.65s), which was sound only while pytesseract
    shelled out and released the GIL across the spawn. OPEN-12 removed the
    spawn, and the in-process reader must not be driven from worker threads —
    see ocr_batch's docstring, and the cysignals note in ocr_glyphs.py. The
    spawn the pool was compensating for is the thing that went away.
  * MAX_OCR_CELLS is a hard ceiling on OCR work, asserted rather than intended,
    so this file cannot silently grow back into a multi-minute stall.

Runtime with the pool and pytesseract was 3.7-4.1s at load average 20 and
14.6-16.2s at load average 28, against that file's serial 20s and 49.6s at the
same two loads. Serial and IN PROCESS, measured 2026-09-05: the 110-cell corpus
takes 3.0s and the whole file 4.7s — AT LOAD AVERAGE 150. Faster with one
thread under a saturated machine than with eight under an idle one, because the
cost was never the OCR; it was the spawn and the temp file. The results are
unchanged: 63/110 correct, 0 wrong, 47 abstained, the same numbers this file
recorded under pytesseract. The whole corpus
is kept because it is what the file is FOR — a mutant that shifts the ban grid
one column produces 65 wrong-card failures here, and nothing else in the suite
would notice.
"""

import os as _os
import sys as _sys
import time as _time

_T0 = _time.time()


def say(msg):
    """Progress, flushed. A hang must be visible as it happens, not inferred
    afterwards from silence — see the quarantine note above."""
    print(f"[{_time.time() - _T0:5.1f}s] {msg}", flush=True)


say("start: importing orchestrator (~2s)")

# Tests live in tests/ but the modules and fixtures they use sit at the project
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
# root, so the root goes on sys.path and _ROOT anchors every fixture path.
_sys.path.insert(0, _ROOT)

import difflib
import itertools
import os

from PIL import Image

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")

import orchestrator
from orchestrator import (BAN_OCR_KEY_CUTOFF, BAN_OCR_KEY_MARGIN,
                          BAN_OCR_MIN_KEY_LEN, KNOWN_BAN_ROSTER,
                          OCR_CONFUSION_CLASSES, ROSTER_BY_NAME,
                          get_ban_grid_card_crop, match_roster_name,
                          match_roster_name_ocr, ocr_ban_card_name,
                          ocr_match_key)

say("imported")

# Hard ceiling on the OCR work this file may do. Each cell is one tesseract
# process. This is asserted below against the cells actually scored, so adding
# frames without thinking about the clock fails the file instead of stalling
# the suite.
MAX_OCR_CELLS = 130

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def ocr_batch(crops, what):
    """OCR every crop ON THIS THREAD, in order, printing as it goes.

    THE POOL IS GONE, AND MUST STAY GONE. It existed because pytesseract SHELLS
    OUT — the GIL is released across the spawn, so eight workers turned 14.97s
    into 2.65s. The old docstring here ended "anything that moves this onto an
    in-process backend must re-check that, not assume it", and OPEN-12 is
    exactly that move: ocr_ban_card_name now drives the Tesseract C API in
    process.

    Re-checked, and the answer is no. ocr_glyphs.py records the measurement in
    full: a pool of eight PyTessBaseAPI handles was built here, ran 3.7x
    faster, agreed on every glyph, and was REMOVED anyway, because tesserocr
    links cysignals and cysignals wraps GetUTF8Text in a PROCESS-GLOBAL
    sig_on/sig_off meant for the main thread. Driven from workers it printed
    `RuntimeWarning: sig_off() without sig_on()`, and that state is what decides
    where a signal longjmps in a process that drives a PS5 and gets Ctrl-C'd.

    There is a second, quieter reason. Backend selection imports tesserocr, and
    that import installs a SIGINT handler, which `signal.signal` refuses to do
    off the main thread. Run first from a worker, ocr_glyphs.backend() would
    catch that, fall back to the CLI, and every read in the process would go
    back to spawning a subprocess — silently, and reported as a passing test.

    Serial is no longer the slow option anyway: the spawn this pool was hiding
    is what OPEN-12 removed.
    """
    done = 0
    t = _time.time()
    out = []
    for crop in crops:
        out.append(ocr_ban_card_name(crop))
        done += 1
        if done % 20 == 0 or done == len(crops):
            say(f"   {what}: {done}/{len(crops)} cells "
                f"({_time.time() - t:.1f}s)")
    return out


# =========================================================================
# 1. THE CONFUSION TABLE IS A MEASUREMENT, PINNED EXACTLY
# =========================================================================
# Tallied 2026-09-03 from 64 genuine reads aligned against their true roster
# names across the frames below. A record, not a tunable — anything added here
# has to come from an alignment over real frames, and the widest possible entry
# (a class that merges two roster cards) is caught by section 5.
check(OCR_CONFUSION_CLASSES == (("d", "o"), ("j", "s")),
      f"OCR_CONFUSION_CLASSES is {OCR_CONFUSION_CLASSES!r}, not the measured "
      "(('d','o'), ('j','s')). This table is a tally of what tesseract did on "
      "real frames, not a list of plausible confusions.")

# The textbook OCR confusions were observed ZERO times on this font. They are
# absent on purpose: each one would widen the matcher against an error this
# pipeline does not make.
_flat = {frozenset(c) for c in OCR_CONFUSION_CLASSES}
for _never in ({"o", "0"}, {"l", "1"}, {"s", "5"}, {"i", "l"}, {"m", "n"}):
    check(frozenset(_never) not in _flat,
          f"{sorted(_never)} is in the confusion table but was never observed "
          "in 64 aligned reads — only measured confusions belong here")

# The projection is what actually carries the work: 9 of the 11 measured error
# classes are separator damage (35 of 88 word spaces fused, 7 of 7 nickname
# quotes dropped, 8 of 8 hyphens dropped), not letter substitution.
check(ocr_match_key('Austin "Cur" Bunz') == ocr_match_key("aUSTIN CUR BUNZ"),
      "the key no longer folds dropped nickname quotes")
check(ocr_match_key("Justin Young") == ocr_match_key("JUSTINYOUNG"),
      "the key no longer folds a fused word space")
check(ocr_match_key("Josef Bunz-Konicky") == ocr_match_key("SOSEF BUNZ KONICKY"),
      "the key no longer folds a dropped hyphen together with j->s")
check(ocr_match_key("Johnny Drawers") == ocr_match_key("JOHNNY ORAWERS"),
      "the key no longer folds the measured d->o confusion")

say("1. confusion table pinned")


# =========================================================================
# 2. THE NEGATIVE SET — what must be REFUSED
# =========================================================================
# Asserted through ocr_ban_card_name() itself, with the tesseract stage stubbed
# out, because that is the function the ban path calls. Testing
# match_roster_name_ocr() directly would prove only that the matcher CAN be
# strict, never that the ban path ASKS it to be (the same reasoning as the N1
# call-site guard in test_ocr_ban_card.py).
#
# Ordered BEFORE the corpus: it costs 0.04s and needs no tesseract, so a
# loosened matcher reports itself in under a second instead of after every
# frame has been OCR'd.
_PROBE = Image.new("L", (200, 300), 128)


def resolve(text):
    # Stub `_ocr_text`, NOT `pytesseract.image_to_string` — see the same note in
    # test_ocr_ban_card.py. Since OPEN-12 the read is in process, so a stub left
    # on pytesseract is simply never consulted, and every MUST_ABSTAIN below
    # then passes because the blank probe reads as nothing.
    real = orchestrator._ocr_text
    orchestrator._ocr_text = lambda *a, **k: text
    try:
        return orchestrator.ocr_ban_card_name(_PROBE)
    finally:
        orchestrator._ocr_text = real


# Every string below is REAL: lifted from the cached frames' raw OCR, or a name
# the roster does not contain. The parenthetical is what it scores against its
# best roster match under the key, measured 2026-09-03.
MUST_ABSTAIN = [
    # Plausible names that are NOT in the roster. Row 6 cols 3-4 have never
    # been catalogued, so this case is live every time the scan reaches them.
    ("Frank Coker", "0.800 vs 'Brian Coker'"),
    ("Harold Blunte", "0.786 vs 'Harold \"Fisto\" Blunt'"),
    ("Jim Gain", "0.556, four '* Jody Gain' cards"),
    # The highest-scoring string in the whole study that must still be refused.
    ("Jody Gain", "0.842 — closest approach to the 0.85 cutoff"),
    # Real fragmentary reads. 'OHNNY' fits three different Johnnys and 'BLAZE'
    # two; resolving either is a coin flip dressed as an answer.
    ("OHNNY", "0.556, three Johnnys"),
    ("BLAZE", "0.455, two candidates"),
    # Real junk, verbatim from the cached frames' raw OCR.
    ("ee ij Aw", "from 133925_665 (1,2)"),
    ("oy ee me", "from 134004_720 (1,3)"),
    ("rh eZ", "from 200601_124 (1,2)"),
    ("aR ie", "from 200604_139 (1,4)"),
    ("nog", "from 200604_139 (1,3)"),
    ("ING", "from 133925_665 (0,2)"),
    # Real junk from the TACTICS section of the ban screen. The scan's early
    # stop is built on ocr_ban_card_name returning None for every tactics
    # position; one resolution there and the scan grinds on through the
    # tactics rows paying vision calls (the 149-of-175-seconds failure).
    ("Le Ki rs", "tactics frame 135724_164 (0,1)"),
    ("NON wtf el", "tactics frame 135724_164 (0,4)"),
    ("re tlt Sy", "tactics frame 135528_823 (1,2)"),
    # Tactics card names, in both the game's casing and the OCR's.
    ("Power Swing", "tactics card"),
    ("Speed Boost", "tactics card"),
    ("Pitch Focus", "tactics card"),
    ("Fielding Play", "tactics card"),
    ("POWER SWING", "tactics card, OCR casing"),
    ("FIELDING PLAY", "tactics card, OCR casing"),
    # Type banners. "Batter" force-matched Jedediah Wetters on 12 turns once.
    ("Batter", "type banner"),
    ("PITCHER", "type banner"),
]

for _text, _why in MUST_ABSTAIN:
    _hit = resolve(_text)
    check(_hit is None,
          f"{_text!r} ({_why}) resolved to {_hit.name if _hit else None!r} — "
          "the ban matcher has been loosened; this is the N1 mis-ban")

# The other side: every one of these is a real read of a card the frame
# genuinely shows. They fail if the gates are tightened past usefulness.
MUST_RESOLVE = {
    # resolved before the confusion-aware pass existed
    "JOHNNY ORAWERS": "Johnny Drawers",          # d -> o
    "JUSTINYOUNG": "Justin Young",               # fused space
    "RUBESHARP": "Rube Sharp",                   # fused space
    "aUSTIN CUR BUNZ": 'Austin "Cur" Bunz',      # dropped quotes
    "JOHNNY TRAIN GOUDENBERG": "Johnny C-Train Goudenberg",   # dropped hyphen
    "NNY MEKESZ": "Donny Mekesz",                # ban-X clipped the first letters
    "SHUA DIAZ": "Joshua Diaz",                  # leading letters lost
    # recovered BY the confusion-aware pass — these are the four cells the
    # change bought, and they fail if it is reverted
    "JOSHUADIAZ ss": "Joshua Diaz",              # fused space + invented "ss"
    "SOSHUADIAZ ss": "Joshua Diaz",              # ... + j -> s
    "JOEJOOYGAIN": "Joe Jody Gain",              # fused spaces + d -> o
    "oanige THE RAT TA TRAN CRUZ": 'Daniel "The Rat-Ta-Train" Cruz',
}

for _text, _want in MUST_RESOLVE.items():
    _hit = resolve(_text)
    check(_hit is not None and _hit.name == _want,
          f"{_text!r} gave {_hit.name if _hit else None!r}, expected {_want!r} "
          "— a real read of a card on screen no longer resolves")

say(f"2. gates: {len(MUST_ABSTAIN)} refused, {len(MUST_RESOLVE)} real garbled "
    "reads still resolved")


# =========================================================================
# 3. BOTH GATES ARE LOAD-BEARING
# =========================================================================
# A probe that fails only ONE gate proves that gate. The straddle is COMPUTED
# here rather than asserted from memory, so the fixture cannot quietly stop
# straddling (the "Zzzz Wetter" lesson in test_roster_matching.py: a probe that
# fails at both thresholds passes whether or not either is present).
def score_and_margin(text):
    key = ocr_match_key(text)
    ranked = sorted(
        ((difflib.SequenceMatcher(None, key, ocr_match_key(n)).ratio(), n)
         for n in ROSTER_BY_NAME), reverse=True)
    return ranked[0][0], ranked[0][0] - ranked[1][0], ranked[0][1], ranked[1][1]

# MARGIN gate. One misread letter in the first word of a "* Jody Gain" card
# leaves the read equidistant from two real cards. Synthetic (m->p is not in
# the measured table) but the SHAPE is the measured one: the roster's four
# near-identical Gains and two Browns are what the margin exists for.
for _probe in ("MAPA JODY GAIN", "XAMA JODY GAIN", "JONNY JODY GAIN"):
    _s, _m, _top, _run = score_and_margin(_probe)
    check(_s >= BAN_OCR_KEY_CUTOFF,
          f"{_probe!r} scores {_s:.3f}, under the {BAN_OCR_KEY_CUTOFF} cutoff "
          "— it no longer straddles, so it proves nothing about the margin")
    check(_m < BAN_OCR_KEY_MARGIN,
          f"{_probe!r} has margin {_m:.3f}, at or over {BAN_OCR_KEY_MARGIN} — "
          "it no longer straddles")
    check(resolve(_probe) is None,
          f"{_probe!r} resolved to {_top!r} over {_run!r} at margin {_m:.3f} — "
          "the runner-up gate is gone and a coin flip is being reported as a "
          "card")

# CUTOFF gate. 'Frank Coker' clears the margin comfortably and is refused only
# by the score, so it proves the cutoff the way the Gains prove the margin.
_s, _m, _top, _ = score_and_margin("Frank Coker")
check(_s < BAN_OCR_KEY_CUTOFF and _m >= BAN_OCR_KEY_MARGIN,
      f"'Frank Coker' scores {_s:.3f} margin {_m:.3f} — it must fail the "
      "cutoff and pass the margin, or it stops proving the cutoff")
check(resolve("Frank Coker") is None,
      f"'Frank Coker' resolved to {_top!r} — it is not in the roster")

# TYPE BANNERS are refused by the cutoff, not by a guard. match_roster_name_ocr
# deliberately has no CARD_TYPE_BANNERS check: one was written and mutation
# testing could not distinguish it from its own absence, because the banners
# score nowhere near the cutoff. That is only true while it is true, so pin the
# scores — if a learned roster entry ever lifts a banner toward 0.85 this fires
# and the guard goes back in on purpose rather than by luck.
from orchestrator import CARD_TYPE_BANNERS

for _banner in sorted(CARD_TYPE_BANNERS):
    _s, _m, _top, _ = score_and_margin(_banner)
    check(_s < BAN_OCR_KEY_CUTOFF - 0.15,
          f"type banner {_banner!r} now scores {_s:.3f} against {_top!r}, "
          f"close to the {BAN_OCR_KEY_CUTOFF} cutoff — the cutoff alone is no "
          "longer what keeps banners out, so match_roster_name_ocr needs its "
          "own CARD_TYPE_BANNERS check back")

# LENGTH gate. Every junk read in the corpus is shorter than this; no roster
# key is (the shortest is 'joelblunt', 9).
check(BAN_OCR_MIN_KEY_LEN >= 4,
      f"BAN_OCR_MIN_KEY_LEN is {BAN_OCR_MIN_KEY_LEN} — 'me', 'be', 'jy' and "
      "'we' all appear in the corpus and must not be matchable")
check(min(len(ocr_match_key(n)) for n in ROSTER_BY_NAME) > BAN_OCR_MIN_KEY_LEN,
      "the length gate is longer than the shortest roster name, so that card "
      "can never be read")

# The gates must be at least as strict as the direct matcher this pass follows.
# It runs only after that one refuses, so a looser second pass silently
# replaces the strictness the first one was measured at.
check(BAN_OCR_KEY_CUTOFF >= 0.85,
      f"the confusion-aware pass runs at {BAN_OCR_KEY_CUTOFF}, under the 0.85 "
      "the direct ban matcher uses — the second pass is now the loose one")
# Stated separately from the straddle probes above so that zeroing the margin
# reports itself as what it is, rather than as "the fixture stopped straddling".
check(BAN_OCR_KEY_MARGIN >= 0.10,
      f"BAN_OCR_KEY_MARGIN is {BAN_OCR_KEY_MARGIN}, under the measured 0.10. "
      "Every true read on the corpus clears its runner-up by >= 0.167 and "
      "every refused negative by <= 0.042, so there is no reason to go under "
      "0.10 except to make an abstention go away")

say("3. both gates load-bearing")


# =========================================================================
# 4. THE KEY MUST NOT MERGE TWO ROSTER CARDS
# =========================================================================
# The projection is lossy on purpose. The invariant that keeps it safe is that
# no two DIFFERENT cards collapse close enough to be confusable — this is what
# fires if a future confusion class is too wide, or a learned roster entry
# arrives that the matcher genuinely cannot tell apart from an existing card.
_keys = {n: ocr_match_key(n) for n in ROSTER_BY_NAME}
_worst = max((difflib.SequenceMatcher(None, _keys[a], _keys[b]).ratio(), a, b)
             for a, b in itertools.combinations(_keys, 2))
check(_worst[0] < BAN_OCR_KEY_CUTOFF,
      f"{_worst[1]!r} and {_worst[2]!r} collapse to {_worst[0]:.3f} under the "
      f"key, at or above the {BAN_OCR_KEY_CUTOFF} cutoff — the matcher can no "
      "longer tell two real cards apart and will ban either")

# And every card must still be recognisable as itself.
for _name, _card in ROSTER_BY_NAME.items():
    _hit = match_roster_name_ocr(_card.name)
    check(_hit is not None and _hit.name == _card.name,
          f"the roster's own {_card.name!r} resolves to "
          f"{_hit.name if _hit else None!r} under the key")

say(f"4. key: {len(ROSTER_BY_NAME)} roster names all self-identify, worst "
    f"pairwise collapse {_worst[0]:.3f} < {BAN_OCR_KEY_CUTOFF}")


# =========================================================================
# 5. THE SECOND PASS IS ADDITIVE, NEVER AN OVERRIDE
# =========================================================================
# It exists to turn abstentions into answers. If it ever changes an answer the
# direct matcher already gave, every measurement behind that matcher's 0.85 is
# void — so assert the ordering directly rather than trusting the source.
#
# HONESTY NOTE, 2026-09-04: this section CANNOT CURRENTLY FAIL, and that is not
# a hole to be papered over with a synthetic probe. Two mutants were built to
# break it — run the confusion-aware pass FIRST so it can override, and delete
# the direct pass entirely — and BOTH passed the whole file. They are equivalent
# mutants, not misses: a search over 2209 garbled variants of the 33 roster
# names (fused spaces, dropped hyphens and quotes, d/o and j/s swaps, leading
# and trailing truncations, 60 random single-letter corruptions per name) found
# ZERO inputs where the two passes resolve to DIFFERENT cards. That is
# orchestrator's own measurement restated ("59 cells resolved by both with zero
# disagreements, 4 by the key alone, 0 by the direct matcher alone"), so on
# every input that exists the two orders are the same function.
#
# The check stays because the invariant is the thing that matters and it is
# cheap, but read it as a tripwire for a FUTURE divergence, not as evidence the
# ordering has been proven. If someone widens the confusion table or adds a
# learned roster entry, this is what fires — and only then does it start
# carrying weight. Do not "fix" it by inventing a probe that no frame produces.
for _text in list(MUST_RESOLVE) + [t for t, _ in MUST_ABSTAIN]:
    _direct = match_roster_name(_text, cutoff=0.85, allow_surname_fallback=False)
    if _direct is not None:
        _hit = resolve(_text)
        check(_hit is not None and _hit.name == _direct.name,
              f"{_text!r}: the direct matcher said {_direct.name!r} but "
              f"ocr_ban_card_name returned {_hit.name if _hit else None!r} — "
              "the confusion-aware pass is overriding, not extending")

say("5. second pass is additive, never an override")


# =========================================================================
# 6. OUTCOME OVER EVERY CACHED BAN-GRID FRAME
# =========================================================================
# The only section that pays for tesseract. It runs LAST because everything
# above is free: a broken matcher should report itself in a second, and this
# section should be the one you are watching when the clock is moving.
#
# (path, absolute roster row shown in the TOP of the two visible grid rows).
# Each mapping was established by reading three or more independently legible
# names in that row against KNOWN_BAN_ROSTER, so the ground truth for the
# ILLEGIBLE cells in the same row comes from the grid's rigid geometry rather
# than from the OCR under test.
FRAMES = [
    ("test_fixtures/20260824_200520_984.jpg", 0),
    ("test_fixtures/20260824_200601_124.jpg", 3),
    ("test_fixtures/20260824_200604_139.jpg", 5),
    ("test_fixtures/ban_scan/20260828_140309_081.jpg", 0),
    ("test_fixtures/ban_scan/20260828_140315_271.jpg", 0),
    ("test_fixtures/ban_counter/20260826_133925_665.jpg", 0),
    ("test_fixtures/ban_counter/20260826_133957_697.jpg", 0),
    ("test_fixtures/ban_counter/20260826_133958_816.jpg", 1),
    ("test_fixtures/ban_counter/20260826_134001_536.jpg", 1),
    ("test_fixtures/ban_counter/20260826_134004_720.jpg", 2),
    ("test_fixtures/ban_ocr/20260828_140320_608.jpg", 0),
]

for _rel, _ in FRAMES:
    if not os.path.exists(os.path.join(_ROOT, _rel)):
        # Never skip silently: a vanished fixture means this file proves
        # nothing, and a green line would say the opposite.
        raise SystemExit(f"missing fixture {_rel} — this test cannot run")

CELLS = 110
_GRID = [(r, c) for r in (0, 1) for c in range(5)]

_jobs, _crops = [], []
for _path, _abs0 in FRAMES:
    _img = Image.open(os.path.join(_ROOT, _path))
    _img.load()
    for _rel_row, _col in _GRID:
        _jobs.append((_path, _abs0 + _rel_row, _col))
        _crops.append(get_ban_grid_card_crop(_img, _rel_row, _col))

correct = wrong = abstain = 0
ocr_cells_done = 0
_hits = ocr_batch(_crops, "corpus")
ocr_cells_done += len(_hits)
for (_path, _row, _col), _hit in zip(_jobs, _hits):
    _truth = KNOWN_BAN_ROSTER.get((_row, _col))
    _truth = _truth.name if _truth else None
    _got = _hit.name if _hit else None
    if _got is None:
        abstain += 1
    elif _got == _truth:
        correct += 1
    else:
        wrong += 1
        failures.append(
            f"WRONG CARD: {os.path.basename(_path)} "
            f"({_row},{_col}) is {_truth!r}, OCR said "
            f"{_got!r} — this bans the wrong physical card")

check(correct + wrong + abstain == CELLS,
      f"expected {CELLS} cells over {len(FRAMES)} frames, scored "
      f"{correct + wrong + abstain}")

# Measured 2026-09-03: 63 correct / 0 wrong / 47 abstain (42.7%). The floor is
# the guard against over-tightening; there is deliberately NO ceiling on
# `correct`, because a ceiling punishes a genuine improvement and the guard
# against loosening is section 2's negative set, not this number.
MIN_CORRECT = 63
check(wrong == 0, f"{wrong} cell(s) resolved to the WRONG card")
check(correct >= MIN_CORRECT,
      f"only {correct} of {CELLS} cells resolved, was {MIN_CORRECT} when "
      "measured — the local path has been tightened into uselessness; every "
      "lost cell is a paid vision call")

say(f"6. corpus: {correct}/{CELLS} correct, {wrong} wrong, {abstain} abstained "
    f"({abstain / CELLS:.1%} abstention) over {len(FRAMES)} real ban frames")


# =========================================================================
# 7. TACTICS FRAMES MUST READ AS NOTHING AT ALL
# =========================================================================
# The scan's early stop ("no player names readable AND past the known roster")
# is built on this. It is asserted over the real frames, not over strings,
# because the crop geometry is half of the claim.
TACTICS_FRAMES = [f for f in
                  ("screenshot_log/run_20260828_135528/20260828_135528_823.jpg",
                   "screenshot_log/run_20260828_135528/20260828_135724_164.jpg")
                  if os.path.exists(os.path.join(_ROOT, f))]
if TACTICS_FRAMES:
    _resolved_on_tactics = []
    _tjobs, _tcrops = [], []
    for _path in TACTICS_FRAMES:
        _img = Image.open(os.path.join(_ROOT, _path))
        _img.load()
        for _rel_row, _col in _GRID:
            _tjobs.append((_path, _rel_row, _col))
            _tcrops.append(get_ban_grid_card_crop(_img, _rel_row, _col))
    _hits = ocr_batch(_tcrops, "tactics")
    ocr_cells_done += len(_hits)
    for (_path, _rel_row, _col), _hit in zip(_tjobs, _hits):
        if _hit is not None:
            _resolved_on_tactics.append(
                (os.path.basename(_path), _rel_row, _col, _hit.name))
    check(not _resolved_on_tactics,
          f"tactics positions resolved to player cards {_resolved_on_tactics} "
          "— the ban scan's early stop is defeated and it will grind through "
          "the tactics section paying vision calls")
    say(f"7. tactics: {len(TACTICS_FRAMES) * 10} positions across "
        f"{len(TACTICS_FRAMES)} real tactics frames, all correctly unread")
else:
    # These live in screenshot_log/, which the pruner deletes oldest-first, so
    # their absence is expected eventually. Say so rather than passing quietly.
    say("7. tactics: SKIPPED — screenshot_log tactics frames have been pruned")

# The ceiling, asserted rather than intended. One cell is one tesseract
# process; this file went to quarantine for taking minutes of them in silence.
check(ocr_cells_done <= MAX_OCR_CELLS,
      f"this file OCR'd {ocr_cells_done} cells, over the {MAX_OCR_CELLS} "
      "ceiling — each one is a tesseract process, and an unbounded corpus is "
      "how this file stalled the suite for minutes with no output")


if failures:
    for f in failures:
        print(f"FAIL: {f}", flush=True)
    raise SystemExit(f"{len(failures)} failure(s)")

say(f"OK: confusion table pinned, 0 wrong over 110 real cells, both gates "
    f"load-bearing, key does not merge two cards "
    f"({ocr_cells_done} cells OCR'd)")
