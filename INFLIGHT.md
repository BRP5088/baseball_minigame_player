# IN-FLIGHT — 2026-09-12, resume from here

Written for a usage-limit reset. HANDOFF_NOW.md is the longer-lived record; this is the
live queue. Delete it when the queue is empty.

## Rules in force RIGHT NOW

- **The paid vision model is OFF** by the user's instruction (commit 689de6d). It raises
  `orchestrator.PaidModelDisabled`. Do not re-enable without the user saying so.
- Crawl mode: **no console press without explicit approval.**
- A real match is LIVE and PARKED: pitching half, 2-0 up, no runners, hand
  `0:` fielding_boost+1 `1:` P6/f0 `2:` P9/f2 `3:` P5/f1 `4:` P8/f0, cursor idle,
  nothing selected. `progress_testing.json` has `match_in_progress=True`, balance 146.
- The standing question the user asked and I answered WRONG once already: play slot 2
  (the 9) or slot 4 (the 8) with the bases empty. Corrected answer: **indistinguishable**
  (1.2 sigma). Either is fine. Do not re-litigate without new evidence.
- chiaki is UP. `tools/state_viewer.py` may be running (read-only, presses nothing).

## Done today (all committed, suite green at 177 files)

    7d890c1  discard path was blind -- look= wired in, AST check on the call sites
    bea5fa4  offline suite was reading the live compass -- read_heading seam threaded
    0b57619  speed boost was worth zero; "score went up" was logged as a home run
    689de6d  paid vision model locked OFF at the choke point
    e3dfed8  simulator reshuffled both hands every round; tactics pools drew a +3

## QUEUE — updated 2026-09-12 late

### CLOSED

- **The `max(discs, key=ink)` "reader fix" is a NO-OP. Do not ship it.** Measured over all
  172 saved base crops with a disc: max-ink and topmost give IDENTICAL power reads on every
  one, and neither produces an impossible power. The caption-letter blob the skeptic found
  existed only inside their own WIDENED crop, which was itself refuted. Their proposed rule
  ("topmost UNCLIPPED") is actively WRONG: on 23 of 172 crops the topmost disc is genuinely
  clipped by the crop edge and the unclipped alternative is card ART lower down, so the
  rule would swap a correct abstention for a confident wrong digit.
- **The proposed crop fractions: refuted, do not ship.** Overlap is 1-2 px not 7; the card
  model was a rigid translate wrong in opposite directions at first vs third; and the new
  box makes one EMPTY base read occupied=True power=1, impossible (powers run 4-9).
- **Runner SPEED: SHIPPED.** local_state.base_badge + read_base["speed"] +
  read_runners["speeds"]. 171/172 occupied bases read, 0 false reads on 1,106 bare bases,
  shipped SHIELD_MIN 0.69 already sits between the populations (empty max 0.592, occupied
  p05 0.857). Five mutants; the first two SURVIVED and the test was fixed, not the mutant.
- **Simulator match shape: SETTLED.** The match is:
      new hand / play as the BATTER / inning 1 ends /
      new hand / inning 2 starts / play as the PITCHER / inning 2 ends.
  So the two innings ARE the two halves -- you bat in inning 1, pitch in inning 2, done.
  simulate_match's original A-bats-then-B-bats shape was right; a change earlier the same
  day that looped it over two innings played FOUR halves and doubled every score. Reverted.
  Confirmed by the user and by the live board: `your [2,0,2]` vs `opponent [0,0,0]` is us
  scoring 2 batting in inning 1, not batting in inning 2, and them yet to score in the
  inning they are batting now.
- **ROUNDS_PER_HALF = 5 is SETTLED too** -- five at-bats batting, five pitching, which is
  what simulate_batting_half has always looped. CLAUDE.md's "a match is 5 rounds" is per
  half. (Was listed as open; it is not.)
- **What DID need fixing in the simulator** was one level down: both hands were redrawn
  every ROUND, where the real hand is dealt once per half and topped up a card at a time
  (refill_hand). That fix stands. 99/1 re-validated and survives.

### OPEN, in priority order

