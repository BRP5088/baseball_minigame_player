# HANDOFF — 2026-09-13, overnight

## STATE AT HANDOFF

    preflight            READY (1 warning: 2 other displays attached)
    suite                197 files green at JOBS=4 (281s) AND at JOBS=1 (901s),
                         both AFTER the width change -- so no result depends on
                         parallelism
    working tree         clean
    console              awake, idle in the world at the spawn, NO match running
    match_in_progress    False
    money                GAME WALLET 246, progress_testing.json 246 -- RECONCILED
                         (read live from the pause menu, locally, no paid call)
    paid vision model    OFF and staying off

**THE MONEY IS DONE -- that was the first job and it is closed.** The tracked
balance had been $50 below the game's because a match was debited and then given
up + reset away. `pause_menu.read_money` on a confirmed pause screen returned
$246 locally with no paid call, and progress_testing.json now matches. The input
target was verified BEFORE any press: `chiaki_pid()` -> 83980, and `ps` confirms
that pid is the patched binary under `chiaki-ng-build/`.

**NOTHING IS OUTSTANDING OR BROKEN.** The JOBS=1 confirmation ran after every
change tonight and came back all green, 197 files, 901s. The working tree is
clean and every change is committed. Start from section 6 below ("WHAT IS LEFT")
if you want more of the same work; nothing there is urgent and nothing is on the
money path.

## TONIGHT'S PROGRESS (appended as it landed)

**1. MONEY IS RECONCILED.** `pause_menu.read_money` on a confirmed pause screen
returned **$246**, locally, no paid call, menu opened once and closed in its
`finally`. `progress_testing.json` balance 196 -> 246. Preflight agrees; the
file is gitignored, so the pre-edit copy is in the session scratchpad.
Input target was verified BEFORE any press: `chiaki_pid()` -> 83980, and
`ps` confirms that pid is the patched binary under `chiaki-ng-build/`.

**2. THE COMPASS WORRY IS REFUTED AND THE DEAD STORE IS GONE.** See the fossil
section below -- the short version is that `VIEW_CENTRE_FRAC` was computed into
a variable overwritten two lines later, proven inert by mutation over 160
frames, and is now deleted with its history kept. Behaviour-preserving against
HEAD on the same 160 frames.

**3. THE REVEAL GATE DOES NOT BLOCK REMOVING THE UPSCALE.** Full census, all
15,799 archived frames, `center_card_edge_fraction` at 1920 native vs 2000
upscaled:

    frames classified REVEAL   @1920 298   @2000 290
    frames that CHANGE SIDE if the upscale goes:  8 of 15,799  (0.051%)
    direction: all 8 are 1920-detects / 2000-misses -- the SAFE direction
    ratio b/a: p05 0.675  p50 0.921  p95 0.944

So `REVEAL_EDGE_THRESHOLD = 0.065` needs NO re-derivation. **Two corrections to
my own earlier reasoning, both from the same mistake -- reading a 700-frame
sample as if it were the census:**
  * I claimed the upscale "widens the false-positive margin 4x and is doing real
    work". WITHDRAWN. At n=700 the 1920 band looked like [0.0627, 0.0745]; at
    n=15,799 it is [0.0649, 0.0664]. The gap closed 8x. That is the at_table
    lesson again -- 500 frames said zero and the 701st fired.
  * The "empty band" metric itself was over-read. It measures the gap around an
    ARBITRARY cut point, not the separation between two LABELLED classes, and in
    any continuous distribution more samples fill in near any cut. It was never
    evidence either way.
  HONEST RESIDUAL: no clean cut exists at either width (largest gap ~0.0015
  both), so that gate has never sat in an empty band. Whether 0.065 is WELL
  placed cannot be answered without labelled reveal frames. Recorded as
  unmeasured, not treated as evidence.

**4. THE WIDTH IS FIXED, AND IT WAS ONE NUMBER, NOT A DELETION.**
`SETTLE_CALIBRATION_WIDTH = 2000 -> 1920` (commit 27cd4ae). I first proposed
deleting the upscale; that was wrong. The normalisation is REAL WORK on the
FALLBACK path, which can return an mss logical grab (1728x1117) or a pyautogui
Retina grab (3456x2234) -- mean-abs-delta is scale-sensitive, so those must be
brought to a common width or the statistic is not comparable between backends.
Only the WIDTH was wrong. At 1920 the primary path is a true no-op, because
game_capture.grab resizes only when the width differs.

It also closed a split `test_reveal_watch` had documented all along: the reveal
watcher scored the dump at native 1920 while the poll resized to 2000 -- two
readers of the SAME screen at different widths BY DESIGN. Both are 1920 now.

