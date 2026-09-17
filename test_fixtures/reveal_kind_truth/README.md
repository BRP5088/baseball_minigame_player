# reveal_kind_truth — ground truth for the tactics-KIND reader

48 reveal frames whose played card is KNOWN, because we played it:

    reveal6/f_*.jpg   25 frames   we PITCHED a fielding boost; they BATTED a speed boost
    reveal/r_*.jpg    23 frames   we BATTED a power swing;     they PITCHED a pitch focus

WHY THEY LIVE HERE. These are the only frames that can re-measure
`reveal_cards.TACTICS_KIND_MIN` (0.75), a shipped gate, and the only source the
shipped template banks are cut from. They sat in `agent_progress/base-timing/`
until 2026-09-17 -- gitignored, untracked, and named by CLAUDE.md as "safe to
delete wholesale". Nothing would have failed when they went; the gate would
simply have become unmeasurable and the banks unbuildable.

FIVE OF THEM SUPPLIED TEMPLATES and must stay excluded from any scoring run --
a template matches its own source at 1.000 (CLAUDE.md 10.30):

    f_001503.jpg  f_002645.jpg  f_003571.jpg  r_003660.jpg  r_006285.jpg

`tools/banner_kind_census.py` holds that exclusion list and scores the rest.
`tools/base_timing.py` still WRITES new captures to `agent_progress/base-timing/`;
that is scratch, and this is the kept copy.

---

## live/ — captured during a real match, 2026-09-17

Two sets, both with the kind known because THE ENGINE CHOSE IT and the frames
were captured by the same process that pressed the button. `manifest.json`
carries the ground truth, the true margin and the observed outcome.

    t1_ours_swing2_theirs_pitch2/   25 of 85   ours POWER SWING +2, theirs PITCH FOCUS +2
    t2_ours_swing1_theirs_none/     25 of 62   ours POWER SWING +1, theirs no tactics card

**THE FIRST SET IS WHY `margin_from` NO LONGER INFERS A +2 ON THEIR SIDE.** The
opponent's card is a PITCH FOCUS carrying **+2**, which refutes section 4's
"POWER SWING is the ONLY card ever above +1" -- a census taken entirely from our
own hand, against a player holding a SEPARATE DECK. See RULES.md.

**AND BOTH SETS SAY THE GATE IS MISMEASURED ON LIVE FRAMES.** Our own card is a
POWER SWING in both, plainly legible to the eye in the saved jpegs, and the
banner reader scores it:

    t1   85 frames   0.455 .. 0.500      TACTICS_KIND_MIN is 0.75
    t2   62 frames   0.563 .. 0.578

**Not one frame of 147 clears the gate**, where the archived corpus this gate was
fitted on abstains on 29% (25 of 86). So the two populations are not the same
population, and the 0.75 was fitted on frames that do not represent a live
reveal. That is OPEN-24's question with real evidence attached for the first
time -- and the cost is concrete: t2's margin of 3 was an automatic HOME RUN the
reader could not compute, confirmed only because the scoreboard went 0-0 to 2-0.

Do NOT re-fit the gate on these alone: 147 frames from two at-bats in one match
is a sample of two plays, not of the game (section 10.8). They are the first
ground-truth-PAIRED reveal frames on this project; the archive has 148 such rows
in `match_log.jsonl` with zero surviving pictures.
