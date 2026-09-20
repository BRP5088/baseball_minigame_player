"""A REFUSED DISCARD MUST NOT LOOP FOREVER.

Live 2026-09-20, pitching half of a paid match. The engine chose to discard hand
slot 4. local_hand.cursor_glow read slot 4 at 6.9-9.8 against CURSOR_GLOW_MIN 10.0
while every other slot sat at 0.0-0.8, so _select_verified refused -- correctly,
because select_card is a TOGGLE and a blind press can throw the wrong card. But the
refusal left the hand unchanged, so play_one_turn reached the IDENTICAL decision on
the next poll:

    [hand] 0: fielding_boost +1  1: pitch_boost +1  2: 6/0  3: 5/1  4: 5/0
    Decision: best card is weak (power 6) and 1 discard(s) left — discarding the weakest
    [cursor] cannot see the cursor (glow=[0.1, 0.0, 0.3, 0.1, 8.1]) — refusing
    discard NOT CONFIRMED — ... Re-reading the hand next poll rather than retrying blind.

Ten cycles, ~25 s each, zero progress, and the run had to be killed by hand. That is
CLAUDE.md 10.1 at the level of a LOOP: a spinning engine and a slow one print the
same thing, so nothing distinguishes them.

IT IS NOT A ONE-OFF. CLAUDE.md 10.35 measured the cause: "slot 4 never exceeds 11.0
at ANY offset, while slots 0-3 read 26-28 at the shipped position." Every hand whose
weakest card lands in slot 4 can reproduce it.

THE BOUND INVENTS NOTHING. Each attempt already retries its presses
PRESS_VERIFY_TRIES (5) times, priced in section 5 at 0.152 * 0.25**4 = 0.059% per
attempt. Three whole attempts failing on an UNCHANGED hand is ~2e-10 under the
press-drop model, so the bound is derived from an existing measurement rather than
fitted to a new one (10.4).

A DISCARD IS OPTIONAL AND A TURN IS NOT, so falling through to the PLAY branch is
the safe direction: it costs at most one weak at-bat, where looping costs the run.
"""
import os as _os
import sys as _sys

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)

import orchestrator as o                                             # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


# The hand that deadlocked, in the shape state_json["hand"] actually carries.
HAND = [
    {"kind": "tactics", "name": "fielding_boost", "type": "fielding_boost",
     "bonus": 1, "hand_index": 0},
    {"kind": "tactics", "name": "pitch_boost", "type": "pitch_boost",
     "bonus": 1, "hand_index": 1},
    {"kind": "player", "name": None, "power": 6, "secondary": 0, "hand_index": 2},
    {"kind": "player", "name": None, "power": 5, "secondary": 1, "hand_index": 3},
    {"kind": "player", "name": None, "power": 5, "secondary": 0, "hand_index": 4},
]
OTHER = [dict(c) for c in HAND]
OTHER[2] = dict(OTHER[2], power=9)          # a genuinely different hand

o._DISCARD_STALL["sig"], o._DISCARD_STALL["n"] = None, 0

# --- 1. a fresh hand is NEVER stalled -----------------------------------------
check(o.discard_stalled(HAND) is False,
      "a hand with no refusals behind it must not be reported stalled")

# --- 2. it takes exactly THREE refusals ---------------------------------------
# PIN THE LITERAL (CLAUDE.md 10.11). The first version of this file looped
# range(o.DISCARD_STALL_MAX - 1) and therefore rose with the constant it guards:
# a mutant setting the bound to 999 SURVIVED, because the test simply counted to
# 998 and agreed with itself. A test that reads the constant under test cannot
# fail, on any input, ever.
check(o.DISCARD_STALL_MAX == 3,
      f"DISCARD_STALL_MAX is {o.DISCARD_STALL_MAX}, not 3. The bound is derived in "
      "orchestrator's comment from PRESS_VERIFY_TRIES and the 15.20% press-drop "
      "rate; moving it needs that derivation redone, not just this literal edited.")
for _i in range(2):
    o.note_discard_refused()
    check(o.discard_stalled(HAND) is False,
          f"stalled after only {_i + 1} refusal(s); the bound is "
          f"{o.DISCARD_STALL_MAX}. Bailing out early throws away a discard the "
          "engine could still have landed.")
o.note_discard_refused()
check(o.discard_stalled(HAND) is True,
      f"after {o.DISCARD_STALL_MAX} refusals on ONE unchanged hand the engine must "
      "stop trying to discard and play instead — this is the deadlock that killed "
      "the 2026-09-20 run.")

# --- 3. CONTROL: a genuinely NEW hand resets the counter ----------------------
# Without this the engine would stop discarding for the rest of the match after one
# bad hand, which is a different bug wearing this fix's clothes.
check(o.discard_stalled(OTHER) is False,
      "a DIFFERENT hand must reset the counter — otherwise one unreachable slot "
      "disables discarding for the whole match")
o.note_discard_refused()
check(o.discard_stalled(OTHER) is False,
      "the counter must have RESET on the new hand, not merely been read once")

# --- 4. CONTROL: the signature ignores nothing that identifies a card ---------
_same = [dict(c) for c in HAND]
o._DISCARD_STALL["sig"], o._DISCARD_STALL["n"] = None, 0
o.discard_stalled(HAND)
for _ in range(o.DISCARD_STALL_MAX):
    o.note_discard_refused()
check(o.discard_stalled(_same) is True,
      "an identical hand rebuilt as fresh dicts must be the SAME signature — if it "
      "is not, the counter resets every poll and the bound can never be reached, "
      "which is the original deadlock with extra steps")

# --- 5. THE WIRING. The helper existing is not the helper being USED. ---------
# CLAUDE.md records a wiring assertion that passed because it matched the function's
# own `def` line, so this asserts on the CONDITION, and requires the guard to sit in
# play_one_turn rather than merely somewhere in the file.
import inspect                                                      # noqa: E402
_src = inspect.getsource(o.play_one_turn)
check("discard_stalled(" in _src,
      "play_one_turn does not call discard_stalled — the bound exists but nothing "
      "consults it, so the loop still spins (10.1: a guard that cannot fire)")
check("and not _stalled" in _src,
      "the should_redraw branch is not gated on the stall flag; without that the "
      "engine re-enters the discard path forever")
check("note_discard_refused()" in _src,
      "nothing increments the counter in play_one_turn, so discard_stalled can "
      "never become True however many discards are refused")

# --- 6. the else branch must SAY it is playing because of the stall -----------
check("REFUSED" in _src and "looping" in _src,
      "the fall-through prints no reason naming the stall — a run that silently "
      "stops discarding is indistinguishable from one that never wanted to")

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print(f"  a discard refused {o.DISCARD_STALL_MAX}x on one unchanged hand falls "
      "through to PLAYING; a new hand resets the count")
