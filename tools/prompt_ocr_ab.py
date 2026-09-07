"""Can OCR of the prompt band tell the Baseball Cards prompt from everything else?

WHY. tools/prompt_mask_ab.py showed no local-contrast stroke mask reads the
prompt over the light table top without losing old positives or admitting
false positives. OCR is a different instrument: the prompt is one line of
specific words, and tesserocr is already in-process and fast (31ms a read).
Measured here over the same corpora: recall on every frame the shipped detector
already accepts, the bright-table frame it cannot, and hits on frames where the
prompt cannot exist (a hit there is a false positive by construction).

Read-only; writes overnight/census/prompt_ocr_ab.json (never overwritten).
    taskpolicy -b .venv/bin/python -B tools/prompt_ocr_ab.py
"""
import difflib
import glob
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from PIL import Image, ImageOps
import ocr_glyphs
import table_prompt as tp

OUT = "overnight/census/prompt_ocr_ab.json"
POS_KNOWN = {
    "anchor_recorded": "demos/spawn_to_table_20260827_212516/f_0054.32.jpg",
    "open14_trial2_arrival": "overnight/streak_table_failframes/at_dealer_table_1788765494244.jpg",
    "bright_table_goalleg_t1": "overnight/goal_leg_failframes/at_dealer_table_1788787236276.jpg",
}
NEG_QL = "demos/walk2_pauses_20260828_044514/f_0049.22.jpg"
BOX = tp.TEXT_BOX
WORDS = ("baseball", "cards", "play")
UPSCALE = 3          # measured on the anchors: PSM 7 reads nothing, PSM 6 at 3-4x reads the line
PSM = 6
FUZZ = 0.75          # "Basehal" / "Candsy" on the bright-table frame


def crops(img):
    w, h = img.size
    x0, y0, x1, y1 = BOX
    c = img.convert("L").crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))
    c = c.resize((c.width * UPSCALE, c.height * UPSCALE), Image.BICUBIC)
    return {"normal": c, "inverted": ImageOps.invert(c)}


def read(img):
    """Best OCR text over both polarities, plus a word-match score 0..3."""
    best = {"text": "", "words": 0, "polarity": None}
    for pol, c in crops(img).items():
        try:
            txt = ocr_glyphs.image_to_text(c, PSM, None) or ""
        except TypeError:
            txt = ocr_glyphs.image_to_text(c, psm=PSM, whitelist=None) or ""
        low = re.sub(r"[^a-z0-9$() ]+", " ", txt.lower().replace("|", " "))
        toks = low.split()
        hits = 0
        for wanted in WORDS:
            if any(difflib.SequenceMatcher(None, wanted, t).ratio() >= FUZZ for t in toks):
                hits += 1
        if hits > best["words"] or (hits == best["words"] and len(txt) > len(best["text"])):
            best = {"text": txt.strip()[:60], "words": hits, "polarity": pol}
    return best


def main():
    # Offline tool: hold every input path OFF -- but only when RUN as a script.
    # Set at import this flag disabled stick injection inside a live harness that
    # imported this module for its read() (prompt_zone, 2026-09-07).
    os.environ.setdefault("BASEBALL_TEST_RUN", "1")
    if os.path.exists(OUT):
        sys.exit(f"refusing to overwrite {OUT}")
    demo = sorted(glob.glob("demos/*/*.jpg"))
    neg_nodes = sorted(f for f in glob.glob("overnight/*failframes*/at_*.jpg")
                       if not os.path.basename(f).startswith("at_dealer_table"))
    table_ends = sorted(glob.glob("overnight/streak_table_failframes/at_dealer_table_*.jpg")
                        + glob.glob("overnight/goal_leg_failframes/at_dealer_table_*.jpg"))
    files = {"POS_KNOWN": list(POS_KNOWN.values()), "DEMO": demo, "NEG_NODES": neg_nodes,
             "TABLE_ENDS": table_ends, "NEG_QL": [NEG_QL]}
    for k, v in files.items():
        print(f"  {k:10} {len(v)} frames", flush=True)
    rows, t0, n = {}, time.time(), 0
    for group, fl in files.items():
        for f in fl:
            img = Image.open(f).convert("RGB")
            r = read(img)
            r["group"] = group
            r["shipped_at_table"] = bool(tp.at_table(img))
            rows[f] = r
            n += 1
            if n % 500 == 0:
                print(f"  {n} frames ({time.time() - t0:.0f}s)", flush=True)
    print(f"  read {n} frames in {time.time() - t0:.0f}s", flush=True)

    def hits(fl, k):
        return [f for f in fl if rows[f]["words"] >= k]
    old_pos = [f for f in demo if rows[f]["shipped_at_table"]]
    demo_rest = [f for f in demo if not rows[f]["shipped_at_table"]]
    summary = {}
    for k in (2, 3):
        summary[f"words>={k}"] = {
            "pos_known": {name: rows[f]["words"] >= k for name, f in POS_KNOWN.items()},
            "old_positives_recall": f"{len(hits(old_pos, k))}/{len(old_pos)}",
            "neg_nodes_false_pos": f"{len(hits(neg_nodes, k))}/{len(neg_nodes)}",
            "demo_rest_hits": f"{len(hits(demo_rest, k))}/{len(demo_rest)}",
            "table_ends_hits": f"{len(hits(table_ends, k))}/{len(table_ends)}",
            "neg_ql": rows[NEG_QL]["words"] >= k,
        }
    print()
    for name, f in POS_KNOWN.items():
        print(f"  POS {name:26} words {rows[f]['words']}  {rows[f]['polarity']}  {rows[f]['text']!r}")
    print(f"  NEG_QL words {rows[NEG_QL]['words']}  {rows[NEG_QL]['text']!r}")
    for k, s in summary.items():
        print(f"  {k}: recall {s['old_positives_recall']}  NEG_NODES fp {s['neg_nodes_false_pos']}  "
              f"demo-rest hits {s['demo_rest_hits']}  table-ends hits {s['table_ends_hits']}")
    print("  NEG_NODES hits (words>=2), top 5 texts:")
    for f in hits(neg_nodes, 2)[:5]:
        print(f"      {rows[f]['text']!r}  {f}")
    print("  demo-rest hits (words>=2) not accepted by the shipped detector, first 8:")
    for f in hits(demo_rest, 2)[:8]:
        print(f"      {rows[f]['text']!r}  {f}")
    print("  TABLE_ENDS hits (words>=2) -- prompts the shipped detector missed at leg ends:")
    for f in hits(table_ends, 2):
        print(f"      {rows[f]['text']!r}  shipped={rows[f]['shipped_at_table']}  {f}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"question": "OCR of TEXT_BOX as a prompt detector", "box": BOX, "words": WORDS,
               "summary": summary, "frames": rows}, open(OUT, "w"), indent=1)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
