# Auto Baseball — the always-loaded core

Automating the "Baseball Cards" minigame in *Mouse: P.I. for Hire*, played on a
PS5 and streamed to this Mac through a patched chiaki-ng.

**THIS FILE IS THE CORE, NOT THE RECORD.** It holds the rules that must be known
before touching anything. The record -- every measurement, correction and incident
behind these rules -- was moved VERBATIM into the topic files below on 2026-09-22,
with its original section numbers, because this file had grown to ~297 KB and was
loaded into every session whether the task needed it or not. **When a rule here is
not enough to act on, open the file it points to. Do not act on a guess about what
the record says.**

**Constants quoted here and in the topic files are COPIES; the source `file:line` is
the authority** -- `tests/harness/test_claude_md_constants.py` enforces that across
all of them.

**DO NOT ASSERT A CLAIM YOU HAVE NOT CHECKED. Say what you ran or read, or say you
are guessing.** The user's instruction, 2026-09-17: *"asserting claims without proof
aren't allowed. they are often wrong and waste time."* An unproven claim is not
cheaper than a verified one; it is the same work plus a retraction (§10.32).

**THE USER IS USUALLY RIGHT. When they propose something, the next move is a
MEASUREMENT, not a counter-argument** (§10.33). An earlier session built dead
reckoning after the user had asked for a closed loop; that cost days (§8).

---

## Read before you act

| Before you... | open |
| --- | --- |
| press anything at the PS5 overlay, or sleep/wake the console | `console_rest_mode_procedure.md`, then `RIG.md` §1 |
| touch chiaki, the stream, the venvs, the test suite | `RIG.md` (§1, §2) |
| change or trust a screen reader | `READERS.md` (§3, and the first-live-match findings) |
| reason about the game's rules, cards or money | `RULES.md`, then `GAME.md` (§4) |
| send input, or change an input path or the FIFO | `INPUT.md` (§5, §6) |
| build ANY navigation change | `GRAVEYARD.md`, then `NAVIGATION.md` (§7, §8) |
| design an A/B, a test, a mutation run or an agent fan-out; call anything dead | `METHODOLOGY.md` (§10) |
| pick up, measure or close a ticket | `OPEN.md` (§11), `CLOSED.md` |

**The §-number map**, because code comments cite "CLAUDE.md §N" and must still
resolve:

    §1, §2   RIG.md             §5, §6   INPUT.md
    §3       READERS.md         §7, §8   NAVIGATION.md
    §4       GAME.md            §9       below, and GRAVEYARD.md
    §10.N    METHODOLOGY.md     §11      OPEN.md

Unnumbered headings moved with their neighbours: "THE FIRST LIVE MATCH" and the
ban/state bugs after it -> `READERS.md`; the `check()` signatures, the input paths
and the keymap -> `INPUT.md`; every `at_table()` heading, the money reconciler, the
stale `match_in_progress`, the jukebox leg, the `cam` field and "SAVING A FRAME CAN
MAKE THE COMPASS READ 90 DEGREES WRONG" -> `NAVIGATION.md`; "Five more guards that
could not fire" -> `METHODOLOGY.md`.

---

## The rig (full text: RIG.md §1)

- **Standing permission (2026-09-01): start chiaki-ng and wake the PS5 when a run
  needs them.** No need to ask each time.
