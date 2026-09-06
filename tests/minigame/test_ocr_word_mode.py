"""Word-mode OCR must return EXACTLY what the pytesseract path returned.

WHY (OPEN-12). orchestrator.py read the ban-grid card names, the scoreboard,
the runner banners and the ban counter through pytesseract, which spawns a
`tesseract` process per call and hands it the image through a TEMP FILE. Two
costs, and the second is the one that hurt: ~193ms against ~79ms in process,
and the temp file itself. This is a work machine running Sophos; six
pytesseract-heavy tests intermittently blew the suite's 300s ceiling and a
`sample` of one caught it with 2671 of 2671 stacks inside a single unlink —
pytesseract.cleanup, deleting that temp file. So the migration removes a class
of stall, not merely 114ms.

None of which is worth anything if the answers move. A ban name decides which
physical card is banned in a $50 match, so a silently different read is a money
bug, and A FASTER WRONG READ IS THE WORST OUTCOME AVAILABLE HERE.

GROUND TRUTH IS WHAT THE SLOW PATH ACTUALLY RETURNED, not what a human thinks
the frames say — the same construction as tests/routing/test_ocr_glyphs.py,
which is how the compass migration was proven. test_fixtures/word_ocr/ holds
the crops exactly as they are handed to tesseract (recorded through the same
PNG round trip this test reads them back over) and truth.json holds what
pytesseract answered for those very files. Accuracy is NOT the question here
and is pinned elsewhere (test_ocr_ban_card, test_ocr_scoreboard,
test_ocr_runner, test_ban_scan's counter cases); the question is agreement.

DELIBERATELY NO pytesseract CALL IN THIS FILE. Recording the truth is what pays
that cost, once, offline. A test that re-measured the slow path every run would
reintroduce the stall it exists to certify away.

WHAT IT CHECKS
  FIXTURE     the corpus is big enough, spans several frames, covers both PSMs
              and both a real-text and an abstention population.
  AGREEMENT   image_to_text reproduces the recorded string BYTE FOR BYTE,
              trailing newline included — ocr_scoreboard splits on lines.
  PSM         psm is really plumbed through, not defaulted. Reading a name at
              SINGLE_CHAR must not give the SINGLE_BLOCK answer.
  WHITELIST   the whitelist is really applied, and constrains the characters.
  CACHE       the per-thread handle cache does not leak one call's mode into
              the next: the ban screen alternates PSM 6 and PSM 7, and the
              compass's PSM 10 runs in the same process.
  CONFIG      the fallback asks tesseract the SAME question, against the
              literal strings orchestrator used before the migration.
  WIRING      all four orchestrator call sites really go through it, and none
              of them still calls pytesseract. Without this the whole file
              could pass while the migration had been reverted.
  FALLBACK    an unavailable in-process reader degrades to pytesseract AND
              says so, naming the combination that otherwise goes untraced.
"""

import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import json
import os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-offline-test")
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

from PIL import Image, ImageOps

import ocr_glyphs
import orchestrator as O

FIX = os.path.join(_ROOT, "test_fixtures", "word_ocr")
fails = []

if not os.path.isdir(FIX):
    raise SystemExit(
        f"missing fixture dir {FIX} — this test must not silently skip. It is "
        "the only evidence that the word-mode migration did not change what "
        "the game reads off its own screen.")

truth = json.load(open(os.path.join(FIX, "truth.json")))
names = sorted(truth)

# --- FIXTURE: the properties every check below leans on --------------------
# A suite that quietly lost its corpus passes by testing nothing.
if len(names) < 80:
    fails.append(f"fixture holds only {len(names)} crops; it is meant to hold "
                 f"~110 covering all four migrated call sites")
kinds = {truth[n]["kind"] for n in names}
for need in ("ban_card", "ban_counter", "scoreboard", "runner"):
    if need not in kinds:
        fails.append(f"fixture never exercises the {need!r} call site, so the "
                     f"migration of that one is unevidenced")
psms = {truth[n]["psm"] for n in names}
if psms != {6, 7}:
    fails.append(f"fixture covers PSMs {sorted(psms)}; the migrated call sites "
                 f"use 6 (text block) and 7 (single line), and a mode that is "
                 f"never exercised is a mode that is never checked")
if not any(truth[n]["whitelist"] for n in names):
    fails.append("no fixture crop carries a whitelist, so whitelist handling "
                 "— the part that differs most between the two backends — is "
                 "untested")
