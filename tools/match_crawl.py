"""CRAWL MODE -- step the match one action at a time, and SHOW EVERYTHING IT SAW.

Why this exists. Three times running I diagnosed a stall from the wrong frame: I grabbed a
screenshot after the loop had already moved on, or joined a log timestamp to the wrong video
frame, and each time the wrong frame read exactly as authoritative as the right one
(CLAUDE.md 10.15). The user was watching the actual stream and was right every time.

So this does not reconstruct anything. At every step it freezes, dumps the ONE frame it is
acting on, runs EVERY reader over that same frame, prints the lot, and waits. Nothing moves
until you say so. What is printed is what it saw -- if it is wrong, you can see that it is
wrong, and the frame that proves it is on disk next to the numbers.

USAGE, NON-INTERACTIVE (one Bash call = one step; this is what an agent debugging the
engine should drive):

    .venv/bin/python -B tools/match_crawl.py --session new --action look
    .venv/bin/python -B tools/match_crawl.py --session overnight/crawl/20260920_120301 --action enter
    .venv/bin/python -B tools/match_crawl.py --session <dir> --action d3 --dry
    .venv/bin/python -B tools/match_crawl.py --session <dir> --action p1+2
    .venv/bin/python -B tools/match_crawl.py --session <dir> --action "k confirm_play"
    .venv/bin/python -B tools/match_crawl.py --summary <dir>
    .venv/bin/python -B tools/match_crawl.py --sheet <dir>

  --session new|<dir>  'new' (default when omitted) starts a fresh
                       overnight/crawl/<stamp>/ directory; a path REUSES one and
                       continues its step numbering (NNN keeps counting up).
  --action ACTION      enter (do the engine's proposed play/discard) | look (read
                       only) | none | s (skip) | r (re-read) | p<slot> |
                       p<slot>+<tactics> | d<slot> | "k <key>" (quote it -- there
                       is a space before the key name, e.g. "k confirm_play")
  --dry                do everything except the press; the printed line and the
                       json both say what it WOULD have sent
  --allow-pay          acknowledge a money-gated action (start_match) -- it is
                       still refused; see apply_action()'s docstring for why
  --summary <dir>      one line per recorded step (action, screen, decision,
                       what changed), no capture -- review a session without
                       opening any file
  --sheet <dir>        tile the session's annotated before-frames into one
                       contact sheet, no capture

  Every step call: grabs ONE frame, runs every reader on it, runs the decision
  engine, prints what it saw and what it would do, presses the resolved action
  (unless --dry, or a reader/guard refuses it), grabs an AFTER frame, re-reads,
  and prints a DIFF of what changed. Writes NNN_before.png, NNN_before_annot.png,
  NNN.json always; NNN_after.png and NNN_after_annot.png too when something was
  pressed. Exit 0 on success, 2 when a reader/guard refused the action (message
  printed and in the json), 1 on error (including an unrecognised --action).

  REFUSES IMMEDIATELY under BASEBALL_TEST_RUN, before any capture -- crawl mode
  presses real keys at a real console and an offline test must never reach one.
  A test that means to exercise this module's OWN logic sets
  tools.match_crawl.CRAWL_DRIVE_IN_TESTS = True and stubs game_capture.grab /
  input_controller.press / select_and_play / select_and_discard directly, the
  same opt-in shape as this project's FOCUS_PRESS_IN_TESTS / RIG_DRIVER_IN_TESTS
  -- it does NOT unset the flag, so every other safety check still sees it.

INTERACTIVE (the original mode; still works, run with no flags):

    .venv/bin/python -B tools/match_crawl.py

  <enter>      do the proposed action
  s            skip it -- advance nothing, just re-read
  r            re-read: grab a FRESH frame and run every reader again, acting on nothing.
               Two reads of a still screen that disagree is a reader bug, not a timing bug.
  p<slot>      override: play that slot   (p3)
  p<slot>+<t>  play that slot WITH a tactics card  (p1+2)
  d<slot>      override: discard that slot (d1)
  k<key>       override: send one raw key (k confirm_play)
  n <text>     attach a note to this step -- it lands in the step's json
  q            quit

Every step writes overnight/crawl/<stamp>/NNN.png and NNN.json, so any step can be pulled up
later by number. It NEVER acts on its own: the only presses are ones you approve.
"""
import argparse
import os, sys, json, time, datetime, re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import orchestrator as o
import local_state as ls
import local_hand as lh

OUT = os.path.join(_ROOT, "overnight", "crawl",
                   datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))


# ---- THE SACRED LOCKOUT -----------------------------------------------------
# This used to `os.environ.pop("BASEBALL_TEST_RUN", None)` at import, "deliberately",
# so the tool would drive the console either way. That is exactly the shape CLAUDE.md
# 10.1 catalogues -- a guard that silently disables itself -- and it is also a FOURTH
# path to the console beyond the three CLAUDE.md already enumerates (keyboard, sticks,
# ensure_stream's recovery keys): crawl mode presses select_and_play/select_and_discard/
# press DIRECTLY. It now refuses instead of popping.
#
# A test that wants to exercise THIS FILE'S own logic (session bookkeeping, the diff,
# the annotation) sets this flag and stubs game_capture.grab / input_controller.press /
# select_and_play / select_and_discard so nothing real is ever reached -- the same
# opt-in shape as FOCUS_PRESS_IN_TESTS / RIG_DRIVER_IN_TESTS / DEAL_FRAMES_IN_TESTS
# elsewhere in this project. It never unsets BASEBALL_TEST_RUN, so every OTHER safety
# check in the process (the emission census, the three-path lockout) still sees it.
CRAWL_DRIVE_IN_TESTS = False


