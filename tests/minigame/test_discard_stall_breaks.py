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

# --- 5. THE WIRING, BEHAVIOURALLY. --------------------------------------------
# QA round 1, F3. Sections 5-6 used to be `"and not _stalled" in inspect.getsource(...)`
# — a source-text substring check that a cosmetic rename of `_stalled` fails while an
# inverted guard (`and _stalled`) that keeps the same words passes. CLAUDE.md's
# "check() SIGNATURES" entry is this exact shape one level up: a check that cannot
# fail on the real regression it is named for. Replaced with the same shape
# test_refused_play_falls_back.py section 7 uses for the sibling PLAY breaker: drive
# the real play_one_turn, with select_and_discard stubbed to refuse FOREVER on a WEAK
# hand (should_redraw fires), and assert on what actually happened.
import contextlib                                                    # noqa: E402
import io                                                             # noqa: E402

STATE_JSON = {"phase": "batting", "your_score": 0, "opp_score": 0,
              "runners": [], "discards_left": 2, "hand": HAND}

_discard_calls = []
_play_calls = []


def _fake_select_and_discard(player_idx, look=None, discards_look=None):
    _discard_calls.append(player_idx)
    return False                       # every discard REFUSED, forever


def _fake_select_and_play(player_idx, tactics_idx, look=None):
    _play_calls.append(player_idx)
    return True


def _fake_grab_settle_regions(names):
    from PIL import Image
    return {n: Image.new("RGB", (4, 4), (0, 0, 0)) for n in names}


def _patch(saved):
    for _name, _fn in {
        "select_and_discard": _fake_select_and_discard,
        "select_and_play": _fake_select_and_play,
        "_grab_settle_regions": _fake_grab_settle_regions,
    }.items():
        saved[_name] = getattr(o, _name)
        setattr(o, _name, _fn)


def _unpatch(saved):
    for _name, _fn in saved.items():
        setattr(o, _name, _fn)


o._DISCARD_STALL["sig"], o._DISCARD_STALL["n"] = None, 0
_saved = {}
_patch(_saved)
_results = []
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf):
        for _ in range(o.DISCARD_STALL_MAX + 1):
            _results.append(o.play_one_turn(dict(STATE_JSON), 0))
finally:
    _unpatch(_saved)
_log = _buf.getvalue()

check(len(_discard_calls) == o.DISCARD_STALL_MAX,
      f"expected exactly {o.DISCARD_STALL_MAX} discard attempts before the guard "
      f"trips, got {len(_discard_calls)}: {_discard_calls!r} (10.1: a guard one "
      "layer up from where the loop actually spins)")
check(len(_play_calls) == 1,
      f"select_and_play must be called exactly ONCE, on the poll right after the "
      f"{o.DISCARD_STALL_MAX}th refused discard — the deadlock this file guards "
      f"against: {_play_calls!r}")
check(all(r == (False, None) for r in _results[:-1]),
      f"every poll before the stall trips must be a refused discard "
      f"(played=False, matchup_info=None): {_results[:-1]!r}")
check(_results[-1][0] is True,
      f"the poll after the stall trips must PLAY instead of discarding again: "
      f"{_results!r}")
check("REFUSED" in _log and "looping" in _log,
      "the fall-through must name the stall as its reason in the log — a run "
      "that silently stops discarding is indistinguishable from one that never "
      f"needed to:\n{_log}")

# --- 6. CONTROL: a genuinely NEW hand gets its own fresh discard budget -------
NEW_HAND = [dict(c) for c in HAND]
NEW_HAND[4] = dict(NEW_HAND[4], power=4)      # still weak (max <= 6), different sig
o._DISCARD_STALL["sig"], o._DISCARD_STALL["n"] = None, 0
_discard_calls.clear()
_play_calls.clear()
_saved = {}
_patch(_saved)
try:
    _r = o.play_one_turn(dict(STATE_JSON, hand=NEW_HAND), 0)
finally:
    _unpatch(_saved)
check(_r == (False, None) and len(_discard_calls) == 1 and not _play_calls,
      f"a DIFFERENT hand must attempt a discard again rather than inherit the "
      f"previous hand's stalled count: result={_r!r} discard_calls="
      f"{_discard_calls!r} play_calls={_play_calls!r}")

if fails:
    for f in fails:
        print("  FAIL:", f)
    _sys.exit(1)
print(f"  a discard refused {o.DISCARD_STALL_MAX}x on one unchanged hand falls "
      "through to PLAYING; a new hand resets the count")
