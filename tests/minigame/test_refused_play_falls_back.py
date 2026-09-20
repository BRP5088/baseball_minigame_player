"""I-03: A REFUSED PLAY MUST NOT SHARE THE DISCARD STOP, AND MUST NOT LOOP FOREVER.

ISSUES.md I-03. `orchestrator.py play_one_turn`: a refused `select_and_play`
(the card could not be verified -- see CLAUDE.md section 5's press-drop
measurements) printed "play REFUSED" and returned `False, None`. `run()`'s
`else` branch after `play_one_turn` was written for DISCARDS ("A discard
leaves the screen looking identical") but caught every `False` the same way,
counted it toward `MAX_STUCK_ATTEMPTS` (15), and stopped with
`stop_reason = "redraw_never_played"` -- the wrong label, since nothing was
ever discarded. Run b, 2026-09-20: eight identical refusals of the same play,
~25s each, until the run was killed by hand.

TWO FIXES, mirroring test_discard_stall_breaks.py's shape for the sibling bug:

1. `play_one_turn` now counts refused plays against the SAME hand identity the
   discard breaker keys on (`_discard_hand_identity`), in a sibling counter
   (`_PLAY_STALL`, `PLAY_STALL_MAX = 3`). Once the card currently being offered
   has been refused 3x running on an unchanged hand, it is EXCLUDED from the
   pool passed to best_batting_play/best_pitching_play, and the next-best
   reachable card gets its own fresh budget. A DISCARD IS OPTIONAL AND CANNOT
   FIX A REFUSED PLAY (there is no "instead" to fall through to, unlike the
   discard breaker), so a refused play with nothing left to fall back to
   returns False rather than looping.

2. `run()` gets its OWN stop_reason, `"play_refused"`, distinct from the
   discard case's `"redraw_never_played"`. play_one_turn signals which is
   which through `matchup_info` on a `False` return: `{"play_refused": True}`
   for a refused play (all its return sites), `None` for a discard (unchanged).
"""
import contextlib
import io
import os as _os
import sys as _sys

_os.environ.setdefault("PERSONAL_ANTHROPIC_API_KEY", "sk-ant-test")
_os.environ.setdefault("BASEBALL_TEST_RUN", "1")
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
# ...and this file's own directory, for _run_harness -- see test_run_motion_gate.py.
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

from _run_harness import Harness, check, failures                    # noqa: E402
import orchestrator as o                                             # noqa: E402

# A five-card batting hand, DESCENDING power, all secondary equal so power
# alone orders the decision -- best_batting_play must pick hand_index 0, then
# (once 0 is excluded) hand_index 1, and so on, deterministically.
HAND = [{"kind": "player", "name": f"Card {i}", "power": 9 - i, "secondary": 1,
         "hand_index": i} for i in range(5)]
STATE_JSON = {"phase": "batting", "your_score": 0, "opp_score": 0,
              "runners": [], "discards_left": 0, "hand": HAND}


def _reset_stall_state():
    o._DISCARD_STALL["sig"], o._DISCARD_STALL["n"] = None, 0
    o._PLAY_STALL["sig"], o._PLAY_STALL["n"], o._PLAY_STALL["excluded"] = None, 0, frozenset()


# --- 1. a fresh hand is never excluded or stalled ------------------------------
_reset_stall_state()
check(o.play_excluded_slots(HAND) == frozenset(),
      "a hand with no refusals behind it must not exclude anything")
check(o.play_stalled(HAND) is False,
      "a hand with no refusals behind it must not be reported stalled")

# --- 2. it takes exactly PLAY_STALL_MAX refusals to stall the current target ---
# PIN THE LITERAL (CLAUDE.md 10.11): a loop that counts to PLAY_STALL_MAX - 1
# rises with the constant it guards and cannot fail on a mutant that changes it.
check(o.PLAY_STALL_MAX == 3,
      f"PLAY_STALL_MAX is {o.PLAY_STALL_MAX}, not 3 -- the sibling of "
      "DISCARD_STALL_MAX should move only against a re-derivation of that bound")