def _refuse_if_test_run():
    if os.environ.get("BASEBALL_TEST_RUN") and not CRAWL_DRIVE_IN_TESTS:
        raise RuntimeError(
            "REFUSING: BASEBALL_TEST_RUN is set. Crawl mode presses real keys at a "
            "real console and must never run under the offline flag -- see "
            "CLAUDE.md §5 'THE TEST-RUN LOCKOUT ONLY EVER COVERED THE TARGETED "
            "PATH' and 'THERE ARE THREE PATHS TO THE CONSOLE'. A test exercising "
            "this module's own logic sets tools.match_crawl.CRAWL_DRIVE_IN_TESTS = "
            "True and stubs the capture/press functions directly -- it does not "
            "unset the flag.")


def _try(fn, *a, **k):
    """Every reader is called behind this: one throwing must not hide the other twelve."""
    try:
        return fn(*a, **k), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def look(step):
    """Grab ONE frame and ask every reader about THAT frame. Returns (report, image)."""
    # THE GUARD SITS WHERE THE DAMAGE HAPPENS. The skeptic on this rebuild called
    # look() directly under BASEBALL_TEST_RUN and reached a real screen grab: the
    # entry-point refusals in run_one_step/main protected only the callers that
    # went through them. Capture has no lockout of its own, so this is its only one.
    _refuse_if_test_run()
    img = o._fast_grab()
    r = {"step": step, "t": time.time(),
         "clock": datetime.datetime.now().strftime("%H:%M:%S"), "size": list(img.size)}
    crops = dict(o.crop_gameplay_regions(img))

    res, err = _try(ls.read_result, img)
    r["result"] = ({"is_result": res["is_result"], "outcome": res["outcome"],
                    "words": {k: round(v, 3) for k, v in res["scores"].items()},
                    "why": res["why"]} if res else {"error": err})

    # OCR NAMES THE OUTCOME on a result screen -- templates only detect one. Shown here
    # beside the template scores so a disagreement between them is visible at the step it
    # happened, not inferred from a log afterwards.
    if res and res.get("is_result"):
        import result_ocr
        (r["ocr_outcome"], r["ocr_detail"]), r["ocr_err"] = _try(result_ocr.read_banner, img)
    else:
        r["ocr_outcome"] = r["ocr_detail"] = None

    r["ban_counter"], r["ban_err"] = _try(o.read_ban_counter, img)

    def _at_table(im):
        import table_prompt as tp
        return bool(tp.at_table(im))
    r["dealer_prompt"], r["dealer_err"] = _try(_at_table, img)

    hand = crops.get("hand")
    rows, err = _try(lh.read_hand, hand) if hand is not None else (None, "no hand crop")
    # read_hand's OWN key names. I printed "slot"/"power" here first and every row came back
    # None -- a display bug that looked exactly like a dead reader, which is the whole class
    # of mistake this tool exists to stop. The keys are digit/x/y; hand_index is assigned
    # later, by local_hand_cards.
    r["hand_rows"] = ([{k: row.get(k) for k in ("kind", "digit", "secondary", "type",
                                                "adds_power", "score", "x", "y",
                                                "y_measured")}
                       for row in rows] if rows else [])
    r["hand_err"] = err
    # WHERE THE CURSOR STARTS, recorded on EVERY step (the user's call, 2026-09-10:
    # "keep track of the starting position of the cursor from now on. I think it
    # always starts from slot 1"). Written to the step json so the claim is settled
    # by a tally rather than by recollection.
    #
    # `_boxes` is the ACTUAL sampled window per slot, not a re-derived guess at one --
    # annotate() draws these, so a wrong box is visible on the frame rather than
    # trusted from a formula that could silently drift from what cursor_glow used
    # (CLAUDE.md 10.23).
    boxes = []
    cg, r["cursor_err"] = (_try(lh.cursor_glow, hand, rows, _boxes=boxes) if hand is not None
                           else (None, "no hand crop"))
    r["cursor_index"] = cg[0] if cg else None
    r["cursor_glow"] = cg[1] if cg else None
    r["glow_boxes"] = boxes if hand is not None else []
    r["selected_cards"] = (sorted(lh.selected_cards(rows, hand.width / lh.ANCHOR_W))
                           if (hand is not None and rows) else [])
    cards, why = (o.local_hand_cards(hand) if hand is not None else (None, "no hand crop"))
    r["hand_usable"] = None if cards is None else len(cards)
    r["hand_why"] = why
    r["hand_cards"] = cards
    # AN INCOMPLETE HAND IS NOT THE SAME AS AN UNREAD ONE -- orchestrator's own
    # local_game_state distinguishes them the same way (bool(why)).
    r["hand_incomplete"] = bool(why)

    # THE STALL COUNTERS' STATE, so a hang like the discard-stall one CLAUDE.md
    # records (ten identical cycles, zero progress, no bound) is visible from the
    # FIRST step that reproduces it rather than after killing a run by hand.
    try:
        r["stall"] = {
            "discard_refused_n": o._DISCARD_STALL.get("n"),
            "discard_stalled": (o.discard_stalled(cards) if cards else None),
            "play_refused_n": o._PLAY_STALL.get("n"),
            "play_stalled": (o.play_stalled(cards) if cards else None),
            "play_excluded": sorted(o._PLAY_STALL.get("excluded") or []),
        }
    except Exception as e:
        r["stall"] = {"error": f"{type(e).__name__}: {e}"}

    ph, err = _try(ls.read_phase, hand) if hand is not None else (None, "no hand crop")
    r["phase"] = ph[0] if isinstance(ph, tuple) else ph
    r["phase_err"] = err

    sb = crops.get("scoreboard")
    if sb is not None:
        d = {}
        r["discards_left"], r["discards_err"] = _try(ls.read_discards_left, sb, d)
        r["discards_detail"] = {k: d.get(k) for k in ("why", "round", "discard", "panel_gap")}
        sc, err = _try(o.ocr_scoreboard, sb)
        r["scoreboard"] = sc
        r["scoreboard_err"] = err

    bases = ("third_base", "second_base", "first_base")
    # RECORDED BESIDE THE READING, because a crawl row is read later by someone who cannot
    # see the frame. On a ban screen the base crops are grid CARDS and read as runners with
    # real badges (orchestrator.on_turn_screen carries the census); a row with
    # on_turn_screen False must not be counted as diamond evidence.
    r["on_turn_screen"] = o.on_turn_screen(crops.get("hand"))
    if all(crops.get(b) is not None for b in bases):
        run, err = _try(ls.read_runners, *[crops[b] for b in bases])
        r["runners"] = ({"count": run["count"], "speeds": run["speeds"],
                         "bases": {k: {"occupied": v["occupied"], "power": v["power"],
                                       "speed": v["speed"], "speed_score": v["speed_score"],
                                       "why": v["why"]}
                                   for k, v in run["bases"].items()}} if run else {"error": err})

    st, gap = _try(o.local_game_state)
    if st and st[0]:
        r["local_game_state"] = {"screen": st[0].get("screen"),
                                 "result_outcome": st[0].get("result_outcome")}
    else:
        r["local_game_state"] = {"screen": None,
                                 "gap": (st[1] if st else gap)}
    return r, img


