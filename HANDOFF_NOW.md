# HANDOFF — 2026-09-13, overnight

## STATE AT HANDOFF

    preflight            READY (1 warning: 2 other displays attached)
    suite                196 files green
    working tree         clean
    console              awake, idle in the world at the spawn, NO match running
    match_in_progress    False
    money                GAME WALLET 246 (restored by the reset earlier today)
                         progress_testing.json tracks 196  <-- NOT RECONCILED
    paid vision model    OFF and staying off

**THE ONE THING TO LOOK AT FIRST IN THE MORNING:** the money line above. The
tracked balance is $50 below the game's because a match was debited and then
given up + reset away. Reconcile it from a LIVE PAUSE-MENU READ, never from
memory or from this file -- a wrong $50 got into this record once already that
way. `pause_menu.read_money` on a confirmed pause screen; then
`orchestrator.save_progress(..., 246, "progress_testing.json", ...)`.

## THE SESSION'S THEME: FOSSILS

The user, on being shown the first one: *"That's a code smell... a lot of ideas
that didn't pan out still exist in code and things may have been reused."*

**THE TEMPLATE, CONFIRMED.** `orchestrator.SETTLE_CALIBRATION_WIDTH = 2000`
upscales every settle frame from the native 1920 before any reader sees it. Its
comment says the calibration frames "were 2000px wide". The ONLY 2000px frames
in the archive are 32 files at **2000x1292, aspect 1.548**. 1728x1117 -- this
Mac's BUILT-IN DISPLAY -- upscaled to width 2000 gives 2000x1293, aspect 1.547.
Opened, they show the macOS menu bar, the Dock down the right edge, and chiaki
in a window. They are dated **Aug 26**; on **Aug 27** the game moved to a second
monitor and `game_capture.grab()` was written to capture the GAME instead.

    the capture layer was replaced underneath the constant, and the constant
    never moved

Cost: the hand reader is handed a 1020px crop against `local_hand.ANCHOR_W`
979, and read ZERO cards in the first live match.

**AND IT IS A FAMILY, NOT ONE CONSTANT.** Two more of the same Aug-26 geometry
surfaced, both verified by hand:

  * `compass.REFERENCE_WIDTH = 2000` with `PITCH_PX_PER_90 = 293.0` and
    `VIEW_CENTRE_FRAC = 0.4840`. **The comment states the dead world outright:**
    "Where the game view's centre sits in the capture. The frame includes the
    macOS menu bar and the dock, so this is NOT the image centre." Measured as
    "a 9-pixel blob at x=968 of a 2000px capture". Today's capture is chiaki's
    FRAME DUMP -- the game's own decoded pixels, no menu bar, no dock -- where
    the view centre would be 0.5. The gap is ~0.016 of width = ~30.7px at 1920
    = **~9.8 degrees of systematic bearing bias**, almost exactly the size of
    the 11-degree bias this constant was introduced to REMOVE.
    **DO NOT ACT ON THIS YET. There is a contradicting measurement:** the spawn
    read 87 tonight and section 8(d) has it deterministic at 86.9-87, which the
    user describes as facing E (90). A 10-degree error would not land there.
    SETTLE IT BY MEASUREMENT: find the aiming reticle in a modern frame-dump
    capture and compute its x-fraction. ~0.484 -> the constant is right and only
    the comment is stale. ~0.5 -> it is a live fossil costing ~10 degrees on
    every absolute bearing.
  * `orchestrator._CALIBRATED_ASPECT = 1728 / 1117` -- the laptop display's
    aspect, compared against `_MSS.monitors[1]` at import to warn that
    "fractional crops will target the wrong pixels". The capture no longer comes
    from mss at all; it comes from the frame dump. So the warning watches a
    display that is not the capture source. It only PRINTS, so it is low blast,
    but it is a guard that cannot mean what it says.

## WHAT LANDED TONIGHT (2 commits, both mutation-tested)

  ae83835  Cherry-pick the fallback counter: the fix landed, its guard did not
  cfac235  A reset recovers spent money, so money is not a reason to refuse a run

