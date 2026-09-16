"""Landmark checks: does a frame actually show the waypoint? Offline, no input.

WHY THIS EXISTS
---------------
On 2026-08-26 the automated walk reported success while the detective stood in
front of a blank wall. reset_walk.walk_route() printed a CHECKPOINT line and
saved a frame at every landmark and then looked at neither, so the log of a
walk that arrived and the log of a walk that wandered into plasterwork were
identical. Every test run since has been uninterpretable for that reason: with
no landmark check, "the walk finished" and "the walk worked" are the same
sentence.

These tests exist to keep the fix honest rather than merely present. The
failure mode being guarded is NOT "the detector missed the table" -- that costs
one aborted walk and nothing else. It is "the detector says yes everywhere",
because that reinstates the original bug in a form that looks like a fix. So
the bulk of what follows is negatives, and the sharpest of them are frames the
walk really does produce when it goes wrong:

  * the TYPEWRITER prompt -- the same font, the same screen position, the same
    Square glyph, two seconds from the spawn point. Anything keying on "there
    is white text in the middle of the screen" passes this and is worthless.
  * the DINING ROOM one step short of the table -- same room, same lighting,
    same furniture, no prompt. This is what stopping 1.5s early looks like.
  * the LOADING SCREEN whose artwork is the Little & Big building, signage and
    all, larger and crisper than the real thing ever appears. A sign-reader
    with no gameplay gate calls this "arrived at L&B" while the game is
    literally still loading.

Fixtures live in test_fixtures/landmarks/ and carry their label as a filename
prefix, so a mislabelled one is visible in `ls`. They were cut from three
recorded walks at three different capture geometries (2000x1292 windowed,
1400x904 windowed, 1400x904 fullscreen) plus one frame from an unrelated
session on a different night, because a detector that only works at one window
size is a detector that breaks the next time the laptop is moved -- which has
already happened once on this project.
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
_os.environ["BASEBALL_TEST_RUN"] = "1"   # before any project import

import glob
import os
import sys

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy")

import numpy as np
from PIL import Image

import landmarks as L

fails = []
HERE = _ROOT
FIX = os.path.join(HERE, "test_fixtures", "landmarks")


def load(prefix):
    out = []
    for p in sorted(glob.glob(os.path.join(FIX, prefix + "*.jpg"))):
        out.append((os.path.basename(p), Image.open(p).convert("RGB")))
    return out


table = load("table_")
lbext = load("lbext_")
lbint = load("lbint_")
plain = load("other_")
notgame = load("notgameplay_")
# In-match card-table frames already in the fixture tree. Not world frames, so
# every landmark question must abstain on them.
inmatch = [(os.path.basename(p), Image.open(p).convert("RGB"))
           for p in sorted(glob.glob(os.path.join(HERE, "test_fixtures",
                                                  "2026*.jpg")))]

# A test that silently validates nothing is exactly the bug under repair, so
# the fixture set is itself asserted.
if len(table) < 8 or len(lbext) < 6 or len(plain) < 6 or not notgame:
    fails.append(f"fixture set is incomplete (table={len(table)} "
                 f"lbext={len(lbext)} other={len(plain)} notgame={len(notgame)}"
                 f") — this test would pass without checking anything")
if len({img.size for _, img in table}) < 2:
    fails.append("every table fixture has the same capture size — the "
                 "fractional boxes would never be exercised against a "
                 "different window geometry")

world = table + lbext + lbint + plain

# --- the gameplay gate ------------------------------------------------------
# Nothing downstream means anything if this is wrong: it is what stops a
# loading screen or the in-match card table from answering a world question.
world_hud = []
for name, img in world:
    s = L.hud_score(img)
    world_hud.append(s)
    if not L.in_gameplay(img):
        fails.append(f"{name}: world frame read as NOT gameplay "
                     f"(hud_score {s:.3f} < {L.HUD_MIN_RUN}) — every landmark "
                     f"check on it would abstain")
off_hud = []
for name, img in notgame + inmatch:
    s = L.hud_score(img)
    off_hud.append(s)
    if L.in_gameplay(img):
        fails.append(f"{name}: not a world frame but in_gameplay said True "
                     f"(hud_score {s:.3f}) — the gate is inert, and the "
                     f"loading screen's L&B artwork will be read as arrival")
if world_hud and off_hud and min(world_hud) <= max(off_hud):
    fails.append(f"gameplay gate has no margin left: worst world frame "
                 f"{min(world_hud):.3f} <= best non-world frame "
                 f"{max(off_hud):.3f}")

# --- at_baseball_table: the checkpoint that gates spending $50 --------------
# Each detector is run ONCE per frame and the verdict reused. Every call is a
# tesseract subprocess, so calling twice to build an error message doubles the
# runtime of the suite for nothing.
verdict = {name: L.at_baseball_table(img) for name, img in world + notgame + inmatch}

for name, img in table:
    if verdict[name] is not True:
        fails.append(f"{name}: AT the table (prompt visible) but "
                     f"at_baseball_table said {verdict[name]!r} — "
                     f"a real arrival would be reported as a failed walk")

for name, img in lbext + lbint + plain:
    got = verdict[name]
    if got is not False:
        why = ("the typewriter prompt is the same font in the same place"
               if "typewriter" in name else
               "this is the room BEFORE the table, with no prompt"
               if "diningroom" in name else "not the table")
        fails.append(f"{name}: {why}, but at_baseball_table said {got!r} — "
                     f"this is the blank-wall bug, restored")

# Off-world frames must ABSTAIN, not answer. False would be a lie of a
# different kind: it would report "the walk failed" when the truth is "the
# game was mid-load and the frame cannot say".
for name, img in notgame + inmatch:
    if verdict[name] is not None:
        fails.append(f"{name}: not a world frame, so the question is "
                     f"unanswerable, but at_baseball_table said "
                     f"{verdict[name]!r}")

# The WORD is the signal, not the geometry. Pinned directly on the matcher so
# it stays a text rule: these are real tesseract outputs from the frames above
# and from the typewriter, and the rule has to keep telling them apart.
for text, want in (
        ("Baseball Cards - playe$s@t", True),      # name intact
        ("Baseut Cands “ Play ($50)", True),  # name mangled, price intact
        ("Baseball Card . a. an)", True),
        ("_ Typewriter “ Save", False),       # same font, same place
        ("| ae “ Save", False),
        ("", False),
        ("Play", False),                           # one fragment is not enough
        ("50", False)):
    if L.prompt_says_baseball(text) is not want:
        fails.append(f"prompt matcher: {text!r} -> "
                     f"{L.prompt_says_baseball(text)}, wanted {want}")

for name, img in plain:
    if "typewriter" in name and L.prompt_says_baseball(L.read_prompt(img)):
        fails.append(f"{name}: the typewriter prompt matched the baseball rule")

# --- inertness: nothing must read as a landmark ----------------------------
# A frame with no game in it at all. If any of these answer True the detector
# is responding to something other than the landmark.
blank = Image.new("RGB", (1400, 904), (0, 0, 0))
white = Image.new("RGB", (1400, 904), (255, 255, 255))
noise = Image.fromarray(
    (np.random.default_rng(7).random((904, 1400, 3)) * 255).astype(np.uint8))
for nm, img in (("all black", blank), ("all white", white), ("noise", noise)):
    if L.at_baseball_table(img) is True:
        fails.append(f"{nm} frame read as the baseball table")
    if L.sees_lb_building(img) is True:
        fails.append(f"{nm} frame read as the L&B building")
# All-white trips a brightness gate but has no compass bar in it; it must be
# rejected as not-gameplay rather than sailing through on brightness.
if L.in_gameplay(white):
    fails.append("an all-white frame passed the gameplay gate — the gate is "
                 "measuring brightness, not the compass bar")

# A frame of the wrong shape cannot be addressed by fractional boxes at all.
for w, h in ((1400, 200), (300, 194)):
    odd = Image.new("RGB", (w, h), (60, 60, 60))
    if L.at_baseball_table(odd) is not None:
        fails.append(f"{w}x{h} frame: the fractional boxes point nowhere on "
                     f"this shape, so the only honest answer is None")

# --- sees_lb_building: confirms only, never denies -------------------------
# The contract this pins is one-sided on purpose. False positives are what
# make a failed walk invisible, so ZERO of them is required. Misses only cost
# an aborted walk, so a floor is asserted rather than perfection.
# Sparse-text OCR over a large crop is the slowest thing here (~1.4s/frame), so
# the negative pool is the pointed subset rather than everything: the loading
# screen that literally depicts the building, the room the walk ends in, and
# the L&B INTERIOR, which is the one place a sign fragment could plausibly be
# in shot and would mean the walk overshot rather than arrived.
lb_neg = notgame + lbint + table[:3] + plain[:4] + inmatch[:2]
lb_saw = {name: L.sees_lb_building(img) for name, img in lbext + lb_neg}

for name, _ in lb_neg:
    if lb_saw[name] is True:
        fails.append(f"{name}: sees_lb_building said True away from the shop "
                     f"front — a false sighting sends the walk onward into a "
                     f"wall")

lb_hits = [name for name, _ in lbext if lb_saw[name] is True]
LB_FLOOR = 5
if len(lb_hits) < LB_FLOOR:
    fails.append(f"sees_lb_building confirmed only {len(lb_hits)}/{len(lbext)} "
                 f"shop-front frames (floor {LB_FLOOR}) — below this it "
                 f"abstains so often the checkpoint stops being informative")
for name, _ in lbext:
    if lb_saw[name] is False:
        fails.append(f"{name}: sees_lb_building returned False; it is "
                     f"documented as confirm-only and must return None when "
                     f"it cannot read the sign")

# --- in_lb_interior: documented abstention, pinned so it cannot rot ---------
# No signal separating the L&B interior from the detective's own office was
# found (see the docstring: eight statistics, p5..p95 overlapping on all of
# them). The risk now is that someone later "fixes" this with a brightness
# rule, which would fire on the office and hide exactly the failure this
# module exists to expose. So: it may abstain, it may never assert.
for name, img in world + notgame + inmatch:
    got = L.in_lb_interior(img)
    if got is not None:
        fails.append(f"{name}: in_lb_interior returned "
                     f"{got!r}. It is documented as not "
                     f"implementable from these frames; if that changed, this "
                     f"test must be replaced with real separation numbers, "
                     f"not deleted")

# --- describe() is the debugging path; it must not crash on anything -------
for name, img in (world[:1] + notgame[:1] + [("synthetic", noise)]):
    try:
        d = L.describe(img)
        if "hud_score" not in d or "at_baseball_table" not in d:
            fails.append(f"describe({name}) missing keys")
    except Exception as exc:
        fails.append(f"describe({name}) raised {exc!r}")

if fails:
    for f in fails:
        print("  FAIL:", f)
    sys.exit(1)

print(f"verified {len(table)} at-table frames (3 capture geometries + 1 "
      f"independent session) against {len(lbext)+len(lbint)+len(plain)} world "
      f"non-table frames incl. {sum(1 for n,_ in plain if 'typewriter' in n)} "
      f"typewriter-prompt and {sum(1 for n,_ in plain if 'diningroom' in n)} "
      f"one-room-short decoys, plus {len(notgame)+len(inmatch)} off-world "
      f"frames that must abstain; gameplay gate margin "
      f"{max(off_hud):.3f}->{min(world_hud):.3f}; sees_lb_building "
      f"{len(lb_hits)}/{len(lbext)} confirmed, 0 false; in_lb_interior "
      f"abstains everywhere by design")
