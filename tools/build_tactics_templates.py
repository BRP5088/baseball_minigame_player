"""Cut REVEAL-SCALE tactics banners, one template per example, at native size.

WHY A SEPARATE BANK. local_hand.read_tactics_type reads the banner at HAND
geometry and scores 0.37 on a reveal at every scale tried -- the reveal renders
smaller. reveal_cards therefore reads both POWERS and both BONUS digits but not
the KIND, and section 4 says only SWING and PITCH boosts add power, so a +1 of
unknown kind cannot enter a margin. This is the bank that closes it.

WHERE THE MISSING TWO CAME FROM. Over five archived recordings every readable
attached tactics was a POWER SWING or a PITCH FOCUS and there were ZERO Speed
Boosts or Fielding Plays -- those runs were engine-driven, and the engine
attaches a swing boost while batting and holds fielding back until runners are
on. The archive can never supply them. Both arrived in ONE live frame on
2026-09-16: we pitched a FIELDING PLAY and the opponent batted a SPEED BOOST.

CLAUDE.md 30: native size, one template per example, never stretched and never
averaged. The banner animates in, so the same word measures differently frame to
frame; the score is the max over the bank.
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "reveal_tactics_templates.npz")

# (kind, frame, box) -- every box measured by locating the letter blobs, not guessed.
R6 = "test_fixtures/reveal_kind_truth/reveal6"
R1 = "test_fixtures/reveal_kind_truth/reveal"
# A THIRD MATCH (2026-09-17), NOT ONE OF THE TWO ABOVE. I-18(c): all 10 templates
# above were cut from the SAME two archived matches, and scored against the 5
# `live/` single-frame fixtures from this third match the bank never saw, 3 of 5
# abstained under TACTICS_KIND_MIN (0.75) -- the 83a4a73 shape ("the bank had
# never seen it there") rather than a bad gate: right-kind scores of 0.35-0.73,
# wrong-kind scores staying under 0.71, never crossing 0.75 (agent_progress/
# issues/I-18/progress.md). The two boxes below were located by matching the
# EXISTING (weak) template inside the padded zone band, then looked at directly
# (agent_progress/issues/I-18/verify_pitch_tight.png, verify_speed_box2.png)
# before being kept -- both scored 1.000 against themselves after rebuilding,
# which is the expected self-match (CLAUDE.md 10.30) and confirms the box sits
# entirely inside the band tactics_kind_scores() actually searches. The pitch
# box is the TEXT ONLY, not the badge above it -- a first cut included the
# badge and the wreath border (172x57 against the archived pitch_boost's
# 142x27) and that extra context spuriously matched 0.7606 against a held-out
# swing_boost frame, OVER the gate (it did not misread it -- swing_boost still
# won at 0.8742 -- but a wrong-kind score over the gate on ANY held-out frame is
# the thing the gate exists to prevent). Trimmed to the text band (132x27,
# matching the archived shape) the same frame's wrong-kind max drops to 0.6712,
# and the archived 48-frame held-out census (tools/banner_kind_census.py) still
# clears the gate too: wrong-kind MAX 0.741, right-kind min 0.304, unchanged
# from before this bank grew (agent_progress/issues/I-18/progress.md).
#
# A THIRD -- fielding_boost from the same match -- is NOT added, and that is a
# finding, not an oversight. Its card renders in ZONE_HOME, not ZONE_MOUND (so
# "fielding/pitch = mound, swing/speed = home", this file's own WHERE-THE-
# MISSING-TWO-CAME-FROM paragraph and reveal_cards.py's zone-naming comment, is
# not a rule that holds across matches) -- and even in ZONE_HOME the "FIELDING
# PLAY" text sits at y=600-632 while the padded ZONE_HOME band this reader
# searches starts at y=624: only the bottom third of the banner is inside the
# band at all. A template cut there cannot self-match (measured: 0.4664, losing
# to a wrong kind) for the same reason the y=757 speed_boost clip above failed --
# a template missing its letter tops is worse than no template. The root cause
# is that this frame's card sits higher than BANNER_ZONE_PAD reaches, not that
# the bank lacks a fielding_boost example; fixing it means moving the zone or
# the pad, which is reveal_cards' geometry, not this bank, and is out of scope
# here (agent_progress/issues/I-18/progress.md has the crops).
LIVE = "test_fixtures/reveal_kind_truth/live"
CUTS = [
    ("fielding_boost", f"{R6}/f_001503.jpg", (1075, 309, 1194, 340)),
    ("fielding_boost", f"{R6}/f_002645.jpg", (1076, 309, 1194, 339)),
    ("fielding_boost", f"{R6}/f_003571.jpg", (1076, 309, 1194, 339)),
    # y STARTED AT 757 AND CLIPPED THE TOPS OF THE LETTERS. It looked fine in the
    # numbers -- 115x30, the same shape as the others -- and was only obvious when
    # the cut-outs were rendered and looked at. The clipped bank abstained on 9 of
    # 11 held-out speed_boost frames, every one scoring ~0.333.
    ("speed_boost",    f"{R6}/f_001503.jpg", (1089, 748, 1206, 789)),
    ("speed_boost",    f"{R6}/f_002645.jpg", (1090, 748, 1206, 789)),
    ("speed_boost",    f"{R6}/f_003571.jpg", (1090, 748, 1206, 789)),
    ("pitch_boost",    f"{R1}/r_003660.jpg", (1071, 314, 1213, 341)),
    ("pitch_boost",    f"{R1}/r_006285.jpg", (1071, 314, 1213, 341)),
    ("swing_boost",    f"{R1}/r_003660.jpg", (1074, 744, 1192, 772)),
    ("swing_boost",    f"{R1}/r_006285.jpg", (1074, 744, 1192, 772)),
    ("pitch_boost",    f"{LIVE}/pitch_boost_1789941284009861000.jpg", (1063, 325, 1195, 352)),
    ("speed_boost",    f"{LIVE}/speed_boost_1789940135610162000.jpg", (1090, 748, 1225, 780)),
]
MIN_W = 100      # the four banners run 114-142 px; a fragment correlates with anything


def main():
    bank, seen = {}, {}
    for i, (kind, rel, box) in enumerate(CUTS):
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            print(f"MISSING {rel}")
            return 1
        crop = Image.open(p).convert("L").crop(box)
        if crop.width < MIN_W:
            print(f"REFUSED {kind} from {rel}: {crop.width}px, under the {MIN_W}px floor")
            return 1
        bank[f"{kind}__{i}"] = np.asarray(crop, dtype=np.uint8)
        seen[kind] = seen.get(kind, 0) + 1
        print(f"  {kind:16} {os.path.basename(rel):16} {crop.width}x{crop.height}")
    np.savez_compressed(OUT, **bank)
    print(f"\n{len(bank)} templates across {len(seen)} kinds -> {OUT}")
    for k, n in sorted(seen.items()):
        print(f"    {k:16} {n}")
    return 0


if __name__ == "__main__":
    os.environ["BASEBALL_TEST_RUN"] = "1"
    raise SystemExit(main())
