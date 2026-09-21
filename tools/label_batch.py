"""A BLIND census of the cursor and selection readers, for the user to label.

WHY BLIND. Every earlier sweep placed the cursor with the VERIFIED walk -- which uses the
detector under test -- so the "known" position was partly the detector's own claim. This
presses a random number of moves in a random direction and never consults the reader to
decide where the cursor is. The reader's answers are written to a separate file that the
sheet does not show, so the labels cannot be anchored on them (CLAUDE.md 31: a census
labelled by the detector under test is worthless).

    .venv/bin/python -B tools/label_batch.py [n]

Writes overnight/crawl/labels/<stamp>/  with f00.png.. , SHEET.png and answers.json.
Label the sheet, then score with tools/label_score.py <dir> "<labels>".

Only move_left / move_right / select_card are pressed. select_card TOGGLES, so the run
can leave cards selected -- it reports what it believes is selected at the end, and the
next batch starts from wherever this one left off, which is itself worth covering.
"""
import os, sys, time, json, random, datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import orchestrator as o
import local_hand as lh
import input_controller as ic

# THIS USED TO `os.environ.pop("BASEBALL_TEST_RUN", None)` AT IMPORT, unconditionally --
# CLAUDE.md 10.1's guard-that-disables-itself, the same defect fixed in crawl_sheet.py.
# It never touches the flag now; the refusal sits at main(), before the first live
# press or capture, and importing this module changes nothing about the environment.
LABEL_BATCH_DRIVE_IN_TESTS = False


def _refuse_if_test_run():
    if os.environ.get("BASEBALL_TEST_RUN") and not LABEL_BATCH_DRIVE_IN_TESTS:
        raise RuntimeError(
            "REFUSING: BASEBALL_TEST_RUN is set. This tool presses move_left/"
            "move_right/select_card at a real console and must never run under the "
            "offline flag -- see CLAUDE.md §5. A test exercising this module's own "
            "logic sets tools.label_batch.LABEL_BATCH_DRIVE_IN_TESTS = True and stubs "
            "input_controller.press / orchestrator._fast_grab directly.")


N = OUT = None   # set inside main(); module-level so grab() can see them via globals


def grab(tag=None):
    img = o._fast_grab()
    hand = dict(o.crop_gameplay_regions(img)).get("hand")
    if hand is not None and tag:
        hand.save(os.path.join(OUT, f"{tag}.png"))
    return hand


def reader_says(hand):
    """What the detector thinks -- RECORDED, never shown, never used to steer."""
    if hand is None:
        return {"rows": 0}
    rows = lh.read_hand(hand)
    sc = hand.width / lh.ANCHOR_W
    idx, glow, _ = lh.cursor_glow(hand, rows)
    return {"rows": len(rows), "cursor": idx, "glow": glow,
            "selected": lh.selected_cards(rows, sc),
            "digits": [r.get("digit") for r in rows],
            "kinds": [r.get("kind") for r in rows],
            "y": [r.get("y") for r in rows]}


def main():
    _refuse_if_test_run()
    global N, OUT
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    OUT = os.path.join(_ROOT, "overnight", "crawl", "labels",
                       datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(OUT, exist_ok=True)

    hand = grab()
    if hand is None or len(lh.read_hand(hand)) != 5:
        print("not a readable hand on screen — start from a turn with five cards")
        sys.exit(1)

    answers, frames = [], []
    for k in range(N):
        # BLIND AND UNIFORM. A random walk was the first version and it is BIASED: presses
        # past the ends are CLAMPED, so the cursor piles up against slot 0 and slot 4 and the
        # middle is barely sampled. Batch 1 never once landed on slot 0 or 1 in twelve frames,
        # which is exactly why it scored 12/12 -- it never tested the slot that fails.
        # So: home hard to the left edge (more presses than the hand is wide, which lands on
        # slot 0 from ANY start without asking the reader), then a uniform number of rights.
        for _ in range(ic.MAX_HAND_SIZE + 2):
            ic.press("move_left")
            time.sleep(ic.MOVE_SETTLE_SEC)
        for _ in range(random.randint(0, ic.MAX_HAND_SIZE - 1)):
            ic.press("move_right")
            time.sleep(ic.MOVE_SETTLE_SEC)
        if random.random() < 0.45:                 # sometimes toggle a selection
            ic.press("select_card")
            time.sleep(ic.SELECT_SETTLE_SEC + 0.5)
        time.sleep(0.3)
        h = grab(f"f{k:02d}")
        answers.append({"frame": k, **reader_says(h)})
        frames.append((k, h))
        print(f"  f{k:02d} captured")

    json.dump(answers, open(os.path.join(OUT, "answers.json"), "w"), indent=1)

    from PIL import Image, ImageDraw, ImageFont
    try:
        F = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 30)
    except Exception:
        F = ImageFont.load_default()
    strips = [(k, h.crop((0, 50, h.width, 300)).convert("RGB")) for k, h in frames if h]
    W = strips[0][1].width
    RH = strips[0][1].height + 46
    sheet = Image.new("RGB", (W, RH * len(strips) + 60), (14, 14, 18))
    d = ImageDraw.Draw(sheet)
    d.text((14, 10), "FOR EACH FRAME:  which slot has the CURSOR, and which are SELECTED?",
           fill=(120, 230, 140), font=F)
    d.text((14, 44), "slots are 0-4 left to right.  e.g.  f00: 2 / none     f01: 3 / 1,3",
           fill=(170, 170, 180), font=F)
    for n, (k, s) in enumerate(strips):
        y = 60 + n * RH
        d.text((14, y + 6), f"f{k:02d}", fill=(250, 190, 90), font=F)
        sheet.paste(s, (0, y + 44))
        d.line([(0, y + RH - 2), (W, y + RH - 2)], fill=(55, 55, 65))
    sheet.save(os.path.join(OUT, "SHEET.png"))
    print(f"\nsheet -> {os.path.join(OUT, 'SHEET.png')}")
    print(f"answers (not shown) -> {os.path.join(OUT, 'answers.json')}")
    print()
    print("--- paste this back with the values filled in -------------------")
    print("    S = selected slots (comma separated, or nothing)   C = cursor slot")
    for k, _h in frames:
        print(f"F{k:02d}: S    C")
    print("-----------------------------------------------------------------")


if __name__ == "__main__":
    main()
