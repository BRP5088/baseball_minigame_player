"""The local hand reader must read the digits it claims to, and MUST NEVER GUESS.

WHY THE SECOND HALF MATTERS MORE THAN THE FIRST. This reader exists to skip a paid
vision call, and its output selects which card gets played for $50. A reader that
abstains costs one API call; a reader that returns a confident wrong digit plays the
wrong card and nothing anywhere reports an error. So the abstention behaviour is
guarded harder than the accuracy: every check below that fires on a wrong answer is
worth more than the one that fires on a missing answer.

Labels come from the paid vision model, recorded in expected.json beside the fixtures.
They are not read off a contact sheet -- five of twenty-eight cluster labels read that
way were wrong, and a wrong template reads a real 5 as an 8 at score 0.99.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import numpy as np                                                      # noqa: E402
from PIL import Image                                                   # noqa: E402

import local_hand                                                       # noqa: E402

FIX = os.path.join(_ROOT, "test_fixtures", "hand_digits")
fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


expected = json.load(open(os.path.join(FIX, "expected.json")))
check("fixtures present", len(expected) >= 3, f"{len(expected)} hands")

# ---- 1. it reads what the paid model read ------------------------------------------
for fname, meta in sorted(expected.items()):
    img = Image.open(os.path.join(FIX, fname)).convert("RGB")
    rows = local_hand.read_hand(img)
    got = [("?" if r["digit"] is None and r["kind"] == "player" else
            ("?" if r["kind"] == "tactics" else r["digit"])) for r in rows]
    check(f"{fname}: reads {' '.join(meta['expected_local'])}",
          got == meta["expected_local"], f"got {' '.join(got)}")

    # ---- 2. and NEVER contradicts the paid model on a position it does read --------
    if len(rows) == len(meta["paid"]):
        wrong = [(i, r["digit"], p.get("power"))
                 for i, (r, p) in enumerate(zip(rows, meta["paid"]))
                 if r["digit"] is not None and p.get("kind") == "player"
                 and str(p.get("power")) != str(r["digit"])]
        check(f"{fname}: no digit contradicts vision", not wrong, str(wrong))

# ---- 3. pure noise must abstain, not produce a digit --------------------------------
# The literal seed keeps this reproducible; a reader that guesses fails here loudly.
rng = np.random.RandomState(7)
noise = Image.fromarray(rng.randint(0, 255, (40, 40), dtype=np.uint8)).convert("RGB")
d, s = local_hand.read_digit(noise, (20, 20, 18))
check("noise abstains", d is None, f"read {d!r} at {s:.3f}")

# ---- 4. a flat patch carries no signal at all and must abstain ----------------------
flat = Image.new("RGB", (40, 40), (255, 255, 255))
d, s = local_hand.read_digit(flat, (20, 20, 18))
check("flat white abstains", d is None, f"read {d!r} at {s:.3f}")

# ---- 5. THE GATE IS PINNED AS A LITERAL, not read from the module ------------------
# Asserting `score >= local_hand.MIN_SCORE` would rise with the constant and pass
# forever (CLAUDE.md 10.11). The value below is the measured separation: real digits
# score 0.996 and above, the card elements the finder still emits top out at 0.521.
check("MIN_SCORE is 0.80", local_hand.MIN_SCORE == 0.80, str(local_hand.MIN_SCORE))
check("MIN_SCORE sits between the two measured populations",
      0.521 < local_hand.MIN_SCORE < 0.996)

# ---- 6. every template is labelled with a digit the game can actually show ---------
vecs, digits = local_hand._templates()
check("templates are unit vectors",
      bool(np.allclose(np.linalg.norm(vecs, axis=1), 1.0, atol=1e-4)))
check("every template label is a single digit",
      all(len(d) == 1 and d.isdigit() for d in digits),
      str(sorted(set(digits))))
check("templates and labels are the same length", len(vecs) == len(digits))

# ---- 7. the recorder APPENDS. A truncating write loses a whole session -------------
import tempfile                                                         # noqa: E402
import orchestrator                                                     # noqa: E402

tmp = tempfile.mkdtemp(prefix=f"lh_{os.getpid()}_")
saved = orchestrator.LOCAL_HAND_DIR
try:
    orchestrator.LOCAL_HAND_DIR = tmp
    small = Image.new("RGB", (8, 8), (0, 0, 0))
    for _ in range(3):
        orchestrator.record_local_hand(small, [], [])
    lines = open(os.path.join(tmp, "agreement.jsonl")).read().strip().splitlines()
    check("recorder appends rather than truncating", len(lines) == 3, f"{len(lines)} lines")
    check("recorder writes one crop per call",
          len([f for f in os.listdir(tmp) if f.endswith(".png")]) == 3)
    # It must never raise into the turn loop, whatever it is handed.
    orchestrator.record_local_hand(None, None, None)
    check("recorder swallows its own failures", True)
finally:
    orchestrator.LOCAL_HAND_DIR = saved
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