srcs = {truth[n]["src"] for n in names}
if len(srcs) < 6:
    fails.append(f"fixture frames come from {len(srcs)} source frames; one or "
                 f"two captures are not evidence of anything")
# Real text and abstentions are different failure modes. A speedup that reads
# blanks perfectly and mangles names would pass a corpus of blanks.
rich = [n for n in names if len(truth[n]["text"].strip()) >= 6]
blank = [n for n in names if not truth[n]["text"].strip()]
if len(rich) < 15:
    fails.append(f"only {len(rich)} fixture crops hold real text; agreement on "
                 f"names is the claim that decides which card gets banned")
if len(blank) < 10:
    fails.append(f"only {len(blank)} fixture crops read as nothing; abstention "
                 f"is the majority case live and the one a careless speedup "
                 f"turns into invented letters")

images = {n: Image.open(os.path.join(FIX, n)) for n in names}

# --- AGREEMENT -------------------------------------------------------------
bad = []
for n in names:
    rec = truth[n]
    got = ocr_glyphs.image_to_text(images[n], psm=rec["psm"],
                                   whitelist=rec["whitelist"])
    if got != rec["text"]:
        bad.append((n, rec["text"], got))
if bad:
    fails.append(f"{len(bad)}/{len(names)} crops disagree with the recorded "
                 f"pytesseract answer; first few: " +
                 "; ".join(f"{n}: slow={t!r} fast={g!r}" for n, t, g in bad[:5]))

# Trailing whitespace is part of the answer, not noise: ocr_scoreboard splits
# this string into lines. A stray .strip() inside image_to_text would pass a
# stripped comparison and change what the scoreboard parser sees.
with_nl = [n for n in names if truth[n]["text"].endswith("\n")]
if not with_nl:
    fails.append("no recorded answer ends in a newline, so this file cannot "
                 "tell a raw read from a stripped one")
else:
    n = with_nl[0]
    if not ocr_glyphs.image_to_text(
            images[n], psm=truth[n]["psm"],
            whitelist=truth[n]["whitelist"]).endswith("\n"):
        fails.append("image_to_text stripped its answer; the raw string is "
                     "what ocr_scoreboard splits into lines")

# --- PSM is really plumbed through ----------------------------------------
# The handle cache used to be keyed on the WHITELIST ALONE, from when this
# module only ever asked for PSM 10. Keyed that way, a word-mode call is handed
# back a SINGLE_CHAR handle and returns one character of a player's name — a
# wrong answer that looks exactly like a working one.
if rich:
    n = rich[0]
    block = ocr_glyphs.image_to_text(images[n], psm=6,
                                     whitelist=truth[n]["whitelist"])
    single = ocr_glyphs.image_to_text(images[n], psm=10,
                                      whitelist=truth[n]["whitelist"])
    if block == single:
        fails.append(f"{n}: PSM 6 and PSM 10 return the same string "
                     f"({block!r}) — psm is not reaching tesseract, so every "
                     f"word-mode caller is silently getting some other mode")

# --- the whitelist is really applied --------------------------------------
wl_names = [n for n in names if truth[n]["whitelist"]
            and truth[n]["text"].strip()]
if not wl_names:
    fails.append("no whitelisted fixture crop reads as anything, so the "
                 "whitelist cannot be shown to be doing anything")
for n in wl_names:
    wl = truth[n]["whitelist"]
    got = ocr_glyphs.image_to_text(images[n], psm=truth[n]["psm"], whitelist=wl)
    stray = {c for c in got.strip() if c not in wl}
    if stray:
        fails.append(f"{n}: whitelisted read returned {sorted(stray)!r}, which "
                     f"is not in {wl!r} — the whitelist did not reach the API")
        break
if wl_names:
    n = wl_names[0]
    free = ocr_glyphs.image_to_text(images[n], psm=truth[n]["psm"],
                                    whitelist=None)
    if free == truth[n]["text"]:
        fails.append(f"{n}: dropping the whitelist changed nothing, so this "
                     f"file cannot tell a whitelisted read from a free one")

