"""Does identify() after the goal leg tell a side-table landing from a dealer-table one?

OPEN-22: the recorded goal leg lands either at the dealer's table or at the
round table beside it. bar_side_table cannot be a node (confusable with
bar_jukebox at ratios 1.0-1.22), but that confusion may itself be the signal:
from the side table identify() names bar_jukebox; from the dealer's table it
names dealer_table or nothing. This tabulates identify() over every goal-leg
landing frame on disk against what is known about the landing. Read-only.

    python -B tools/landing_signature.py
"""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# what is KNOWN about each landing, from the prompt / the frames read by eye
KNOWN = {
    "at_dealer_table_1788787236276.jpg": "dealer (t1: prompt on the bright table)",
    "at_dealer_table_1788788260564.jpg": "side (t3: wrong table by eye)",
    "at_dealer_table_1788790683096.jpg": "dealer (t6: prompt on screen)",
    "at_dealer_table_1788793238379.jpg": "dealer? (t10 postsweep arrival)",
    "pz_w1_x+0.00_y+0.00_h2_1788804269350.jpg": "side (walk 1 by eye)",
    "pz_w2_x+0.00_y+0.00_h2_1788804790255.jpg": "side (walk 2 by eye)",
    "pz_w3_x+0.00_y+0.00_h2_1788805234000.jpg": "dealer (walk 3: prompt 0.05u ahead)",
}


def main():
    os.environ.setdefault("BASEBALL_TEST_RUN", "1")
    from PIL import Image
    import places
    files = sorted(glob.glob("overnight/goal_leg_failframes/at_dealer_table_[0-9]*.jpg")
                   + glob.glob("overnight/goal_extend_failframes/at_dealer_table_[0-9]*.jpg")
                   + glob.glob("overnight/prompt_zone_frames/pz_w[123]_x+0.00_y+0.00_h2_*.jpg"))
    print(f"{'frame':44} {'identify':14} {'score':>6} {'ratio':>6}  known")
    for f in files:
        room, score, margin = places.identify(Image.open(f).convert("RGB"))
        base = os.path.basename(f)
        known = next((v for k, v in KNOWN.items() if base.startswith(k[:30])), "")
        print(f"{base[:44]:44} {str(room):14} {score:6.0f} {margin:6.2f}  {known}", flush=True)


if __name__ == "__main__":
    main()