def show(r):
    print("\n" + "=" * 78)
    print(f"STEP {r['step']}   {r['clock']}   capture {r['size'][0]}x{r['size'][1]}")
    print("=" * 78)
    g = r["local_game_state"]
    print(f"  SCREEN         : {g.get('screen')!r}" + (f"   gap: {g['gap']}" if g.get("gap") else ""))
    res = r.get("result", {})
    if "words" in res:
        print(f"  result word    : templates {res['outcome']!r}  is_result={res['is_result']}  {res['words']}")
        if res.get("is_result"):
            print(f"  result OCR     : {r.get('ocr_outcome')!r}   read {r.get('ocr_detail')!r}"
                  + ("   <-- DISAGREES WITH THE TEMPLATES"
                     if r.get("ocr_outcome") and res.get("outcome")
                     and r["ocr_outcome"] != res["outcome"] else ""))
    print(f"  ban counter    : {r.get('ban_counter')!r}      dealer prompt: {r.get('dealer_prompt')!r}")
    print(f"  phase          : {r.get('phase')!r}        discards_left: {r.get('discards_left')!r}"
          f"   scoreboard: {r.get('scoreboard')}")
    run = r.get("runners") or {}
    if "count" in run:
        occ = {k: v["occupied"] for k, v in run["bases"].items()}
        print(f"  runners        : count={run['count']}  speeds={run.get('speeds')}  {occ}")
    print(f"  CURSOR         : index {r.get('cursor_index')!r}   glow {r.get('cursor_glow')}"
          f"   lifted {r.get('selected_cards')}")
    print(f"  HAND           : read_hand {len(r['hand_rows'])} row(s); "
          f"usable {r['hand_usable']}   incomplete={r.get('hand_incomplete')}   why: {r['hand_why']}")
    for i, row in enumerate(r["hand_rows"]):
        print(f"      pos {i}  {str(row['kind']):8s} digit={str(row.get('digit')):4s} "
              f"secondary={str(row.get('secondary')):4s} type={str(row.get('type')):12s} "
              f"score={row.get('score')} @({row['x']},{row['y']})"
              f" y_measured={row.get('y_measured')}")
    for c in (r.get("hand_cards") or []):
        print(f"      -> hand_index {c.get('hand_index')}  {c.get('kind'):8s} "
              f"power={str(c.get('power')):4s} secondary={str(c.get('secondary')):4s} "
              f"bonus={c.get('bonus')}")
    stall = r.get("stall") or {}
    if stall.get("discard_stalled") or stall.get("play_stalled"):
        print(f"  STALL          : discard_stalled={stall.get('discard_stalled')}"
              f" ({stall.get('discard_refused_n')})   play_stalled={stall.get('play_stalled')}"
              f" ({stall.get('play_refused_n')})   excluded={stall.get('play_excluded')}")
    for k in ("hand_err", "ban_err", "dealer_err", "phase_err", "discards_err", "scoreboard_err"):
        if r.get(k):
            print(f"  ! {k}: {r[k]}")


