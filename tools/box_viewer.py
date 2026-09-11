"""WATCH WHAT THE HAND READER IS LOOKING AT, live, in a window beside chiaki.

    .venv/bin/python -B tools/box_viewer.py            the hand crop, ~4 Hz
    .venv/bin/python -B tools/box_viewer.py --full     the whole frame

Draws each card's glow window with its reading, marks the card the reader calls the
CURSOR and the ones it calls SELECTED, and prints the same line the ladder would see.
It PRESSES NOTHING -- one capture and one draw per tick, the same grab the poll loop
already does, so it is safe to leave up during a live match.

Why it exists: on 2026-09-11 a turn refused with glow [5.2, 6.8, 0.0, 0.2, 8.1] and no
way to tell from the numbers alone that the box for slot 1 was sitting in the sky. One
look at the boxes drawn on the frame settled it in a minute (CLAUDE.md 10.23).
"""
import os, sys, argparse, tkinter as tk
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw, ImageTk
import orchestrator as o, local_hand as lh

ap = argparse.ArgumentParser()
ap.add_argument("--full", action="store_true", help="draw the whole frame, not the hand crop")
ap.add_argument("--hz", type=float, default=4.0)
ap.add_argument("--scale", type=float, default=1.0)
A = ap.parse_args()

CUR, SEL, BOX = "#00ff00", "#ff3b30", "#ffcc00"
root = tk.Tk()
root.title("hand reader — boxes")
root.attributes("-topmost", True)
lbl = tk.Label(root, bg="black"); lbl.pack()
txt = tk.Label(root, font=("Menlo", 13), anchor="w", justify="left")
txt.pack(fill="x")
state = {"img": None}

def tick():
    try:
        frame = o._fast_grab()
        crops = dict(o.crop_gameplay_regions(frame))
        hand = crops.get("hand")
        if hand is None:
            txt.config(text="no hand region in this frame")
            root.after(int(1000 / A.hz), tick); return
        rows = lh.read_hand(hand)
        boxes = []
        _, glow, _ = lh.cursor_glow(hand, rows, _boxes=boxes)
        sc = hand.width / lh.ANCHOR_W
        sel = lh.selected_cards(rows, sc)
        cur = lh.cursor_slot(glow, sel)
        canvas = (frame if A.full else hand).convert("RGB")
        ox = oy = 0
        if A.full:      # the hand crop's own offset inside the frame
            fx0, fy0, _, _ = o.GAMEPLAY_REGIONS_FRAC["hand"]
            ox, oy = int(frame.width * fx0), int(frame.height * fy0)
        d = ImageDraw.Draw(canvas)
        for i, b in enumerate(boxes):
            if b is None: continue
            x0, y0, x1, y1 = b[0] + ox, b[1] + oy, b[2] + ox, b[3] + oy
            colour = CUR if i == cur else (SEL if i in sel else BOX)
            d.rectangle((x0, y0, x1, y1), outline=colour, width=3)
            tag = f"{i}:{glow[i]}" + ("  CURSOR" if i == cur else "") + ("  SEL" if i in sel else "")
            d.text((x0, max(0, y0 - 14)), tag, fill=colour)
        if A.scale != 1.0:
            canvas = canvas.resize((int(canvas.width * A.scale), int(canvas.height * A.scale)))
        state["img"] = ImageTk.PhotoImage(canvas)       # held, or Tk drops it
        lbl.config(image=state["img"])
        txt.config(text=f"glow {glow}   cursor {cur}   selected {sel}   "
                        f"digits {[r.get('digit') for r in rows]}")
    except Exception as e:
        txt.config(text=f"{type(e).__name__}: {e}")
    root.after(int(1000 / A.hz), tick)

root.after(50, tick)
root.mainloop()
