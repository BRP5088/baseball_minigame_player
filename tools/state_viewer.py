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
import os, sys, re, argparse, time, tempfile, contextlib, tkinter as tk
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
            f"w write to ban_grid.py | 0 revert | c copy (drag to select, or all)"
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
LOCKED_WASH = (200, 40, 40)               # a locked card: nothing reads it, so it is washed
BAN, NAME = "#ff5ecb", "#8affff"          # ban-grid card box, and its name strip
FALLBACK = "#ff9d00"                      # the FIXED box, drawn when the fit failed
POWER, SHIELD = "#7CFC00", "#ffa8ff"      # the power disc and the shield badge
root = tk.Tk()
root.title("state — what the crawl reads")
root.attributes("-topmost", True)
lbl = tk.Label(root, bg="black"); lbl.pack()
# A SELECTABLE PANEL, not a Label. The user, 2026-09-13: "can you make it so I can copy
# values from the live viewer?" A tk.Label cannot be selected at all, so every number on it
# had to be retyped by hand.
#
# I SHIPPED IT DISABLED FIRST AND THAT KILLED THE SELECTION. The reasoning was that a
# disabled Text still selects with the mouse; on this Tk it does not, and the user found it
# in a minute: "It doesn't look like the PWR/SHD is working... I would also like to select
# a section to copy too."
#
# So it is NORMAL, and the keyboard is kept away from it a different way: takefocus=0 keeps
# Tab out, and a ButtonRelease hands focus straight back to root, so a click selects text
# and then stops being the focus. That matters because the box editor owns the arrow keys,
# and a focused Text would eat them to move an insertion cursor nobody can see. Anything
# typed into it is overwritten by the next tick anyway.
txt = tk.Text(root, font=("Menlo", 12), height=18, wrap="none", bd=0,
              takefocus=0, cursor="arrow")
txt.pack(fill="both", expand=True)


class _Panel:
    """Keeps txt.config(text=...) working over a Text widget, and remembers the text."""

    last = ""

    @staticmethod
    def config(text=""):
        _Panel.last = text
        sel = None
        try:                                  # do not destroy a selection mid-drag
            sel = (txt.index("sel.first"), txt.index("sel.last"))
        except tk.TclError:
            pass
        txt.delete("1.0", "end")
        txt.insert("1.0", text)
        if sel:
            try:
                txt.tag_add("sel", *sel)
            except tk.TclError:
                pass

    @staticmethod
    def cget(_what):
        return _Panel.last


def copy_panel(_e=None):
    """Copy the SELECTION if there is one, otherwise the whole panel.

    One behaviour on every key that means copy, so there is nothing to remember: drag a few
    lines and press c (or cmd-C) to get those lines, press it with nothing selected to get
    the lot. Bound on root rather than on the Text, because the Text deliberately does not
    hold focus and cmd-C is delivered to whatever does.
    """
    try:
        what = txt.get("sel.first", "sel.last")
    except tk.TclError:
        what = _Panel.last
    root.clipboard_clear()
    root.clipboard_append(what)
    root.update()                      # macOS needs this before the app can lose focus
    S["note"] = f"copied {len(what)} chars"
    return "break"
S = {"img": None, "slow": {}, "t": 0.0, "frame": None, "rows": None, "note": ""}


