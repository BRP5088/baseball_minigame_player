# HANDOFF — 2026-09-16, overnight

## READ THIS FIRST: A PAID MATCH IS SUSPENDED, NOT FINISHED

**$50 is spent on a match that is parked mid-turn.** The user put the PS5 to sleep
with the match open. `match_in_progress` is `true` and **that is CORRECT — do not
clear it.** CLAUDE.md's own rule: the flag is often NOT stale; check the screen
before clearing it. Clearing it and re-entering at the dealer prompt spends a
SECOND $50 for the same match.

    wallet (game)        $146, read locally off the pause menu earlier at $196,
                         then debited $50 at the Square press. Never re-read after.
    progress_testing     39W / 10L / 5D, balance 146,
                         match_in_progress TRUE, bans_done_this_match TRUE
    console              ASLEEP. User put it to sleep deliberately.

### The exact match state to resume into

    match                inning 1, BATTING, score 0-0, bases empty
    round                turn 1 of 5, 2 discards left
    bans placed          3/3 VERIFIED at press time, zero wrong-ban callbacks
                         Joshua Diaz 4/0 (1,3) | Marian Bunz-Twarog 4/1 (4,0)
                         | Jedediah Wetters 4/2 (4,1)
    hand on screen       0: speed_boost +1   1: 7/1   2: 4/3   3: 4/3   4: 5/3
    ENGINE PICK, NOT YET PLAYED AND NOT YET APPROVED:
                         play slot 1 (7/1) + slot 0 (SPEED BOOST +1)
                         effective power 7; the boost adds no power, it sends the
                         batter 2 bases instead of 1 on a hit. should_redraw False.

**THE PLAY WAS NEVER APPROVED.** The user's standing rule is "do not make plays
without my approval". Ask before pressing anything.

`hand_memory.json` was deleted on purpose at handoff. The hand reads all five
slots, so the memory can only ever serve a stale slot; let the reader re-read.

### Deferred, queued by the user for THIS match

**The fielding test** — "we will do the field test in the next match". It needs us
PITCHING with runners on base, i.e. the inning-2 half. n=1 on that arm today.

---

## WHAT LANDED TODAY (three commits, all local, nothing pushed)

    67e8c82  margin_from reads the tactics KIND, so a +1 can finally count
    fdd1737  choose_bans breaks a power tie on secondary
    d0141c9  the ban scan starts at the top; three doc claims withdrawn

### fdd1737 — choose_bans was banning the wrong cards, every match

`sorted(collection, key=lambda c: c.power)[:3]` left ties to SCAN ORDER. On today's
live collection that banned two 4/3 cards and KEPT a 4/1 and a 4/2 — strictly worse
cards, kept, invisibly, because the picks always looked like "three 4s".

The tie-break needs no role plumbing: `secondary` is SPEED on a batter (bases run)
and FIELDING on a pitcher (subtracts runner movement), and higher is better in BOTH,
so ascending `(power, secondary)` is worst-first either way. 3 mutants, 3 caught.

### d0141c9 — OPEN-23's mechanism, and it is not what the ticket guessed

**It is not a scroll that stops early. It is a scan that starts late.** `top_row` is
derived from the PRESS COUNT as `presses_so_far - 1`, which is a row number only if
the grid began at row 0, and nothing asserted that.

Measured live: three consecutive scans on a grid parked at level 3+ returned **10, 6
and 14 cards of 25**, every one from rows 3-6. The scrollbar cross-check correctly
refused to cache all three, but it can only relabel a row it can SEE — it cannot
conjure a row the viewport never visited. Six `move_up` presses to level 0 and the
next scan returned all 25.

`_ban_scroll_to_top()` now runs first; a scan that cannot reach row 0 says so and is
never cached. 5 mutants, 5 caught.

**MY OWN TEST WAS THE INTERESTING BUG, and a mutant is what said so.** The first
cache check could not fail: it passed `use_cache=False` (so the cache was never
written on any path) AND returned 0 cards (which trips the independent `len < 3`
floor). Two reasons to pass, neither the one under test. It now runs the real scan
twice, varying only whether the top was reached, with a control proving the
top-reached arm actually caches.

### Three doc claims withdrawn, all found by reading source, not by a failure

CLAUDE.md §4 said `best_batting_play` "sorts on POWER alone and attaches a speed
boost only as a fallback, and only when runners are already on base", that it cannot
value a fast batter, and that `simulate.py` never consults speed. **All three describe
code that is gone.** The function scores every (batter, tactics) PAIR at
`99*power + 1*speed`; `MODEL_SPEED` has been True since 2026-09-12.

Caught the cheapest way there is: the engine attached a speed boost with the bases
EMPTY, which the file said it could not do.

What SURVIVES and is restated: 99/1 is a TIE-BREAK not a trade; the engine still has
**no notion of tie risk**; and the 79% figure really was measured in a speed-blind
model. `decision_engine`'s docstring was also still citing +0.726/+0.034/"21x" — the
figures CLAUDE.md withdrew as a scrambled-pool artefact — now the re-measured 4.7x.

---

## WHAT IS RUNNING / WHAT HAPPENS NEXT

    suite baseline    ALL GREEN, 207 files, JOBS=4, 293s, taken BEFORE the QA round.
                      Anything red afterwards is the round's doing, not pre-existing.

    QA round 4        launched as a background workflow, run id wf_3a60802d-ebb.
                      Four READ-ONLY finders on disjoint axes, then one adversarial
                      skeptic per confirmed finding:
                        A ban-path        (after fdd1737 + d0141c9)
                        B reveal readers  (thresholds, missing classes, abstention)
                        C turn-loop state (half boundary, counters, hand memory)
                        D input/selection (the path that played a card told to discard)
                      Notes land in agent_progress/qa4-*/progress.md.
                      Finders may NOT touch the console or any project file.

### The order for whoever picks this up

1. Read the QA round's findings. Fix only CONFIRMED ones, each with a test that
   provably bites, each mutation-tested. Run the full suite against the 207-green
   baseline above.
2. **Do NOT touch the console without the user.** The match is suspended mid-turn
   and the pending play is unapproved.
3. When the user is back: wake the console, confirm the match is still on turn 1
   with the same hand, and ASK before playing slot 1 + slot 0.

### Rules in force

- **The paid vision model is OFF** (`orchestrator.PAID_MODEL_ENABLED = False`,
  raises `PaidModelDisabled`). Do not re-enable without the user saying so.
- **No plays without the user's approval.** Stop after every console action.
- Play the engine's pick; if it picks wrong, FIX THE ENGINE, never hand-override.
- Snoopy is a labelling aid and is never wired into the live ladder.
- Commit locally as much as you like; ask before pushing or posting.