- **The console is usually ALREADY ASLEEP** -- it auto-sleeps when nothing reaches
  it. Three tells, no input needed: `game_capture.grab()` returns 1831x1030 rather
  than 1920x1080 (that is chiaki's window, not the game); `ensure_stream.looks_like_ui()`
  is True; `ensure_stream.streaming()` is False. **If it is asleep, leave it alone.**
- **Do NOT press `ps_button` to find out.** With no session running it raises
  chiaki's own "Quit?" dialog, one keystroke from killing the app. Dismiss it with
  ESCAPE only, with chiaki frontmost -- never Enter or Space.
- **To put it to sleep:** follow `console_rest_mode_procedure.md`, step and look.
  Presses are dropped (15% on the ban screen, clustered), X is SUBMIT, and
  "Turn Off PS5" sits directly under "Enter Rest Mode". Or stop sending input and
  let it auto-sleep. chiaki's own sleep path is unreachable on macOS; do not probe
  its keymap with keystrokes while a paid match is live.
- **`ensure_live()` returning True means the STREAM is up, not that the game takes
  input** -- the PS5 overlay can still be on top. Before pressing, wait until a
  reader that only answers on the screen you want says yes:
  `orchestrator.read_ban_counter(img)`, `local_hand.read_hand(...)`,
  `table_prompt.at_table(img)`.
- chiaki runs on the SECOND display (the LG ultrawide). `screencapture -x one.png`
  captures only the built-in display; use `screencapture -x a.png b.png`.
- The stream needs the **patched** build in `chiaki-ng-build/`, started with
  `./restart_chiaki.sh`. `/Applications/chiaki-ng.app` is stock: every input goes
  nowhere.
- **NEVER `cp` over a running binary** -- macOS kills it. Quit, copy, re-sign, relaunch.
- Capture the game through `game_capture.grab()`, never `mss.monitors[1]` (that is
  the laptop display, and it logged the user's work for 247 frames). Window geometry
  does not match capture geometry: never map capture fractions onto screen
  coordinates.
- A frozen picture is almost never a dead stream; `ensure_stream._clear_blocking_ui()`
  runs the ladder before any restart. OPTIONS and the PS button are TOGGLES: press
  once, then poll.
- The PS5 overlay is up and you want it gone: `ic.press('ps_button')`. X is SUBMIT
  and takes whatever the cursor is on -- it can drop you to the PS5 home screen.
- **Nothing that matters goes in `/tmp`.**

## The environment and the tests (full text: RIG.md §2)

- Everything runs on `./.venv` (Python 3.14):

      .venv/bin/python -B tools/doctor.py
      PATH="$PWD/.venv/bin:$PATH" ./run_tests.sh

- **`paddle_venv/` is never the interpreter and must never be deleted** --
  `result_ocr.py` spawns it to read the result banner on the live path. This file
  has been wrong about "unused" three times; verify before deleting anything on the
  strength of a sentence in it.
- **`grep` here skips every `.gitignore`d path.** For any count or "nothing uses
  this", use `grep --no-ignore-files` or `find ... -print0 | xargs -0 grep`, and
  exclude `agent_progress`, `drafts`, `backups`, `_obsolete`, `tests_quarantine`
  when the question is "is this dead" (§10.36). grep exits 1 on zero matches.
- **Two progress files.** Live runs pass `progress_file="progress_testing.json"`
  explicitly. `match_in_progress` guards the $50 debit -- check the screen before
  clearing it.
- `./run_tests.sh` sets `BASEBALL_TEST_RUN=1`, which holds every input path off.
  Anything that spawns test files must pass it down. Never set it at import time.
- Fixtures live in `test_fixtures/` at the project root. A test must never glob a
  directory a live run writes to.
- **A test that passes when the code is broken is worse than none.** Break what it
  guards and watch it fail. Delete `__pycache__/<module>*.pyc` between mutants.
  The suite has nine `check()` signatures in two argument orders, and a reversed
  call always passes (INPUT.md).
- **Mutation testing while the console is live:** ask whether anything
  timing-sensitive is in flight (a leg walking, a stick held, an A/B trial). If so,
  run it on Snoopy (`Snoopy_testing.md`) or wait. Parked on a turn, ban or result
  screen with nothing in flight: go, and say which it is.

## Reading the screen (full text: READERS.md §3)

- **THE PAID VISION MODEL IS OFF.** The user, 2026-09-12: *"stop using the paid
  model. you are no longer allowed to use it unless I say so."* Every field has a
  local reader.
- **The big coin in the bottom-left of the world HUD is HEALTH, not money.** Money
  is readable only on the pause menu: `orchestrator.read_balance_from_pause_menu()`.
- **Every offset is in anchor units and is scaled** (`s = img.width / ANCHOR_W`).
  Never a raw pixel; check any fixed-region reader at both capture geometries.
- Hand cards do not display a name. Match a played card on POWER.
- **Open the logged frame before theorising about a failure**, and check WHICH
  frame it is.
- OCR goes through one persistent handle and never off the main thread.

## Money and the game (full text: GAME.md §4, RULES.md)

- A match costs **$50**. "Load Last Save" restores the wallet to **$246**.
  `reset_env.reset_environment(progress_file=...)` restores the wallet AND clears
  `match_in_progress`; set the tracked balance by hand afterwards, because the
  wallet is not read from the game.
- **The shape:** bat in inning 1, pitch in inning 2, a fresh hand of 5 each half,
  5 rounds and 2 discards per half. The scoreboard is `[inning1, inning2, TOTAL]`:
  take `[-1]`, never sum it.
- **You cannot pause an active match.** OPTIONS opens "Give up?": NO = circle,
  YES = cross.
- On the ban screen, TRIANGLE is PLAY and starts the match with whatever is banned.

## Input (full text: INPUT.md §5, §6)

- **Buttons go to the KEYBOARD. Sticks go over the FIFO.** FIFO button bits do
  nothing on this console; `input_controller.INJECT_BUTTONS = False`.
- **The game ignores about one press in six, clustered, and nothing we send is
  lost.** The only remedy is to LOOK after a press and press again if it did not take.
- There are five paths to the console (keyboard, targeted Quartz, sticks, recovery
  keys, raw masks) and each needs its own `BASEBALL_TEST_RUN` lockout.
  `tests/rig/test_no_real_input_under_test_run.py` is the census.
- Anything that holds a stick is chunked or timed under chiaki's 5 s injection
  timeout.

## Navigation: current state (full text: NAVIGATION.md §8)

**The closed loop reached the goal: 40 trials, 40 arrivals, median 76 s
(2026-09-08, build 2c8fea7).** It looks after every push and takes position from the
screen, never from the stick. `dealer_table` is a POSE: confirm arrival with
`table_prompt.at_table()`, never `identify()`. **Read `GRAVEYARD.md` before building
any navigation change.**

## §9 The graveyard

**13 well-motivated navigation and rig changes have been built, reviewed
and measured here. None moved the number it was built to move** — two were kept
anyway, for a speed gain and for correctness, and both say so. The full table, with the numbers that make each one
stick, is in **`GRAVEYARD.md`** — deliberately not loaded automatically.

**Read `GRAVEYARD.md` before building any navigation change.** The failures are
not random: every change that failed MOVED the character, and the only two
survivors (the aim sweep, and turning) move nothing.

Two families are closed on both sides and any proposal of that shape is a
rediscovery unless it brings new evidence:

- **Steering while walking** — a 30 deg heading lag became METRES of position
  error. Turn-then-walk exists precisely because it cannot convert a heading
  error into a position error.
- **Chunking a leg into more cycles** — re-accelerates from standstill every
  chunk and walks the leg SHORT; once ended two rooms adrift.

`LEG_TURN_TOLERANCE` is NOT that shape, which is why it is the one in-leg idea
still worth testing: it adds no chunks and does not steer while walking. The leg
already contains N turn-then-walk steps; tightening the tolerance only makes
turns that are currently NO-OPS actually execute — same structure, same
accelerations, same distance. OPEN-3 was cancelled on exactly that re-derivation — `GRAVEYARD.md`.

---

## §10 Methodology, the short form (full text: METHODOLOGY.md)

- **10.1** The commonest bug: the code did nothing, and doing nothing looked
  exactly like working. Ask what the log would show if the step never ran.
- **10.2-10.8** Only an interleaved A/B counts; at least 10 trials an arm; change
  one thing at a time; state n beside every rate; a threshold sits BETWEEN two
  measured populations, never inside one.
- **10.9** Mutation-test anything load-bearing.
- **10.15** Keep a frame -- and check what moment it captured.
- **10.16** A dispatched sub-agent writes `agent_progress/<label>/progress.md` AS IT
  GOES. Routine scouting runs on a cheap model. In a fan-out, the scratch path and
  the model must be set PER AGENT (10.16b). Scratch trees are copies, never symlinks
  into the checkout (10.16a).
- **10.16c** This shell is zsh with bfs/BSD tools: `find -newermt` fails silently
  (use `-mmin`), awk has no `\b`, zsh does not word-split, `$?` after a pipe is the
  last command's. Run any wait condition once by hand before arming it.
- **10.21** Never edit a module on disk while a live run is importing it.
- **10.29** Before any experiment on a live match, assert the starting state.
- **10.37** Before reporting a function broken, check the argument shape it wants.
- **10.38** A sub-agent's "I ran it and got X" is a hypothesis. Re-run it.

## §11 Open work

The ticket list, with status, is `OPEN.md`. Nothing outside it may claim to be open.