# ---------------------------------------------------------------- THE TWO DIGITS
# The user, 2026-09-13: "can you make the live viewer show the values so I can see if they
# are read correctly?" Showing them IS the instrument -- and it immediately corrected a
# figure I had reported. "1 of 7, confidently wrong" was measured on the OLD columns, where
# the power box sat a fifth of a card off on column 0, and at the worst PSM. Re-measured on
# the corrected geometry over 172 labelled owned cells (the label is the roster card that
# ocr_ban_card_name resolves from the NAME BANNER -- a different box, a different reader, at
# the other end of the card, so it is not this reader marking its own homework):
#
#     PSM 13   right 54   WRONG 19   out-of-range 23   abstained 76
#     PSM 10   right 61   WRONG  6   out-of-range 24   abstained 81
#     PSM  7   right 56   WRONG  4   out-of-range 20   abstained 92     <- shipped here
#
# "out-of-range" is the 4-9 rule doing work: power runs 4 to 9 and there is no 1, 2 or 3
# power card in the game (CLAUDE.md section 4), so a digit outside it is a known misread and
# is thrown away rather than printed.
#
# STILL NOT DECISION-GRADE. 4 wrong in the 60 it commits to is fine for a human reading a
# panel and nowhere near good enough to choose a ban in a $50 match, which is why this lives
# in the VIEWER and nothing imports it.
#
# THE SHIELD HAS NO READER AT ALL. local_hand.read_shield scores 0.31-0.42 against its own
# 0.69 gate here, so it answers 0 for every card; the reason is CLAUDE.md 10.30 -- it sizes
# its template from the FRAME width, which is right for a hand card and meaningless for a
# ban card, where the same sprite is drawn far smaller. A scale sweep lifts argmax to 2 of 7
# and it picks "1" every time: the bank holds 1, 2 and 3, has no 0 at all, and cannot
# separate them at this size.
#
# So these numbers carry a "?" prefix and MUST NOT be wired into a ban decision. A ban-scale
# template bank is being built as ban_digits.py; the moment it exists this picks it up.
def _digits(frame, rows, row, col, card=None):
    """(power, second, source) for one card. `card` is the roster card, if the name read.

    THE NAME IS THE READER. ocr_ban_card_name resolves the name banner to a roster
    PlayerCard, and that card ALREADY CARRIES power and secondary exactly -- so where the
    name reads there is nothing to OCR, and the digit reader is only for the cards it
    misses. That is not a shortcut, it is the more accurate path, and the evidence is a
    contact sheet: on every one of the 12 cells where the digit OCR contradicted the
    roster, the crop plainly showed the ROSTER's digit. Charlie Pepper is an 8 read as 5,
    Jenny Jody Gain a 6 read as 5, Johnny Drawers a 7 read as 9. The ball sprite clips the
    top-left of the disc and tesseract loses to it every time.
    ALL 12 DISAGREEMENTS WENT THE ROSTER'S WAY. Zero went the reader's.

    AND THE NAME MATCH IS SOUND, checked against something it cannot influence: the card's
    ROLE from simulate.CARD_POOL against the TYPE BANNER, read by a different reader from a
    different box. 129 of 129 agree, with zero violations of the range rule (a batter's
    secondary is never 0, a pitcher's never 3). If the name match were sloppy, that is
    where it would show.
    """
    if card is not None and getattr(card, "power", None) is not None:
        return str(card.power), str(card.secondary), "roster"
    try:
        import ban_digits as bd                     # the real bank, when it lands
    except Exception:
        bd = None
    if bd is not None:
        # ADVISORY UNTIL IT ANSWERS. The bank is being built as this runs, so a half-built
        # one must not silently replace the OCR fallback with a row of dashes -- an empty
        # answer and a working answer would look the same, which is 10.1's whole family.
        try:
            p, _ = bd.read_power(frame, rows, row, col)
            sh, _ = bd.read_shield(frame, rows, row, col)
        except Exception:
            p = sh = None
        if p is not None or sh is not None:
            return ("-" if p is None else str(p)), ("-" if sh is None else str(sh)), "bank"
    pb = bg.power_box(frame, rows, row, col)
    p = "-"
    if pb is not None:
        crop = frame.crop(pb).convert("L")
        if crop.width < 6 or crop.height < 6:
            return "-", "-", "ocr"
        up = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
        # THE FIRST MODE THAT ANSWERS IN RANGE WINS. One mode reaches 43% of cells; asking
        # three in order and stopping at the first in-range answer reaches 64% at the SAME
        # precision, for 1.93 OCR calls a cell. Measured over 118 labelled crops:
        #
        #     psm 10 alone            right 43  WRONG  8  abstain 50
        #     psm  7 alone            right 41  WRONG  4  abstain 59
        #     first-in-range 10,13,7  right 63  WRONG 12  abstain 43   84.0% precision
        #     majority of all three   right 45  WRONG  7  abstain 66   86.5% precision
        #
        # A vote buys nothing here -- precision is 84-86% however it is counted, so the
        # ceiling is tesseract on a 51x61 crop, not the counting. Reach is what a human
        # checking a panel wants, so reach is what this takes.
        for _psm in (10, 13, 7):
            raw = o._ocr_text(up, psm=_psm, whitelist="0123456789") or ""
            dig = "".join(ch for ch in raw if ch.isdigit())
            # POWER IS 4 TO 9 (CLAUDE.md section 4). There is no 1, 2 or 3 power card, so a
            # digit outside that range is a known misread -- 14-18 of 118 crops per mode --
            # and dropping it is what lets the next mode have a turn.
            if dig and 4 <= int(dig[0]) <= 9:
                p = "?" + dig[0]
                break
    # NO SHIELD READER EXISTS AT BAN SCALE. local_hand.read_shield answers 0 for every card
    # here (0.31-0.42 against its own 0.69 gate) and a scale sweep only reaches argmax 2 of
    # 7, always guessing "1". Printing 0 for everything would look like a reading; "-" is
    # the honest shape of "nobody asked a question that got an answer".
    return p, "-", "ocr"


