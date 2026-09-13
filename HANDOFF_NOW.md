# HANDOFF — 2026-09-13, end of session

## UPDATE, ~04:30: THE PS5 LEFT THE GAME. Nothing is mid-match any more.

The console is on the **PS5 HOME SCREEN** ("Continue where you left off - MOUSE: P.I. For
Hire | 65%"). The game is closed, so the match described below is GONE and its
`match_in_progress` flag was stale -- checked against the screen, then cleared with
`clear_match_state.py`. Evidence: `agent_progress/ban-labels/EVIDENCE_ps5_home_match_gone.png`.

    money        progress_testing.json balance $96, match_in_progress FALSE
    preflight    READY (it said NOT READY while the flag was set -- correctly)
    to resume    press Play Game on the PS5, then reload the save

**THE ONE WARNING WORTH ACTING ON**, and it is the oldest open item on the project:

    no calibrated window position recorded for this machine yet

`window_drift()` can only ever report "ok" until a reference exists, and what it guards is
a MONEY path -- a 110px window shift silently flipped a ban-grid cell and banned a different
card, with no error raised. Arming it takes one command, on a ban screen that is reading
correctly:

    python3 -c 'import input_controller as i; i.save_window_reference()'

That needs the game up and a good ban screen, so it is the first thing to do on waking.

## THE ORIGINAL NOTE, kept for the money trail

## THE CONSOLE IS LEFT MID-MATCH. READ THIS FIRST.

A **paid match is open** and parked on the **ban screen, 0/3 banned**. Nothing was pressed
after that. `$50 was spent and IS tracked`: `progress_testing.json` went 146 -> 96 with
`match_in_progress: true`, debited BEFORE the press, which is the order `run()` uses so a
crash leaves the record over-debited rather than under.

    what            where
    screen          ban screen, BANNED CARDS 0/3, scroll level 0
    money           progress_testing.json balance 96, match_in_progress true
    stream          healthy (chiaki restarted this session, see below)

**Do not start another match without checking that flag.** A stale `match_in_progress`
with a real dealer prompt on screen is how this project spends an untracked $50
(CLAUDE.md). The flag is TRUE and CORRECT right now — a match really is open.

To finish it: Triangle plays with 0 bans. To abandon: OPTIONS, then Cross (YES); the
reload restores the wallet. Either is fine; neither is urgent.

## The stream froze mid-session and the fix is documented

`tools/doctor.py` reported `picture frozen True` with the frame dump 6.6 MINUTES stale, and
captures silently fell back to screen-grabbing the chiaki window — so two "live" renders
were of a frozen picture. The user spotted it, not me. `_clear_blocking_ui()` did not clear
it (the sequence number never moved), `./restart_chiaki.sh` did, in ~12 s. **Check
`doctor.py`'s frozen line before trusting any capture**; a frozen frame looks completely
normal.

## What landed today (all committed, suite green at 182 files)

    1f22a23  the diamond capture never ran, and test_no_undefined_names was blind to it
    92465ff  the paid lockout was one attribute name wide; the diamond lies on a ban screen
    00365bf  every card is a BATTER or a PITCHER, and the simulator did not know
    7001662  the live viewer drew match boxes on a ban screen
    62755f6  the ban-grid rows MOVE; find them in the frame
    290736c  read the card TYPE off the ban grid
    a981ea2  locked is not unknown
    d8b4f79  it is a 2D array: one row and the pitch place all of them
    01a88cc  the pitch is confirmed by a second method (which is not a better estimator)
    2b2bc1f  solve the grid's one unknown: 17 of 17 frames, phase error <= 0.003
    053d5c4  the live viewer was broken and its error was only visible on screen

## The ban grid is solved; here is the geometry, measured

    columns   starts 0.145 0.280 0.415 0.550 0.685   pitch 0.135 (all four gaps identical)
              width 0.130
    rows      pitch 0.328   card height 0.2995   name banner at 0.79-0.93 of card height
    phase     SOLVED PER FRAME by pooling the name banner's edges across every row
              error vs a hand-read ruler: +0.001 +0.001 +0.001 +0.003 +0.003
    coverage  17 of 17 archived frames, one box height per frame

`ban_grid.py` is standalone and has no test file yet — **that is the first thing to do.**
It is load-bearing for everything below and is currently guarded only by the fact that I
ran it on 17 frames by hand.

## Open, in the order I would take them

1. **`ban_grid` has no tests.** Pin the phase against the frames in
   `agent_progress/ban-labels/` (gitignored — copy the two or three that matter into
   `test_fixtures/` first, named, never globbed) and mutation-test it.
2. **Promote the fit into `orchestrator`.** `get_ban_grid_card_crop` still uses the fixed
   fractions, which are wrong at most scroll positions. The offline 383-frame harvest
   should be re-run through the fitted box; that is what finally audits the roster's
   numbers rather than its names.
3. **Read power and shield off ban cards.** `ban_grid.power_box` / `shield_box` exist and
   are unused. The hand reader's TEMPLATE matcher is the right tool (the user's suggestion)
   and beats tesseract, but it is anchored on a disc centre in hand-strip anchor units, so
   the ban card has to be mapped into that frame first.
4. **Two cards still untyped:** Brian Coker (8/1) and Zachary Lee (6/2). 31 of 33 are typed
   from four agreeing signals. `simulate.UNTYPED` names them and keeps them in both pools.
5. **QA findings not yet fixed** — two git worktrees still hold pre-lockout `orchestrator.py`
   with 5 unguarded paid call sites reading the real key. Removal is destructive and needs
   the user's yes. `xenodochial-babbage-349ee0` has 0 unique commits; `eloquent-spence-03fe41`
   has 1 that duplicates `bea5fa4`.

## Open questions that need the console, not code

  * **Does a speed boost persist while a runner sits on base?** Two runners read +1 over
    their card (Rube Sharp 1->2, Noah Kelly 2->3). The user's source says it does NOT
    persist, and `simulate` models it that way. Unresolved; one live at-bat decides it.
  * `FIELDING_SUBTRACT_PER_POINT = 1` is still unmeasured.

## Rules in force

The paid vision model is OFF and may not be re-enabled without the user saying so. Crawl
mode: no console action without explicit approval.
