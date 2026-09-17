# HANDOFF — 2026-09-17, overnight

## READ THIS FIRST: A PAID MATCH IS SUSPENDED, NOT FINISHED

**$50 is spent on a match parked mid-turn, and the PS5 is in REST MODE.** Rest
mode SUSPENDS the game, so the match survives. `match_in_progress` is `true` and
**that is CORRECT — do not clear it.** Check the screen before touching it (§2).

State when it was put to sleep, read off the frame:

    JACK PEPPER  2 0 2      OPPONENT  0 0 0
    a runner on HOME PLATE (Donny Mekesz, stranded) and Rube Sharp on a base
    hand of five, one turn of the BATTING half still unplayed

**The console was slept deliberately, at the user's instruction, and the walked
procedure is `console_rest_mode_procedure.md`.** Confirm the state before any
press with the three tells in §1 — capture size, `looks_like_ui()`, `streaming()`.

## NOTHING WAS CHANGED ON THE $50 PATH

No reader, no input path, no engine code was modified tonight. `local_hand.py`,
`input_controller.py`, `orchestrator.py` and `decision_engine.py` are untouched
(`git diff 2e54dcd..HEAD --stat` names only docs, fixtures and one new tool).

The user's standing rules were in force all night and still are:

    do not make plays without my approval
    the paid vision model stays OFF
    play the engine's pick; if it is wrong, fix the ENGINE

## WHAT WAS DONE, AND THE HEADLINE IS A NEGATIVE

The task: *"figure out exactly where the cards are so you more accurately read
the cursor no matter the drift or weird scenarios."*

**The cards ARE locatable exactly, and the reader already has the locator.**
Tophat (k=9, >30) strips the card art; the disc-to-corner offset is constant to
±2-5 px on clean slots. The power disc IS an exact locator; nothing to build.

**Four ways to exploit that were measured and ALL FAILED — and three would have
shipped on their TRUE numbers alone.** Full table and the mechanism are in
CLAUDE.md §10.35. One line: the window works BECAUSE it is pinned to the narrow
dark strip outside the card, the cards are white art, and every degree of freedom
added moves the box onto the card and destroys the discrimination.

**The binding constraint is the corpus, not the reader.** 4,183 five-row turn
frames exist and **4,142 are one run**, at 10 Hz. A "finding" — slot 4 blind 71%
of the time — dissolved into ONE fade burst sampled ten times (§10.8).

## THE UNLOCK, AND IT IS THE THING TO USE NEXT

`tools/cursor_labels_from_lifts.py <run_dir>` produces the first labels for
`cursor_slot` that the reader cannot influence: a card that RISES above its fan
anchor was selected, and selecting requires the cursor to be on it, so the frame
before it rises has a known cursor slot. Geometry, not brightness (§10.22).

    raw lift transitions 29 -> persisted 4   (86% dropped as deal-frame artefacts)
    shipped reader on the 4:  4 correct, 0 blind, 0 wrong

**~4 labels per recorded run. Point it at every future run** and the corpus
accumulates with no console time and no live change. That is what a threshold on
this path needs and does not have.

## WHAT IS WRITTEN AND DELIBERATELY NOT APPLIED

A **vertical bound** for the glow box — it is bounded horizontally by neighbour
midpoints and not bounded above, so on an unsettled hand it samples the card
ABOVE and returns a confident wrong answer. The patch is written, vectorised
(0.11 ms a slot, verified 300/300 against the loop it replaces) and **NOT
applied**, because its instrument fails its own control: on the one unambiguous
cursor in the archive, disc-to-backdrop reads 37-38 while NOT the cursor and
49-50 while it IS. **It rises with the halo it would police.** A gate would also
zero a plausibly-genuine reading of 142 mid-play, on the $50 path.

Evidence kept: `test_fixtures/card_above_box/` (3 frames + a README that states
what is and is not established). Scratchpad scripts are session-local and gone
on reboot; the tool and the fixtures are committed.

## THREE CORRECTIONS TO MY OWN WORK TONIGHT

Recorded because each read as a finding before it was checked:

    the phantom-card explanation for slot 2    killed by its own failed prediction:
                                               blanking the home-plate strip made the
                                               reading MORE extreme (-67 -> -77)
    "slot 4 is structurally weak"              an archived frame reads 28.2 at slot 4;
                                               the claim holds for THAT HAND only
    the vertical-bound guard                   its instrument is not independent of
                                               what it polices (above)

## SUITE

233 files, **5 failures, all confirmed PRE-EXISTING** at `2e54dcd` by running
them in a worktree at that commit: `test_run_resume_and_persist`,
`test_paid_reads_no_cards`, `test_reveal_kind_capture`, `test_post_play_timing`,
`test_local_retry_not_paid`. Not caused by tonight's work and not investigated.

## SUGGESTED NEXT STEP, THE USER'S CALL

1. Finish the batting half's last turn when the user is present (the engine's
   pick was slot 0 + a speed boost; a home run is arithmetically impossible).
2. Run `tools/cursor_labels_from_lifts.py` against every run the rig records
   from now on, and revisit the cursor gate once the label count is in the
   dozens rather than 4.
3. Leave the glow window alone until then — §10.35 is four nights' worth of
   reasons not to touch it without a FALSE column.
