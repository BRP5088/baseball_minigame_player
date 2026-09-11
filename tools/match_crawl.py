"""CRAWL MODE -- step the match one action at a time, and SHOW EVERYTHING IT SAW.

Why this exists. Three times running I diagnosed a stall from the wrong frame: I grabbed a
screenshot after the loop had already moved on, or joined a log timestamp to the wrong video
frame, and each time the wrong frame read exactly as authoritative as the right one
(CLAUDE.md 10.15). The user was watching the actual stream and was right every time.

So this does not reconstruct anything. At every step it freezes, dumps the ONE frame it is
acting on, runs EVERY reader over that same frame, prints the lot, and waits. Nothing moves
until you say so. What is printed is what it saw -- if it is wrong, you can see that it is
wrong, and the frame that proves it is on disk next to the numbers.

    .venv/bin/python -B tools/crawl.py

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
import os, sys, json, time, datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.pop("BASEBALL_TEST_RUN", None)          # this drives the console, deliberately

import orchestrator as o
import local_state as ls
import local_hand as lh

OUT = os.path.join(_ROOT, "overnight", "crawl",
                   datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
os.makedirs(OUT, exist_ok=True)


def _try(fn, *a, **k):
    """Every reader is called behind this: one throwing must not hide the other twelve."""
    try:
        return fn(*a, **k), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def look(step):
    """Grab ONE frame and ask every reader about THAT frame. Returns (report, image)."""
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
                                                "adds_power", "score", "x", "y")}
                       for row in rows] if rows else [])
    r["hand_err"] = err
    # WHERE THE CURSOR STARTS, recorded on EVERY step (the user's call, 2026-09-10:
    # "keep track of the starting position of the cursor from now on. I think it
    # always starts from slot 1"). Written to the step json so the claim is settled
    # by a tally rather than by recollection.
    cg, r["cursor_err"] = (_try(lh.cursor_glow, hand, rows) if hand is not None
                           else (None, "no hand crop"))
    r["cursor_index"] = cg[0] if cg else None
    r["cursor_glow"] = cg[1] if cg else None
    cards, why = (o.local_hand_cards(hand) if hand is not None else (None, "no hand crop"))
    r["hand_usable"] = None if cards is None else len(cards)
    r["hand_why"] = why
    r["hand_cards"] = cards

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
    if all(crops.get(b) is not None for b in bases):
        run, err = _try(ls.read_runners, *[crops[b] for b in bases])
        r["runners"] = ({"count": run["count"],
                         "bases": {k: {"occupied": v["occupied"], "power": v["power"],
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
        print(f"  runners        : count={run['count']}  {occ}")
    print(f"  CURSOR         : index {r.get('cursor_index')!r}   glow {r.get('cursor_glow')}")
    print(f"  HAND           : read_hand {len(r['hand_rows'])} row(s); "
          f"usable {r['hand_usable']}   why: {r['hand_why']}")
    for i, row in enumerate(r["hand_rows"]):
        print(f"      pos {i}  {str(row['kind']):8s} digit={str(row.get('digit')):4s} "
              f"secondary={str(row.get('secondary')):4s} type={str(row.get('type')):12s} "
              f"score={row.get('score')} @({row['x']},{row['y']})")
    for c in (r.get("hand_cards") or []):
        print(f"      -> hand_index {c.get('hand_index')}  {c.get('kind'):8s} "
              f"power={str(c.get('power')):4s} secondary={str(c.get('secondary')):4s} "
              f"bonus={c.get('bonus')}")
    for k in ("hand_err", "ban_err", "dealer_err", "phase_err", "discards_err", "scoreboard_err"):
        if r.get(k):
            print(f"  ! {k}: {r[k]}")


def propose(r):
    """What it WOULD do. Never executed without approval."""
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
                players.append(PlayerCard(name=c.get("name") or "?",
                                          power=c.get("power") or 0,
                                          secondary=c.get("secondary") or 0))
        sc = r.get("scoreboard") or {}
        st = GameState(half=r.get("phase") or "batting", batters_used=0,
                       your_score=(sc.get("your") or [0])[-1] or 0,
                       opp_score=(sc.get("opponent") or [0])[-1] or 0,
                       runners=[], redraws_left=r.get("discards_left") or 0)
        d = (best_batting_play(players, tactics, st) if st.half == "batting"
             else best_pitching_play(players, tactics, st))
        # MAP THE CHOSEN CARD BACK TO A SLOT. The engine returns a card, the cursor needs a
        # position, and that translation is exactly where a play can go to the wrong place --
        # so it is printed, every step, next to the card it came from.
        # THE LOOP TARGETS INPUT BY hand_index (orchestrator: select_and_play(player_idx)),
        # and production finds it by OBJECT IDENTITY against the list it built. Here the
        # cards are rebuilt, so it is matched on power -- printed beside the card so a
        # mismatch between "the card chosen" and "the position pressed" is visible.
        slot = None
        for c in r["hand_cards"]:
            if c.get("kind") != "tactics" and c.get("power") == d.player_card.power:
                slot = c.get("hand_index"); break
        if should_redraw(players, st) and (r.get("discards_left") or 0) > 0:
            weakest = min(players, key=lambda p: p.power)
            for c in r["hand_cards"]:
                if c.get("kind") != "tactics" and c.get("power") == weakest.power:
                    return ("discard", c.get("hand_index")), (
                        f"DISCARD slot {c.get('hand_index')} (power {weakest.power}) -- "
                        f"hand is weak, {r.get('discards_left')} discard(s) left")
        return ("play", slot), (f"PLAY slot {slot} (power {d.player_card.power}, "
                                f"tactics {d.tactics_card}) -- {d.reasoning}")
    except Exception as e:
        return None, f"could not build a decision ({type(e).__name__}: {e})"


def main():
    print(__doc__)
    print(f"steps -> {OUT}\n")
    step = 0
    while True:
        step += 1
        r, img = look(step)
        img.save(os.path.join(OUT, f"{step:03d}.png"))
        show(r)
        # A LABELLED SHEET FOR EVERY STEP, rendered from THIS step's frame. The numbers say
        # what each reader decided; the sheet shows what it was looking at, which is the half
        # that catches a reader cropping the wrong pixels.
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
        acted = None
        pressed = False
        if cmd == "q":
            json.dump(r, open(os.path.join(OUT, f"{step:03d}.json"), "w"), indent=1, default=str)
            print("  bye"); return
        elif cmd.startswith("n "):
            r["note"] = cmd[2:].strip(); print(f"  noted: {r['note']}")
        elif cmd == "r":
            acted = "re-read only"
        elif cmd == "s":
            acted = "skipped"
        elif cmd.startswith("p") and "+" in cmd and all(
                x.strip().isdigit() for x in cmd[1:].split("+", 1)):
            # p<slot>+<tactics> -- ONLY SWING_BOOST/PITCH_BOOST add power (CLAUDE.md 4),
            # so attaching the right tactic is worth a whole point of power and there was
            # no way to ask for it here.
            _p, _t = (int(x) for x in cmd[1:].split("+", 1))
            acted = f"select_and_play({_p}, tactics={_t})"; pressed = True
            acted += (" -> COMMITTED"
                      if o.select_and_play(_p, _t, look=o.hand_cursor_look)
                      else " -> REFUSED (nothing committed)")
        elif cmd.startswith("p") and cmd[1:].strip().isdigit():
            s = int(cmd[1:]); acted = f"select_and_play({s})"; pressed = True
            acted += " -> COMMITTED" if o.select_and_play(s, look=o.hand_cursor_look) else " -> REFUSED (nothing committed)"
        elif cmd.startswith("d") and cmd[1:].strip().isdigit():
            s = int(cmd[1:]); acted = f"select_and_discard({s})"; pressed = True
            acted += " -> COMMITTED" if o.select_and_discard(s, look=o.hand_cursor_look) else " -> REFUSED (nothing committed)"
        elif cmd.startswith("k "):
            key = cmd[2:].strip(); acted = f"press({key})"; pressed = True; o.press(key)
        elif cmd == "" and dec is not None:
            kind, slot = dec
            if slot is None:
                acted = "PROPOSAL HAS NO SLOT -- the chosen card was not found in the hand"
            elif kind == "discard":
                acted = f"select_and_discard({slot})"; pressed = True
                acted += " -> COMMITTED" if o.select_and_discard(slot, look=o.hand_cursor_look) else " -> REFUSED (nothing committed)"
            else:
                acted = f"select_and_play({slot})"; pressed = True
                acted += " -> COMMITTED" if o.select_and_play(slot, look=o.hand_cursor_look) else " -> REFUSED (nothing committed)"
        # DID IT LAND? The whole point. Compare the frame before against the frame after,
        # on the SAME measure the deal gate uses, so a press that changed nothing is
        # visible immediately rather than 35 s later. This sits OUTSIDE the branch chain:
        # it used to run only for the PROPOSED action, so p<slot>/d<slot>/k<key> -- the
        # commands a live diagnosis actually uses -- pressed a button and recorded nothing.
        if pressed:
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
        r["acted"] = acted
        if acted:
            print(f"  -> {acted}")
        json.dump(r, open(os.path.join(OUT, f"{step:03d}.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