def propose(r):
    """What it WOULD do. Never executed without approval. Attaches r["decision"]
    -- the raw engine output, not just the printed sentence -- so a session's
    json holds the decision/reasoning/should_redraw a human reading it later
    cannot re-derive from the text alone."""
    r["decision"] = None
    if r["local_game_state"].get("screen") != "turn" or not r.get("hand_cards"):
        return None, "not a readable turn -- nothing proposed"
    try:
        from decision_engine import (GameState, PlayerCard, TacticsCard, TacticsType,
                                     best_batting_play, best_pitching_play, should_redraw)
        players, tactics = [], []
        for c in r["hand_cards"]:
            if c.get("kind") == "tactics":
                # THE REAL KIND. Hardcoding SWING_BOOST here made crawl propose a SPEED boost
                # while calling it a swing boost -- and only SWING_BOOST and PITCH_BOOST add
                # power (CLAUDE.md 4), so that is the difference between a boost that helps
                # and one that does nothing. Production reads c["type"]; so does this now.
                try:
                    kind = TacticsType(c.get("type"))
                except Exception:
                    kind = None
                if kind is None:
                    continue          # an unread kind is not guessed
                tactics.append(TacticsCard(name=c.get("name") or c.get("type") or "?",
                                           bonus=c.get("bonus") or 0, kind=kind))
            else:
                # NAME CARRIES THE SLOT, so the engine's own answer can be mapped
                # back without searching by power. The engine tie-breaks equal-power
                # cards on `secondary`, so "the first card of this power" is a
                # DIFFERENT card from the one it chose whenever two share a power.
                players.append(PlayerCard(name=str(c.get("hand_index")),
                                          power=c.get("power") or 0,
                                          secondary=c.get("secondary") or 0))
        sc = r.get("scoreboard") or {}
        # REFUSE AN UNREAD PHASE rather than defaulting to "batting". The default is
        # a whole STRATEGY: while pitching it runs best_batting_play and proposes the
        # wrong kind of card. orchestrator.local_game_state refuses for this reason.
        if r.get("phase") is None:
            return None, "phase not read -- not proposing a play"
        st = GameState(half=r["phase"], batters_used=0,
                       your_score=(sc.get("your") or [0])[-1] or 0,
                       opp_score=(sc.get("opponent") or [0])[-1] or 0,
                       runners=[], redraws_left=r.get("discards_left") or 0)
        d = (best_batting_play(players, tactics, st) if st.half == "batting"
             else best_pitching_play(players, tactics, st))
        # MAP THE CHOSEN CARD BACK TO A SLOT. The engine returns a card, the cursor needs a
        # position, and that translation is exactly where a play can go to the wrong place --
        # so it is printed, every step, next to the card it came from.
        try:
            slot = int(d.player_card.name)
        except (TypeError, ValueError):
            slot = None
        redraw = should_redraw(players, st)
        r["decision"] = {"should_redraw": redraw, "redraws_left": r.get("discards_left") or 0,
                         "play_slot": slot, "play_power": d.player_card.power,
                         "tactics": str(d.tactics_card), "reasoning": d.reasoning}
        if redraw and (r.get("discards_left") or 0) > 0:
            # (power, secondary), matching orchestrator's discard picker -- power
            # alone settles a tie by SLOT ORDER and throws the better weak card.
            weakest = min(players, key=lambda p: (p.power, p.secondary))
            for c in r["hand_cards"]:
                if c.get("hand_index") == int(weakest.name):
                    r["decision"]["kind"] = "discard"
                    r["decision"]["slot"] = c.get("hand_index")
                    r["decision"]["discard_power"] = weakest.power
                    return ("discard", c.get("hand_index")), (
                        f"DISCARD slot {c.get('hand_index')} (power {weakest.power}) -- "
                        f"hand is weak, {r.get('discards_left')} discard(s) left")
        r["decision"]["kind"] = "play"
        r["decision"]["slot"] = slot
        return ("play", slot), (f"PLAY slot {slot} (power {d.player_card.power}, "
                                f"tactics {d.tactics_card}) -- {d.reasoning}")
    except Exception as e:
        r["decision"] = {"error": f"{type(e).__name__}: {e}"}
        return None, f"could not build a decision ({type(e).__name__}: {e})"


# ---- ANNOTATION --------------------------------------------------------------
# The colours and the box math are state_viewer's, not re-derived -- CLAUDE.md
# 10.23's whole lesson is a reader cropping the wrong pixels reporting that as "I
# am not sure", and a SECOND, independently-computed box is exactly how an
# annotation drifts from what the reader actually looked at without anyone
# noticing. `_boxes`/`glow` come straight from lh.cursor_glow's own call.
_CUR, _SEL, _BOX, _REG = "#00ff66", "#ff3b30", "#ffcc00", "#4da3ff"
_ANCHOR = "#707078"


