"""Questionable-card queue for the user (I-59).

Every refused select_and_play() call and every dropped-slot decision already
keeps a frame: `diagnostics/deal_frames/refused_select_<ns>/{hand.png,why.json}`
(orchestrator.record_refused_select) and `dropped_<ns>/{hand.png,why.json}`
(orchestrator._save_dropped_hand). Both why.json name exactly which slot the
run could not resolve on its own. This tool turns those into something the
user can answer between sessions instead of missing a live notification: crop
the questionable slot out of each hand.png, tile the crops into a numbered
contact sheet, and write a table with an empty "Your answer" column next to
each one.

    python tools/questions_sheet.py --since <ns-or-ISO> [--out DIR] [--log FILE]

Never modifies or deletes a source frame -- only reads hand.png/why.json and
writes into --out.
"""
import argparse
import datetime
import json
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import local_hand

DEAL_FRAME_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "diagnostics", "deal_frames")
DEDUPE_WINDOW_S = 60.0
COLS = 6
MAX_PER_SHEET = 24
TILE_W = 200
TILE_IMG_H = 260
LABEL_H = 40
TILE_H = TILE_IMG_H + LABEL_H


def _parse_since(s):
    """A bare integer is ns-since-epoch (matches the diagnostics dir names
    directly); anything else is parsed as an ISO timestamp."""
    if s.isdigit():
        return int(s)
    return int(datetime.datetime.fromisoformat(s).timestamp() * 1e9)


def slot_box(img_w, img_h, slot):
    """(left, 0, right, img_h) for one slot -- full card height, 15% margin each
    side. CLAUDE.md section 3: never a raw pixel. Every offset here comes from
    local_hand.SLOT_PLAYER/SLOT_TACTICS (the two anchors for the same physical
    slot -- a player disc or a tactics wreath, whichever this card turns out to
    be) and is scaled by the capture's own width.
    """
    n = len(local_hand.SLOT_PLAYER)
    centers = [(local_hand.SLOT_PLAYER[i][0] + local_hand.SLOT_TACTICS[i][0]) / 2
               for i in range(n)]
    s = img_w / local_hand.ANCHOR_W
    c = [x * s for x in centers]
    left = c[slot] - (c[1] - c[0]) / 2 if slot == 0 else (c[slot - 1] + c[slot]) / 2
    right = c[slot] + (c[-1] - c[-2]) / 2 if slot == n - 1 else (c[slot] + c[slot + 1]) / 2
    margin = 0.15 * (right - left)
    return (max(0, int(left - margin)), 0, min(img_w, int(right + margin)), img_h)


def _events(root, since_ns):
    """(ns, kind, dirpath, why) for every refused_select_*/dropped_* dir newer
    than since_ns, oldest first."""
    if not os.path.isdir(root):
        return
    out = []
    for name in os.listdir(root):
        for prefix, kind in (("refused_select_", "refused"), ("dropped_", "dropped")):
            if not name.startswith(prefix):
                continue
            ns_part = name[len(prefix):]
            if not ns_part.isdigit():
                continue
            ns = int(ns_part)
            if ns <= since_ns:
                continue
            d = os.path.join(root, name)
            why_path = os.path.join(d, "why.json")
            if not (os.path.isfile(os.path.join(d, "hand.png")) and os.path.isfile(why_path)):
                continue
            with open(why_path) as fh:
                why = json.load(fh)
            out.append((ns, kind, d, why))
    out.sort(key=lambda e: e[0])
    return out


def _log_line(log_lines, dirname):
    """The log line naming this event's directory, if --log was given. Both
    record_refused_select and _save_dropped_hand print the directory path they
    wrote, so a substring search on the directory's own basename is enough --
    no timestamp parsing required."""
    if not log_lines:
        return None
    for line in log_lines:
        if dirname in line:
            return line.strip()
    return None


def _questions(root, since_ns, log_lines):
    """One row per questionable slot, oldest first."""
    out = []
    for ns, kind, d, why in _events(root, since_ns):
        dirname = os.path.basename(d)
        line = _log_line(log_lines, dirname)
        if kind == "refused":
            said = (f"refused select (kind={why.get('kind')}, "
                     f"attempt={why.get('attempt')}, "
                     f"already_selected={why.get('already_selected')})")
            if line:
                said += f" | log: {line}"
            out.append({"ns": ns, "slot": why.get("target"), "dir": d,
                        "hand_png": os.path.join(d, "hand.png"), "said": said})
        else:
            for slot in why.get("dropped", []):
                said = f"UNKNOWN (dropped: {why.get('why')})"
                if line:
                    said += f" | log: {line}"
                out.append({"ns": ns, "slot": slot, "dir": d,
                            "hand_png": os.path.join(d, "hand.png"), "said": said})
    return out


