"""WATCH THE WHOLE READ, live, beside chiaki -- everything a crawl step decides on.

    .venv/bin/python -B tools/state_viewer.py              the frame + every region + the read
    .venv/bin/python -B tools/state_viewer.py --hand       just the hand, bigger
    .venv/bin/python -B tools/state_viewer.py --scale 0.7
    .venv/bin/python -B tools/state_viewer.py --no-reload    pin the code, do not self-restart

IT RELOADS ITSELF when this file, orchestrator, local_hand or local_state changes on disk,
so a box can be tuned against the live screen without relaunching.

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
import orchestrator as o, local_hand as lh, local_state as ls, ban_grid as bg

# RELOAD ITSELF WHEN THE CODE CHANGES, so a constant can be tuned against the live screen
# without killing and relaunching (the user, 2026-09-13: "so when you make changes, I don't
# have to kill the process and restart it").
#
# RE-EXEC, NOT importlib.reload. Reloading orchestrator mid-tick leaves half the module
# graph on the old objects and the new ones disagreeing about constants -- a stale-module
# trap this project already pays for in other places (CLAUDE.md 10.17). Replacing the whole
# process has one state and cannot be half-applied. It presses nothing, so restarting it at
# any moment is free.
_WATCH = ["tools/state_viewer.py", "orchestrator.py", "local_hand.py", "local_state.py"]
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _stamp():
    out = {}
    for rel in _WATCH:
        p = os.path.join(_ROOT_DIR, rel)
        try:
            st = os.stat(p)
            out[rel] = (st.st_mtime, st.st_size)     # mtime AND size: a same-second edit
        except OSError:                              # of the same length is otherwise invisible
            out[rel] = None
    return out


_SEEN = _stamp()


def _reexec_if_changed():
    if getattr(A, "no_reload", False):
        return
    now = _stamp()
    changed = [k for k in now if now[k] != _SEEN.get(k)]
    if not changed:
        return
    print(f"[state_viewer] {', '.join(changed)} changed — reloading", flush=True)
    sys.stdout.flush()
    os.execv(sys.executable, [sys.executable, "-B"] + sys.argv)


ap = argparse.ArgumentParser()
ap.add_argument("--hand", action="store_true", help="hand crop only")
ap.add_argument("--hz", type=float, default=4.0)
ap.add_argument("--scale", type=float, default=0.0, help="0 = fit the window")
ap.add_argument("--no-reload", action="store_true",
                help="do not re-exec when the source changes")
ap.add_argument("--once", action="store_true",
                help="run one tick, print what the panel would say, and exit")
A = ap.parse_args()

CUR, SEL, BOX, REG = "#00ff66", "#ff3b30", "#ffcc00", "#4da3ff"
BAN, NAME = "#ff5ecb", "#8affff"          # ban-grid card box, and its name strip
FALLBACK = "#ff9d00"                      # the FIXED box, drawn when the fit failed
POWER, SHIELD = "#7CFC00", "#ffa8ff"      # the power disc and the shield badge
root = tk.Tk()
root.title("state — what the crawl reads")
root.attributes("-topmost", True)
lbl = tk.Label(root, bg="black"); lbl.pack()
txt = tk.Label(root, font=("Menlo", 12), anchor="w", justify="left")
txt.pack(fill="x")
S = {"img": None, "slow": {}, "t": 0.0, "frame": None, "rows": None, "note": ""}


def _type_ocr(img):
    """OCR for the TYPE banner. PSM comes from ban_grid, which measured it."""
    try:
        return o._ocr_text(img, bg.TYPE_BANNER_PSM, "ABCDEFGHIJKLMNOPQRSTUVWXYZ") or ""
    except Exception:
        return ""


def _ocr_strip(frame, box):
    """Upper-case text off one banner strip, or None. Raw OCR, no roster lookup."""
    try:
        strip = frame.crop(box).convert("L")
        strip = strip.resize((strip.width * 4, strip.height * 4))
        t = (o._ocr_text(strip, 7, "ABCDEFGHIJKLMNOPQRSTUVWXYZ' -\"") or "").strip()
        return t or None
    except Exception:
        return None


def slow_read(frame, crops):
    """The OCR-backed fields. Once a second, not every tick."""
    out = {}
    try:
        out["score"] = o.ocr_scoreboard(crops["scoreboard"])
    except Exception as e:
        out["score"] = f"err {type(e).__name__}"
    # THE DIAMOND IS ONLY A DIAMOND ON A TURN SCREEN. On a ban grid these crops land on
    # CARDS, which read as occupied bases carrying real shield badges -- see
    # orchestrator.on_turn_screen for the census. Labelled, not suppressed: this is a
    # diagnostic, so hiding the reading would remove the evidence it exists to show.
    if not o.on_turn_screen(crops.get("hand")):
        out["runners"] = "n/a — NOT A TURN SCREEN (the base crops are not the diamond)"
    else:
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
    # WHICH BOXES BELONG ON THIS SCREEN. Computed HERE, with the other OCR-backed fields,
    # and not in the draw block: read_ban_counter OCRs the "N/3" counter, and running that
    # every tick makes the viewer sluggish for a verdict that cannot change between frames.
    try:
        n = o.read_ban_counter(frame)
    except Exception:
        n = None
    out["on_ban"] = n is not None
    out["banned"] = n
    if out["on_ban"]:
        # ON A BAN SCREEN, REPORT THE BAN SCREEN. phase/cursor/cards/score are match fields
        # and read None or nonsense here, which looks like a broken reader rather than the
        # wrong screen (the user, 2026-09-13). Name what this screen actually has.
        try:
            lvl, _thumb = o.read_ban_scroll_level(frame)
        except Exception:
            lvl = None
        out["scroll"] = lvl
        # FIT THE BOXES TO THE FRAME. The rows MOVE with scroll position (card tops 0.282 /
        # 0.609 at the top of the grid, 0.231 / 0.558 two presses later), so a fixed
        # fraction cannot frame them all -- see ban_grid.
        rows = bg.find_card_rows(frame, o.BAN_GRID_COL_X_FRAC)
        out["fitted"] = rows is not None
        out["rows"] = rows
        names, types = [], []
        n_rows = len(rows) if rows else 2
        for row in range(n_rows):
            for col in range(5):
                key = f"r{row}c{col}"
                fitted_cell = bool(rows) and row < len(rows)
                if fitted_cell and rows[row].get("clipped"):
                    # A PART-VISIBLE ROW IS NOT A CARD TO READ. Its crop holds a slice of a
                    # card, and OCR on that returns confident nonsense ('Ss S Ss Ue') --
                    # which reads as a bad reader rather than as half a card.
                    names.append((key, "clipped"))
                    types.append((key, "clipped"))
                    continue
                try:
                    box = (bg.card_box(frame, rows, row, col, o.BAN_GRID_COL_X_FRAC)
                           if fitted_cell else None)
                    if fitted_cell and box is not None:
                        cell = frame.crop(box)
                    elif fitted_cell:
                        raise ValueError("off screen")
                    else:
                        cell = o.get_ban_grid_card_crop(frame, row, col)
                    c = o.ocr_ban_card_name(cell)
                except Exception:
                    c = None
                nm = getattr(c, "name", None) if c else None
                # TACTICS CARDS CANNOT BE NAMED BY THE ROSTER -- KNOWN_BAN_ROSTER is 33
                # PLAYER cards and no tactics at all (CLAUDE.md section 4). So when the
                # roster lookup declines, read the banner RAW: that is how a Power Swing or
                # a Speed Boost gets its real name instead of "unknown", and it also
                # surfaces whatever is legible on a card the roster has never seen.
                locked = bg.is_locked(frame, box) if fitted_cell else None
                raw = None
                # RAW OCR ONLY ON A CARD THAT IS ACTUALLY LEGIBLE. On a LOCKED card the
                # game draws the name at sd 16-19, and tesseract returns confident junk
                # ('Dd', 'Bm --') that reads as a name. "locked" is both true and useful;
                # a two-letter fragment is neither.
                if nm is None and fitted_cell and locked is False:
                    nb = bg.name_box(frame, rows, row, col, o.BAN_GRID_COL_X_FRAC)
                    raw = _ocr_strip(frame, nb) if nb else None
                    # A NAME IS NOT TWO LETTERS. Where the PLAY prompt overlaps a banner,
                    # OCR returns fragments ('Bm --') that read as a name in a grid of
                    # names. The shortest real card name on the roster is "Rube Sharp";
                    # anything under five letters is a fragment, and unknown is the honest
                    # answer for one.
                    if raw and sum(ch.isalpha() for ch in raw) < 5:
                        raw = None
                names.append((key, nm or (raw and raw.title()) or
                              ("locked" if locked else None)))
                # THE TYPE IS ITS OWN FIELD, not crammed into the name (the user,
                # 2026-09-13). "unknown" on a locked card is a real answer: the box is
                # right and the card simply cannot be read yet.
                t = None
                if fitted_cell:
                    t = bg.read_card_type(frame, rows, row, col, o.BAN_GRID_COL_X_FRAC,
                                          _type_ocr)
                # LOCKED AND UNKNOWN ARE DIFFERENT ANSWERS. Locked means the card is there
                # and the game is drawing it faded; unknown means the reader failed. Saying
                # "unknown" for a locked card hides the fact that nothing is wrong.
                label = (t if isinstance(t, str)
                         else (t[1].title() if t else ("locked" if locked else None)))
                types.append((key, label))
                if isinstance(t, tuple) and names[-1][1] is None:
                    names[-1] = (key, t[1].title())    # a tactics card names itself
        out["ban_names"] = names
        out["ban_types"] = types
    return out


def tick():
    try:
        frame = o._fast_grab()
        crops = dict(o.crop_gameplay_regions(frame))
        hand = crops.get("hand")
        if not S["slow"] or time.time() - S["t"] > 1.0:
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

        S["frame"] = frame                      # the EXACT pixels the panel is showing,
        S["rows"] = S["slow"].get("rows")        # so a save cannot capture a later frame
        canvas = (hand if (A.hand and hand is not None) else frame).convert("RGB")
        d = ImageDraw.Draw(canvas)
        ox = oy = 0
        if not A.hand:
            # WHICH BOXES BELONG ON THIS SCREEN? The gameplay regions are meaningless on a
            # ban grid -- the base crops land on grid CARDS there and read as runners
            # (orchestrator.on_turn_screen) -- so a viewer that draws them anyway is
            # showing the user boxes for a screen that is not up. Draw the ban grid
            # instead when the ban counter reads, which is the same detector the live
            # ladder uses to name that screen.
            if S["slow"].get("on_ban"):
                fitted = S["slow"].get("rows")
                for row in range(len(fitted) if fitted else 2):
                    for col in range(5):
                        if fitted and row < len(fitted):
                            cb = bg.card_box(frame, fitted, row, col,
                                             o.BAN_GRID_COL_X_FRAC)
                            if cb is None:
                                continue              # this row is entirely off screen
                            x0, y0, x1, y1 = cb
                            colr = BAN
                        else:
                            fx0, fx1 = o.BAN_GRID_COL_X_FRAC[col]
                            fy0 = o.BAN_CARD_ROW_TOP_FRAC[row]
                            x0, y0 = int(frame.width * fx0), int(frame.height * fy0)
                            x1 = int(frame.width * fx1)
                            y1 = int(frame.height * (fy0 + o.BAN_GRID_CARD_HEIGHT_FRAC))
                            colr = FALLBACK      # a different colour, because it is a
                        d.rectangle((x0, y0, x1, y1), outline=colr, width=3)
                        nm = dict(S["slow"].get("ban_names") or []).get(f"r{row}c{col}")
                        ty = dict(S["slow"].get("ban_types") or []).get(f"r{row}c{col}")
                        d.text((x0 + 4, y0 + 3),
                               f"{nm or 'unknown'} [{ty or 'unknown'}]", fill=colr)
                        if fitted and row < len(fitted):
                            nb = bg.name_box(frame, fitted, row, col,
                                             o.BAN_GRID_COL_X_FRAC)
                            if nb is not None:
                                d.rectangle(nb, outline=NAME, width=2)
                            # the two number boxes, so what the readers LOOK at is visible
                            for _b, _c in ((bg.power_box(frame, fitted, row, col,
                                                         o.BAN_GRID_COL_X_FRAC), POWER),
                                           (bg.shield_box(frame, fitted, row, col,
                                                          o.BAN_GRID_COL_X_FRAC), SHIELD)):
                                if _b is not None:
                                    d.rectangle(_b, outline=_c, width=2)
                        # the strip ocr_ban_card_name reads the NAME from -- drawn because
                        # it is the thing that goes wrong: at some scroll positions a row-1
                        # crop starts on row 0's name banner, so the name and the stats in
                        # one crop come from DIFFERENT cards (CLAUDE.md 10.23).

            else:
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
        if sl.get("on_ban"):
            cells = sl.get("ban_names") or []
            tys = sl.get("ban_types") or []
            got = [1 for _k, v in cells if v]
            gott = [1 for _k, v in tys if v]
            fit = "FITTED to the frame" if sl.get("fitted") else "FIT FAILED — fixed box"

            def _grid(pairs):
                # ONE LINE PER ROW, however many rows the fit returned. This assumed two
                # and ran fifteen cells onto one line the moment the fit started reporting
                # the part-visible rows as well.
                out = []
                for i in range(0, len(pairs), 5):
                    out.append(f"  row{i // 5}  " + "  ".join(
                        f"{k[-2:]}:{v or 'unknown'}" for k, v in pairs[i:i + 5]))
                return "\n".join(out)

            # NAMES AND TYPES IN SEPARATE GRIDS, not one crowded line (the user's call,
            # 2026-09-13). A type of "unknown" on a locked card is a real answer.
            txt.config(text=(
                f"BAN SCREEN   banned {sl.get('banned')}/3   scroll {sl.get('scroll')}   {fit}\n"
                f"NAME  named {len(got)}/{len(cells)}\n{_grid(cells)}\n"
                f"TYPE  typed {len(gott)}/{len(tys)}\n{_grid(tys)}"
                + (f"\n[s] {S['note']}" if S.get("note") else "\n[s] save a labelling sheet")))
        else:
            txt.config(text=(
                f"phase {phase}   cursor {cur}   selected {sel}   rows {len(rows)}\n"
                f"glow {glow}\n"
                f"cards {[(r.get('digit'), r.get('kind')) for r in rows]}\n"
                f"score {sl.get('score')}   runners {sl.get('runners')}   "
                f"result {sl.get('result')}"))
    except Exception as e:
        # PRINT IT TOO. Showing the error only in the label means a viewer that is failing
        # looks identical to one that is working badly, and nothing lands in a log anyone
        # can paste back (CLAUDE.md 10.1). The traceback goes to stdout as well.
        import traceback
        traceback.print_exc()
        txt.config(text=f"{type(e).__name__}: {e}")
    if A.once:
        print(txt.cget("text"))
        root.quit()
        return
    _reexec_if_changed()
    root.after(int(1000 / A.hz), tick)


def save_sheet(_event=None):
    """`s` — dump the ban grid on screen as a NUMBERED contact sheet to label by hand.

    THE BLOCKED TASK IS A LABELLING TASK. The hand's digit bank does not read ban cards
    (argmax right on 3 of 7; under 0.5 is wrong), so auditing the roster's NUMBERS needs a
    ban-specific bank -- and its labels must be independent of the roster, or the audit is
    circular. That means a human reading cards. This makes that one keypress instead of a
    scripting session, and it saves the FRAME TOO, so the labels can always be re-derived
    from the same pixels.
    """
    frame, rows = S.get("frame"), S.get("rows")
    if frame is None:
        S["note"] = "nothing captured yet"
        return
    out = os.path.join(_ROOT_DIR, "agent_progress", "ban-labels")
    os.makedirs(out, exist_ok=True)
    stamp = str(S["slow"].get("scroll", "x"))
    n = 0
    while os.path.exists(os.path.join(out, f"sheet_scroll{stamp}_{n}.jpg")):
        n += 1
    base = os.path.join(out, f"sheet_scroll{stamp}_{n}")
    frame.save(base + "_frame.png")
    if not rows:
        S["note"] = f"saved {os.path.basename(base)}_frame.png (no fit — frame only)"
        return
    tiles = []
    for r in range(len(rows)):
        if rows[r].get("clipped"):
            continue
        for c in range(5):
            b = bg.card_box(frame, rows, r, c, o.BAN_GRID_COL_X_FRAC)
            if b is not None:
                tiles.append((f"r{r}c{c}", frame.crop(b)))
    if not tiles:
        S["note"] = "no unclipped cards to sheet"
        return
    tw = max(t.size[0] for _, t in tiles)
    th = max(t.size[1] for _, t in tiles)
    k = 2
    sheet = Image.new("RGB", (tw * k * len(tiles), th * k + 34), (18, 18, 20))
    dd = ImageDraw.Draw(sheet)
    for i, (name, t) in enumerate(tiles):
        t = t.resize((tw * k, th * k), Image.LANCZOS)
        sheet.paste(t, (i * tw * k, 34))
        dd.text((i * tw * k + 6, 8), name, fill=(255, 220, 60))
    sheet.save(base + "_sheet.jpg", quality=94)
    S["note"] = f"saved {os.path.basename(base)}_sheet.jpg ({len(tiles)} cards)"


root.bind("<KeyPress-s>", save_sheet)
root.bind("<KeyPress-S>", save_sheet)
root.focus_force()

root.after(50, tick)
root.mainloop()
