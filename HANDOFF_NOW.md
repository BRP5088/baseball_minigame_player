# HANDOFF — 2026-09-11, end of session

## State of the rig

- **A match is PARKED mid-turn** on the PS5, with a card selected. Nothing was
  pressed without approval; crawl mode was in force all session. The console will
  auto-sleep. `match_in_progress` may be set — **check the screen before clearing
  it** (CLAUDE.md §2).
- `tools/box_viewer.py` was run and has been **killed**. Nothing of mine is running.
- Suite: **all green, 174 files, 251 s**, at the commit below.

## What changed, and why it is trustworthy

The cursor reader was stalling live turns. Two defects, both in the GLOW WINDOW,
neither in the cursor logic:

1. **The window was bounded by raw disc positions.** A TACTICS disc sits 60-83
   anchor px left of a player disc in the same slot, so a tactics card beside a
   player card produced a midpoint that was not the card boundary: live, slot 1's
   window was crushed 104 -> 36 px and left the halo entirely. Every disc is now
   mapped into one reference frame first (`local_hand.cursor_glow`).
2. **The window sat in the BACKDROP above each card**, not on the rim, so what it
   measured was how much of a card's own white top rim fell inside — which tracks
   how HIGH the card sits. A SELECTED card, raised ~44 px, out-read the card
   actually holding the cursor. The user spotted it on the stream: *"should you
   move slot 0's box down a little more? it's barely covering it."*

        window            argmax    true cursor      every other card     gap
        110,10,70,30      74/74     8.7 .. 36        0.0 .. 9.7         -1.0  OVERLAP
         80, 0,55,35      74/74    20.7 .. 36.1      0.0 .. 8.4        +12.3

`CURSOR_GLOW_MIN` 1.5 -> **15.0**, now between two measured populations rather
than inside one. `CURSOR_DOMINANCE` and the subtract-the-selected-cards rule are
**deleted**: both existed to work around the bad window, and with the window on
the rim a selected-but-unhovered card reads at most **1.9**.

**Evidence.** 74 labelled frames: 56 the user labelled BLIND (recovered from the
session transcript, including both corrections they issued) plus 18 curated
fixtures. Geometry chosen **leave-one-fold-out over all seven folds**; every fold
scored 74/74 on its held-out frames. Corpus and every script:
`agent_progress/rise-cursor/` (`corpus.py` is the single source of truth).

**Six mutants, six caught**, each by a different check, including behavioural ones
on the user's own frames (`agent_progress/rise-cursor/mutants.py`).

**The near-miss worth keeping.** A geometry picked on the 56 blind frames alone
won all six of ITS folds and then read 3.4 on `sweep_f00_slot2`, whose cursor is
plainly on slot 2 — that frame was in no fold. This is CLAUDE.md's at_table
lesson exactly (a 500-frame sample said zero; the 701st fired). The curated
fixtures are now in the corpus.

## Open, in priority order

1. **A run scoring is not detected.** `read_runners` gives base occupancy per
   poll and `ocr_scoreboard` gives totals, but **nothing compares consecutive
   reads**, so a runner advancing home just becomes `third: False` with no record.
   The user asked about this directly. Real gap, not a bug.
2. **`/QA` was requested and is running/queued** — see the session log. Offline
   only; the console must not be driven.
3. The hand reader is still not scale-free BELOW the windows (CLAUDE.md §3 OPEN):
   0.73x returns one row, 1.25x `find_tactics` misses the wreath on raw-pixel
   blob gates.
4. Crawl mode is NOT finished — the user: *"I'm not convinced that we're done
   doing crawl mode."*

## Rules that were in force and stay in force

- No console action without explicit approval.
- Never read or print `PERSONAL_ANTHROPIC_API_KEY`; presence checks only.
- Snoopy is a labelling aid, never wired into the live ladder.
- Ask before pushing, opening a PR, or posting anywhere shared. **Nothing has
  been pushed.**

---

# QA ROUND — 2026-09-11, after the window fix (42 agents, 0 errors, 48 min)

Four read-only finders on disjoint axes, one adversarial skeptic per finding.
**23 CONFIRMED, 15 REFUTED, 0 unproven.** The skeptics earned their keep: they
killed "a refusal leaves a card SELECTED and the next turn commits both", which
would have been the scariest finding of the night and is not true.

## Fixed tonight (all committed, suite green)

