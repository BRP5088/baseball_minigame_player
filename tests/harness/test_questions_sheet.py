"""tools/questions_sheet.py: contact sheet + answer table for questionable slots (I-59).

Builds a synthetic `diagnostics/deal_frames`-shaped tree (3 refused_select_* dirs,
2 dropped_* dirs) in a scratch directory, runs the tool against it, and checks the
whole pipeline end to end: the sheet PNG exists at the tile count the row count
implies, questions.md/questions.json carry one row per question with an empty
answer column, the two dropped frames 30s apart at the same slot collapse into
one question, and nothing under the source tree is touched.

The slot-crop check does NOT reuse tools.questions_sheet.slot_box to paint the
synthetic image -- it derives the expected boundary independently from the same
local_hand.SLOT_PLAYER/SLOT_TACTICS DATA the tool reads, so a mutant that breaks
the crop math (wrong neighbour, flipped margin, off-by-one slot) shows up as the
extracted tile no longer matching the colour painted at that boundary, rather
than trivially agreeing with itself.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile


_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))

os.environ.setdefault("BASEBALL_TEST_RUN", "1")

from PIL import Image

import local_hand
import questions_sheet as qs

ok = True


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        ok = False


IMG_W, IMG_H = 979, 300
SLOT_COLOR = {0: (220, 30, 30), 1: (30, 180, 30), 2: (30, 30, 220),
              3: (220, 200, 30), 4: (200, 30, 200)}


def _expected_bounds(w):
    """Independent re-derivation of the slot boundaries from the DATA (not from
    questions_sheet.slot_box) -- see module docstring for why."""
    n = len(local_hand.SLOT_PLAYER)
    centers = [(local_hand.SLOT_PLAYER[i][0] + local_hand.SLOT_TACTICS[i][0]) / 2
               * w / local_hand.ANCHOR_W for i in range(n)]
    bounds = [0.0]
    for i in range(n - 1):
        bounds.append((centers[i] + centers[i + 1]) / 2)
    bounds.append(float(w))
    return bounds


def _make_hand_png(path):
    im = Image.new("RGB", (IMG_W, IMG_H), (0, 0, 0))
    px = im.load()
    bounds = _expected_bounds(IMG_W)
    for slot in range(5):
        x0, x1 = int(bounds[slot]), int(bounds[slot + 1])
        for x in range(x0, x1):
            for y in range(IMG_H):
                px[x, y] = SLOT_COLOR[slot]
    im.save(path)


def _tree_hash(root):
    h = hashlib.sha256()
    for base, dirs, files in os.walk(root):
        for f in sorted(files):
            p = os.path.join(base, f)
            h.update(os.path.relpath(p, root).encode())
            h.update(open(p, "rb").read())
    return h.hexdigest()


scratch = tempfile.mkdtemp(prefix="qsheet_test_")
src = os.path.join(scratch, "deal_frames")
out = os.path.join(scratch, "out")
os.makedirs(src)

BASE_NS = 1_800_000_000_000_000_000
S = 1_000_000_000

# 3 refused_select dirs, well separated (200s apart, distinct slots -- no dedupe)
REFUSED = [
    (BASE_NS + 0 * S, 0, {"target": 0, "kind": "player", "already_selected": [], "attempt": 1}),
    (BASE_NS + 200 * S, 1, {"target": 1, "kind": "player+tactics", "already_selected": [0], "attempt": 2}),
    (BASE_NS + 400 * S, 2, {"target": 2, "kind": "player", "already_selected": [], "attempt": 1}),
]
for ns, slot, why in REFUSED:
    d = os.path.join(src, f"refused_select_{ns}")
    os.makedirs(d)
    _make_hand_png(os.path.join(d, "hand.png"))
    json.dump(why, open(os.path.join(d, "why.json"), "w"))

# 2 dropped dirs, same slot, 30s apart -- must dedupe into one question
DROPPED = [
    (BASE_NS + 600 * S, {"why": "played without slots [3] (unreadable)", "dropped": [3]}),
    (BASE_NS + 630 * S, {"why": "played without slots [3] (unreadable)", "dropped": [3]}),
]
for ns, why in DROPPED:
    d = os.path.join(src, f"dropped_{ns}")
    os.makedirs(d)
    _make_hand_png(os.path.join(d, "hand.png"))
    json.dump(why, open(os.path.join(d, "why.json"), "w"))

before_hash = _tree_hash(src)

sheet_paths, rows = qs.build(str(BASE_NS - 1), out, root=src)

after_hash = _tree_hash(src)
check("source tree byte-for-byte unchanged after build()", before_hash == after_hash)

# ---- dedupe: 5 raw questions (3 refused + 2 dropped-slot) collapse to 4 ----
check("dedupe collapsed the two same-slot frames 30s apart into one question "
      f"(got {len(rows)} rows, want 4)", len(rows) == 4)
check("the merged row is the dropped-slot-3 one and remembers it was seen twice",
      len(rows) == 4 and rows[3]["slot"] == 3 and "2x" in rows[3]["said"])
check("row order is oldest first (slots 0,1,2,3)",
      [r["slot"] for r in rows] == [0, 1, 2, 3])

# ---- questions.md: exactly N rows, empty answer column ----
md_path = os.path.join(out, "questions.md")
check("questions.md exists", os.path.exists(md_path))
if os.path.exists(md_path):
    lines = [l for l in open(md_path).read().splitlines() if l.startswith("| ")]
    data_lines = lines[1:]  # drop the header row
    check(f"questions.md has exactly {len(rows)} data rows (got {len(data_lines)})",
          len(data_lines) == len(rows))
    check("every row's answer column is empty",
          all(l.rstrip().endswith("|  |") for l in data_lines))

# ---- questions.json: rows match the in-memory rows build() returned ----
json_path = os.path.join(out, "questions.json")
check("questions.json exists", os.path.exists(json_path))
if os.path.exists(json_path):
    on_disk = json.load(open(json_path))
    check("questions.json rows match build()'s own rows", on_disk == rows)
    check("every question.json row has an empty answer",
          all(r["answer"] == "" for r in on_disk))

# ---- sheet PNG: exists, at the tile count the row count implies ----
check(f"exactly one sheet written for {len(rows)} questions (<= MAX_PER_SHEET)",
      len(sheet_paths) == 1)
if sheet_paths:
    im = Image.open(sheet_paths[0])
    want_rows = -(-len(rows) // qs.COLS)
    check("sheet PNG has the expected tile-grid dimensions",
          im.size == (qs.COLS * qs.TILE_W, want_rows * qs.TILE_H))

# ---- slot crop: each extracted crop is dominated by that slot's synthetic colour ----
for ns, slot, why in REFUSED:
    hand_png = os.path.join(src, f"refused_select_{ns}", "hand.png")
    im = Image.open(hand_png).convert("RGB")
    box = qs.slot_box(im.width, im.height, slot)
    crop = im.crop(box)
    dominant = max(crop.getcolors(crop.width * crop.height), key=lambda c: c[0])[1]
    check(f"slot {slot}'s crop is dominated by its own synthetic colour "
          f"(want {SLOT_COLOR[slot]}, got {dominant})",
          dominant == SLOT_COLOR[slot])

shutil.rmtree(scratch, ignore_errors=True)

print("\nall green" if ok else "\nFAILURES above")
sys.exit(0 if ok else 1)
