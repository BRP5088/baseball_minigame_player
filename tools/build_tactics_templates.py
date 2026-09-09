"""Build the TACTICS TYPE template bank, labelled by the paid vision model.

WHY A SECOND BANK. The digit reader answers "what number is on this card"; it cannot answer
"what KIND of card is this", and that is the question that decides play. CLAUDE.md section 4:
only SWING_BOOST and PITCH_BOOST add power, while speed and fielding boosts carry a nonzero
bonus that adds NONE. So a speed boost read as a swing boost plays the wrong card for $50.

WHAT IS BEING MATCHED. Not the disc -- the BANNER. Each tactics card carries its name across
the middle in white on a dark band: FIELDING PLAY, PITCH FOCUS, SPEED BOOST, POWER SWING.
It is a fixed game asset, one font, one size, so it templates exactly like the digits do.

MEASURED, leave-one-HAND-out over 83 located tactics cards in 30 distinct hands (a hand
sampled twice is nearly the same picture, so scoring across the pair would measure JPEG,
not recognition):

    top score   RIGHT p05 0.773   WRONG MAX 0.761      the two populations do not overlap
    accuracy    73 of 83 correct before the gate; every one of the 10 errors scores below
                the worst right answer, so the gate rejects all ten

    .venv/bin/python -B tools/build_tactics_templates.py
"""
import json
import os
import sys
from collections import Counter

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import local_hand as lh                                                 # noqa: E402

# NO os.environ HERE. A tools/ module that sets BASEBALL_TEST_RUN at IMPORT time
# once switched stick injection off inside a live harness and cost three runs
# (CLAUDE.md section 5); tests/harness/test_no_import_time_test_run_flag.py scans
# for exactly that and caught this file. This reader needs no flag: it opens
# saved images and touches no input path.


def main():
    CORPUS = "overnight/local_hand/agreement.jsonl"
    OUT = "tactics_templates.npz"

    groups, items, gid, prev = {}, [], -1, None
    # A LABEL THE LOCAL READER CONFIDENTLY CONTRADICTS IS NOT A LABEL.
    # The paid model read three 6s as 5s on 2026-09-09 (confirmed by the user against the
    # frame), and a template cut under that label matches its own source crop at 1.0000 and
    # reads it wrong forever. This does not adjudicate -- it SKIPS, and it counts.
    CONFIDENT_DISAGREE = 0.95
    skipped = []

    def _contradicted(rows, cards):
        """Slot indices where local names a digit >= CONFIDENT_DISAGREE that paid denies."""
        out = set()
        for i, (x, c) in enumerate(zip(rows, cards)):
            if c.get("kind") != "player" or x.get("digit") is None:
                continue
            if x.get("score", 0.0) >= CONFIDENT_DISAGREE and \
                    str(x["digit"]) != str(c.get("power")):
                out.add(i)
        return out

    for line in open(CORPUS):
        r = json.loads(line)
        p = os.path.join(os.path.dirname(CORPUS), r["crop"])
        if not os.path.exists(p):
            continue
        key = tuple((c["kind"], c["power"], c["bonus"], c["type"]) for c in r["vision"])
        if key != prev:
            gid += 1
            prev = key
        img = Image.open(p).convert("RGB")
        rows = lh.read_hand(img)
        # Only a hand whose POSITIONS agree with the paid model can label a slot. This is
        # CLAUDE.md 10.22: a matching count is not correspondence, so the kind pattern must
        # match too or the label belongs to a different card.
        if len(rows) != len(r["vision"]):
            continue
        if [x["kind"] for x in rows] != [c["kind"] for c in r["vision"]]:
            continue
        bad = _contradicted(rows, r["vision"])
        if bad:
            skipped.append((r.get("crop"), sorted(bad)))
            continue
        for i, (x, c) in enumerate(zip(rows, r["vision"])):
            if c["kind"] == "tactics" and c.get("type"):
                v = lh.tactics_banner_vector(img, i)
                if v is not None:
                    items.append({"v": v, "type": c["type"], "group": gid})

    # One template per (hand, type): a hand sampled ten times must not out-vote nine others.
    seen, vecs, labs = set(), [], []
    for it in items:
        k = (it["group"], it["type"])
        if k in seen:
            continue
        seen.add(k)
        vecs.append(it["v"])
        labs.append(it["type"])
    np.savez_compressed(OUT, vectors=np.stack(vecs), types=np.array(labs))
    if skipped:
        print(f"SKIPPED {len(skipped)} hand(s) whose paid label the local reader "
              f"confidently contradicts -- neither label is trusted:")
        for crop, slots in skipped:
            print(f"    {crop}  slots {slots}")
    print(f"{len(items)} located tactics cards in {len({i['group'] for i in items})} hands")
    print(f"{len(labs)} templates written to {OUT}: {dict(sorted(Counter(labs).items()))}")

if __name__ == "__main__":
    main()
