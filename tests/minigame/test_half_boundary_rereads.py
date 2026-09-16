"""On a half flip, the hand that gets PLAYED must be read AFTER the memory reset.

QA round 4, upheld end to end by an adversarial refuter that drove run() itself.

    state_json = read_state_for_turn()          <- runs local_hand_cards, which is
                                                   WHERE the hand memory is consulted
    ...
    if state_json["phase"] != last_phase:
        reset_hand_memory()                     <- too late; the hand already exists
    play_one_turn(state_json, ...)              <- plays the pre-reset hand

The reset protected turns 2-5 of the new half and not the one turn that needed it.
A match is 5 rounds BATTING then 5 rounds PITCHING, each dealing a FRESH five, so
the first pitching turn was played from a hand still carrying batting cards.

The carried card is worst-case by construction: forget_hand_slot removes every slot
the old half SPENT, so what survives is a card the engine passed over -- often the
highest power left in the old hand -- and best_pitching_play sorts on power, so the
phantom slot is exactly the one it selects.

Why the flip detection itself is trustworthy: local_game_state REFUSES when the
phase is unread ("phase not read locally", orchestrator.py), so state_json["phase"]
is never a guess. The defect was ordering, not sensing.
"""
import os as _os, sys as _sys
_ROOT = _os.path.dirname(_os.path.abspath(__file__))
while _ROOT != _os.path.dirname(_ROOT) and not _os.path.exists(
        _os.path.join(_ROOT, "requirements.txt")):
    _ROOT = _os.path.dirname(_ROOT)
_sys.path.insert(0, _ROOT)
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import orchestrator
# _run_harness.check is (cond, msg) -- COND FIRST, and silent on a pass. CLAUDE.md
# records four different say() signatures in this suite and that a reversed call
# passes on every input, so the order here is deliberate, not incidental.
from _run_harness import Harness, check, failures


def say(cond, msg):
    print(f"{'PASS' if cond else 'FAIL'}  {msg}")
    check(cond, msg)


def turn(phase, tag):
    return {"screen": "turn", "phase": phase, "your_score": 0, "opp_score": 0,
            "hand": [{"tag": tag}], "runners": [], "discards_left": 2}


class Recording(Harness):
    """Records the hand tag play_one_turn actually received, per call."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.played_tags = []
        self.resets = 0

    def _play_one_turn(self, state_json, turns_this_half):
        self.played_tags.append(state_json["hand"][0]["tag"])
        return super()._play_one_turn(state_json, turns_this_half)

    def run(self, **kw):
        real = orchestrator.reset_hand_memory

        def counting():
            self.resets += 1
            return real()

        orchestrator.reset_hand_memory = counting
        try:
            return super().run(**kw)
        finally:
            orchestrator.reset_hand_memory = real


# BATTING turn, then the flip. STALE is the state read BEFORE the reset; FRESH is
# what a re-read returns. The harness hands out one screen per read_state_for_turn
# call, so consuming FRESH is itself the evidence that a second read happened.
screens = [turn("batting", "BAT")] + [turn("pitching", "STALE")] + \
          [turn("pitching", "FRESH")] * 6
h = Recording(screens, play_results=[(True, None)] * 8)
h.run(target_wins=99)

say(h.played_tags and h.played_tags[0] == "BAT",
      f"turn 1 plays the batting hand: {h.played_tags[:1]}")

say(h.resets >= 1,
      f"the half flip reset the hand memory ({h.resets} reset(s))")

say("STALE" not in h.played_tags,
      f"the PRE-RESET hand is never played: got {h.played_tags}")

say(len(h.played_tags) >= 2 and h.played_tags[1] == "FRESH",
      f"the first pitching turn plays a hand read AFTER the reset: "
      f"{h.played_tags[:2]} (without the fix this is ['BAT', 'STALE'])")

# CONTROL. Without a flip there must be NO extra read -- otherwise the check above
# could pass on a run() that simply re-reads on every single turn, which would be a
# different bug (and would halve the loop's rate) rather than a fix.
h2 = Recording([turn("batting", f"B{i}") for i in range(6)],
               play_results=[(True, None)] * 6)
h2.run(target_wins=99)
say(h2.played_tags == [f"B{i}" for i in range(len(h2.played_tags))],
      f"CONTROL: with NO flip every state read is the one played, in order, with "
      f"no extra reads: {h2.played_tags}")
# RELATIVE, not absolute: run() resets the memory once at match start regardless,
# so "no flip means zero resets" is false for a reason that has nothing to do with
# this fix. What must hold is that the FLIP causes an ADDITIONAL one.
say(h.resets > h2.resets,
      f"CONTROL: the flip causes an EXTRA reset beyond the match-start one "
      f"(flip run {h.resets}, no-flip run {h2.resets})")

print()
if failures:
    for f in failures:
        print(f"FAIL: {f}")
    raise SystemExit(f"{len(failures)} half-boundary failure(s)")
print("all good")