for _i in range(2):
    o.note_play_refused()
    check(o.play_stalled(HAND) is False,
          f"stalled after only {_i + 1} refusal(s); the bound is {o.PLAY_STALL_MAX}")
o.note_play_refused()
check(o.play_stalled(HAND) is True,
      f"after {o.PLAY_STALL_MAX} refusals on ONE unchanged hand the current "
      "target must be considered stalled")

# --- 3. excluding a slot clears the count and starts the next target fresh ----
o.exclude_play_slot(0)
check(o.play_excluded_slots(HAND) == frozenset({0}),
      "excluding hand_index 0 must add it to this hand's exclusion set")
check(o.play_stalled(HAND) is False,
      "excluding the stalled slot must give the NEXT target a fresh budget, "
      "not carry the old count forward onto it")

# --- 4. CONTROL: a genuinely new hand resets both the count and the exclusions
OTHER = [dict(c) for c in HAND]
OTHER[0] = dict(OTHER[0], power=1)          # a genuinely different hand
check(o.play_excluded_slots(OTHER) == frozenset(),
      "a DIFFERENT hand must reset the exclusion set -- otherwise one "
      "unreachable card on a past hand disables playing that slot forever")
check(o.play_stalled(OTHER) is False,
      "a DIFFERENT hand must reset the refusal count")

# --- 5. CONTROL: the signature ignores nothing that identifies a card ---------
_reset_stall_state()
o.play_excluded_slots(HAND)
for _ in range(o.PLAY_STALL_MAX):
    o.note_play_refused()
_same = [dict(c) for c in HAND]
check(o.play_stalled(_same) is True,
      "an identical hand rebuilt as fresh dicts must be the SAME signature -- "
      "if it is not, the counter resets every poll and the bound can never be "
      "reached")

# --- 6. THE WIRING. The helpers existing is not the helpers being USED. -------
import inspect                                                       # noqa: E402
_src = inspect.getsource(o.play_one_turn)
check("play_excluded_slots(" in _src,
      "play_one_turn does not consult play_excluded_slots -- a stalled card "
      "would keep being offered to the decision forever")
check("note_play_refused()" in _src,
      "nothing increments the counter in play_one_turn, so play_stalled can "
      "never become True however many plays are refused")
check("play_stalled(" in _src,
      "play_one_turn never asks play_stalled -- the bound exists but is never "
      "consulted")
check("exclude_play_slot(" in _src,
      "play_one_turn never excludes the stalled slot -- the same refused card "
      "would be offered again next poll")
check('"play_refused": True' in _src,
      "a refused play must mark matchup_info so run() can tell it apart from "
      "a discard -- see the run() wiring check below")

_run_src = inspect.getsource(o.run)
check('matchup_info.get("play_refused")' in _run_src,
      "run() does not branch on matchup_info.get('play_refused') -- a refused "
      "play still falls into the discard else and is mislabelled")
check('stop_reason = "play_refused"' in _run_src,
      "run() never sets stop_reason to play_refused -- I-03's whole point")
check('stop_reason = "redraw_never_played"' in _run_src,
      "the discard branch's own stop_reason must survive unchanged -- a "
      "regression here would be a silent behaviour change on the discard path")

# --- 7. BEHAVIOUR: select_and_play refuses ONE slot forever, accepts any other
# Direct, repeated calls to play_one_turn -- one call per simulated poll, the
# same shape run() drives it in (screen unchanged between polls because
# nothing landed). No screen, no console: every I/O seam play_one_turn touches
# is stubbed.
_reset_stall_state()
_REFUSED_SLOT = 0
_play_calls = []


def _fake_select_and_play(player_idx, tactics_idx, look=None):
    _play_calls.append(player_idx)
    return False if player_idx == _REFUSED_SLOT else True


def _fake_grab_settle_regions(names):
    from PIL import Image
    return {n: Image.new("RGB", (4, 4), (0, 0, 0)) for n in names}


_saved = {}
for _name, _fn in {
    "select_and_play": _fake_select_and_play,
    "_grab_settle_regions": _fake_grab_settle_regions,
}.items():
    _saved[_name] = getattr(o, _name)
    setattr(o, _name, _fn)

