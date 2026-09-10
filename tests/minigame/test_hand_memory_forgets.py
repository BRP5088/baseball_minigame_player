"""The hand memory is safe ONLY because every site that spends a card forgets that slot.

WHY THIS FILE IS THE WHOLE SAFETY STORY. When a card cannot be read, its value is carried
forward from the last turn that slot was read. That is sound because a card only changes
when it is PLAYED or DISCARDED, and we are the ones who do that -- so the slots that
changed are KNOWN, not inferred.

VERIFIED LIVE (2026-09-09, clean starting state asserted first): playing slot 2 changed
slot 2 and nothing else, twice, and the replacement was readable the moment it landed.

AN ART-SIMILARITY GUARD WAS TRIED AND REJECTED, and the numbers are why: gated on art the
memory fired 0 times in 445 hands, because the same overlap that hides a card's disc also
covers part of its art -- identity cannot be confirmed exactly when it is needed. Without
any guard at all, replayed over the corpus WITHOUT the spend events, carrying forward was
wrong on 6 of 9 carries. So the correctness rests ENTIRELY on forget_hand_slot() being
called at every spend site, and this file is what stops that rotting.

If you add a new way to spend a card, this test fails until it forgets the slot.
"""
import ast
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)
os.environ["BASEBALL_TEST_RUN"] = "1"

import orchestrator                                                     # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


SPENDERS = {"select_and_play", "select_and_discard"}
src = open(os.path.join(_ROOT, "orchestrator.py")).read()
tree = ast.parse(src)


def calls_in(node):
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            if nm:
                out.append((getattr(n, "lineno", 0), nm))
    return sorted(out)


# ---- 1. EVERY SPEND SITE FORGETS, and the forget comes FIRST ------------------------
spend_lines = [(ln, nm) for ln, nm in calls_in(tree) if nm in SPENDERS]
forget_lines = [ln for ln, nm in calls_in(tree) if nm == "forget_hand_slot"]
check("orchestrator really spends cards somewhere", len(spend_lines) >= 2,
      f"{len(spend_lines)} spend calls")
check("and forget_hand_slot is called", len(forget_lines) >= 2, f"{len(forget_lines)} forgets")
for ln, nm in spend_lines:
    near = [f for f in forget_lines if 0 < ln - f <= 6]
    check(f"{nm} at line {ln} forgets its slot FIRST",
          bool(near), f"nearest forget above: {near or 'none within 6 lines'}")

# ---- 2. A NEW MATCH RESETS IT --------------------------------------------------------
starts = [ln for ln, nm in calls_in(tree) if nm == "press"]
resets = [ln for ln, nm in calls_in(tree) if nm == "reset_hand_memory"]
check("a new match resets the memory", len(resets) >= 2, f"{len(resets)} resets")

# ---- 3. THE BEHAVIOUR ITSELF ---------------------------------------------------------
orchestrator.reset_hand_memory()
orchestrator._hand_memory[2] = {"power": "7", "secondary": 1, "art": None}
check("a remembered slot is remembered", orchestrator._hand_memory.get(2) is not None)
orchestrator.forget_hand_slot(2)
check("a SPENT slot is forgotten", orchestrator._hand_memory.get(2) is None)
orchestrator._hand_memory[1] = {"power": "5", "secondary": 0, "art": None}
orchestrator.forget_hand_slot(None)          # a play with no tactics card attached
check("forgetting None is harmless", orchestrator._hand_memory.get(1) is not None)
orchestrator.reset_hand_memory()
check("a reset clears everything", not orchestrator._hand_memory)

# ---- 4. AND THE CARRY-FORWARD ACTUALLY USES IT ---------------------------------------
# Without this the file passes while the memory is wired to nothing.
import local_hand                                                       # noqa: E402
from PIL import Image                                                   # noqa: E402

FULL = [
    {"kind": "tactics", "x": 0, "y": 0, "digit": None, "type": "swing_boost", "bonus": 1},
    {"kind": "player", "x": 1, "y": 0, "digit": "5", "secondary": 0},
    {"kind": "player", "x": 2, "y": 0, "digit": "6", "secondary": 1},
    {"kind": "player", "x": 3, "y": 0, "digit": "7", "secondary": 0},
    {"kind": "player", "x": 4, "y": 0, "digit": "4", "secondary": 2},
]
blank = Image.new("RGB", (979, 307), (20, 20, 20))
_real = local_hand.read_hand
try:
    orchestrator.reset_hand_memory()
    local_hand.read_hand = lambda img: [dict(c) for c in FULL]
    orchestrator.local_hand_cards(blank)                 # banks every slot

    def hide2(img):
        rows = [dict(c) for c in FULL]
        rows[2]["digit"] = None
        return rows

    local_hand.read_hand = hide2
    cards, why = orchestrator.local_hand_cards(blank)
    got = {c["hand_index"]: c.get("power") for c in (cards or [])}
    check("an unreadable slot we did NOT spend is carried forward",
          got.get(2) == 6, f"got {got}")

    # and once it IS spent, it must NOT be carried forward
    orchestrator.forget_hand_slot(2)
    cards, why = orchestrator.local_hand_cards(blank)
    got = {c["hand_index"]: c.get("power") for c in (cards or [])}
    check("a slot we SPENT is not carried forward -- it is dropped",
          2 not in got, f"got {got}  why={why!r}")
finally:
    local_hand.read_hand = _real
    orchestrator.reset_hand_memory()

# ---- 5. AN UNKNOWN SLOT IS RETRIED EVERY TURN UNTIL IT RESOLVES ---------------------
# The user's requirement, and it must be a GUARANTEE rather than an accident of the
# current control flow: a slot that cannot be read is never given up on permanently. The
# whole hand is re-read every turn, so the moment the occluding card is played and the
# slot becomes visible, it is read and banked -- and from then on it is available even if
# it goes back under.
_real2 = local_hand.read_hand
try:
    orchestrator.reset_hand_memory()

    def hidden(img):
        rows = [dict(c) for c in FULL]
        rows[2]["digit"] = None
        return rows

    # two turns where slot 2 cannot be read and was never seen: dropped, not invented
    local_hand.read_hand = hidden
    for turn in (1, 2):
        cards, why = orchestrator.local_hand_cards(blank)
        got = {c["hand_index"]: c.get("power") for c in (cards or [])}
        check(f"turn {turn}: an unseen, unreadable slot is dropped rather than guessed",
              2 not in got, f"got {got}")

    # the occluder is played, the slot becomes visible: it must be read and BANKED
    local_hand.read_hand = lambda img: [dict(c) for c in FULL]
    cards, why = orchestrator.local_hand_cards(blank)
    got = {c["hand_index"]: c.get("power") for c in (cards or [])}
    check("the turn it becomes visible, it is read", got.get(2) == 6, f"got {got}")

    # and it goes back under: now memory carries it, because it has been SEEN
    local_hand.read_hand = hidden
    cards, why = orchestrator.local_hand_cards(blank)
    got = {c["hand_index"]: c.get("power") for c in (cards or [])}
    check("once seen, it survives going back under", got.get(2) == 6, f"got {got}")
finally:
    local_hand.read_hand = _real2
    orchestrator.reset_hand_memory()

print(f"\n{'FAILED: ' + ', '.join(fails) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