def annotate(img, r):
    """Draw what every reader was shown and decided, straight onto the frame it
    acted on. One picture must be able to explain a wrong read."""
    from PIL import ImageDraw
    canvas = img.convert("RGB").copy()
    d = ImageDraw.Draw(canvas)
    fw, fh = img.size
    for name, frac in o.GAMEPLAY_REGIONS_FRAC.items():
        x0, y0 = int(fw * frac[0]), int(fh * frac[1])
        x1, y1 = int(fw * frac[2]), int(fh * frac[3])
        d.rectangle((x0, y0, x1, y1), outline=_REG, width=2)
        d.text((x0 + 3, y0 + 2), name, fill=_REG)
    hf = o.GAMEPLAY_REGIONS_FRAC["hand"]
    ox, oy = int(fw * hf[0]), int(fh * hf[1])

    # slot ANCHORS -- where the reader expects a card to rest, drawn even when
    # nothing was found there, because the gap between an anchor and a found
    # disc is the whole story on a wrongly-cropped card.
    sc = (img.width / lh.ANCHOR_W) if img.width else 1.0
    for ax, ay in lh.SLOT_PLAYER:
        px, py = int(ax * sc) + ox, int(ay * sc) + oy
        d.line((px - 6, py, px + 6, py), fill=_ANCHOR, width=1)
        d.line((px, py - 6, px, py + 6), fill=_ANCHOR, width=1)

    cur = r.get("cursor_index")
    sel = set(r.get("selected_cards") or [])
    glow = r.get("cursor_glow") or []
    for i, box in enumerate(r.get("glow_boxes") or []):
        if box is None:
            continue
        col = _CUR if i == cur else (_SEL if i in sel else _BOX)
        b = (box[0] + ox, box[1] + oy, box[2] + ox, box[3] + oy)
        d.rectangle(b, outline=col, width=3)
        g = glow[i] if i < len(glow) else None
        tag = ("  CURSOR" if i == cur else "") + ("  LIFTED" if i in sel else "")
        d.text((b[0], max(0, b[1] - 14)), f"{i}: {g}%{tag}", fill=col)

    # the found disc (x, y) and what it read
    for i, row in enumerate(r.get("hand_rows") or []):
        x, y = row.get("x"), row.get("y")
        if x is None or y is None:
            continue
        px, py = x + ox, y + oy
        d.ellipse((px - 6, py - 6, px + 6, py + 6), outline="#ffffff", width=2)
        label = (f"{row.get('kind')}:{row.get('digit')}" if row.get("kind") == "player"
                 else f"{row.get('kind')}:{row.get('type')}")
        d.text((px + 8, py - 8), f"{label} s={row.get('score')}", fill="#ffffff")
    return canvas


# ---- DIFFING ------------------------------------------------------------------
def _hand_digest(r):
    return [(row.get("kind"), row.get("digit"), row.get("type"), row.get("secondary"))
           for row in (r.get("hand_rows") or [])]


def _runner_digest(r):
    bases = (r.get("runners") or {}).get("bases") or {}
    return {k: {"occupied": v.get("occupied"), "power": v.get("power"),
               "speed": v.get("speed")} for k, v in bases.items()}


# What a step is judged to have changed. Deliberately a curated list, not
# "every key" -- most keys (clock, size, t) change on every step by construction
# and a diff of those would bury the one that matters.
WATCHED_FIELDS = [
    ("screen", lambda r: (r.get("local_game_state") or {}).get("screen")),
    ("ban_counter", lambda r: r.get("ban_counter")),
    ("dealer_prompt", lambda r: r.get("dealer_prompt")),
    ("phase", lambda r: r.get("phase")),
    ("discards_left", lambda r: r.get("discards_left")),
    ("scoreboard", lambda r: r.get("scoreboard")),
    ("cursor_index", lambda r: r.get("cursor_index")),
    ("selected_cards", lambda r: r.get("selected_cards")),
    ("hand_usable", lambda r: r.get("hand_usable")),
    ("hand_digest", _hand_digest),
    ("runners", _runner_digest),
    ("result_outcome", lambda r: (r.get("result") or {}).get("outcome")),
]


def diff_reports(before, after):
    """{name: {"before": ..., "after": ...}} for every WATCHED_FIELDS entry that
    changed between two look() reports. Never raises: a field whose extractor
    throws is reported as a diff rather than crashing the step."""
    out = {}
    for name, fn in WATCHED_FIELDS:
        try:
            b, a = fn(before), fn(after)
        except Exception as e:
            out[name] = {"error": f"{type(e).__name__}: {e}"}
            continue
        if b != a:
            out[name] = {"before": b, "after": a}
    return out


# ---- SESSION BOOKKEEPING -------------------------------------------------------
_STEP_RE = re.compile(r"^(\d{3})_before\.png$")


def _next_step(session_dir):
    """The next NNN for this session dir, continuing a resumed one rather than
    overwriting it -- match_crawl.py wrote step001.jpg over an earlier run's
    before this file's own crawl.py sibling learned that lesson; step numbers in
    a session must be unique on disk for the same reason a labelled crawl row
    must be."""
    if not os.path.isdir(session_dir):
        return 1
    nums = [int(m.group(1)) for fn in os.listdir(session_dir)
           for m in (_STEP_RE.match(fn),) if m]
    return (max(nums) + 1) if nums else 1