_results = []
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf):
        for _attempt in range(6):
            _results.append(o.play_one_turn(dict(STATE_JSON), 0))
            if _results[-1][0]:
                break
finally:
    for _name, _fn in _saved.items():
        setattr(o, _name, _fn)
_log = _buf.getvalue()

check(len(_results) <= 4,
      f"a different slot must be played by attempt 4; it took "
      f"{len(_results)} attempts")
check(all(r == (False, {"play_refused": True}) for r in _results[:-1]),
      "every attempt before the successful one must be a refused play, "
      f"flagged play_refused: {_results[:-1]!r}")
check(_results[-1][0] is True,
      f"no attempt within the first 6 succeeded: {_results!r}")
check(_play_calls[:3] == [_REFUSED_SLOT] * 3,
      f"the first {min(3, len(_play_calls))} attempts must target the slot "
      f"that ends up refused, exactly PLAY_STALL_MAX times: {_play_calls!r}")
check(_REFUSED_SLOT not in _play_calls[3:],
      f"the excluded slot must never be re-targeted after it stalls: "
      f"{_play_calls!r}")
check(len(set(_play_calls[3:])) >= 1 and _play_calls[-1] != _REFUSED_SLOT,
      f"a DIFFERENT hand_index must be the one actually played: {_play_calls!r}")
check("excluded" in _log and "next-best" in _log,
      "the log must name the fallback (which slot was excluded, and that a "
      "next-best card is being offered instead) -- got:\n" + _log)

# --- 8. run()-LEVEL WIRING: a play_refused stall stops labelled correctly,
# and a genuine discard stall (matchup_info=None) is UNCHANGED. Driven through
# the Harness, which replaces play_one_turn wholesale with scripted results --
# i.e. play_one_turn's own PLAY_STALL_MAX fallback plays NO part here. This is
# the "fallback disabled" control: run()'s own MAX_STUCK_ATTEMPTS bound is what
# has to catch a stall that never resolves, exactly as it always has.
_h_play_refused = Harness(["turn"] * 200,
                          play_results=[(False, {"play_refused": True})] * 200)
_buf2 = io.StringIO()
with contextlib.redirect_stdout(_buf2):
    _h_play_refused.run(target_wins=99)
_out2 = _buf2.getvalue()
check(_h_play_refused.idx <= o.MAX_STUCK_ATTEMPTS + 2,
      f"a run stalled entirely on play_refused took {_h_play_refused.idx} "
      f"turns to stop, expected the old bound ({o.MAX_STUCK_ATTEMPTS})")
check("Play refused repeatedly" in _out2,
      "run() did not print the play_refused stop message:\n" + _out2)
check("redraw_never_played" not in _out2 and "Discarding repeatedly" not in _out2,
      "a play_refused stall must not be mislabelled as the discard stop:\n" + _out2)

_h_discard = Harness(["turn"] * 200, play_results=[(False, None)] * 200)
_buf3 = io.StringIO()
with contextlib.redirect_stdout(_buf3):
    _h_discard.run(target_wins=99)
_out3 = _buf3.getvalue()
check(_h_discard.idx <= o.MAX_STUCK_ATTEMPTS + 2,
      f"CONTROL: a genuine discard stall took {_h_discard.idx} turns to stop, "
      f"expected the old bound ({o.MAX_STUCK_ATTEMPTS}) -- unchanged from before I-03")
check("Discarding repeatedly" in _out3,
      "CONTROL: a genuine discard stall (matchup_info=None) must still stop "
      "labelled redraw_never_played, unchanged:\n" + _out3)
check("Play refused repeatedly" not in _out3,
      "CONTROL: a discard stall must not be mislabelled play_refused:\n" + _out3)

if failures:
    for f in failures:
        print("  FAIL:", f)
    _sys.exit(1)
print(f"  a play refused {o.PLAY_STALL_MAX}x on one unchanged hand excludes "
      "that slot and falls back to the next-best card; run() labels a "
      "play_refused stall distinctly from a discard stall")
