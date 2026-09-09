"""Build the digit template set, with EVERY LABEL VERIFIED rather than read off a sheet.

WHY THIS EXISTS IN THIS FORM. The first large template set was labelled by looking at
cluster contact sheets, and five of the twenty-eight labels were wrong. That is not a
careless reading; a 5 and an 8 at 24x24, cut from a fanned card, look alike enough that a
glance gets it wrong at a rate of about one cluster in six. The cost is not a bad sheet --
it is a WRONG TEMPLATE, which then reads a real 5 as an 8 with a score of 0.99 and no
signal anywhere that anything is wrong. Measured: templates from those five clusters
produced 6 disagreements against the paid model where the smaller hand-labelled set had 0.

So labels come from the paid vision model instead, in two steps:

  SEED   Every digit in the live corpus hands where the finder's card count matches the
         paid model's exactly. Position aligns them, so each patch carries a label nobody
         eyeballed. This is small (tens of patches) and correct.
  GROW   Every archive cluster is classified BY THE SEED SET. A cluster is admitted only
         if its members agree with each other and clear a margin over the runner-up digit.
         A cluster that cannot be classified confidently is DROPPED, not guessed.

That inverts the previous flow: the human-labelled part is now the part with truth behind
it, and the large unlabelled archive inherits labels rather than defining them.

    .venv/bin/python -B agent_progress/bakeoff/build_templates.py
"""
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import circle_finder as cf                                              # noqa: E402
import local_hand                                                       # noqa: E402

# The corpus and clustered patches live under agent_progress/, which is gitignored and
# disposable. If it is gone, rebuild it with mine_recording.py + cluster_digits.py; the
# METHOD -- seed from the paid model, grow by inheritance -- is what this file preserves.
BO = "agent_progress/bakeoff"
SIDE = 24
# A cluster is admitted only if the seed set calls it the same digit this often. Below
# this the cluster is mixed or is something the seeds have never seen, and either way a
# template cut from it is a liability.
CLUSTER_AGREE = 0.80
CLUSTER_MIN_SCORE = 0.75      # the seed match must actually be close, not merely best
PER_DIGIT_CAP = 200           # 2000 templates cost 0.087 ms for a hand; the cap is taste


def vec(img_or_path, box=None):
    im = Image.open(img_or_path) if isinstance(img_or_path, str) else img_or_path
    if box:
        im = im.crop(box)
    a = np.asarray(im.convert("L").resize((SIDE, SIDE), Image.LANCZOS),
                   dtype=np.float32).ravel()
    a = a - a.mean()
    n = np.linalg.norm(a)
    return None if n < 1e-6 else a / n


# ---- SEED: labels straight off the paid model --------------------------------------
seeds, seed_lab = [], []
hands = [h for h in json.load(open(f"{BO}/corpus.json"))["hands"] if h["paid_api_answer"]]
used = 0
for h in hands:
    img = Image.open(os.path.join(BO, h["hand_crop"])).convert("RGB")
    paid = [str(c.get("power") if c.get("kind") == "player" else c.get("bonus"))
            for c in h["paid_api_answer"]]
    # read_hand's own ordering, so a tactics card occupies its position and the rest
    # line up with the paid list. Only an exact count is trusted -- a hand where the
    # finder missed a card would shift every label by one.
    rows = local_hand.read_hand(img)
    if len(rows) != len(paid):
        continue
    used += 1
    circles = {c[0]: c for c in cf.find_circles(img)}
    for row, truth in zip(rows, paid):
        if row["kind"] != "player" or row["x"] not in circles:
            continue
        c = circles[row["x"]]
        rr = int(c[2] * 1.05)
        v = vec(img, (max(0, c[0] - rr), max(0, c[1] - rr),
                      min(img.width, c[0] + rr), min(img.height, c[1] + rr)))
        if v is not None:
            seeds.append(v)
            seed_lab.append(truth)
S = np.stack(seeds)
print(f"SEED  {len(seeds)} digits from {used} of {len(hands)} hands, labelled by the "
      f"paid model: {dict(sorted(Counter(seed_lab).items()))}")

# ---- GROW: the archive inherits labels from the seeds --------------------------------
vectors, digits = list(seeds), list(seed_lab)
report = []
for name, folder, cl, ix in (("archive", f"{BO}/big", f"{BO}/clusters.json", f"{BO}/big_index.json"),
                             ("recording", f"{BO}/mined", f"{BO}/mined2_clusters.json",
                              f"{BO}/mined2_index.json")):
    index = {r["patch"]: r for r in json.load(open(ix))}
    for c in json.load(open(cl)):
        members = [p for p in c["members"] if os.path.exists(os.path.join(folder, p))]
        if len(members) < 8:
            continue
        vs, srcs = [], []
        for p in members:
            v = vec(os.path.join(folder, p))
            if v is not None:
                vs.append(v)
                srcs.append(index.get(p, {}).get("src"))
        if not vs:
            continue
        M = np.stack(vs) @ S.T
        best = M.argmax(axis=1)
        votes = Counter(seed_lab[k] for k in best)
        lab, n = votes.most_common(1)[0]
        frac = n / len(vs)
        close = float(np.median(M.max(axis=1)))
        ok = frac >= CLUSTER_AGREE and close >= CLUSTER_MIN_SCORE
        report.append((name, c["cluster"], len(vs), lab, round(frac, 2), round(close, 2), ok))
        if not ok:
            continue
        seen = set()
        for v, src, k in zip(vs, srcs, best):
            if Counter(digits)[lab] >= PER_DIGIT_CAP:
                break
            if seed_lab[k] != lab or src in seen:      # one per source frame, and only
                continue                                # members that voted with the label
            seen.add(src)
            vectors.append(v)
            digits.append(lab)

print("\nCLUSTERS, label inherited from the seeds:")
for name, cid, n, lab, frac, close, ok in report:
    print(f"  {name:9} #{cid:<3} n={n:<4} -> {lab}  agree {frac:.2f}  score {close:.2f}"
          f"   {'admitted' if ok else 'DROPPED'}")

np.savez_compressed("digit_templates.npz", vectors=np.stack(vectors),
                    digits=np.array(digits))
print(f"\n{len(digits)} templates: {dict(sorted(Counter(digits).items()))}")
