"""Cut the reveal-banner templates at NATIVE size, one per example.

CLAUDE.md 30, learned building the WINNER/LOSER reader and paid for twice:
  * STRETCHING destroys the discrimination. HOME RUN! is 328 px wide and
    PLAY BALL! is 578; resized to one box they become the same shape, and after
    TM_CCOEFF_NORMED normalises brightness away there is almost nothing left to
    tell apart. It also means the template no longer has the SIZE of the thing
    on screen, so the search is looking for something that is not there.
  * AVERAGING blurs two different things into one. The banner animates in, so
    the same word measures differently frame to frame. Each example is its own
    template; the score is the max over the bank.

A FRAGMENT IS NOT A WORD. The animation's tail reads "RUN!" alone at 132x44 and
its head reads "HOME" behind a ball graphic. A tiny template correlates with
anything -- on the result reader a 14x39 crop made a turn frame with no banner
read DRAW at 0.935 -- so only the full settled words are banked, and the floor
on template width is recorded here rather than discovered later.
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "test_fixtures/reveal_kind_truth/reveal")
OUT = os.path.join(ROOT, "reveal_banner_templates.npz")

# (label, source frame, bbox) -- measured by locating the letter blobs, not guessed.
CUTS = [
    ("home_run",  "r_004785.jpg", (797, 511, 1125, 558)),
    ("play_ball", "r_001099.jpg", (672, 507, 1250, 569)),
    ("play_ball", "r_001738.jpg", (671, 508, 1249, 570)),
]
MIN_W = 300      # HOME RUN! is 328 and PLAY BALL! is 578; the RUN! fragment is 132


def main():
    bank = {}
    for i, (label, fname, box) in enumerate(CUTS):
        p = os.path.join(SRC, fname)
        if not os.path.exists(p):
            print(f"MISSING {p}"); return 1
        crop = Image.open(p).convert("L").crop(box)
        if crop.width < MIN_W:
            print(f"REFUSED {label} from {fname}: {crop.width}px wide, under the "
                  f"{MIN_W}px floor -- a fragment correlates with anything")
            return 1
        bank[f"{label}__{i}"] = np.asarray(crop, dtype=np.uint8)
        print(f"  {label:10} {fname}  {crop.width}x{crop.height}")
    np.savez_compressed(OUT, **bank)
    print(f"\n{len(bank)} templates -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
