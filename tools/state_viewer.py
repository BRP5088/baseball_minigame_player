"""WATCH THE WHOLE READ, live, beside chiaki -- everything a crawl step decides on.

    .venv/bin/python -B tools/state_viewer.py              the frame + every region + the read
    .venv/bin/python -B tools/state_viewer.py --hand       just the hand, bigger
    .venv/bin/python -B tools/state_viewer.py --scale 0.7
    .venv/bin/python -B tools/state_viewer.py --no-reload    pin the code, do not self-restart

TUNE THE CARD BOXES LIVE, on the ban screen, with the game on the other monitor:

    1 2 3 4        pick type banner / power disc / shield / name banner
    arrows         slide the selected box      shift+arrows   resize it
    [  ]           step 0.002 / 0.010
    w              write the values into ban_grid.py (the viewer then reloads itself)
    0              throw the working values away and reload from ban_grid.py

Everything is a fraction of the FITTED CARD BOX, so a tuned value holds at every capture
size and every scroll position. It presses nothing at the console.

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
import os, sys, re, argparse, time, tkinter as tk
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
_WATCH = ["tools/state_viewer.py", "orchestrator.py", "local_hand.py", "local_state.py",
          "ban_grid.py"]
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


def _edit_panel():
    """One line of editor state, so the keys are never something to remember."""
    k = _sel_key()
    v = " ".join(f"{x:.4f}" for x in E["vals"][k])
    who = "  ".join(f"[{i + 1}]{n.upper() if n == k else n}"
                    for i, n in enumerate(_EDIT_KEYS))
    star = "*" if E["dirty"] else " "
    return (f"BOX{star} {who}   {_EDIT_CONST[k]} = ({v})   step {E['step']:.3f}\n"
            f"     arrows move | shift+arrows resize | [ fine  ] coarse | "
            f"w write to ban_grid.py | 0 revert"
            + (f"   -- {E['msg']}" if E["msg"] else "") + "\n")


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
TYPE = "#ffffff"                          # the BATTER / PITCHER ribbon box
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
        # BAN_GRID'S OWN COLUMNS, never orchestrator's. This viewer passed
        # o.BAN_GRID_COL_X_FRAC into every ban_grid call, and ban_grid's sub-boxes
        # (power disc, shield, type and name ribbons) are fractions of the card box THOSE
        # columns produce -- 0.108 wide, not the shipped 0.130. Handing it the wider box
        # slid every badge box right and down by a fifth of a card, which is exactly what
        # the user saw: "the bounding boxes for the batting and pitching power is off now,
        # same with the shield and pitching debuff" (2026-09-13). Nothing was wrong with
        # the constants; they were being applied to the wrong rectangle.
        rows = bg.find_card_rows(frame)
        out["fitted"] = rows is not None
        out["rows"] = rows
        names, types = [], []
        n_rows = len(rows) if rows else 2
        for row in range(n_rows):
            for col in range(5):
                key = f"r{row}c{col}"
                fitted_cell = bool(rows) and row < len(rows)
                box = (bg.card_box(frame, rows, row, col) if fitted_cell else None)
                # ASK "IS IT LOCKED" FIRST, AND STOP THERE IF IT IS. The user, 2026-09-13:
                # "if the card isn't playable, there isn't a need to try to read the info
                # on the card." Locked is a CONTRAST answer (sd 16-19 faded against 62-66
                # owned, a 3.5x gap) and it costs no OCR, while every reader below does --
                # so the order was backwards: this loop OCR'd the name and the type of
                # every locked card and then threw both away. It also removes a way to be
                # wrong: a faded banner returns junk like 'N HER', and a junk banner that
                # happens to fuzzy-match is a tactics label on a player card.
                locked = bg.is_locked(frame, box) if fitted_cell else None
                c = None
                if not locked:
                    try:
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
                raw = None
                # RAW OCR ONLY ON A CARD THAT IS ACTUALLY LEGIBLE. On a LOCKED card the
                # game draws the name at sd 16-19, and tesseract returns confident junk
                # ('Dd', 'Bm --') that reads as a name. "locked" is both true and useful;
                # a two-letter fragment is neither.
                if nm is None and fitted_cell and locked is False:
                    nb = bg.name_box(frame, rows, row, col)
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
                if fitted_cell and not locked:
                    t = bg.read_card_type(frame, rows, row, col, ocr=_type_ocr)
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
                            cb = bg.card_box(frame, fitted, row, col)
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
                            # Every card sub-box, drawn from the LIVE EDITOR's working
                            # values so a nudge shows up on the next tick. The selected
                            # one is drawn thick, so you can see which keys move what.
                            for _k, _c in (("name", NAME), ("type", TYPE),
                                           ("power", POWER), ("shield", SHIELD)):
                                _b = _ebox(frame, fitted, row, col, _k)
                                if _b is not None:
                                    d.rectangle(_b, outline=_c,
                                                width=4 if _k == _sel_key() else 2)
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
                f"TYPE  typed {len(gott)}/{len(tys)}\n{_grid(tys)}\n"
                + _edit_panel()
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
        for c in range(5):
            b = bg.card_box(frame, rows, r, c)
            if b is not None:
                tiles.append((f"r{r}c{c}", frame.crop(b)))
    if not tiles:
        S["note"] = "no cards to sheet"
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


# ---------------------------------------------------------------- LIVE BOX EDITOR
# The user, 2026-09-13: "is it possible for you to make it so I can adjust the bounding
# boxes in real time? I would like to help adjust them."
#
# Every card sub-box is a fraction of the FITTED CARD BOX, so they are all the same kind
# of number and one editor tunes all four. The working values are drawn every tick, so a
# keypress shows on the live screen inside a frame. `w` writes them back into ban_grid.py,
# which this viewer WATCHES -- so the write re-execs the process and what you then see is
# the shipped constant, not a working copy. That closes the loop: nothing is tuned against
# a value the rest of the project does not have.
#
# It presses NOTHING at the console. Every key here edits numbers in this process.
_EDIT_KEYS = ["type", "power", "shield", "name"]
_EDIT_CONST = {"type": "TYPE_BANNER_BOX", "power": "POWER_DISC_BOX",
               "shield": "SHIELD_BOX", "name": "NAME_BANNER_BOX"}
E = {"i": 1, "step": 0.005, "vals": {}, "dirty": False, "msg": ""}


def _sel_key():
    return _EDIT_KEYS[E["i"]]


def _edit_load():
    E["vals"] = {k: list(getattr(bg, _EDIT_CONST[k])) for k in _EDIT_KEYS}
    E["dirty"] = False


_edit_load()


def _ebox(frame, fitted, row, col, key):
    """One sub-box from the editor's WORKING value, not from ban_grid's constant."""
    return bg._sub(frame, fitted, row, col, None, tuple(E["vals"][key]))


def _nudge(dx, dy, resize):
    v = E["vals"][_sel_key()]
    s = E["step"]
    if resize:                      # move only the far edges: width and height
        v[2] = round(v[2] + dx * s, 4)
        v[3] = round(v[3] + dy * s, 4)
    else:                           # slide the whole box
        v[0] = round(v[0] + dx * s, 4); v[2] = round(v[2] + dx * s, 4)
        v[1] = round(v[1] + dy * s, 4); v[3] = round(v[3] + dy * s, 4)
    E["dirty"] = True
    E["msg"] = ""


def _edit_write(_e=None):
    """Write the working values into ban_grid.py. The re-exec watcher does the rest.

    Anchored on the constant's exact current text and asserted before the file is touched
    (CLAUDE.md 10.19): a half-applied write to a module every reader imports is worse than
    no write at all.
    """
    path = os.path.join(_ROOT_DIR, "ban_grid.py")
    src = out = open(path, encoding="utf-8").read()
    wrote = []
    for k in _EDIT_KEYS:
        name = _EDIT_CONST[k]
        new_t = tuple(round(x, 4) for x in E["vals"][k])
        if tuple(getattr(bg, name)) == new_t:
            continue
        # ANCHOR ON THE ASSIGNMENT, NOT ON THE LITERAL'S FORMATTING. Matching the current
        # numbers as text worked exactly once: the first write reformats them, and the
        # second write then cannot find what it wrote. One regex per constant, and it must
        # match exactly once or nothing is written at all.
        pat = re.compile(r"^%s = \([^)]*\)" % re.escape(name), re.M)
        if len(pat.findall(out)) != 1:
            E["msg"] = f"NOT WRITTEN: {name} is not one plain assignment — edit by hand"
            return
        out = pat.sub("%s = (%s)" % (name, ", ".join(repr(x) for x in new_t)), out, count=1)
        wrote.append(name)
    if not wrote:
        E["msg"] = "nothing changed"
        return
    open(path, "w", encoding="utf-8").write(out)
    E["msg"] = f"wrote {', '.join(wrote)} to ban_grid.py — reloading"
    E["dirty"] = False


def _edit_reset(_e=None):
    _edit_load()
    E["msg"] = "working values back to what ban_grid.py says"


for _n in range(4):
    root.bind(f"<KeyPress-{_n + 1}>",
              lambda e, n=_n: (E.__setitem__("i", n), E.__setitem__("msg", "")))
root.bind("<Left>",  lambda e: _nudge(-1, 0, False))
root.bind("<Right>", lambda e: _nudge(+1, 0, False))
root.bind("<Up>",    lambda e: _nudge(0, -1, False))
root.bind("<Down>",  lambda e: _nudge(0, +1, False))
root.bind("<Shift-Left>",  lambda e: _nudge(-1, 0, True))
root.bind("<Shift-Right>", lambda e: _nudge(+1, 0, True))
root.bind("<Shift-Up>",    lambda e: _nudge(0, -1, True))
root.bind("<Shift-Down>",  lambda e: _nudge(0, +1, True))
root.bind("<KeyPress-bracketleft>",  lambda e: E.__setitem__("step", 0.002))
root.bind("<KeyPress-bracketright>", lambda e: E.__setitem__("step", 0.010))
root.bind("<KeyPress-w>", _edit_write)
root.bind("<KeyPress-0>", _edit_reset)

root.bind("<KeyPress-s>", save_sheet)
root.bind("<KeyPress-S>", save_sheet)
root.focus_force()

root.after(50, tick)
root.mainloop()