def resolve_session(session_arg):
    """'new'/None -> a fresh timestamped dir under overnight/crawl/; anything
    else is a path, relative to the repo root unless already absolute, and is
    REUSED (continuing its step numbering) rather than recreated."""
    if not session_arg or session_arg == "new":
        d = os.path.join(_ROOT, "overnight", "crawl",
                         datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    elif os.path.isabs(session_arg):
        d = session_arg
    else:
        d = os.path.join(_ROOT, session_arg)
    os.makedirs(d, exist_ok=True)
    return d


# ---- ACTING ---------------------------------------------------------------------
def _money_guard(key, allow_pay):
    """None if `key` is not money-gated; otherwise the refusal message.

    start_match pays $50. orchestrator.run()'s debit bookkeeping -- balance,
    max_spend, save_progress, match_in_progress, debited_this_process -- is
    ~200 lines inline inside its poll loop (orchestrator.py, the
    "match_start_prompt" branch), not a function this tool can call, and crawl
    mode may not edit orchestrator.py to extract one. So this refuses rather
    than pressing the key blind and leaving a real $50 untracked -- exactly the
    failure CLAUDE.md's OPEN-25 spent a session on ("A STALE match_in_progress
    SPENDS AN UNTRACKED $50"). --allow-pay does not change the answer; it only
    changes which sentence explains it, so the refusal is never silently a
    missing flag.
    """
    if key.strip().lower() != "start_match":
        return None
    if not allow_pay:
        return ("start_match pays $50 and is refused without --allow-pay.")
    return ("start_match pays $50. Even with --allow-pay this refuses: the debit "
            "bookkeeping lives inline inside orchestrator.run()'s poll loop, not "
            "in a reusable function, and crawl mode may not edit orchestrator.py "
            "to extract one. Start a real match through run(), not through here.")


def apply_action(cmd, r, dec, dry=False, allow_pay=False):
    """Resolve one ACTION into a press, or a documented refusal. Returns
    {"acted": str, "pressed": bool, "refused": bool, "refusal_reason": str|None}.

    Never calls select_and_play/select_and_discard directly -- always
    spend_and_play/spend_and_discard, so forget_hand_slot runs and the
    disk-persisted hand memory does not go stale on the very next crawl process
    (tests/harness/test_tools_spend_properly.py's whole-tools scan enforces
    exactly this for every file under tools/).
    """
    _refuse_if_test_run()   # same reason as look(): presses have input_controller's
                            # own lockout behind them, but the refusal belongs here too

    cmd = (cmd or "").strip()
    out = {"acted": None, "pressed": False, "refused": False, "refusal_reason": None}

    if cmd in ("", "enter"):
        if dec is None:
            out["acted"] = "no proposal to act on"
            return out
        kind, slot = dec
        if slot is None:
            out["refused"] = True
            out["refusal_reason"] = ("PROPOSAL HAS NO SLOT -- the chosen card was "
                                     "not found in the hand")
            out["acted"] = out["refusal_reason"]
            return out
        if dry:
            out["acted"] = f"DRY: would select_and_{kind}({slot})"
            return out
        out["pressed"] = True
        ok, why = (o.spend_and_discard(slot) if kind == "discard"
                  else o.spend_and_play(slot))
        out["acted"] = (f"select_and_{kind}({slot})"
                        + (" -> COMMITTED" if ok else f" -> REFUSED ({why})"))
        if not ok:
            out["refused"] = True
            out["refusal_reason"] = why
        return out

    if cmd == "s":
        out["acted"] = "skipped"
        return out
    if cmd == "r":
        out["acted"] = "re-read only"
        return out
    if cmd in ("none", "look"):
        out["acted"] = f"{cmd} -- no press"
        return out

    if cmd.startswith("p") and "+" in cmd and all(
            x.strip().isdigit() for x in cmd[1:].split("+", 1)):
        # p<slot>+<tactics> -- ONLY SWING_BOOST/PITCH_BOOST add power (CLAUDE.md 4),
        # so attaching the right tactic is worth a whole point of power.
        _p, _t = (int(x) for x in cmd[1:].split("+", 1))
        if dry:
            out["acted"] = f"DRY: would select_and_play({_p}, tactics={_t})"
            return out
        out["pressed"] = True
        ok, why = o.spend_and_play(_p, _t)
        out["acted"] = (f"select_and_play({_p}, tactics={_t})"
                        + (" -> COMMITTED" if ok else f" -> REFUSED ({why or 'nothing committed'})"))
        if not ok:
            out["refused"] = True
            out["refusal_reason"] = why or "nothing committed"
        return out

    if cmd.startswith("p") and cmd[1:].strip().isdigit():
        s = int(cmd[1:])
        if dry:
            out["acted"] = f"DRY: would select_and_play({s})"
            return out
        out["pressed"] = True
        ok, why = o.spend_and_play(s)
        out["acted"] = f"select_and_play({s})" + (" -> COMMITTED" if ok else f" -> REFUSED ({why})")
        if not ok:
            out["refused"] = True
            out["refusal_reason"] = why
        return out

    if cmd.startswith("d") and cmd[1:].strip().isdigit():
        s = int(cmd[1:])
        if dry:
            out["acted"] = f"DRY: would select_and_discard({s})"
            return out
        out["pressed"] = True
        ok, why = o.spend_and_discard(s)
        out["acted"] = f"select_and_discard({s})" + (" -> COMMITTED" if ok else f" -> REFUSED ({why})")
        if not ok:
            out["refused"] = True
            out["refusal_reason"] = why
        return out

    if cmd.startswith("k "):
        key = cmd[2:].strip()
        money = _money_guard(key, allow_pay)
        if money:
            out["refused"] = True
            out["refusal_reason"] = money
            out["acted"] = f"press({key}) -> REFUSED"
            return out
        if dry:
            out["acted"] = f"DRY: would press({key})"
            return out
        out["pressed"] = True
        o.press(key)
        out["acted"] = f"press({key})"
        return out

    raise ValueError(f"unrecognised action {cmd!r} -- expected enter/look/none/s/r/"
                     f"p<slot>/p<slot>+<tactics>/d<slot>/'k <key>'")


# ---- THE ONE-STEP ENTRY --------------------------------------------------------
def run_one_step(session_dir, action, dry=False, allow_pay=False):
    """One Bash call, one step: look, propose, act (maybe), look again (if
    something was pressed), diff, write, print. Returns (exit_code, report)."""
    _refuse_if_test_run()
    os.makedirs(session_dir, exist_ok=True)
    step = _next_step(session_dir)
    prefix = os.path.join(session_dir, f"{step:03d}")
    t0 = time.time()

    r, img = look(step)
    r["session"] = session_dir
    img.save(prefix + "_before.png")
    try:
        annotate(img, r).save(prefix + "_before_annot.png")
    except Exception as e:
        print(f"  annot          : could not render ({type(e).__name__}: {e})")
    show(r)
    dec, why = propose(r)
    print(f"\n  PROPOSED       : {why}")

    import input_controller as _ic
    counts_before = list(_ic.press_path_counts())
    r["command"] = action
    r["dry"] = dry
    exit_code = 0
    try:
        result = apply_action(action, r, dec, dry=dry, allow_pay=allow_pay)
    except ValueError as e:
        exit_code = 1
        r["acted"] = None
        r["error"] = str(e)
        print(f"  ERROR          : {e}")
        result = {"pressed": False, "refused": False, "refusal_reason": None}
    else:
        r["acted"] = result["acted"]
        if result["acted"]:
            print(f"  -> {result['acted']}")
        if result["refused"]:
            exit_code = 2
            print(f"  REFUSED        : {result['refusal_reason']}")

    r["press_path_counts"] = {"before": counts_before, "after": list(_ic.press_path_counts())}

    if result.get("pressed"):
        time.sleep(1.5)
        after_r, after_img = look(step)
        after_img.save(prefix + "_after.png")
        try:
            annotate(after_img, after_r).save(prefix + "_after_annot.png")
        except Exception as e:
            print(f"  after annot    : could not render ({type(e).__name__}: {e})")
        diff = diff_reports(r, after_r)
        r["after"] = after_r
        r["diff"] = diff
        print("\n  DIFF (before -> after):")
        if diff:
            for k, v in diff.items():
                print(f"    {k}: {v.get('before')!r} -> {v.get('after')!r}")
        else:
            print("    nothing changed")

    r["timing"] = {"total_s": round(time.time() - t0, 3)}
    with open(prefix + ".json", "w") as fh:
        json.dump(r, fh, indent=1, default=str)
    print(f"\n  step json      : {prefix}.json")
    return exit_code, r


def summarize_session(session_dir):
    """One line per recorded step -- action, screen, what it did, what changed.
    Reads only the jsons already on disk; no capture."""
    if not os.path.isabs(session_dir):
        session_dir = os.path.join(_ROOT, session_dir)
    if not os.path.isdir(session_dir):
        print(f"no such session dir: {session_dir}")
        return
    files = sorted(f for f in os.listdir(session_dir) if re.match(r"^\d{3}\.json$", f))
    if not files:
        print(f"no steps recorded in {session_dir}")
        return
    for fn in files:
        with open(os.path.join(session_dir, fn)) as fh:
            r = json.load(fh)
        screen = (r.get("local_game_state") or {}).get("screen")
        acted = r.get("acted") or "(no action)"
        diff = r.get("diff") or {}
        changed = ",".join(sorted(diff.keys())) if diff else "-"
        print(f"{r.get('step', '?'):>3}  cmd={r.get('command', '')!r:16s} "
              f"screen={str(screen):10s} acted={acted[:55]:55s} changed=[{changed}]")


def build_contact_sheet(session_dir):
    """Tile every recorded step's annotated before-frame into one contact sheet.

    Reuses crawl_sheet's own thumbnail resizer (`panel`) rather than a second,
    independently-tuned one -- and deliberately does NOT call crawl_sheet.build()
    here: that function grabs a fresh frame (and now refuses to under
    BASEBALL_TEST_RUN) when none is supplied, which this function has no frame
    to give it -- it only tiles PNGs already on disk.
    """
    if not os.path.isabs(session_dir):
        session_dir = os.path.join(_ROOT, session_dir)
    if not os.path.isdir(session_dir):
        print(f"no such session dir: {session_dir}")
        return None
    from PIL import Image, ImageDraw
    from crawl_sheet import panel
    steps = sorted(f for f in os.listdir(session_dir) if _STEP_RE.match(f))
    if not steps:
        print(f"no steps recorded in {session_dir}")
        return None
    thumbs = []
    for fn in steps:
        num = fn[:3]
        annot = os.path.join(session_dir, f"{num}_before_annot.png")
        src = annot if os.path.exists(annot) else os.path.join(session_dir, fn)
        thumbs.append((num, panel(Image.open(src), 480)))
    cols = 3
    cw, ch = thumbs[0][1].size
    pad, label_h = 8, 22
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cw + pad) + pad, rows * (ch + label_h + pad) + pad),
                      (10, 10, 12))
    d = ImageDraw.Draw(sheet)
    for i, (num, im) in enumerate(thumbs):
        row, col = divmod(i, cols)
        x = pad + col * (cw + pad)
        y = pad + row * (ch + label_h + pad)
        sheet.paste(im, (x, y))
        d.text((x, y + ch + 2), f"step {num}", fill=(230, 230, 230))
    out = os.path.join(session_dir, "contact_sheet.png")
    sheet.save(out)
    print(f"contact sheet -> {out}")
    return out