# --- the handle cache must not leak a mode across calls -------------------
# Live, the ban screen alternates PSM 6 (card names) and PSM 7 (the counter),
# and compass runs PSM 10 in the same process. Re-reading everything after
# that traffic must give the same answers.
_glyph = images[names[0]].convert("L").resize((60, 50))
ocr_glyphs.recognise([_glyph, _glyph])                 # PSM 10 + NESW
if wl_names and rich:
    for _ in range(3):
        ocr_glyphs.image_to_text(images[wl_names[0]], psm=7,
                                 whitelist=truth[wl_names[0]]["whitelist"])
        ocr_glyphs.image_to_text(images[rich[0]], psm=6, whitelist=None)
    ocr_glyphs.recognise([_glyph])
after = [(n, ocr_glyphs.image_to_text(images[n], psm=truth[n]["psm"],
                                      whitelist=truth[n]["whitelist"]))
         for n in names]
drifted = [n for n, g in after if g != truth[n]["text"]]
if drifted:
    fails.append(f"{len(drifted)} crops changed answer after interleaved "
                 f"PSM 6 / 7 / 10 traffic ({drifted[:4]}) — the per-thread "
                 f"handle cache is handing one call site another's mode")

# --- the fallback asks tesseract the SAME question ------------------------
# Literals on purpose. These are the exact config strings orchestrator.py
# passed before the migration; deriving them from the module's own constants
# would rise with any change to those constants and pass forever.
if ocr_glyphs.PSM_TEXT_BLOCK != 6 or ocr_glyphs.PSM_SINGLE_LINE != 7:
    fails.append(f"PSM constants moved: TEXT_BLOCK="
                 f"{ocr_glyphs.PSM_TEXT_BLOCK} SINGLE_LINE="
                 f"{ocr_glyphs.PSM_SINGLE_LINE}. These are tesseract's own "
                 f"page-segmentation numbers, not tunables.")
for got, want in ((ocr_glyphs.tesseract_config(6), "--psm 6"),
                  (ocr_glyphs.tesseract_config(6, None), "--psm 6"),
                  (ocr_glyphs.tesseract_config(7, "0123456789/"),
                   "--psm 7 -c tessedit_char_whitelist=0123456789/"),
                  (ocr_glyphs.tesseract_config(10, "NESW"),
                   "--psm 10 -c tessedit_char_whitelist=NESW")):
    if got != want:
        fails.append(f"tesseract_config returned {got!r}, not {want!r} — the "
                     f"fallback would ask a different question from the fast "
                     f"path and answer it just as confidently")

# --- WIRING: the four call sites really use it, and none uses pytesseract --
# Anti-vacuity. Everything above holds even if orchestrator never calls
# image_to_text at all.
import pytesseract as _pyt

_seen = []
_real_word = ocr_glyphs.image_to_text


def _spy(image, psm=ocr_glyphs.PSM_TEXT_BLOCK, whitelist=None):
    _seen.append((psm, whitelist))
    return _real_word(image, psm=psm, whitelist=whitelist)


_spawned = []


def _no_spawn(*a, **k):
    _spawned.append(k.get("config"))
    return ""


_real_pyt = _pyt.image_to_string
ocr_glyphs.image_to_text = _spy
_pyt.image_to_string = _no_spawn
try:
    frame = Image.open(os.path.join(_ROOT, "test_fixtures",
                                    "20260824_200601_124.jpg"))
    O.ocr_ban_card_name(O.get_ban_grid_card_crop(frame, 0, 0))
    n_names = len(_seen)

    counter_frame = Image.open(os.path.join(
        _ROOT, "test_fixtures", "ban_counter", "20260826_134004_720.jpg"))
    O.read_ban_counter(counter_frame)
    n_counter = len(_seen) - n_names

    play = Image.open(os.path.join(_ROOT, "test_fixtures",
                                   "20260824_201103_128.jpg"))
    crops = dict(O.crop_gameplay_regions(play))
    O.ocr_scoreboard(crops["scoreboard"])
    O.ocr_runner_card(crops["first_base"])
    n_play = len(_seen) - n_names - n_counter
finally:
    ocr_glyphs.image_to_text = _real_word
    _pyt.image_to_string = _real_pyt

if n_names != 1:
    fails.append(f"ocr_ban_card_name made {n_names} word-mode reads, expected "
                 f"1 — it is not routed through ocr_glyphs")
if n_counter < 1:
    fails.append("read_ban_counter made no word-mode read — it is not routed "
                 "through ocr_glyphs")
if n_play != 2:
    fails.append(f"ocr_scoreboard + ocr_runner_card made {n_play} word-mode "
                 f"reads, expected 2")
