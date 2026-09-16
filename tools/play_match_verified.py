"""Play out a match through the VERIFIED selection loop, timing every turn.

The point is the user's original complaint: the loop stalling ~35 s on the card-selection
screen because a swallowed select_card meant confirm_play fired into nothing. Every turn
is timed so a stall is a number, not an impression.

SAFETY. The match is already paid for, so playing it out spends nothing further. It reads
LOCALLY only (no paid vision calls), it never presses confirm on a refusal, it stops at
the result screen, and it stops after MAX_TURNS or on two consecutive refusals rather than
hammering a screen it cannot read.
"""
import os, sys, time, json, datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.pop("BASEBALL_TEST_RUN", None)

import orchestrator as o
import local_hand as lh
import local_state as ls
import input_controller as ic
from decision_engine import (GameState, PlayerCard, TacticsCard, TacticsType,
                             best_batting_play, best_pitching_play)

MAX_TURNS = 40
OUT = os.path.join(_ROOT, "overnight", "crawl",
                   "match_" + datetime.datetime.now().strftime("%H%M%S"))
os.makedirs(OUT, exist_ok=True)
log = []


def look():
    img = o._fast_grab()
    crops = dict(o.crop_gameplay_regions(img))
    return img, crops, crops.get("hand")


def decide(hand, cards, crops):
    """The engine's own choice, so this exercises the real decision path."""
    players, tactics = [], []
    for c in cards:
        if c.get("kind") == "tactics":
            try:
                k = TacticsType(c.get("type"))
            except Exception:
                continue
            tactics.append(TacticsCard(name=c.get("type") or "?",
                                       bonus=c.get("bonus") or 0, kind=k))
        else:
            players.append(PlayerCard(name=str(c.get("hand_index")),
                                      power=c.get("power") or 0,
                                      secondary=c.get("secondary") or 0))
    if not players:
        return None, None, "no player cards"
    # REFUSE, DO NOT DEFAULT. `or "batting"` turns an ABSTENTION into a value, and
    # the value it picks is a whole strategy: while PITCHING it would run
    # best_batting_play and propose the wrong kind of card entirely.
    # orchestrator.local_game_state refuses for exactly this reason ("phase not read
    # locally"); this tool drives a live match and did not.
    phase = ls.read_phase(hand)[0]
    if phase is None:
        return None, None, "phase not read -- not proposing a play"
    sc = o.ocr_scoreboard(crops["scoreboard"]) or {}
    st = GameState(half=phase, batters_used=0,
                   your_score=(sc.get("your") or [0])[-1] or 0,
                   opp_score=(sc.get("opponent") or [0])[-1] or 0,
                   runners=[], redraws_left=0)
    d = (best_batting_play(players, tactics, st) if phase == "batting"
         else best_pitching_play(players, tactics, st))
    # THE SLOT IS ALREADY IN THE CARD, so do not search for it by POWER. The engine
    # tie-breaks equal-power cards on `secondary` (decision_engine), so "the first
    # card of this power" is a DIFFERENT card from the one it chose whenever two
    # share a power -- and it then presses that one. PlayerCard.name is set to
    # str(hand_index) fifteen lines above, so the answer is already carried.
    pi = ti = None
    try:
        pi = int(d.player_card.name)
    except (TypeError, ValueError):
        pi = None
    for c in cards:
        if (d.tactics_card is not None and c.get("kind") == "tactics"
                and c.get("type") == d.tactics_card.kind.value and ti is None):
            ti = c.get("hand_index")
    return pi, ti, f"{phase}: power {d.player_card.power}" + (
        f" + {d.tactics_card.kind.value}" if d.tactics_card else "")


refusals = 0
for turn in range(1, MAX_TURNS + 1):
    t0 = time.time()
    # ---- wait for a readable turn -------------------------------------------
    hand = rows = cards = None
    while time.time() - t0 < 90:
        img, crops, hand = look()
        res = ls.read_result(img)
        if res["is_result"]:
            print(f"\nRESULT SCREEN: {res['outcome']}  ({res['why']})")
            json.dump(log, open(f"{OUT}/turns.json", "w"), indent=1)
            sys.exit(0)
        if hand is not None:
            cards, why = o.local_hand_cards(hand)
            if cards:
                rows = lh.read_hand(hand)
                break
        time.sleep(0.4)
    if not cards:
        print(f"turn {turn}: no readable hand in 90s — stopping"); break
    t_read = time.time()

    pi, ti, why = decide(hand, cards, crops)
    if pi is None:
        print(f"turn {turn}: {why} — stopping"); break
    sel = lh.selected_cards(rows, hand.width / lh.ANCHOR_W)
    print(f"turn {turn:2d}  {why:34s} -> play {pi}" + (f" + {ti}" if ti is not None else "")
          + f"   (selected {sel})")

    # spend_and_play, NOT select_and_play: it forgets the spent slots AND takes the
    # verified path. Calling the raw function leaves _hand_memory holding the card
    # that was just played, and local_hand_cards then serves it for that slot on the
    # next turn whenever the slot is unreadable -- which is exactly the slot the
    # memory is consulted for.
    # (ok, why), not a bare bool -- a non-empty tuple is always truthy, which
    # would make every refusal read as a commit.
    ok, _why = o.spend_and_play(pi, ti)
    if not ok:
        print(f"    REFUSED: {_why}")
    t_commit = time.time()

    # ---- wait for the hand to come back --------------------------------------
    back = False
    while time.time() - t_commit < 60:
        _i, _c, h2 = look()
        if h2 is not None:
            c2, _w = o.local_hand_cards(h2)
            if c2:
                back = True
                break
        time.sleep(0.4)
    t_deal = time.time()

    row = {"turn": turn, "committed": bool(ok), "why": why,
           "read_s": round(t_read - t0, 2), "commit_s": round(t_commit - t_read, 2),
           "deal_s": round(t_deal - t_commit, 2), "total_s": round(t_deal - t0, 2),
           "dealt": back}
    log.append(row)
    print(f"          {'COMMITTED' if ok else 'REFUSED  '}  "
          f"read {row['read_s']:5.1f}s  commit {row['commit_s']:5.1f}s  "
          f"deal {row['deal_s']:5.1f}s  total {row['total_s']:5.1f}s")
    refusals = 0 if ok else refusals + 1
    if refusals >= 2:
        print("two refusals in a row — stopping rather than hammering"); break

json.dump(log, open(f"{OUT}/turns.json", "w"), indent=1)
print(f"\nturns -> {OUT}/turns.json")