def _tactics_bonus(frame, rows, row, col):
    """The +N badge on a TACTICS card. Its own box, top CENTRE, not the player disc."""
    bb = bg.tactics_bonus_box(frame, rows, row, col)
    if bb is None:
        return "-"
    crop = frame.crop(bb).convert("L")
    if crop.width < 6 or crop.height < 6:
        return "-"                     # leptonica prints "box outside rectangle" and
    up = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)   # answers anyway
    for _psm in (10, 13, 7):
        raw = o._ocr_text(up, psm=_psm, whitelist="0123") or ""
        dig = "".join(ch for ch in raw if ch.isdigit())
        # EVERY OWNED TACTICS CARD SHOWS A 1 -- 299 hand-labelled cards, zero 3s, and a +3
        # does not exist in the game (CLAUDE.md section 4). A 2 is possible only on POWER
        # SWING. Anything else is a misread.
        if dig and dig[0] in "12":
            return "+" + dig[0]
    return "-"


# ---------------------------------------------------------------- HOLD A GOOD READ
# The user, 2026-09-13: "sometimes I see them change while it's just idling." Filmed --
# twelve grabs of a screen nobody was touching, which is the only way to see this
# (CLAUDE.md 10.26) -- FOUR OF TEN CELLS CHANGED:
#
#     r0c1  pitcher x11, nothing x1
#     r1c1  SPEED BOOST x9, nothing x3
#     r1c4  PITCH FOCUS x8, nothing x4
#     r1c2  SPEED BOOST x6, LOCKED x6
#
# THE READER IS NOT CHANGING ITS MIND, IT IS INTERMITTENTLY ABSTAINING. The letters it does
# return are unambiguous: 'POWERSWING' at 0 edits, 'SPEEPBOOST' at 1, 'PITCHFOCUS' at 0,
# against 9-12 edits for every runner-up. So the answer is never in doubt when it arrives;
# some grabs just yield no letters at all.
#
# The last cell is a different fault: its card sd runs 32.7-35.8 and LOCKED_SD_MAX is 34.0,
# so it crosses the gate between grabs. A single frame cannot tell which side it is on --
# but a card whose LABEL READS is not locked, whatever its contrast says, so a successful
# read now outranks the sd.
#
# The rule is the project's own: local_hand_cards commits only to a hand that read twice
# running. Here a NEW answer has to appear twice before it replaces the held one, and an
# ABSTENTION never replaces anything. Cleared when the scroll level changes, because then
# the cards under these coordinates are genuinely different ones.
_STABLE = {"scroll": None, "held": {}, "cand": {}}


# LEPTONICA AND TK TALK TO fd 2 DIRECTLY, and python cannot see it to filter it. The user,
# 2026-09-13, pasting a live log: "Error in boxClipToRectangle: box outside rectangle" four
# times a tick, plus Tk's own "Task policy set failed: 4" on every reload. Neither is ours
# and neither means anything -- leptonica prints and then answers anyway.
#
# NOT a blanket redirect to /dev/null: that would swallow a real traceback, and a viewer
# that cannot report its own crash is how the last one died silently for an afternoon.
# fd 2 is captured for the duration of the OCR, then everything that is NOT on the mute
# list is written straight back out.
_MUTE = (b"boxClipToRectangle", b"pixScanForForeground", b"Task policy set failed",
         b"pixGetInvBackgroundMap", b"pixaGetPix")