# ---- INTERACTIVE MODE (unchanged behaviour, sharing apply_action/annotate) ----
def main():
    _refuse_if_test_run()
    print(__doc__)
    print(f"steps -> {OUT}\n")
    os.makedirs(OUT, exist_ok=True)
    step = 0
    while True:
        step += 1
        r, img = look(step)
        img.save(os.path.join(OUT, f"{step:03d}.png"))
        show(r)
        try:
            annotate(img, r).save(os.path.join(OUT, f"{step:03d}_annot.png"))
        except Exception as e:
            print(f"  annot          : could not render ({type(e).__name__}: {e})")
        # A LABELLED SHEET FOR EVERY STEP, rendered from THIS step's frame. crawl_sheet
        # no longer touches BASEBALL_TEST_RUN at all (it used to pop it unconditionally
        # at import) -- passing `img` here means build() never reaches its own capture
        # guard, so no save/restore dance is needed any more.
        try:
            import crawl_sheet
            sheet = crawl_sheet.build(img, os.path.join(OUT, f"{step:03d}_sheet.png"))
            r["sheet"] = sheet
            print(f"  sheet          : {sheet}")
        except Exception as e:
            print(f"  sheet          : could not render ({type(e).__name__}: {e})")
        dec, why = propose(r)
        print(f"\n  PROPOSED       : {why}")
        try:
            cmd = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            cmd = "q"
        r["command"] = cmd
        if cmd == "q":
            json.dump(r, open(os.path.join(OUT, f"{step:03d}.json"), "w"), indent=1, default=str)
            print("  bye"); return
        if cmd.startswith("n "):
            r["note"] = cmd[2:].strip(); print(f"  noted: {r['note']}")
        else:
            result = apply_action(cmd, r, dec, dry=False, allow_pay=False)
            r["acted"] = result["acted"]
            # DID IT LAND? Compare the frame before against the frame after, on the
            # SAME measure the deal gate uses, so a press that changed nothing is
            # visible immediately rather than 35s later.
            if result["pressed"]:
                time.sleep(1.5)
                after = o._fast_grab()
                after.save(os.path.join(OUT, f"{step:03d}_after.png"))
                try:
                    d0 = o._mean_abs_delta(dict(o.crop_gameplay_regions(img)).get("hand"),
                                           dict(o.crop_gameplay_regions(after)).get("hand"))
                    r["hand_delta_after_press"] = round(float(d0), 1)
                    print(f"  -> hand delta after the press: {d0:.1f} "
                          f"({'SOMETHING MOVED' if d0 >= 15 else 'NOTHING MOVED -- the press did not land'})")
                except Exception as e:
                    r["hand_delta_after_press"] = f"error: {e}"
            if result["refused"]:
                print(f"  REFUSED        : {result['refusal_reason']}")
            if result["acted"]:
                print(f"  -> {result['acted']}")
        json.dump(r, open(os.path.join(OUT, f"{step:03d}.json"), "w"), indent=1, default=str)


