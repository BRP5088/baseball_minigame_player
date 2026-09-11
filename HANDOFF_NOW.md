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