@contextlib.contextmanager
def _quiet_ocr():
    tmp = tempfile.TemporaryFile(mode="w+b")
    saved = os.dup(2)
    os.dup2(tmp.fileno(), 2)
    try:
        yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        tmp.seek(0)
        for line in tmp.read().splitlines(True):
            if not any(m in line for m in _MUTE):
                os.write(2, line)
        tmp.close()


def _rowkey(rows):
    """A stable id for WHERE the grid is, used to clear the latch when it scrolls.

    NOT read_ban_scroll_level: it returns None often enough that keying on it would leave
    the latch never cleared, holding the previous page's names over the new page's cards --
    a stale answer that looks exactly like a confident one (CLAUDE.md 10.1).
    """
    if not rows:
        return None
    return tuple(round(r["top"], 2) for r in rows)


def _latch(key, value, scroll):
    """The value to SHOW for this cell: held unless a new one has been seen twice."""
    if scroll != _STABLE["scroll"]:
        _STABLE.update({"scroll": scroll, "held": {}, "cand": {}})
    held = _STABLE["held"].get(key)
    if value is None:                       # an abstention is not evidence of anything
        return held
    if value == held:
        _STABLE["cand"].pop(key, None)
        return held
    if _STABLE["cand"].get(key) == value:   # seen twice running -- believe it
        _STABLE["held"][key] = value
        _STABLE["cand"].pop(key, None)
        return value
    _STABLE["cand"][key] = value
    return held if held is not None else value


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
        names, types, locks, nums, cellrecs = [], [], [], [], []
        _scrollkey = _rowkey(rows)
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
                # is_locked STRADDLES ITS GATE on some cards -- one measured sd 32.7-35.8
                # against a LOCKED_SD_MAX of 34.0, so it answered True on half the grabs
                # and None on the rest. Latching the flag is the honest fix: a single frame
                # genuinely cannot say which side of the gate that card is on, so the
                # answer should not change unless two frames running agree it has.
                locked = _latch(key + ":locked", locked, _scrollkey)
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
                names.append((key, _latch(key + ":name",
                                          nm or (raw and raw.title()) or
                                          ("locked" if locked else None),
                                          _scrollkey)))
                # THE TYPE IS ITS OWN FIELD, not crammed into the name (the user,
                # 2026-09-13). "unknown" on a locked card is a real answer: the box is
                # right and the card simply cannot be read yet.
                t = None
                if fitted_cell and not locked:
                    t = bg.read_card_type(frame, rows, row, col, ocr=_type_ocr)
                # A READ DOES NOT BEAT `locked`, AND I TRIED IT. Letting a successful
                # banner read clear the locked flag put a THIRD "Power Swing" on a screen
                # that holds two -- a faded card returns junk, junk fuzzy-matches, and the
                # match is then dressed up as evidence. CLAUDE.md warns about this exact
                # move in section 3. The flicker is fixed by the latch instead, which costs
                # nothing and cannot invent a card.
                # LOCKED AND UNKNOWN ARE DIFFERENT ANSWERS. Locked means the card is there
                # and the game is drawing it faded; unknown means the reader failed. Saying
                # "unknown" for a locked card hides the fact that nothing is wrong.
                label = (t if isinstance(t, str)
                         else (t[1].title() if t else ("locked" if locked else None)))
                label = _latch(key + ":type", label, _scrollkey)
                types.append((key, label))
                locks.append((key, bool(locked)))
                if isinstance(t, tuple) and names[-1][1] is None:
                    names[-1] = (key, t[1].title())    # a tactics card names itself
                # ONE RECORD PER CELL, which is what the panel prints. A tactics card is a
                # DIFFERENT KIND with different boxes and different fields -- no name, no
                # shield, a bonus instead of a power -- so it gets its own branch rather
                # than empty columns under player headings.
                # UNKNOWN IS ITS OWN ANSWER, NOT "PLAYER". The user, 2026-09-13: "I see
                # a speed boost that switches from having a player name box to a tactics
                # name box... It seems like when it abstains, it defaults to the player.
                # maybe it should be a different state." Exactly right -- `None` was
                # falling through the draw's else branch and painting four player windows
                # over a tactics card. Latched too, so a single bad frame cannot flip it.
                kind = ("tactics" if isinstance(t, tuple)
                        else ("player" if isinstance(t, str) else None))
                kind = _latch(key + ":kind", kind, _scrollkey)
                rec = {"key": key, "kind": kind, "locked": bool(locked),
                       "name": names[-1][1], "type": label,
                       "power": "-", "second": "-", "src": ""}
                if locked or not fitted_cell:
                    rec["kind"] = "locked" if locked else None
                elif kind == "tactics":
                    # THE LABEL IS THE NAME. Printing "Speed Boost" under both card and
                    # type says nothing twice; the useful second column is the KIND.
                    rec["name"] = t[1].title() if isinstance(t, tuple) else rec["name"]
                    rec["type"] = "tactics"
                    rec["power"] = _tactics_bonus(frame, rows, row, col)
                    rec["src"] = "badge"
                else:
                    rec["power"], rec["second"], rec["src"] = _digits(
                        frame, rows, row, col, c)
                # THE NUMBERS ARE LATCHED TOO, and leaving them out was an oversight that
                # the user saw immediately: the badge box was swept to read 3 of 3 and then
                # showed "-" on the very next grab. The abstention is the PICTURE -- proved
                # by running the OCR 20 times on ONE crop and getting the identical answer
                # every time -- so a value that read once is better evidence than a blank
                # that arrived after it. "-" is converted to None first, or a failed read
                # would overwrite a good one.
                for _f in ("power", "second"):
                    _v = _latch(f"{key}:{_f}", None if rec[_f] == "-" else rec[_f],
                                _scrollkey)
                    rec[_f] = _v if _v is not None else "-"
                cellrecs.append(rec)
                nums.append((key, f"{rec['power']}/{rec['second']}"
                             if not locked else "locked"))
        out["ban_names"] = names
        out["ban_types"] = types
        # PUBLISHED SO THE DRAW CAN SEE IT. is_locked is already computed up there, once a
        # second; the draw runs at tick rate and must not recompute it, or the picture and
        # the panel can disagree about the same cell.
        out["ban_locked"] = locks
        out["ban_nums"] = nums
        out["ban_cells_full"] = cellrecs
        out["ban_kinds"] = [(r["key"], r.get("kind")) for r in cellrecs]
    return out


