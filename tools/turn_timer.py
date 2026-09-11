"""Play ONE turn through the verified loop and time every phase of it.

The metric the user reported originally: the loop stalling ~35 s on the card-selection
screen, because a swallowed select_card meant confirm_play fired into nothing and the
deal never came. This measures the whole cycle so a stall shows up as a number rather
than an impression:

    read      hand readable, decision made
    walk      cursor moved to the target and verified at each step
    select    card selected and the selection confirmed
    commit    confirm_play sent
    deal      waiting for the hand to be readable again

It proposes and STOPS unless --play is given, per the crawl-mode rule the user set:
nothing is pressed without approval.
"""
import os, sys, time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
os.environ.pop("BASEBALL_TEST_RUN", None)

import orchestrator as o
import local_hand as lh
import input_controller as ic

PLAY = "--play" in sys.argv
marks = []


def mark(tag):
    marks.append((tag, time.time()))


def hand_now():
    img = o._fast_grab()
    h = dict(o.crop_gameplay_regions(img)).get("hand")
    if h is None:
        return None, None, None
    rows = lh.read_hand(h)
    return h, rows, lh.selected_cards(rows, h.width / lh.ANCHOR_W) if len(rows) == 5 else None


t0 = time.time()
mark("start")
h, rows, sel = hand_now()
if h is None or len(rows) != 5:
    print(f"no readable hand ({0 if rows is None else len(rows)} rows)"); sys.exit(1)
cards, why = o.local_hand_cards(h)
mark("read")

idx, glow, _ = lh.cursor_glow(h, rows)
print(f"cursor {idx}   selected {sel}   glow {glow}")
print(f"hand: {[(c.get('kind'), c.get('power')) for c in (cards or [])]}")
if cards is None:
    print(f"hand not usable: {why}"); sys.exit(1)

# the strongest player card, which is the decision the engine makes when batting
players = [(c["hand_index"], c.get("power") or 0) for c in cards if c.get("kind") != "tactics"]
target = max(players, key=lambda p: p[1])[0]
print(f"\nPROPOSED: play hand_index {target} (power {dict(players)[target]})")
if not PLAY:
    print("\n(dry run — pass --play to actually commit)")
    sys.exit(0)

ok = ic.select_and_play(target, None, look=o.hand_cursor_look)
mark("commit")
print(f"  -> {'COMMITTED' if ok else 'REFUSED'}")

# wait for the hand to come back
deadline = time.time() + 60
rows_back = None
while time.time() < deadline:
    _h, rows_back, _s = hand_now()
    if rows_back is not None and len(rows_back) == 5:
        break
    time.sleep(0.4)
mark("deal")

print()
prev = t0
for tag, t in marks[1:]:
    print(f"  {tag:8s} {t - prev:6.2f}s   (cumulative {t - t0:6.2f}s)")
    prev = t
print(f"  {'TOTAL':8s} {marks[-1][1] - t0:6.2f}s")