1. **A REGRESSION I INTRODUCED HOURS EARLIER.** The canonicalising comprehension in
   `cursor_glow` indexed `SLOT_PLAYER[i]` for EVERY row, and `read_hand`'s ungated
   path is unbounded (one row per strong disc plus one per unmatched tactics blob),
   so a six-row read raised `IndexError`. `selected_cards` already had the bound;
   this did not. Degrades to a retry rather than a wrong card — orchestrator catches
   and re-polls — but a reader that RAISES cannot abstain, and abstaining is its
   whole contract. Bounded, pinned, two mutants caught.
   **The first version of that test was decorative** and a mutant survived it: a row
   that BORROWS slot 0's anchor still reads 0.0 on a blank probe, so a reading-only
   check cannot see it. The check now asserts on the WINDOW (`_boxes`), and both
   mutants are caught.
2. **A measured number in the shipped docstring was from the SUPERSEDED window.**
   "a selected-but-unhovered card reads at most 1.9" was measured at (80,20,55,40),
   not the shipped (80,0,55,35), where it is **5.7**. Corrected in `local_hand`, in
   the test's comment, and in the fake screen the loop tests against.
3. **Six of the scoring scripts could not run at HEAD** (no repo root on `sys.path`)
   — the scripts that ARE the evidence for today's window and gate. Path-fixed.
   `rule.py` additionally hardcoded the superseded window, so its output read like
   evidence and was not; it now reads `local_hand`'s own constants and reproduces
   74/74 with a true floor of 20.7.

## CONFIRMED and NOT fixed — needs your call, ranked by money

1. **The production DISCARD path is blind.** `orchestrator.py:5429-5431` calls
   `select_and_discard(player_idx)` with **no `look=`** and **ignores its return**,
   so a discard takes the old blind counted-press path with no verification at all,
   while the PLAY path beside it is fully verified. Severity: plays-wrong-card, on
   the live $50 ladder. This is the highest-value item in the whole sweep.
2. **`tools/play_match_verified.py` plays a different card than the engine chose**
   whenever two cards tie on power (it re-derives the index by first-match on POWER,
   discarding the engine's speed tie-break) and a weaker tactics card when two share
   a type. Measured mismatch: **4.3% of turns** (player) and 3.1% (tactics) over 540
   recorded hands. **Do not run this tool on a paid match until it is fixed.**
   It also hardcodes `runners=[]`, which mis-values every decision with runners on.
3. **`find_tactics` gates the wreath on 28-48 x 30-50 RAW pixels** (CLAUDE.md §3's
   known example, now quantified). The wreath is 36.5-37.4 x 40.3-41.3 in ANCHOR
   units at every scale, so only the gate moves: the working band is s in
   [0.74, 1.24]. Every geometry this rig produces (0.972, 1.000, 1.042) is inside it
   and the reader is 74/74 today — latent, not live. **The fix is not one line:**
   scaling `find_tactics` ALONE takes the false-glow ceiling from 10.6 to 45.1 at
   1.25x, far above `CURSOR_GLOW_MIN` 15, i.e. confident WRONG cursor picks.
   `DISC_WHITE_SIZE` must be scaled with it (ceiling back to 8.0).
4. **`agent_progress/rise-cursor/mutants.py` mutates `local_hand.py` in the live
   checkout** with no `console_lock` check and no clean baseline (CLAUDE.md 10.17).
   It restored correctly tonight and I verified the sha, but the shape is the one
   that left `places.py` mutated for eleven minutes.
5. **Two "curated" fixtures are byte-identical duplicates** of blind-labelled crawl
   frames — the corpus is 74 entries but **72 distinct frames**. Does not change the
   window (both are interior, not at either population edge), but every "74" quoted
   anywhere should be read as 72.
6. **The corpus contains ZERO frames with no cursor on screen**, so the gate's
   NEGATIVE side is untested at frame level. During a turn the cursor is always
   somewhere, so this may be unfixable rather than unfixed — but `CURSOR_GLOW_MIN`'s
   protection against a black or mid-animation frame rests on the row-count and
   `y_measured` checks upstream, not on the gate.

Smaller confirmed items (label_score scoring unfilled template lines as real labels;
`turn_timer`'s docstring advertising five phases where the code marks three;
`play_match_verified` recording `dealt=True` on a REFUSED turn; `GLOW_WHITE = 190`
asserted rather than measured) are in the workflow journal:
`.../subagents/workflows/wf_59a3ee23-07d/journal.jsonl`, one result line per agent,
and each finder's notes under `agent_progress/qa-*/`.

## Swept clean — do not re-derive

`DISC_MIN_R`'s scale margin (refuted); the six other "raw pixel" distances (refuted,
they have no scale available and are genuinely scale-free); `label_batch`'s sampling
bias (refuted — homing-then-uniform does fix it); the duplicated argmax+gate rule
(refuted — both copies are tested); `forget_hand_slot`'s ordering (refuted); the
`is False` guard at every caller (checked, correct).