1. **Deal timing -- HALF DONE. The input is shipped; the coefficient is not, deliberately.**
   `orchestrator.bases_to_travel(bases, batter_speed, margin)` gives 1 for a routine out
   and 10 for a bases-loaded home run, and `wait_for_hand_deal(predicted_bases=...)` logs
   it beside the measured wait. NOT wired at the call site yet -- the prediction must be
   captured at the PLAY (the bases as they were when the ball was hit) and popped at the
   gate, the same stash/pop pattern `stash_hand_baseline`/`pop_hand_baseline` already uses
   in play_one_turn. That is the next concrete step: ~20 lines.
   **WHY NO SECONDS-PER-BASE CONSTANT.** The archived release times are FLOOR-CENSORED:
   the gate cannot release before POST_PLAY_MIN_WAIT and 77% land within one poll of it,
   and the whole distribution MOVES with that constant (floor 6.0 -> pile at 6.1, floor
   3.0 -> pile at 3.6). There are 76 uncensored turns between 7 and 18.5 s, but no [deal]
   line on disk carries runner state to join against. So the pair is logged and the
   coefficient waits for a few matches of real data. A test asserts no PER_BASE constant
   exists, so adding one has to be justified.
   NOTE the floor was already fixed on 2026-09-10 (6.0 -> 3.0, hand first settles at
   median 1.1 s); the workflow's timing axis mined the STALE 6.0 archive and was mostly
   REFUTED anyway (16 of 25 timeouts tautological, 9 from a deleted rule, 0 from shipped
   code). Do not reuse its numbers.
2. **best_batting_play runner-awareness: TESTED, NOT SHIPPED.** An expected-runs rule that
   sees each runner's real base is INDISTINGUISHABLE from power-first (+0.015, 1.5 sigma;
   0.2-0.3 sigma at other settings of OUT_RUNNER_ADVANCE). It is not power-first in
   disguise — it disagrees on 8.2% of hands and the rate triples once runners are on — it
   just does not win. Full write-up and the mechanism:
   `agent_progress/batting-runners/FINDING.md`. The graveyard entry's VERDICT survives; its
   stated REASON ("it loses") does not, having been measured with every runner assumed on
   first. To go further, GameState would need to carry runner BASES; today it carries
   `runners` as a list of cards only.

3. **Runner NAME** reads 140/171 with ZERO names on 1,106 bare bases (verdict NEEDS_WORK:
   numbers reproduce, write-up overstated the sample). Not wired in.
4. The live match is still parked mid-turn. Slot 2 vs slot 4 is a genuine coin-flip.

## (historical) the reader fix, from the workflow's own skeptics

Workflow `wf_fb45937c-afa` (21 agents) proposed re-cutting the base crops. The skeptics
REFUTED that and found the real defect. Full results:
`~/.claude/projects/-Users-bpatterson-*/subagents/workflows/wf_fb45937c-afa/journal.jsonl`
(one {"type":"result"} line per agent; read it rather than trusting this summary).

1. **[IN PROGRESS] `local_state.read_base` picks the wrong blob.**
   `disc = max(discs, key=lambda d: d["ink"])` selects the INKIEST blob, which on several
   frames is a 33x33 white overlay caption letter, not the power disc. Skeptic's evidence:
   on ts 1788970426076701000 the real disc is at frame x 0.6349-0.6484 ink 96 clipped
   False, while a caption fragment at x 0.5500-0.5672 ink 223 clipped True wins the max.
   **Fix: take the topmost UNCLIPPED disc, falling back to topmost.** The power disc is
   the card's topmost badge. Consider tightening `BASE_DISC_H`'s floor (9.0 admits caption
   fragments) only if the census supports it -- do not invent a bound.
   This recovers the power reads with NO crop change, so the 464x3 saved crops in
   `overnight/local_hand/` stay valid.

2. **DO NOT ship the proposed crop fractions.** Measured overlap is 1-2 px, not the 7 the
   proposal claimed; its card-edge model was a rigid translate of the disc blob by one
   hand-eyeballed constant per base, wrong in opposite directions at first vs third. And
   the new box makes one EMPTY base read `occupied=True power=1`, which is impossible
   (powers run 4-9).

3. **Unread: the remaining workflow verdicts** (runner reader axis, deal-timing axis).
   Skim the journal for `"verdict"` and handle anything marked STANDS.

4. **Deal timing** is still unanswered. The user: "I didn't say it's broken. It's just not
   working correctly. make it work." Runner per-card stats are the blocker; see the runner
   reader axis.

## Corrections I owe / have made (do not re-assert the old versions)

- `ocr_scoreboard` returns `[inning1, inning2, TOTAL]`. Do NOT sum it; production takes
  `[-1]` and is correct. My crawl scripts summed it -- cosmetic only, no decision used it.
- A +3 tactics bonus does NOT exist (299 hand-labelled cards). Max effective batter power
  is 9+2 = 11.
- The "3+ margin is an automatic home run" rule IS absolute; the 26 log rows that
  contradict it are bad OLD labels from the score read, not evidence against the rule.
- Speed-boost fix is worth +0.034 runs/half, NOT the +0.262 I first reported.
- Neither `best_batting_play` nor `best_pitching_play` reads the score, and that is
  CORRECT: you bat once then defend, so no score-dependent lever exists for card choice.
  The one place score matters is risk tolerance when defending a lead.