**The cherry-pick is the interesting one.** Auditing the stale worktrees found
one commit never on main, a2b71d7. Checked BOTH halves rather than assuming:
the production seam (`read_heading` threaded through `_look_around_for_a_node`
into `ws.turn_to`) was ALREADY on main; the TEST's fallback counter was ABSENT.
So the fix was fine and the thing that PROVES it stays fine was sitting where
nothing runs it. `test_frozen_stream_is_invalid.py` still passed for the reason
it always had -- because chiaki happened to be up -- and went red at ~04:00 on
2026-09-09 when chiaki exited. Two mutants, both caught:
  M1 `start = (read_heading or _default_heading)()` -> `_default_heading()`
     -> FAIL on the compass check, capture check still PASSES (the original
        bug's exact signature: only read_heading leaked)
  M2 delete `_FELL_BACK["capture"] += 1`
     -> caught by the second anti-vacuity control, which is the mutant that
        SURVIVED before that control existed

The commit's two OTHER test edits were deliberately NOT taken: they widened
stubs to `**_kw`, while main now MIRRORS the real signature -- strictly better,
because `**_kw` swallows a signature drift instead of failing on it.

## WORKTREES REMOVED (user-approved), 987M -> 8K

Both held complete, runnable copies of the whole input stack with NONE of
today's lockouts:

                          focus_input_allowed  targeted  BASEBALL_TEST_RUN
    live checkout                   5              3            12
    both worktrees                  0              0           3-5
    ensure_stream.py     live 5  ·  worktrees 0
    inject_reset.py      live 3  ·  worktrees 0

Unguarded `inject_reset.reset()` is OPTIONS x5 -> DPAD_DOWN x4 -> **CROSS x6**;
mid-match OPTIONS opens "Give up?" and CROSS answers YES.

Checked before deleting: everything was tracked (overnight/ alone is 4,880
tracked files), the only untracked things were .DS_Store and one JSON that is
byte-identical and same-dated in main. The xenodochial tree's ignored entries
were SYMLINKS INTO THE MAIN CHECKOUT (.venv, paddle_venv, screenshot_log, ...)
-- `git worktree remove` was used rather than anything that could follow them,
and all nine targets were verified present afterwards, with `git status` clean
and no tracked file turned into a symlink (10.16a's signature).

**The branch `claude/eloquent-spence-03fe41` was KEPT** so a2b71d7 stays
reachable at zero disk cost. `git log --oneline -1 claude/eloquent-spence-03fe41`.

## IN FLIGHT WHEN THIS WAS WRITTEN

Two background workflows, both in their Refute phase:

  wf_e5ec5d71-6c8   settle-width-provenance -- re-derives SETTLE_THRESHOLDS at
                    1920 and at 2000 off the 14,437-frame 10Hz run, measures how
                    many pairs change side of their gate, maps what breaks if
                    the upscale is deleted
  wf_013a062e-f8b   fossil-hunt -- five axes (stale constants, dead generations,
                    duplicated facts, obsolete workarounds, inert flags), three
                    skeptics per confirmed finding

Transcripts under
`~/.claude/projects/-Users-bpatterson-.../subagents/workflows/<runId>/`;
read `journal.jsonl` before assuming any cached result is non-empty.

## THE PROTOCOL FOR ACTING ON A FOSSIL (user-approved)

Never delete on an agent's say-so. CLAUDE.md's loudest warning is that the
claims it gets WRONG are exactly the "unused / safe to remove" ones --
`paddle_venv` was 777M of "nothing uses it" while five production runners
shelled into it by subprocess.

  1. Re-verify personally. An agent describing its own finding is the weakest
     evidence available (10.16).
  2. **Prove inertness by MUTATION, not grep.** A constant claimed unread: set
     it to an absurd VALUE and run the suite -- if nothing changes, nothing
     reads it. A function claimed uncalled: make the body raise -- if nothing
     raises, nothing calls it. A grep misses `getattr`, a dict registry, a path
     built from a string; a value change cannot be missed by a real reader.
  3. **Name what the suite does not reach, and stop there.** The offline suite
     never walks a leg, plays a match, or takes the recovery ladder. A fossil
     living on one of those passes step 2 and is still live -- record it as
     UNVERIFIED-DEAD and leave it. This is the step that would have saved
     paddle_venv.
  4. **Quarantine to `_obsolete/`, do not delete.** Git makes deletion
     recoverable in principle; nobody does archaeology at 3am mid-run. The
     exception is anything whose EXISTENCE is the hazard -- a second unguarded
     copy of an input path -- which is why the worktrees went.
  5. One commit per fossil, with a pointer left where it was, so a bisect names
     it and the next person does not re-derive it.

**NOT TO BE TOUCHED:** `armor_venv` (601M, arrived 2026-09-09 with the local-OCR
bake-off; its ONLY reference anywhere is a test's SKIP_DIRS list -- the exact
paddle_venv shape, so it is recorded, not removed). Anything invoked by
subprocess. Anything whose only consumer is a test -- a test IS a use.

## RULES IN FORCE

  * The paid vision model is OFF. `orchestrator.PAID_MODEL_ENABLED = False`,
    raises `PaidModelDisabled`. Re-enabling needs the user to say so.
  * Online work IS permitted (user, tonight): a reset recovers spent money, so a
    bad match costs time and not money. It does NOT make a bad RESULT cheap --
    see the wrong-ban defect below.
  * Button presses go to the chiaki window and nothing else.
  * Never read or print `PERSONAL_ANTHROPIC_API_KEY`; presence only.
  * Mutation testing runs here only while nothing timing-sensitive is in flight
    (no stick held, no leg walked, no A/B, no settle measured). Quote the
    mechanism when overriding. Otherwise Snoopy, or wait.

## THE OPEN DEFECT THAT SHOULD GATE ANY UNATTENDED MATCH

**A stale column frame bans the WRONG CARD and reads as 3/3.** A horizontal
press mid-travel moves no scrollbar, so `ban_cursor_absolute` reads a valid
level and reports the halo where it still is -- a confident, stale cell. 126
wrong-ban outcomes over 10,927 late-frame combinations; on the realistic
3-target run **75 of them end with three cards banned, one of them wrong**, and
`read_ban_counter` says 3/3 while the run prints "verified 3/3 bans placed".
`ban_x_on` logs the wrong ban as a MISSING ban.

The fix is identified and not built: `ban_grid.banned_cells` already returns
EVERY visible X and `ban_x_on` throws all but one away -- compare the full hit
set against the expected set after each `select_card`. It changes ban
verification on the $50 path and wants a live screen.

**Do that BEFORE spending recovered money on matches**, because a reset repairs
the wallet and does not repair a conclusion.