def tick():
    try:
        frame = o._fast_grab()
        crops = dict(o.crop_gameplay_regions(frame))
        hand = crops.get("hand")
        if not S["slow"] or time.time() - S["t"] > 1.0:
            with _quiet_ocr():
                S["slow"] = slow_read(frame, crops)
            S["t"] = time.time()
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
                        nm = dict(S["slow"].get("ban_names") or []).get(f"r{row}c{col}")
                        ty = dict(S["slow"].get("ban_types") or []).get(f"r{row}c{col}")
                        lk = dict(S["slow"].get("ban_locked") or []).get(f"r{row}c{col}")
                        if lk:
                            # A LOCKED CARD IS WASHED RED AND GETS NO READER BOXES. Nothing
                            # reads it -- the name and type OCR are both skipped upstream --
                            # so drawing their windows showed the user the aim of readers
                            # that never fire (their words, 2026-09-13: "I'm still seeing
                            # locked cards with OCR boxes ... the engine doesn't look at
                            # them but the live view does"). Blended, not filled: the card
                            # has to stay readable underneath, because the point of looking
                            # at the picture is to check the box is on the right card.
                            patch = frame.crop((x0, y0, x1, y1))
                            wash = Image.new("RGB", patch.size, LOCKED_WASH)
                            frame.paste(Image.blend(patch, wash, 0.38), (x0, y0))
                            d.rectangle((x0, y0, x1, y1), outline=LOCKED_WASH, width=3)
                            d.text((x0 + 4, y0 + 3), "locked", fill=LOCKED_WASH)
                            continue
                        d.rectangle((x0, y0, x1, y1), outline=colr, width=3)
                        d.text((x0 + 4, y0 + 3),
                               f"{nm or 'unknown'} [{ty or 'unknown'}]", fill=colr)
                        if fitted and row < len(fitted):
                            # THE BOXES FOLLOW THE KIND OF CARD. Drawing a player card's
                            # four windows over a tactics card shows the aim of readers
                            # that are not the ones running on it -- the tactics label sits
                            # below where the player ribbon box ends, and the bonus badge
                            # is top CENTRE where the power disc is top right.
                            _kind = dict(S["slow"].get("ban_kinds") or []).get(
                                f"r{row}c{col}")
                            if _kind == "tactics":
                                _set = (("tac_label", TYPE), ("tac_bonus", POWER))
                            elif _kind == "player":
                                _set = (("name", NAME), ("type", TYPE),
                                        ("power", POWER), ("shield", SHIELD))
                            else:
                                _set = ()      # KIND UNKNOWN: draw no reader windows at
                                               # all. Drawing the player set was a guess
                                               # wearing the same clothes as an answer.
                            for _k, _c in _set:
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

            # ONE LINE PER CARD, ALIGNED (the user, 2026-09-13: "can you make the live
            # viewer easier to read?"). Three stacked grids meant reading down three
            # separate blocks to assemble one card; this reads across.
            recs = sl.get("ban_cells_full") or []
            lines = [f"   cell   {'card':24s}  {'type':8s}  {'pwr':>4s} {'2nd':>4s}   from",
                     "   " + "-" * 60]
            last_row = None
            for r in recs:
                # A BLANK LINE BETWEEN THE TWO ROWS OF THE GRID (the user, 2026-09-13:
                # "can you add more spacing so it easier to tell the information between
                # the different cards apart?"). The grid IS two rows; the panel should
                # look like the screen.
                this_row = r["key"][1]
                if last_row is not None and this_row != last_row:
                    lines.append("")
                last_row = this_row
                if r.get("kind") == "locked":
                    lines.append(f"   {r['key']}   {'— locked —':24s}")
                    continue
                lines.append(
                    f"   {r['key']}   {(r.get('name') or 'unknown')[:24]:24s}  "
                    f"{(r.get('type') or 'unknown')[:8]:8s}  "
                    f"{r.get('power', '-'):>4s} {r.get('second', '-'):>4s}   "
                    f"{r.get('src', '')}")
            n_res = sum(1 for r in recs if r.get("src") == "roster")
            n_open = sum(1 for r in recs if r.get("kind") not in (None, "locked"))
            _Panel.config(text=(
                f"BAN SCREEN   banned {sl.get('banned')}/3   scroll {sl.get('scroll')}"
                f"   {fit}\n"
                f"from=roster means power and 2nd are the ROSTER's, exact. ocr = guessed, "
                f"84% right. {n_res}/{n_open} exact\n"
                + "\n".join(lines) + "\n"
                + _edit_panel()
                + (f"\n[s] {S['note']}" if S.get("note") else "\n[s] save a labelling sheet")))
        else:
            _Panel.config(text=(
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
        _Panel.config(text=f"{type(e).__name__}: {e}")
    if A.once:
        print(_Panel.cget("text"))
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
# SIX BOXES, BECAUSE THERE ARE TWO KINDS OF CARD. 1-4 are the player card's; 5 and 6 are
# the tactics card's, which sits in a different place entirely -- its label is centred at
# y 0.175-0.214 where the player ribbon is upper-left and ends at 0.13, and its badge is
# top CENTRE at x 0.43-0.62 where the player disc is top right at 0.72-0.94.
_EDIT_KEYS = ["type", "power", "shield", "name", "tac_label", "tac_bonus"]
_EDIT_CONST = {"type": "TYPE_BANNER_BOX", "power": "POWER_DISC_BOX",
               "shield": "SHIELD_BOX", "name": "NAME_BANNER_BOX",
               "tac_label": "TACTICS_TYPE_BOX", "tac_bonus": "TACTICS_BONUS_BOX"}
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


for _n in range(len(_EDIT_KEYS)):
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

txt.bind("<ButtonRelease-1>", lambda e: root.focus_set())
root.bind("<KeyPress-c>", copy_panel)
root.bind("<Command-c>", copy_panel)
root.bind("<Control-c>", copy_panel)
root.bind("<<Copy>>", copy_panel)
root.bind("<KeyPress-s>", save_sheet)
root.bind("<KeyPress-S>", save_sheet)
root.focus_force()

root.after(50, tick)
root.mainloop()