def cli_main(argv=None):
    ap = argparse.ArgumentParser(
        description="Crawl mode: one match action per invocation, every reader on "
                    "the frame it acted on.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", default=None,
                    help="session dir (relative to the repo root, or absolute), "
                         "or 'new'/omitted for a fresh overnight/crawl/<stamp>/")
    ap.add_argument("--action", default=None,
                    help="enter | look | none | s | r | p<slot> | p<slot>+<tactics> "
                         "| d<slot> | 'k <key>'")
    ap.add_argument("--dry", action="store_true", help="do everything except the press")
    ap.add_argument("--allow-pay", action="store_true",
                    help="acknowledge a money-gated action; it still refuses")
    ap.add_argument("--summary", metavar="SESSION_DIR",
                    help="print one line per recorded step and exit")
    ap.add_argument("--sheet", metavar="SESSION_DIR",
                    help="tile the session's annotated before-frames into one "
                         "contact sheet and exit")
    a = ap.parse_args(argv)

    if a.summary:
        summarize_session(a.summary)
        return 0
    if a.sheet:
        build_contact_sheet(a.sheet)
        return 0
    if a.session is not None or a.action is not None:
        sess = resolve_session(a.session)
        try:
            code, _r = run_one_step(sess, a.action or "look", dry=a.dry,
                                    allow_pay=a.allow_pay)
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            return 1
        return code
    main()
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
