"""Harvest reveal-scale TACTICS BANNERS from the archive. Read-only.

WHY. reveal_cards reads both powers and both bonus digits, but NOT the tactics
KIND -- and section 4 says only SWING_BOOST and PITCH_BOOST add power, so a +1
of unknown kind cannot enter a margin. local_hand.read_tactics_type scores 0.37
at every scale tried because its templates are cut at HAND geometry, and the
reveal renders smaller. A reveal-scale bank is what closes it.

THE 23 LIVE FRAMES HOLD ONLY TWO OF THE FOUR TYPES (pitch_focus, swing_boost).
The other two have to come from somewhere, and the archive is full of reveals --
found for free, because reveal_banner's PLAY BALL! template marks every one.

WHAT THIS DOES AND DOES NOT DECIDE. It only CUTS crops and says where they came
from. Which type each one IS gets adjudicated BY EYE off a contact sheet, never
by the reader that is about to be built from them -- a bank labelled by its own
output is CLAUDE.md 10.22, and this project has already cut six wrong digit
templates that way, each matching its own source at 1.0000 forever after.
"""
import json
import os
import sys

import cv2
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import reveal_banner as rb
import reveal_cards as rc

STRIDE = 24          # 2.5 Hz; PLAY BALL! holds well over a second
# The banner sits below-left of its badge. Measured on the live reveal: badge
# (1109, 305) with text spanning x[1060,1230] y[315,345].
BANNER_DX = (-80, 130)
BANNER_DY = (6, 46)


def harvest(path, outdir, cap=40):
    os.makedirs(outdir, exist_ok=True)
    cap_v = cv2.VideoCapture(path)
    name = os.path.basename(os.path.dirname(path))
    i, found, rows = 0, 0, []
    while found < cap:
        if not cap_v.grab():
            break
        if i % STRIDE == 0:
            ok, fr = cap_v.retrieve()
            if ok:
                im = Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
                try:
                    label, _d = rb.read_banner(im)
                except Exception:
                    i += 1
                    continue
                if label == "play_ball":
                    for side, zone in (("ours", rc.ZONE_OURS), ("theirs", rc.ZONE_THEIRS)):
                        discs = rc._discs(im, zone)
                        if len(discs) < 2:
                            continue      # no tactics card was played on that side
                        player = max(discs, key=lambda c: c[1])
                        badge = min((c for c in discs if c[1] < player[1] - 20),
                                    key=lambda c: c[1], default=None)
                        if badge is None:
                            continue
                        bx, by = badge[0], badge[1]
                        crop = im.crop((bx + BANNER_DX[0], by + BANNER_DY[0],
                                        bx + BANNER_DX[1], by + BANNER_DY[1]))
                        # IS THIS A BANNER AT ALL? Disc geometry alone picked a
                        # second PLAYER disc as often as a tactics badge -- 88 of
                        # the first 92 crops were card art. A tactics banner is a
                        # DARK BAND WITH BRIGHT TEXT across it, which card art is
                        # not: require both a dark majority and a few per cent of
                        # bright pixels, so neither a blank card back nor a
                        # brightly-lit mouse can pass.
                        import numpy as _np
                        g = _np.asarray(crop.convert("L"), dtype=float)
                        if g.size == 0:
                            continue
                        dark = float((g < 90).mean())
                        text = float((g > 200).mean())
                        if not (dark > 0.35 and 0.03 < text < 0.35):
                            continue
                        fn = f"{name}_{side}_f{i:07d}.png"
                        crop.save(os.path.join(outdir, fn))
                        rows.append({"file": fn, "video": path, "frame": i,
                                     "side": side, "badge": [bx, by], "dark": round(dark,3), "text": round(text,3),
                                     "size": list(crop.size)})
                        found += 1
        i += 1
    cap_v.release()
    print(f"{name}: {found} banner crops from {i} frames", flush=True)
    return rows


if __name__ == "__main__":
    os.environ["BASEBALL_TEST_RUN"] = "1"
    out = sys.argv[-1]
    allrows = []
    for p in sys.argv[1:-1]:
        allrows += harvest(p, out)
    with open(os.path.join(out, "index.json"), "w") as fh:
        json.dump(allrows, fh, indent=1)
    print(f"{len(allrows)} crops -> {out}")
