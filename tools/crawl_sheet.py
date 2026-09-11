"""SHOW EVERY CROP A READER LOOKED AT, WITH WHAT IT CONCLUDED WRITTEN ON IT.

The numbers in a crawl step say what each reader decided. They do not show WHAT IT WAS
LOOKING AT, and this project's whole history is wrong diagnoses made from the right numbers
about the wrong pixels (CLAUDE.md 10.23: a reader cropping the wrong region reports it as
"I am not sure"). This renders the actual crops, labelled, so a human can see in one glance
whether a reader was even shown the thing it was asked about.

    .venv/bin/python -B tools/crawl_sheet.py [out.png]
"""
import os, sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.pop("BASEBALL_TEST_RUN", None)

from PIL import Image, ImageDraw, ImageFont
import orchestrator as o
import local_hand as lh
import local_state as ls

OUT = sys.argv[1] if len(sys.argv) > 1 else "agent_progress/crawl_sheet.png"


def font(sz):
    for p in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(p, sz)
        except Exception:
            pass
    return ImageFont.load_default()


F_BIG, F_MID, F_SML = font(30), font(22), font(17)
INK, GOOD, BAD, WARN = (245, 245, 245), (120, 255, 140), (255, 110, 110), (255, 210, 80)


def panel(img, w):
    h = max(1, int(w * img.size[1] / img.size[0]))
    return img.convert("RGB").resize((w, h), Image.LANCZOS)


