"""I-67: after I-64's BANNER_SEARCH step fix, 8 of the user's 14 hand-labelled
readable tactics slots (test_fixtures/user_truth/20260923_c20-26/labels.json)
still missed MIN_TYPE_SCORE. A SLOT x TYPE census over 510
diagnostics/deal_frames/*/hand.png (agent_progress/issues/I-67/measure.py's
slot_census(), same shape as the 2026-09-20 fielding_boost census in
tools/build_hand_tactics_templates.py) found real bank-coverage gaps at:

    slot 1 speed_boost      n=24   95.8% rejected
    slot 1 fielding_boost   n= 9   88.9% rejected
    slot 3 fielding_boost   n=14   64.3% rejected   (the 12 existing donors
                                                       never covered x~644)
    slot 2 speed_boost      n=20   45.0% rejected
    slot 4 swing_boost      n= 8   50.0% rejected

THE FIX: four new DONORS entries in tools/build_hand_tactics_templates.py, one
per cell, cut from the confirmed frames at their FOUND positions -- the same
mechanism the 12 fielding_boost + 1 pitch_boost (I-22) donors already use, not
a new code path. tactics_templates.npz grew 373 -> 377 templates. See
test_fixtures/tactics_banner_misses/expected_i67.json for the full recovery
table, including what did NOT recover and why (q53, q62, q75 -- measured, not
guessed).

NOT ATTEMPTED: a right-portion-only banner match (I-64 built and measured one,
recovering 4 more of the original 14, but reverted it because it defeats
tests/minigame/test_i22_pitch_boost_slot3.py's mutation guard for a real
reason). Re-measured here (agent_progress/issues/I-67/progress.md): the I-22
donor frame sits at the SAME banner x-position (642) and the SAME slot-to-
neighbour gap (93 anchor units) as the confirmed-clipped q16/q18 (92-93), so
gap alone cannot gate a right-only fallback without re-defeating that guard.
The DONORS mechanism used here does not touch read_tactics_type/_best_banner
at all, so it cannot threaten that guard.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ.setdefault("BASEBALL_TEST_RUN", "1")

import numpy as np                                                      # noqa: E402
from PIL import Image                                                   # noqa: E402

import local_hand as lh                                                 # noqa: E402

FIX = os.path.join(_ROOT, "test_fixtures", "tactics_banner_misses")
fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


data = json.load(open(os.path.join(FIX, "expected_i67.json")))

# ---- 1. THE DONOR COUNT, PINNED AS A LITERAL --------------------------------
# A test that reads the constant back from itself rises with it and passes
# forever (CLAUDE.md 10.11). Four NEW donors on top of whatever I-22 shipped.
sys.path.insert(0, os.path.join(_ROOT, "tools"))
import build_hand_tactics_templates as builder                          # noqa: E402

_NEW = [d for d in builder.DONORS if d[0].startswith("test_fixtures/hand_reads/i67_")]
check("exactly 4 new I-67 donors are registered", len(_NEW) == 4, str(len(_NEW)))
check("the 4 donors are the expected (slot, type) cells",
      sorted((s, k) for _f, s, k in _NEW) ==
      sorted([(1, "speed_boost"), (2, "speed_boost"), (3, "fielding_boost"), (4, "swing_boost")]),
      str(sorted((s, k) for _f, s, k in _NEW)))

_z = __import__("numpy").load(lh.TACTICS_TEMPLATES, allow_pickle=True)
check("the shipped bank has 377 templates (373 + 4)", len(_z["vectors"]) == 377,
      str(len(_z["vectors"])))

# ---- 2. THE FIVE RECOVERED MISSES NOW READ THEIR TYPE ------------------------
n_graded = 0
for m in data["misses"]:
    img = Image.open(os.path.join(FIX, m["file"])).convert("RGB")
    rows = lh.read_hand(img)
    i = m["slot"]
    if i >= len(rows):
        check(f"q{m['q']} {m['file']} slot {i}: row exists", False, "row missing")
        continue
    row = rows[i]
    n_graded += 1
    check(f"q{m['q']} {m['file']} slot {i}: kind=='tactics'", row.get("kind") == "tactics",
          f"got {row.get('kind')!r}")
    check(f"q{m['q']} {m['file']} slot {i}: type=={m['expected_type']!r}",
          row.get("type") == m["expected_type"], f"got {row.get('type')!r}")
    check(f"q{m['q']} {m['file']} slot {i}: type_score >= MIN_TYPE_SCORE",
          (row.get("type_score") or 0) >= lh.MIN_TYPE_SCORE, str(row.get("type_score")))
    check(f"q{m['q']} {m['file']} slot {i}: bonus=={m['expected_bonus']!r}",
          row.get("bonus") == m["expected_bonus"], f"got {row.get('bonus')!r}")
check("the miss fixtures actually graded something", n_graded == len(data["misses"]),
      f"{n_graded} of {len(data['misses'])}")

# ---- 3. THE CONTROLS: clipped PLAYER banners must never leak a tactics type --
for p in data["players"]:
    img = Image.open(os.path.join(FIX, p["file"])).convert("RGB")
    rows = lh.read_hand(img)
    i = p["slot"]
    row = rows[i] if i < len(rows) else {}
    check(f"{p['file']} slot {i}: kind != 'tactics'", row.get("kind") != "tactics",
          f"got {row.get('kind')!r}")
    check(f"{p['file']} slot {i}: no tactics type leaked", row.get("type") is None,
          f"got {row.get('type')!r}")

# ---- 4. MUTATION: strip the 4 new donors and watch every recovery regress ----
# lh._type_cache caches the loaded bank at module level, so the only way to
# prove the new rows are load-bearing rather than vacuous (CLAUDE.md's check()
# lesson) is to strip them and watch the donor AND the held-out frame (q18)
# both fall back to the pre-fix failure. Same shape as test_i22's own mutation
# check -- but the I-67 donors sit at [-5:-1], NOT [-4:]: the I-22 donor is
# kept LAST on purpose (tools/build_hand_tactics_templates.py's DONORS list
# comment) so that test's own `_full_types[-1] == "pitch_boost"` control needs
# no edit here.
_full_vecs, _full_types = lh._type_templates()
check("CONTROL: the I-22 donor is still last (this test's slice depends on it)",
      _full_types[-1] == "pitch_boost", str(_full_types[-1]))
_stripped_vecs = np.concatenate([_full_vecs[:-5], _full_vecs[-1:]])
_stripped_types = np.concatenate([_full_types[:-5], _full_types[-1:]])
check("CONTROL: the mutation removes exactly 4 templates",
      len(_stripped_types) == len(_full_types) - 4,
      f"{len(_stripped_types)} of {len(_full_types)} kept")
check("CONTROL: the 4 stripped templates are the I-67 donors",
      list(_full_types[-5:-1]) == ["fielding_boost", "swing_boost", "speed_boost", "speed_boost"],
      str(list(_full_types[-5:-1])))
lh._type_cache = (_stripped_vecs, _stripped_types)
try:
    for m in data["misses"]:
        img = Image.open(os.path.join(FIX, m["file"])).convert("RGB")
        rows = lh.read_hand(img)
        row = rows[m["slot"]] if m["slot"] < len(rows) else {}
        regressed = row.get("type") != m["expected_type"] or (row.get("type_score") or 1.0) < lh.MIN_TYPE_SCORE
        check(f"q{m['q']} {m['file']}: regresses with the I-67 donors removed", regressed,
              f"still reads {row.get('type')!r} at {row.get('type_score')} -- some OTHER "
              "template is doing the work, not the one added")
finally:
    lh._type_cache = (_full_vecs, _full_types)  # restore for any test that runs after this

# ---- 5. RESTORE CONFIRMED -----------------------------------------------------
for m in data["misses"]:
    img = Image.open(os.path.join(FIX, m["file"])).convert("RGB")
    rows = lh.read_hand(img)
    row = rows[m["slot"]] if m["slot"] < len(rows) else {}
    check(f"q{m['q']} {m['file']}: recovers after the bank is restored",
          row.get("type") == m["expected_type"] and (row.get("type_score") or 0) >= lh.MIN_TYPE_SCORE,
          f"type={row.get('type')!r} score={row.get('type_score')}")

print()
if fails:
    print(f"{len(fails)} FAILED: " + ", ".join(fails))
    sys.exit(1)
print("all checks passed")
