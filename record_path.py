"""Record a human walk, then label it automatically.

    python3 record_path.py 90                 # 90 seconds
    python3 record_path.py 90 spawn_to_table  # ...with a name

Recording only WATCHES — it sends no input and never takes focus.

WHAT COMES OUT
--------------
    demos/<name>_<stamp>/
        f_<seconds>.jpg      the frames
        manifest.json        what this recording IS, captured at record time
        timeline.json        per frame: heading, and whether the picture moved
        timeline.txt         the same, readable
        contact.png          every ~2s tiled, labelled with time and heading

WHY THE ANALYSIS IS SEPARATE FROM THE RECORDING
-----------------------------------------------
Decoding a bearing takes ~0.4s. Doing it live would sample a walk twice a
second at best and miss every turn, and the extra load makes the game stutter
for the person playing — the one thing a recording must not do. So frames are
captured fast and cheap, and decoded afterwards.

WHY BOTH HEADING AND MOTION
---------------------------
Heading alone is not enough, and assuming otherwise cost a full rebuild of this
route. A stretch of constant heading can be walking OR standing still, and the
first attempt to replay demo3 read an 11-second segment held at ~88 degrees as
"turn to 88 and stop", when it was actually WALKING EAST for eleven seconds.
The frame-to-frame picture change is what separates the two.
"""

import json
import os
import sys
import time

os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "dummy-record")

TARGET_FPS = 6.0
CONTACT_EVERY_SEC = 2.0
MOVING_DELTA = 6.0        # mean picture change that counts as travelling
STILL_DELTA = 2.0


def analyse(out_dir, log=None):
    """Decode heading + motion for every frame and write the labelled outputs."""
    import glob

    import numpy as np
    from PIL import Image, ImageDraw

    import compass

    if log is None:
        def log(m):
            print(m, flush=True)

    files = sorted(glob.glob(os.path.join(out_dir, "f_*.jpg")))
    rows, prev = [], None
    for i, f in enumerate(files):
        t = float(os.path.basename(f)[2:-4])
        img = Image.open(f)
        small = np.asarray(img.convert("L").resize((160, 90)), dtype=float)
        motion = None if prev is None else float(np.abs(small - prev).mean())
        prev = small
        rows.append({"t": t, "file": os.path.basename(f),
                     "heading": compass.read_bearing(img), "motion": motion})
        if i % 50 == 0:
            log(f"    analysed {i}/{len(files)}")

    json.dump(rows, open(os.path.join(out_dir, "timeline.json"), "w"), indent=1)

    with open(os.path.join(out_dir, "timeline.txt"), "w") as fh:
        fh.write(f"{'time':>7} {'heading':>8} {'motion':>7}  state\n")
        for r in rows:
            h = "--" if r["heading"] is None else f"{r['heading']:8.1f}"
            m = "--" if r["motion"] is None else f"{r['motion']:7.2f}"
            if r["motion"] is None:
                state = ""
            elif r["motion"] >= MOVING_DELTA:
                state = "MOVING"
            elif r["motion"] <= STILL_DELTA:
                state = "still"
            else:
                state = "slow"
            fh.write(f"{r['t']:7.2f} {h} {m}  {state}\n")

    # contact sheet, labelled with time AND heading so a landmark can be placed
    picks, last = [], -99.0
    for r in rows:
        if r["t"] - last >= CONTACT_EVERY_SEC:
            picks.append(r)
            last = r["t"]
    if picks:
        W, H, COLS = 300, 169, 6
        rowsn = (len(picks) + COLS - 1) // COLS
        sheet = Image.new("RGB", (COLS * W, rowsn * (H + 18)), (16, 16, 16))
        d = ImageDraw.Draw(sheet)
        for i, r in enumerate(picks):
            x, y = (i % COLS) * W, (i // COLS) * (H + 18)
            sheet.paste(Image.open(os.path.join(out_dir, r["file"]))
                        .resize((W, H), Image.LANCZOS), (x, y + 18))
            h = "--" if r["heading"] is None else f"{r['heading']:.0f}"
            d.text((x + 4, y + 4), f"{r['t']:.1f}s  {h} deg", fill=(255, 210, 90))
        sheet.save(os.path.join(out_dir, "contact.png"))

    decoded = sum(1 for r in rows if r["heading"] is not None)
    moving = sum(1 for r in rows if r["motion"] and r["motion"] >= MOVING_DELTA)
    log(f"  {len(rows)} frames | heading decoded {decoded} | moving {moving}")
    return rows


if __name__ == "__main__":
    import record_demo

    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    name = sys.argv[2] if len(sys.argv) > 2 else "walk"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = os.path.join("demos", f"{name}_{stamp}")
    os.makedirs(out, exist_ok=True)

    print(f"  recording {secs:.0f}s -> {out}", flush=True)
    print("  walk the route when the countdown ends. Nothing is sent to the game.", flush=True)
    for i in (3, 2, 1):
        print(f"    {i}...", flush=True)
        time.sleep(1)
    print("  GO", flush=True)
    n, fps = record_demo.record(out, seconds=secs, target_fps=TARGET_FPS)
    json.dump({"name": name, "recorded": stamp, "seconds": secs,
               "frames": n, "fps": round(fps, 2),
               "purpose": "human walk to be replayed as a route"},
              open(os.path.join(out, "manifest.json"), "w"), indent=1)
    print(f"  recorded {n} frames at {fps:.1f}fps. analysing...", flush=True)
    analyse(out)
    print(f"\n  done -> {out}/  (timeline.txt, contact.png)", flush=True)
