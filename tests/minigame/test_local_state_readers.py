"""The three local readers for game-state fields the paid vision call supplies.

EACH ABSTAINS RATHER THAN GUESSES. None means ASK THE PAID MODEL: an abstention costs one
API call, a wrong answer plays the wrong card in a $50 match.

THE DISCARD COUNTER IS THE ONE WITH HUMAN TRUTH BEHIND IT, and it is the strongest result
on this project so far. Over 360 turns the local reader and the paid model disagreed 155
times. The user adjudicated eight of those by eye, chosen to span every disagreement shape:

    LOCAL 8 of 8 correct        PAID 0 of 8 correct

The paid model answers 2 on 286 of 360 turns -- a default, not a reading -- and returned an
impossible 3 in a live run (orchestrator clamps it). The user named the mechanism: the fat
middle of the S in "DISCARDS" reads as an extra dot. The pixel scan supports it and also
shows why the LOCAL reader is immune -- it samples two fixed anchors at x=215 and x=241,
while everything left of x=202, where the text sits, reads brightness 194-197 and is never
looked at.

So on this field the paid model is not merely replaceable. It is WRONG, and the local
reader is the correction.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import numpy as np                                                      # noqa: E402
from PIL import Image                                                   # noqa: E402

import local_state as ls                                                # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# ---- 1. THE DISCARD COUNTER, against the user's own eyes -----------------------------
FIX = os.path.join(_ROOT, "test_fixtures", "discards")
truth = json.load(open(os.path.join(FIX, "truth.json")))
right = wrong = abstained = 0
for b in truth["boards"]:
    img = Image.open(os.path.join(FIX, b["file"])).convert("RGB")
    got = ls.read_discards_left(img)
    if got is None:
        abstained += 1
    elif got == b["discards_left"]:
        right += 1
    else:
        wrong += 1
    check(f"{b['file']}: reads {b['discards_left']}", got == b["discards_left"],
          f"got {got}, paid model said {b['paid_said']}")
check("the fixtures span every disagreement shape", len(truth["boards"]) >= 8,
      f"{len(truth['boards'])} boards")
check("and NONE is wrong", wrong == 0, f"{wrong} wrong")

# ---- 2. IT MUST BE INCAPABLE OF AN IMPOSSIBLE ANSWER. A match allows exactly two
# discards. The paid model returned 3 in a live run; this reader counts two dots and
# cannot exceed them by construction, which is the point.
for b in truth["boards"]:
    got = ls.read_discards_left(Image.open(os.path.join(FIX, b["file"])).convert("RGB"))
    if got is not None:
        check(f"{b['file']}: answer is in 0..2", 0 <= got <= 2, str(got))

# ---- 3. NOISE ABSTAINS. A reader that answers anything answers wrongly on a bad frame.
rng = np.random.RandomState(3)
noise = Image.fromarray(rng.randint(0, 255, (248, 359), dtype=np.uint8)).convert("RGB")
check("noise abstains on the discard counter", ls.read_discards_left(noise) is None)
ph, _ = ls.read_phase(Image.fromarray(
    rng.randint(0, 255, (307, 979), dtype=np.uint8)).convert("RGB"))
check("noise abstains on phase", ph is None, str(ph))

# ---- 4. THE THREE READERS EXIST AND RETURN THE SHAPES THE CALLER EXPECTS -------------
check("read_discards_left is exported", callable(ls.read_discards_left))
check("read_phase is exported", callable(ls.read_phase))
check("read_runners is exported", callable(ls.read_runners))
blank = Image.new("RGB", (140, 180), (30, 30, 30))
out = ls.read_runners(blank, blank, blank)
check("read_runners returns bases and a count",
      isinstance(out, dict) and "bases" in out and "count" in out, str(type(out)))
check("and a count with a hole in it is None, never a partial number",
      out["count"] is None or isinstance(out["count"], int))

# ---- 5. THE RUNNERS READER, against the user's own eyes ------------------------------
# Every third-base crop the reader calls occupied was shown to the user, who confirmed all
# twenty hold a runner: 20 of 20, ZERO false positives. On a separate 8-row sheet third was
# empty every time and the reader agreed on all 8 -- 28 judgements, 28 agreements. Second
# base: 4 of 4. First base: of 4 occupied it read 1 and ABSTAINED on 3, never wrong, and the
# user diagnosed the cause by eye ("the crop box should be shifted up"), fixed in patch83.
RFIX = os.path.join(_ROOT, "test_fixtures", "runners")
rtruth = json.load(open(os.path.join(RFIX, "truth.json")))
occ_right = occ_wrong = occ_abst = 0
for c in rtruth["crops"]:
    # read_base takes the BASE NAME now: the adopted reader has per-base coin templates
    # and per-base geometry, so it cannot infer which base a crop came from.
    b = ls.read_base(Image.open(os.path.join(RFIX, c["file"])).convert("RGB"), c["base"])
    if b["occupied"] is None:
        occ_abst += 1
    elif b["occupied"] == c["occupied"]:
        occ_right += 1
    else:
        occ_wrong += 1
check("every user-confirmed third-base runner is still read as occupied",
      occ_wrong == 0 and occ_abst == 0,
      f"{occ_right} right, {occ_wrong} WRONG, {occ_abst} abstained of {len(rtruth['crops'])}")
check("and there are enough of them to mean something", len(rtruth["crops"]) >= 20,
      f"{len(rtruth['crops'])} crops")

# The base crop boxes: first and third were cut too low, measured at y 0.299..0.494 for the
# card against a box starting at 0.320. second_base has a different placement and reads
# correctly, so it is deliberately NOT aligned with them.
import orchestrator                                                     # noqa: E402
FR = orchestrator.GAMEPLAY_REGIONS_FRAC
check("first and third base share the corrected vertical box",
      FR["first_base"][1] == FR["third_base"][1] == 0.290
      and FR["first_base"][3] == FR["third_base"][3] == 0.500,
      f"third {FR['third_base']}, first {FR['first_base']}")
check("the box now starts ABOVE the card's measured top (0.299)",
      FR["first_base"][1] < 0.299, str(FR["first_base"][1]))
check("second_base is left alone -- it is the one that reads correctly",
      FR["second_base"] == (0.430, 0.080, 0.580, 0.320), str(FR["second_base"]))

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