NEW GUARD: `tests/rig/test_settle_calibration_width.py`. Nothing had pinned this
constant for months. It asserts BEHAVIOUR, not the value (10.11): a frame at the
rig's geometry passes through untouched, a foreign geometry is normalised, the
hand crop lands on ANCHOR_W from either. Two mutants caught, and the driver
PROVES each mutant is live first, because 1920 -> 2000 is a same-SIZE edit and
10.10's stale-bytecode trap would otherwise report a good test as decorative.

**5. THE COMPASS GEOMETRY CONSTANTS ARE GONE** (commit 14ffada): two dead stores
plus PITCH_PX_PER_90 / REFERENCE_WIDTH / VIEW_CENTRE_FRAC. Equivalence against
the previous revision on 160 explore/ frames: 0 differing bearings, 0 abstention
flips -- WITH a control proving the harness bites (a deliberate
`centre_x = vmid + 30.0` gives 135/160). 44 of 44 compass tests green.

**6. WHAT IS LEFT, in order:**
  a. the surviving fossils in `agent_progress/HARVEST/triage.json` -- but see
     the note below on how few of them are real
  b. `compass.TURN_FIXED_DEG` / `TURN_RATE_DEG_PER_SEC` / `MIN_HOLD_SEC` are
     value-for-value duplicates of `turn_gain.FIXED_DEG` / `RATE_DEG_PER_SEC` /
     `MIN_HOLD_SEC`, and production turning goes through `turn_gain.run_turn`.
     `tests/routing/test_turn_control.py` builds its FAKE actuator from the
     compass copies, so if turn_gain's values changed the test would keep
     simulating with the stale ones and pass. NOTE: an agent filed this as
     10.11 ("a test asserting against the constant it guards") and that framing
     is WRONG -- the test guards the stop RULE, not the value, and simulating an
     actuator that matches the controller's model is legitimate. Fix it as
     "the fake models the wrong module", which is narrower and true.
  c. `MASK_KERNEL = 41  # roughly card-art scale at SCREENSHOT_MAX_WIDTH`
     is a raw-pixel kernel calibrated at 2000 and now applied to 1920 frames;
     the matched value would be ~39. Marginal, unmeasured, NOT acted on.

**7. HOW MUCH OF THE FOSSIL SWEEP WAS REAL -- read this before mining the
triage file.** Two workflows produced 48 CONFIRMED fossils. Three skeptics per
finding then refuted **17 of the 22 they reached -- a 77% kill rate -- including
EVERY wrong-card, money and ends-match candidate, all 3/3 unanimous.** Four
survived, all low-blast compass/turning items. 27 were never tested because the
workflows were stopped.

    THE 27 UNTESTED ARE NOT A BACKLOG OF FINDINGS. At the observed kill rate
    expect ~20 of them to die too. Each one gets the mutation-prove treatment
    (change the value / make the body raise, run the suite) or nothing.

That is the lesson worth more than any single fossil: the raw fan-out output was
mostly noise, and the adversarial pass is what turned it into signal. Reported
without it, most of that list would have been wrong -- including the
scary-sounding entries.

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
    **SETTLED, AND THE WORRY IS REFUTED. The constants are INERT.** The
    contradicting measurement (the spawn reading 87, i.e. facing E) was the true
    one. `read_bearing` computes `centre_x = w * VIEW_CENTRE_FRAC` and then
    OVERWRITES it two lines later with `centre_x = vmid`, measured from the bar
    itself -- a dead store wearing the comment of a live calibration. Proven by
    MUTATION rather than by reading: over 160 explore/ frames at the live
    1920x1080 geometry, forcing VIEW_CENTRE_FRAC to 0.10, PITCH_PX_PER_90 to
    50.0 and REFERENCE_WIDTH to 600 each moved ZERO bearings and flipped ZERO
    abstentions. (Baseline abstention 25/160 = 15.6%, reproducing OPEN-15's
    recorded 15.6% exactly -- an independent check that the harness reads the
    way the project does.)
    FIXED: the dead store and VIEW_CENTRE_FRAC are deleted, the history kept in
    a comment; verified behaviour-preserving against HEAD's compass.py on the
    same 160 frames (0 differing bearings, 0 abstention flips).
    PITCH_PX_PER_90 and REFERENCE_WIDTH are KEPT: they measured inert over the
    same corpus, but their consumer `pitch` is only reassigned inside
    CONDITIONALS, so the fallback is reachable in principle. Empirically inert
    is not structurally dead.
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