if _spawned:
    fails.append(f"{len(_spawned)} call(s) still went to pytesseract while the "
                 f"in-process reader was available ({_spawned[:3]}) — each one "
                 f"spawns a process and writes the temp file this migration "
                 f"exists to remove")
wanted = {(6, None), (7, "0123456789/")}
if _seen and not wanted <= set(_seen):
    fails.append(f"call sites asked for {sorted(set(_seen))}; expected at "
                 f"least {sorted(wanted)} — the ban counter needs its digit "
                 f"whitelist and a single LINE, the names a text BLOCK")

# --- FALLBACK: degrade to pytesseract, and say so -------------------------
# Both ways in: a backend that is merely not the fast one, and a reader that
# raises. Neither may go silent, because the failure is invisible downstream —
# the answers stay right and the run simply gets slower and starts stalling.
def _run_fallback(backend_stub):
    calls = []

    def _capture(image, config=None):
        calls.append(config)
        return "fallback text\n"

    real_backend = ocr_glyphs.backend
    _pyt.image_to_string = _capture
    ocr_glyphs.backend = backend_stub
    O._WARNED_ONCE.clear()
    import io
    buf, real_stdout = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        out = O._ocr_text(images[names[0]], 7, "0123456789/")
    finally:
        sys.stdout = real_stdout
        ocr_glyphs.backend = real_backend
        _pyt.image_to_string = _real_pyt
    return out, calls, buf.getvalue()


def _raiser():
    raise RuntimeError("tessdata missing")


for label, stub in (("slow backend selected", lambda: "pytesseract"),
                    ("reader raises", _raiser)):
    out, calls, said = _run_fallback(stub)
    if out != "fallback text\n":
        fails.append(f"fallback ({label}): _ocr_text returned {out!r}, not the "
                     f"pytesseract answer — the fallback does not fall back")
    if calls != ["--psm 7 -c tessedit_char_whitelist=0123456789/"]:
        fails.append(f"fallback ({label}): pytesseract was asked {calls!r}, "
                     f"not the same question the fast path was asked")
    low = said.lower()
    if not said.strip():
        fails.append(f"fallback ({label}) was SILENT. This is the exact shape "
                     f"this project keeps being bitten by: the answers stay "
                     f"correct, so nothing looks broken, and the slowdown gets "
                     f"blamed on the console or the network.")
    else:
        for phrase in ("correct", "slow", "pytesseract"):
            if phrase not in low:
                fails.append(f"fallback ({label}) warning never says "
                             f"{phrase!r}: {said.strip()[:160]!r}. It must say "
                             f"the answers stay right AND the run gets slower "
                             f"— that combination is what goes untraced.")

# --- warn ONCE ------------------------------------------------------------
# This sits on a per-card path: the ban scan reads ten cells a screen, and a
# warning per cell is a wall nobody reads, which is how a real diagnosis gets
# lost among its own repetitions.
calls2 = []
real_backend = ocr_glyphs.backend
_pyt.image_to_string = lambda image, config=None: (calls2.append(config) or "x")
ocr_glyphs.backend = lambda: "pytesseract"
O._WARNED_ONCE.clear()
import io as _io
_buf, _so = _io.StringIO(), sys.stdout
sys.stdout = _buf
try:
    O._ocr_text(images[names[0]], 6, None)
    O._ocr_text(images[names[0]], 6, None)
    O._ocr_text(images[names[0]], 6, None)
finally:
    sys.stdout = _so
    ocr_glyphs.backend = real_backend
    _pyt.image_to_string = _real_pyt
if len(calls2) != 3:
    fails.append(f"fallback did not run on every call ({len(calls2)}/3)")
if _buf.getvalue().count("WARNING") != 1:
    fails.append(f"the fallback warning printed "
                 f"{_buf.getvalue().count('WARNING')} times for 3 reads; it "
                 f"must be once per process — this sits on a per-card path")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)

print(f"backend={ocr_glyphs.backend()}: {len(names)} word-mode crops from "
      f"{len(srcs)} real frames across all four migrated call sites "
      f"({len(rich)} with real text, {len(blank)} abstentions, PSMs "
      f"{sorted(psms)}) reproduce the recorded pytesseract answer byte for "
      f"byte; psm and whitelist both reach the API and both change the answer; "
      f"answers survive interleaved PSM 6/7/10 traffic; the config strings "
      f"match the pre-migration literals; all four orchestrator call sites go "
      f"through ocr_glyphs and none spawns a process; and the fallback both "
      f"works and warns exactly once.")
