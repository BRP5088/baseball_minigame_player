"""WATCH THE WHOLE READ, live, beside chiaki -- everything a crawl step decides on.

    .venv/bin/python -B tools/state_viewer.py              the frame + every region + the read
    .venv/bin/python -B tools/state_viewer.py --hand       just the hand, bigger
    .venv/bin/python -B tools/state_viewer.py --scale 0.7

PRESSES NOTHING. One capture and one draw per tick, the same grab the poll loop already
does, so it is safe to leave up during a live match. The cheap reads (hand, cursor,
selection) run every tick; the OCR ones (scoreboard, runners, phase) run once a second,
because at 4 Hz they are the only thing here heavy enough to matter (CLAUDE.md 10.13).

Colour, on the hand: GREEN the card the reader calls the cursor, RED a selected card,
YELLOW neither. A box is the window cursor_glow actually sampled, not a guess at one --
that distinction is what found both of 2026-09-11's defects.
"""
import os, sys, argparse, time, tkinter as tk
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw, ImageTk
import orchestrator as o, local_hand as lh, local_state as ls

ap = argparse.ArgumentParser()
ap.add_argument("--hand", action="store_true", help="hand crop only")
ap.add_argument("--hz", type=float, default=4.0)
ap.add_argument("--scale", type=float, default=0.0, help="0 = fit the window")
A = ap.parse_args()

CUR, SEL, BOX, REG = "#00ff66", "#ff3b30", "#ffcc00", "#4da3ff"
root = tk.Tk()
root.title("state — what the crawl reads")
root.attributes("-topmost", True)
lbl = tk.Label(root, bg="black"); lbl.pack()
txt = tk.Label(root, font=("Menlo", 12), anchor="w", justify="left")
txt.pack(fill="x")
S = {"img": None, "slow": {}, "t": 0.0}


def slow_read(frame, crops):
    """The OCR-backed fields. Once a second, not every tick."""
    out = {}
    try:
        out["score"] = o.ocr_scoreboard(crops["scoreboard"])
    except Exception as e:
        out["score"] = f"err {type(e).__name__}"
    try:
        r = ls.read_runners(crops["third_base"], crops["second_base"], crops["first_base"])
        out["runners"] = (r["count"], [b for b, v in r["bases"].items() if v["occupied"]])
    except Exception as e:
        out["runners"] = f"err {type(e).__name__}"
    try:
        res = ls.read_result(frame)
        out["result"] = res.get("outcome") if res.get("is_result") else None
    except Exception as e:
        out["result"] = f"err {type(e).__name__}"
    return out


def tick():
    try:
        frame = o._fast_grab()
        crops = dict(o.crop_gameplay_regions(frame))
        hand = crops.get("hand")
        if time.time() - S["t"] > 1.0:
            S["slow"] = slow_read(frame, crops); S["t"] = time.time()
        rows, glow, boxes, sel, cur, phase = [], [], [], [], None, None
        if hand is not None:
            rows = lh.read_hand(hand)
            boxes = []
            _, glow, _ = lh.cursor_glow(hand, rows, _boxes=boxes)
            sc = hand.width / lh.ANCHOR_W
            sel = lh.selected_cards(rows, sc)
            cur = lh.cursor_slot(glow, sel)
            try:
                phase = ls.read_phase(hand)[0]
            except Exception:
                phase = None

        canvas = (hand if (A.hand and hand is not None) else frame).convert("RGB")
        d = ImageDraw.Draw(canvas)
        ox = oy = 0
        if not A.hand:
            for name, frac in o.GAMEPLAY_REGIONS_FRAC.items():
                x0, y0 = int(frame.width * frac[0]), int(frame.height * frac[1])
                x1, y1 = int(frame.width * frac[2]), int(frame.height * frac[3])
                d.rectangle((x0, y0, x1, y1), outline=REG, width=2)
                d.text((x0 + 3, y0 + 2), name, fill=REG)
            f = o.GAMEPLAY_REGIONS_FRAC["hand"]
            ox, oy = int(frame.width * f[0]), int(frame.height * f[1])
        for i, b in enumerate(boxes):
            if b is None:
                continue
            col = CUR if i == cur else (SEL if i in sel else BOX)
            d.rectangle((b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy), outline=col, width=3)
            d.text((b[0] + ox, max(0, b[1] + oy - 14)),
                   f"{i}:{glow[i]}" + ("  CURSOR" if i == cur else "") + ("  SEL" if i in sel else ""),
                   fill=col)

        k = A.scale or min(1.0, 1500 / canvas.width)
        if k != 1.0:
            canvas = canvas.resize((int(canvas.width * k), int(canvas.height * k)))
        S["img"] = ImageTk.PhotoImage(canvas)       # held, or Tk drops it
        lbl.config(image=S["img"])
        sl = S["slow"]
        txt.config(text=(
            f"phase {phase}   cursor {cur}   selected {sel}   rows {len(rows)}\n"
            f"glow {glow}\n"
            f"cards {[(r.get('digit'), r.get('kind')) for r in rows]}\n"
            f"score {sl.get('score')}   runners {sl.get('runners')}   result {sl.get('result')}"))
    except Exception as e:
        txt.config(text=f"{type(e).__name__}: {e}")
    root.after(int(1000 / A.hz), tick)


root.after(50, tick)
root.mainloop()