def build(img=None, out=None):
    """Render the sheet. `img` MUST be the frame the step actually read -- grabbing a fresh
    one here would label a step with pixels it never saw, which is the exact mistake this
    tool exists to prevent (CLAUDE.md 10.15)."""
    if img is None:
        img = o._fast_grab()
    crops = dict(o.crop_gameplay_regions(img))
    hand = crops.get("hand")
    rows = lh.read_hand(hand) if hand is not None else []
    # WHICH STAT IS `secondary`?  It is SPEED on a batter and FIELDING on a pitcher,
    # and the label was gated on rows[i]['phase_hint'] -- a key read_hand does not
    # write, so the fielding branch could never fire and every pitching hand was
    # labelled "speed" (CLAUDE.md 10.1).  Caught by the user reading the sheet.
    phase = ls.read_phase(hand)[0] if hand is not None else None
    cards, why = o.local_hand_cards(hand) if hand is not None else (None, "no crop")
    st, gap = None, None
    try:
        st, gap = o.local_game_state()
    except Exception as e:
        gap = f"{type(e).__name__}: {e}"

    W = 1680
    tiles = []

    # 1. the whole frame, with every region the readers crop drawn on it
    full = panel(img, W - 40)
    d = ImageDraw.Draw(full)
    fw, fh = img.size
    for label, col in (("hand", (90, 200, 255)), ("scoreboard", (255, 200, 90)),
                       ("third_base", (180, 140, 255)), ("second_base", (180, 140, 255)),
                       ("first_base", (180, 140, 255))):
        fr = o.GAMEPLAY_REGIONS_FRAC.get(label)
        if not fr:
            continue
        s = full.size[0] / fw
        box = [int(fw * fr[0] * s), int(fh * fr[1] * s * (full.size[1] / (fh * s))),
               int(fw * fr[2] * s), int(fh * fr[3] * s * (full.size[1] / (fh * s)))]
        d.rectangle(box, outline=col, width=3)
        d.text((box[0] + 6, box[1] + 4), label, fill=col, font=F_SML)
    # the result-word search window
    s = full.size[0] / fw
    S = ls.RESULT_SEARCH
    d.rectangle([int(fw * S[0] * s), int(fh * S[1] * s * (full.size[1] / (fh * s))),
                 int(fw * S[2] * s), int(fh * S[3] * s * (full.size[1] / (fh * s)))],
                outline=(255, 120, 220), width=3)
    d.text((int(fw * S[0] * s) + 6, int(fh * S[1] * s * (full.size[1] / (fh * s))) + 4),
           "result word search", fill=(255, 120, 220), font=F_SML)
    tiles.append(("THE FRAME every reader was given  —  "
                  f"screen={(st or {}).get('screen')!r}" + (f"   GAP: {gap}" if gap else ""),
                  full, GOOD if st else WARN))

    # 2. every hand card, cut around the disc the reader actually found
    if hand is not None and rows:
        cw, ch = 250, 300
        strip = Image.new("RGB", (cw * len(rows), ch + 76), (16, 16, 18))
        sd = ImageDraw.Draw(strip)
        hw, hh = hand.size
        for i, r in enumerate(rows):
            x, y = r.get("x"), r.get("y")
            box = (max(0, (x or 0) - 105), max(0, (y or 0) - 120),
                   min(hw, (x or 0) + 105), min(hh, (y or 0) + 130))
            sub = hand.crop(box).convert("RGB")
            sub = sub.resize((cw - 16, ch - 16), Image.LANCZOS)
            strip.paste(sub, (i * cw + 8, 8))
            card = next((c for c in (cards or []) if c.get("hand_index") == i), None)
            kind = r.get("kind")
            # decision_engine: "secondary: speed (batter) or fielding (pitcher)".
            # It was labelled "shield" here, which is the BADGE it is read from, not what it
            # means -- and speed decides how many bases a runner takes.
            stat = "fielding" if phase == "pitching" else ("speed" if phase == "batting" else "secondary")
            read = (f"power {r.get('digit')}   {stat} {r.get('secondary')}"
                    if kind == "player" else f"{r.get('type')}  +{r.get('bonus')}")
            col = GOOD if (card is not None) else BAD
            sd.text((i * cw + 10, ch), f"index {i}   {kind}", fill=col, font=F_MID)
            sd.text((i * cw + 10, ch + 26), read, fill=INK, font=F_SML)
            sd.text((i * cw + 10, ch + 48),
                    f"score {r.get('score')}   @({x},{y})", fill=(150, 150, 160), font=F_SML)
            if card is None:
                sd.text((i * cw + 10, ch + 48), "DROPPED — not usable", fill=BAD, font=F_SML)
        tiles.append((f"THE HAND — read_hand found {len(rows)}, "
                      f"{len(cards) if cards else 0} usable" + (f"   ({why})" if why else ""),
                      panel(strip, W - 40), GOOD if cards else BAD))

    # 3. the small crops, side by side, each with its verdict
    small = []
    sb = crops.get("scoreboard")
    if sb is not None:
        try:
            sc = o.ocr_scoreboard(sb)
        except Exception as e:
            sc = {"err": str(e)}
        small.append(("scoreboard", sb, f"your {sc.get('your')}  opp {sc.get('opponent')}"))
        dbg = {}
        dl = ls.read_discards_left(sb, dbg)
        small.append(("discards", sb, f"{dl!r}" + (f"  ({dbg.get('why')})" if dbg.get("why") else "")))
    for b in ("third_base", "second_base", "first_base"):
        c = crops.get(b)
        if c is None:
            continue
        try:
            rd = ls.read_base(c, b.replace("_base", ""))
            v = f"{rd['occupied']!r}  power {rd['power']!r}"
        except Exception as e:
            v = f"ERR {e}"
        small.append((b, c, v))
    if small:
        tw = (W - 40) // len(small)
        row = Image.new("RGB", (tw * len(small), 300), (16, 16, 18))
        rd_ = ImageDraw.Draw(row)
        for i, (name, im, verdict) in enumerate(small):
            p = panel(im, tw - 16)
            p = p.crop((0, 0, p.size[0], min(p.size[1], 210)))
            row.paste(p, (i * tw + 8, 8))
            rd_.text((i * tw + 10, 226), name, fill=(150, 200, 255), font=F_MID)
            rd_.text((i * tw + 10, 252), verdict, fill=INK, font=F_SML)
        tiles.append(("THE OTHER CROPS, and what each reader said about its own pixels",
                      row, INK))

    # 4. the result-word window with the template scores
    res = ls.read_result(img)
    band = img.convert("RGB").crop((int(fw * S[0]), int(fh * S[1]),
                                    int(fw * S[2]), int(fh * S[3])))
    words = "   ".join(f"{k} {v:.3f}" for k, v in sorted(res["scores"].items(), key=lambda kv: -kv[1]))
    tiles.append((f"RESULT WORD WINDOW — is_result={res['is_result']}  "
                  f"outcome={res['outcome']!r}   {words}",
                  panel(band, W - 40), GOOD if res["is_result"] else (150, 150, 160)))

    total = sum(t[1].size[1] + 52 for t in tiles) + 30
    sheet = Image.new("RGB", (W, total), (10, 10, 12))
    sd = ImageDraw.Draw(sheet)
    y = 16
    for title, im, col in tiles:
        sd.text((20, y), title, fill=col, font=F_BIG)
        y += 40
        sheet.paste(im, (20, y))
        y += im.size[1] + 12
    dest = out or OUT
    sheet.save(dest)
    return dest


if __name__ == "__main__":
    build()