def _dedupe(questions):
    """The same slot in consecutive (time-sorted) frames within
    DEDUPE_WINDOW_S collapses to one question, keeping the first frame."""
    merged = []
    for q in questions:
        if (merged and merged[-1]["slot"] == q["slot"]
                and (q["ns"] - merged[-1]["_last_ns"]) <= DEDUPE_WINDOW_S * 1e9):
            merged[-1]["count"] += 1
            merged[-1]["_last_ns"] = q["ns"]
        else:
            m = dict(q, count=1, _last_ns=q["ns"])
            merged.append(m)
    return merged


def _tile(q, n):
    im = Image.open(q["hand_png"]).convert("RGB")
    crop = im.crop(slot_box(im.width, im.height, q["slot"]))
    crop = crop.resize((TILE_W, TILE_IMG_H), Image.LANCZOS)
    tile = Image.new("RGB", (TILE_W, TILE_H), (255, 255, 255))
    tile.paste(crop, (0, 0))
    d = ImageDraw.Draw(tile)
    t = datetime.datetime.fromtimestamp(q["ns"] / 1e9).strftime("%H:%M:%S")
    extra = f" x{q['count']}" if q["count"] > 1 else ""
    d.text((2, TILE_IMG_H + 2), f"Q{n}  {t}  slot {q['slot']}{extra}", fill=(0, 0, 0))
    said = q["said"] if len(q["said"]) <= 42 else q["said"][:39] + "..."
    d.text((2, TILE_IMG_H + 20), said, fill=(0, 0, 0))
    return tile


def _write_sheets(questions, out_dir):
    paths = []
    for start in range(0, max(len(questions), 1), MAX_PER_SHEET):
        chunk = questions[start:start + MAX_PER_SHEET]
        if not chunk:
            break
        rows = -(-len(chunk) // COLS)
        sheet = Image.new("RGB", (COLS * TILE_W, rows * TILE_H), (25, 25, 25))
        for i, q in enumerate(chunk):
            tile = _tile(q, start + i + 1)
            sheet.paste(tile, ((i % COLS) * TILE_W, (i // COLS) * TILE_H))
        path = os.path.join(out_dir, f"sheet_{start // MAX_PER_SHEET + 1:02d}.png")
        sheet.save(path)
        paths.append(path)
    return paths


def build(since, out_dir, log_path=None, root=DEAL_FRAME_DIR):
    since_ns = _parse_since(since)
    log_lines = open(log_path).readlines() if log_path else None
    questions = _dedupe(_questions(root, since_ns, log_lines))
    os.makedirs(out_dir, exist_ok=True)

    rows = []
    for n, q in enumerate(questions, 1):
        rows.append({
            "Q": n,
            "time": datetime.datetime.fromtimestamp(q["ns"] / 1e9).isoformat(),
            "frame": q["hand_png"],
            "slot": q["slot"],
            "said": q["said"] + (f" (seen {q['count']}x)" if q["count"] > 1 else ""),
            "answer": "",
        })

    with open(os.path.join(out_dir, "questions.json"), "w") as fh:
        json.dump(rows, fh, indent=1)

    with open(os.path.join(out_dir, "questions.md"), "w") as fh:
        fh.write("| Q | time | frame | slot | what the reader said | Your answer |\n")
        fh.write("|---|---|---|---|---|---|\n")
        for r in rows:
            fh.write(f"| {r['Q']} | {r['time']} | {r['frame']} | {r['slot']} "
                      f"| {r['said']} | {r['answer']} |\n")

    sheet_paths = _write_sheets(questions, out_dir)
    return sheet_paths, rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", required=True, help="ns epoch or an ISO timestamp")
    ap.add_argument("--out", default=None,
                     help="default: diagnostics/questions/<YYYYMMDD_HHMM>")
    ap.add_argument("--log", default=None, help="a run log to pull the matching line from")
    args = ap.parse_args()
    out = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "diagnostics", "questions", datetime.datetime.now().strftime("%Y%m%d_%H%M"))
    sheets, rows = build(args.since, out, log_path=args.log)
    print(f"{len(rows)} question(s) -> {out}")
    for p in sheets:
        print(f"  {p}")
    print(f"  {os.path.join(out, 'questions.md')}")
    print(f"  {os.path.join(out, 'questions.json')}")
