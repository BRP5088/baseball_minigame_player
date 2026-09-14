# Auto Baseball — things that are expensive to relearn

Automating the "Baseball Cards" minigame in *Mouse: P.I. for Hire*, played on a
PS5 and streamed to this Mac through a patched chiaki-ng.

Everything here was learned by getting it wrong first. The cost of re-deriving
any of it is a wrong conclusion reported confidently, real money, or both.

**How to read this file.** Current state is §8. Dead ideas are `GRAVEYARD.md`
(not loaded automatically — **read it before building any navigation change**).
Open work is §11. Nothing else here is a status report. Constants quoted here
are COPIES; the source `file:line` is the authority.

---

## §1 The rig: PS5, chiaki, the stream

**Standing permission (2026-09-01): start chiaki-ng and wake the PS5 when a run
needs them.** No need to ask each time. The console auto-sleeps when nothing
reaches it — that killed the 2026-09-01 overnight run four minutes in, and
contaminated a whole leg-tolerance A/B on 2026-09-03.

- The stream needs the **patched** build in `chiaki-ng-build/`.
  `/Applications/chiaki-ng.app` is stock: no injection, every input silently
  goes nowhere. Verify a binary with `nm -U <binary> | grep -i inject`.
- Start with `./restart_chiaki.sh` (aliased `chiaki-analog`).
- **NEVER `cp` over a running binary** — macOS kills it with "Code Signature
  Invalid" and the next launch dies the same way. Quit, copy, re-sign, relaunch.
- Capture the GAME window through `game_capture.grab()`, never
  `mss.monitors[1]` — that is the laptop display, and it logged the user's own
  work for 247 frames.
- **Window geometry does NOT match capture geometry**: the chiaki window
  measured 2540x1030 while `fast_capture()` returned 1867x1050. Never map
  capture fractions onto screen coordinates; use key presses or the
  accessibility API.

### A frozen picture is almost never a dead stream

Every real cause SITS ON TOP of a healthy stream, and a restart fixes none of
them (it re-creates the first one). `ensure_stream._clear_blocking_ui()` runs
this ladder before any restart:

1. Dismiss the macOS "Problem Report" window **by name**, not by coordinates:
   `osascript -e 'tell application "System Events" to tell process "Problem
   Reporter" to click button "OK" of window 1'`
2. Front chiaki. `_key()` posts to the pid, which reaches the game but **not** a
   modal Qt dialog — those only clear when the process is frontmost.
3. Return — clears chiaki's own modal **and** connects from the host list.
4. Escape (PS button) — clears the PS5 Control Center.

chiaki shows **"Vulkan renderer is unavailable"** on every launch (MoltenVK is
absent; libplacebo dlopens Vulkan). It predates the 2026-09-03 rebuild and is
not a regression. In-game, `escape` opens the PAUSE book and `backspace`
(Circle) closes it.

**OPTIONS and the PS button are TOGGLES.** A retry loop that presses on every
poll closes the menu and reopens it forever. Press ONCE, then poll for the
result. `ic.press('ps_button')` works where a raw `pyautogui.press('escape')`
did not.

### Rebuilding chiaki-ng (recipe verified 2026-09-03, ~15 minutes)

Everything needed is already installed via brew: `chiaki-ng-qt` 6.7.3 — **not**
`qt@6`, a different formula that is not present — plus `ffmpeg@7`, `libplacebo`,
`protobuf@29`, `openssl@3`, `opus`, `speexdsp`, `json-c`, `miniupnpc`,
`libevent`, `nasm`. Only `hidapi` is missing and the repo builds its own.

    git clone --recursive https://github.com/streetpea/chiaki-ng.git chiaki-ng-src
    export PATH="/opt/homebrew/opt/protobuf@29/bin:$PATH"
    cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DCHIAKI_ENABLE_CLI=OFF -DCHIAKI_ENABLE_STEAMDECK_NATIVE=OFF \
      -DCMAKE_PREFIX_PATH="/opt/homebrew/opt/openssl@3;/opt/homebrew/opt/chiaki-ng-qt;/opt/homebrew/opt/protobuf@29;/opt/homebrew/opt/ffmpeg@7;/opt/homebrew/opt/libplacebo"
    cmake --build build --config Release --target chiaki

Flags come from the project's own `.github/workflows/build-macos-arm.yml`, which
is the authority if this drifts.

**THE PATCH IS FIVE EDITS ACROSS THREE FILES, plus two new files.** Two of them
fail SILENTLY:

1. `gui/src/streamsession.cpp` — `#include "injectinput.h"`
2. `gui/src/streamsession.cpp` — the 8ms `inject_pump_timer` in the constructor
3. `gui/src/streamsession.cpp` — `InjectInputApply(&state)` in
   `SendFeedbackState()` (NOT its twin `DpadSendFeedbackState`)
4. **`gui/CMakeLists.txt` — add `src/injectinput.cpp` to `SOURCE_FILES`.**
   Sources are LISTED, not globbed; without this the file is never compiled.
5. **`gui/src/main.cpp` — call `InjectInputStart()`.** Without it the FIFO
   listener never starts, every symbol still links, the build looks fine, and no
   input ever reaches the console.

Source of truth is `git diff` in `chiaki-ng-src/`. No line count is quoted
here on purpose — the one that was ("31 insertions") was already wrong, and a
number that must be hand-synced is a constant pretending to be evidence. `chiaki-patch/` holds all five edits (OPEN-2, closed
2026-09-04); `cd chiaki-ng-src && git diff` remains the authority.

**NOTHING THAT MATTERS GOES IN `/tmp`.** `/tmp/chiaki-ng` was found as 825 empty
directories with every file gone. Screenshots for analysis are fine there;
source and findings are not.

---

## §2 The environment and the entry points

Everything runs on **`./.venv`** (Python 3.14) from `requirements.txt`, which was
derived from the ACTUAL imports across every module and test.

    .venv/bin/python -B tools/doctor.py
    PATH="$PWD/.venv/bin:$PATH" ./run_tests.sh

**`paddle_venv/` is NOT the project environment — but it IS a live dependency.
DO NOT DELETE IT.** Both halves matter and the file used to state only the first:

- Never SELECT it as the interpreter. It is Python 3.11 with no `pytesseract`,
  no `mss`, no `Quartz`, so every module fails at import.
- It IS used, by subprocess, and it is 777M for a reason: it holds `paddleocr`,
  `paddlepaddle` and `paddlex`, which have no Python 3.14 wheel. That is why it
  is a second venv rather than part of `.venv`.
  `hand_digit_reader.py` shells out to `paddle_venv/bin/python`,
  `orchestrator.py` calls `check_paddle_venv()` whenever
  `compare_local_reads=True`, and **five production runners pass exactly that**
  (`run_cycles.py`, `run_tonight.py`, `run_testing.py`, `run_one_match.py`,
  `play_now.py`). `preflight.py` checks it unconditionally.

This file said "777M and nothing uses it" until 2026-09-04, and a deletion was
nearly carried out on that basis. **The claims this file gets wrong are the ones
about what is unused or safe to remove** — nothing exercises them until someone
acts on them, so they rot silently while the rest stays accurate. Verify before
deleting anything on the strength of a sentence here.

`.vscode/launch.json` pins `.venv` on both remaining debug profiles (Doctor, Tests).

**`tesserocr` IS a requirement** (`requirements.txt:45`) — pip installs a
prebuilt wheel, no compiler needed. Only `pygame` is deliberately excluded
(imported inside a function in `record_input.py`).

### The hand-walk entry points are gone (2026-09-07, at the user's request)

`Bretts_walk.py`, `brett_walk.py`, `perform_brett_walk.py` and `last_mile.py`
were deleted with their two tests and thirteen launch profiles. Two subcommands
survive as scripts because they guard the rig and a money path:

    .venv/bin/python -B tools/doctor.py             chiaki, FIFO, streaming, frozen,
                                                    current frame, runaways — MOVES NOTHING
    .venv/bin/python -B tools/calibrate_window.py   arm the window-drift guard ONCE, on a
                                                    ban screen that is reading correctly

`connect` was `ensure_stream.ensure_live()`; `reset` is
`reset_env.reset_environment()`; routing is `graph_walk.go_to_node_verified` /
`follow_verified`. Anything that holds a stick is chunked or timed under chiaki's
`INJECT_TIMEOUT_MS` (5s), because the injector releases it after that (§5).

### Two progress files

`progress.json` is the default; recent training uses `progress_testing.json`.
Passing the wrong one mixes two records and corrupts both. `run_cycles.py` and
any live run should pass `progress_file="progress_testing.json"` explicitly.

`match_in_progress` is the guard against double-debiting $50. It is often NOT
stale — check the screen before clearing it.

### Testing

- `./run_tests.sh` runs everything offline and sets `BASEBALL_TEST_RUN=1`, which
  is what holds every input path OFF. Anything that spawns test files itself
  must pass it down. **Do not quote a pass count here** — it goes stale and the
  script prints the real one.
- Fixtures live at the PROJECT ROOT in `test_fixtures/`, never under `tests/`.
- **A test must never glob a directory a live run writes to.** `test_map_admit`
  fed `overnight/failframes/*.jpg` to `admit()` as its failure population; the
  2026-09-06 streak runs appended 165 leg-end frames there and G5's pinned
  profile went 15 -> 9 with no code change. Name the fixture files.
- **A test that passes when the code is broken is worse than no test.** After
  writing one, break the thing it guards and confirm it fails.
- Do not swap in convenient fixtures to make a test green.
- `world_log.py` records a mapping walk; `map_build.py` turns it into legs
  offline. Mapping frames stay out of `screenshot_log/` — all three archives
  there are match-playing runs.
- **Mutation testing while the console is live runs on Snoopy, never here** —
  the workflow and its four Windows footguns are in `Snoopy_testing.md`.
  **If Snoopy is unavailable, mutation testing WAITS until the live run has
  finished.** It never falls back to this Mac while the console is live: the
  write-and-rescan I/O spike degrades `sleep()`, walks the character into a
  wall, and the log scores that as a routing failure (§10.13). No exception for
  "just one mutant" — that is exactly what §10a's eleven-minute mutant was.

  **THE EXCEPTION IS WHEN THE MECHANISM DOES NOT APPLY, AND IT IS THE MECHANISM
  THAT DECIDES — NOT THE WORDING.** The harm above is specific: degraded
  `sleep()` while `slow_traverse` HOLDS THE STICK and sleeps out each push, so
  the leg walks short. If nothing is holding a stick, nothing can walk short.
  The user's call, 2026-09-11, with the console live but the match PAUSED on a
  turn screen: *"IO spike is a big problem yes but we're just idling on a turn
  screen so it doesn't matter."* That was correct, and the sweep ran here with
  no ill effect.

  So: **"the console is live" is not the test. "Is anything timing-sensitive in
  flight" is.** Walking a leg, a stick hold, an A/B trial, a settle being
  measured — wait. Parked on a turn, ban or result screen with no run in
  flight — go, and say which it is.

  The distinction generalises, and it is worth more than this one rule: a
  deliberate override with the mechanism checked is engineering; an unnoticed
  violation is a bug wearing a principle's clothes. Every rule here names its
  mechanism for exactly this reason. Quote the mechanism when you override one.
- `tests/harness/test_no_undefined_names.py` scans every non-vendored module for
  names nothing binds, with a positive control so it cannot pass by finding
  nothing. It earned its keep the day it landed: deleting `_something_moved` as
  a block also took six constants the escape ladder reads, which would have
  raised `NameError` on the first blockage. (OPEN-10, closed 2026-09-04.)
- `tests/cpp/test_injectinput_cpp.py` compiles and runs the C++ injector checks
  and is discovered by `run_tests.sh`'s own `find`, so it needs no special case.
  **It never skips**: absent `clang++`, absent `chiaki-ng-src/`, a compile error,
  an empty run or an unsampleable timing check are each a FAIL naming the fix.
  It compares all five patched files BYTE FOR BYTE against the sources the app
  builds and asserts the list COVERS `chiaki-patch/` — a replaced row once kept
  the count at five and compared `main.cpp` against nothing. Every timing
  assertion is bounded by a clock the process measures, so load can only make a
  check INCONCLUSIVE, never a false pass; one writer `FILE*` is held for the whole
  run because per-line open/close lost lines into the injector's
  fopen/fgets/fclose gap (3 bad runs in 20). `chiaki-ng-src/` is gitignored, so a
  fresh clone has one failing test until that tree is present — deliberate, an
  unverifiable claim is not a passing one. (OPEN-11, closed 2026-09-05.)

---

## §3 Reading the screen

### THE PAID VISION MODEL IS OFF, AND EVERY FIELD HAS A LOCAL READER

**The user, 2026-09-12: "stop using the paid model. you are no longer allowed to use
it unless I say so."** `orchestrator.PAID_MODEL_ENABLED = False`, enforced at the ONE
choke point every `client.messages.create` passes through, so a call site added later
is covered the day it is written. It RAISES `PaidModelDisabled` rather than returning
None — all four callers branch on the answer, and a paid read that silently answers
nothing is 10.1's no-op-indistinguishable-from-success. Re-enabling is deliberate:
that flag, or `BASEBALL_ALLOW_PAID=1` for one process, and only if the user says so.

Nothing is lost by it. The local ladder covers every field:

    the hand (power, kind, tactics type/bonus)   local_hand.read_hand
    which card the cursor is on / is selected    local_hand.cursor_slot / selected_cards
    batting or pitching                          local_state.read_phase
    runners: occupancy, power, and SPEED         local_state.read_runners
    the result screen (WINNER/LOSER/DRAW)        local_state.read_result
    the score                                    orchestrator.ocr_scoreboard

**And the paid model was wrong about cards in seven documented ways** — see §10.24 for
six of them; the seventh is tactics bonuses, where it recorded eleven "+3" values that
do not exist in the game and one "+11".

### THE 100 IS HEALTH. IT IS NOT MONEY.

The user has corrected this **three times**. The big round coin in the
**bottom-left of the world HUD**, with a smiling embossed face and a ribbon, is
**HEALTH**. It looks exactly like a coin. It is not one.

**Money is readable ONLY on the PAUSE MENU**, as the topmost of three stacked
counters along the right edge. So a money read is valid only if the pause menu
is confirmed open first. `read_balance_from_pause_menu()` checks
`pause_menu.is_pause_screen()` before spending the vision call and requires all
three counters — because `toggle_pause` is a TOGGLE that does not always land,
and when it did not, the capture was the WORLD, the only number on it was the
health coin, and the run reported the bankroll collapsing from $246 to $100.

Misreading that coin has produced two confident wrong findings. Use
`orchestrator.read_balance_from_pause_menu()`, never a gameplay frame.

### THE BAN GRID IS A UNIFORM 2D ARRAY, AND ITS ROWS MOVE

`BAN_CARD_ROW_TOP_FRAC` pins the two visible rows at fixed fractions. **They are not
fixed.** At the top of the grid the card tops sit at 0.280 / 0.607; four scroll presses
later the same rows are at 0.229 / 0.557. No constant frames both, and the shipped one only
ever "worked" by being loose enough to contain the card wherever it drifted -- which is why
it wins a name-OCR yield contest (1242 names against 1180 for a tight box, at BOTH capture
geometries) while being visibly wrong on screen.

Everything ELSE is fixed, measured:

    columns    starts 0.145 0.280 0.415 0.550 0.685    pitch 0.135, all four gaps identical
               card width 0.130
    rows       pitch 0.328     card height 0.2995 (= CARD_ASPECT 1.296 x column width x w/h)
    the name banner sits at 0.79-0.93 of card height -- the ONLY dominant horizontal edges
    on a card, 0.98 and 1.00 normalised against everything else under 0.25

So the grid has exactly ONE unknown: the vertical PHASE. `ban_grid.find_card_rows` solves it
by pooling the name banner's two edges across EVERY row at once, which lets a row of locked
cards be placed by its neighbours' evidence. Phase error against a hand-read ruler: +0.001
to +0.003, on 17 of 17 archived frames.

**THREE THINGS THAT DO NOT WORK, so they are not retried.** Scoring the card's OUTER top and
bottom edges: those are thin light lines, and the solver slides until its lower sample finds
the BANNER instead -- a systematic 0.187 card-heights. Autocorrelating a column to measure
the pitch: it confirms 0.3280 exactly on a clean frame and is wrong one frame in five on
faded ones. And horizontal periodicity for the row phase: a card's SIDE borders run its full
height, so a band's vertical position barely changes the score -- horizontal structure pins
the COLUMNS and says almost nothing about rows.

**LOCKED IS NOT UNKNOWN.** A locked card is drawn faded: contrast (sd of grey) is **16-19**
against an owned card's **62-66**, a 3.5x gap with nothing between. That is both a clean
locked/owned detector (`ban_grid.is_locked`, 10 of 10 on a held-out player row) and the
reason a locked row cannot be detected on its own. Reporting "unknown" for a locked card
hides that nothing is wrong.

**THE HAND'S DIGIT BANK DOES NOT READ BAN CARDS.** Argmax correct on only 3 of 7, everything
scoring under 0.5 wrong; lowering the gate manufactures wrong digits. Auditing the roster's
NUMBERS offline needs a ban-specific bank, and its labels must be independent of the roster
or the audit is circular. The card TYPE does read, at **PSM 11** (sparse text) -- PSM 7 and 6
score 3 of 7 on the same crop and PSM 11 scores 6 of 7, which three rounds of moving the box
could not find.

**`read_phase` IS NOT A TURN-SCREEN GATE.** Neither is the hand reader, exactly -- but both
abstain on ban screens (0 of 368 labelled ban frames, against 112 and 116 of 255 non-ban).
An earlier claim here that read_phase leaked on ban screens was an artefact of scoring an
UNLABELLED population.

### The other reading traps

**Hand cards do not display a name.** Vision returns the type banner —
"Batter"/"Pitcher" — because that is the only text on the card. Matching a
played card against a reveal BY NAME can never work; match on POWER.

**There is another mouse NPC OUTSIDE the bar, visible through the windows.** She
is not the dealer. She appears in frames taken at and near the table, so she is
a hazard for the dealer template and for anyone eyeballing a screenshot.

**"Am I streaming?" is not "can I read the compass".** `compass.read_bearing()`
has to identify a LETTER and fails on bright scenes — ~6% of world frames,
reliably inside the bar. `compass.find_bar()` locates the strip without reading
it, which is why `ensure_stream.streaming()` uses it.

**BUT `find_bar` IS NOT A STREAM CHECK, and this file used to say it was.** The
line here read "and is None only when genuinely disconnected". That was never
measured and it is false: `find_bar` fires on 9 of 13 of chiaki's own Qt
screenshots, on 5 of 6 arbitrary photographs, and on a synthetic dark window
with one light toolbar. Only a flat image returns None. Ask it "is there a
horizontal light band here", nothing more. `streaming()` now pairs it with
`ensure_stream.looks_like_ui()` — see OPEN-18, CLOSED.

**"Am I in the world?" cannot be answered by the compass readers either.**
Measured: `find_bar()` returns non-None on EVERY frame including ban and
gameplay screens, and `read_bearing()` returned 177.4 on a gameplay turn. Use
`table_prompt.at_table()` when the question is "is the dealer prompt up".

**THERE ARE TWO PS5 OVERLAY SCREENS AND THEY TAKE DIFFERENT BUTTONS.** This entry read
"the PS5 dashboard overlay says `▢ Resume Game` — that is SQUARE, not Cross. Cross navigates
*into* the game card instead", and acting on it on 2026-09-10 got nowhere: Square did
nothing at all, three times. The user, who could see the screen, said press X.

    CONTROL CENTER (the icon bar along the bottom, game still visible behind)
        X on the game tile  ->  opens that game's CARD
    THE GAME CARD (a panel with "Total progress 65%" and a highlighted button)
        the button IS "Resume Game", already focused, and X takes it

So it is X, then X. The old note is not wrong about Square existing somewhere in the PS5 UI;
it is wrong as an instruction, because it names one screen and the recovery needs two.

**BUT X IS THE RIGHT BUTTON ONLY ONCE THE CURSOR IS ON THE GAME TILE, AND THE CHEAP EXIT IS
THE PS BUTTON.** Read as a recipe for "the overlay is up, get back to the game", the two
lines above are a trap: X is SUBMIT, so it takes whatever the cursor happens to be sitting
on, and from a fresh Control Center that is not necessarily the game tile -- it can drop you
to the PS5 HOME SCREEN, out of the match. The user, watching the screen on 2026-09-10:
*"if you pressed X, it would take you to the PS5 home screen. you don't want to do that.
press the PS5 symbol again to remove the Playstation overlay."*

    overlay is up, you just want it GONE     ->  ic.press('ps_button')   (it is a TOGGLE, section 1)
    you have NAVIGATED to the game card and
    "Resume Game" is highlighted             ->  X

Verified 2026-09-10: one `ps_button` press returned a paused match to `screen: 'turn'` with
all five hand rows reading and the cursor located, in 2.5 s. Prefer it. X-then-X describes
the path THROUGH the game card, not the way out of the overlay.

**AND THE REASON THIS TOOK FOUR ATTEMPTS IS A MEASUREMENT MISTAKE WORTH THE SPACE.** Between
presses I scored `_mean_abs_delta` over the whole frame, got 0.1-0.2, and concluded "nothing
is reaching the console — this is not a button problem". Input was landing the whole time.
Two different PS5 overlay screens are ~99% identical pixels (same dimmed game behind, same
dark panel), so a whole-frame mean cannot see the navigation that actually happened, and I
had also left the `before` frame stale across several presses. ONE SCREENSHOT settled it
instantly and showed "Resume Game" sitting highlighted. §10.15 in a new place: on a screen
that is mostly unchanged by design, a frame-difference number is not evidence of anything —
look at the frame.

**The pause book is bright AND has DARK MENU TEXT. A bright wall is not.**
`is_pause_screen()` once tested only "is this mostly paper-bright", and a
gameplay frame facing a blown-out white wall passed:

    gameplay bright wall   page 0.927   menu text 0.0055
    real pause menu        page 0.944   menu text 0.1054

`page_fraction` CANNOT separate them. `menu_text_fraction()` measures ink in the
title band (`MENU_TEXT_BAND = (0.14, 0.30)`) against
`MENU_TEXT_MIN_FRAC = 0.03` (`pause_menu.py:188-201`).

**`pause_menu.selected_item` measures a WHITE FRACTION per row**, so the score
rises with how much TEXT a row contains. On a real frame where "Load Last Save"
was visibly highlighted it returned "Quit to Main Menu" — and the caller commits
a `cross` on whatever it names, so an unattended run would have quit the game.
Fixed by `WHITE_LEVEL` 200 -> **225** (unselected text peaks at 210, selected is
255) plus `SELECTED_MARGIN = 2.0`; `SELECTED_MIN_FRAC = 0.02`
(`pause_menu.py:121`, `:235`, `:130`). Verified: it now returns "Load Last Save" on the
frame that failed.

### EVERY OFFSET IS IN ANCHOR UNITS AND IS SCALED. NEVER A RAW PIXEL.

**This one keeps happening, and the user called it out on 2026-09-10:** *"don't use
exact pixels because that will screw you over the moment it's on a different screen."*

**Capture geometry changes under you.** One session produced both 1867x1050 and
1920x1080 captures, and row calibration is not robust to that — at 1920x1080
every row scored ~0.55 because the bands landed on the page instead of the text.
Anything reading fixed regions must be checked against BOTH geometries.

The project already has the mechanism and the readers that predate this use it:
`s = img.width / ANCHOR_W`, and `SLOT_PLAYER` / `SLOT_TACTICS` are multiplied by it at
every call. **A new window written in raw pixels works perfectly on the machine it was
tuned on and silently lands on the wrong thing everywhere else** — there is no error, the
number just becomes meaningless, which is section 10.1's whole family.

It happened AGAIN the same day, in the cursor-glow reader: `GLOW_XL/XR/DY0/DY1` and
`SELECT_LIFT_MIN_PX` were all written as raw pixels, tuned at one capture size, and every
measurement in this file quoting them (the 9.1-16.1 true band, the 0.5 false ceiling, the
44 px lift) is at THAT scale. They now multiply by `s` like everything else.

**How to tell the two kinds of constant apart, because only one needs scaling:**

    an OFFSET or a DISTANCE in pixels   ->  SCALE IT      GLOW_XL, SLOT_TOL, a box height
    a FRACTION, PERCENTAGE or RATIO     ->  leave it      CURSOR_GLOW_MIN (a % of pixels)
    a GREY LEVEL or a CORRELATION       ->  leave it      GLOW_WHITE 190, RESULT_MIN 0.80

**And the guard is a test, not a promise.** `tests/minigame/test_verified_selection.py`
re-reads fixtures at 0.9x, 1.1x and 1.25x and requires the same answer, with a floor on
how many resized frames it actually exercised so it cannot pass by skipping them all.
Pin any new window the same way — resizing a fixture costs nothing and is the only thing
that actually catches this.

**OPEN, and found BY that test: the hand reader itself is not scale-free, one layer below
the windows above.** Writing the check immediately failed in two places that predate it:

    at 0.73x   read_hand returns ONE row -- the discs fall under find_circles' size gates
    at 1.25x   find_tactics misses the wreath: its blob is checked against 28-48 x 30-50
               RAW pixels, so scaling the capture moves the card out of the gate

So every measurement in this file is at ONE capture geometry, and a different rig would
degrade silently rather than error. Not fixed: it is a change to the core reader's size
gates and wants the 540-hand corpus check plus mutants behind it. The scale test is
deliberately scoped to the cases where the reader still produces a full fan, and says so,
rather than claiming a scale-invariance the system does not have.

**Open the logged frame before theorising about a failure.** Nearly every wrong
diagnosis here came from reasoning about what the game "must" have been doing
instead of looking at the screenshot already on disk. And **check WHICH frame** —
`go.main(n=1)` writes to `attempt01` under its `shot_root`, so two runs sharing a
root overwrite each other.

### OCR goes through one persistent handle, and never off the main thread

`ocr_glyphs.image_to_text(image, psm, whitelist)` is the ONE word-mode OCR path.
orchestrator's four local sites route through `orchestrator._ocr_text`
(`ocr_ban_card_name`, `ocr_scoreboard`, `ocr_runner_card` at PSM 6;
`read_ban_counter` at PSM 7 with `0123456789/`), and `ocr_glyphs.tesseract_config`
is the single definition of the config string, so the fast path and the
pytesseract fallback cannot ask different questions. **The handle cache is keyed
on `(psm, whitelist)`**, bounded LRU: keyed on the whitelist alone, a word-mode
call was handed a SINGLE_CHAR handle and returned one character of a player's
name, correctly, forever. The evidence was function-level, not string-level:
137 answers from live in-memory crops, migrated tree against a HEAD worktree,
**zero differences**; the 110-cell ban corpus gives 63 correct / 0 wrong / 47
abstained in both arms, in 4.8s against 229.8s.

**Do not reintroduce a thread pool for OCR.** `tesserocr` links `cysignals`,
whose `sig_on`/`sig_off` is process-global and main-thread-only, and its SIGINT
handler cannot be installed off the main thread — a worker-first call silently
drops the WHOLE PROCESS back to spawning subprocesses. Serial and in-process
beats eight threads by ~48x here. Still shelling out, deliberately and recorded
so they are not lost: `reset_env`'s `give_up_dialog` (on the LIVE path, the best
remaining candidate) and two sites in `landmarks.py`. Two test seams that
stubbed `pytesseract.image_to_string` passed every MUST_ABSTAIN case for the
wrong reason after the migration — the code OCR'd a blank probe and abstained;
both now stub `orchestrator._ocr_text`. (OPEN-12, closed 2026-09-05.)

### `streaming()` rejects chiaki's own window

`find_bar` fires on chiaki's host list (`test_fixtures/not_streaming/hostlist_standby.png`,
the rig's own 1867x1050, `State: standby`), so `streaming()` once answered True
in 0.0s on a console that was asleep, and `connect` never ran its wake sequence.
It now pairs `find_bar` with `ensure_stream.looks_like_ui()`: Qt draws flat
fills and full-width exact runs; H.264 never does, because quantisation dithers
even a dark room. Over 848 real streaming frames against the host list and 70
non-game images `find_bar` fires on:

                              streaming p50    p99     MAX  |  host list
        flatness                  0.0357  0.1131  0.2949  |  0.6678
        widest exact row run      0.1208  0.3917  0.6208  |  1.0000

`UI_FLAT_FRAC = 0.25` and `UI_ROW_RUN_FRAC = 0.50` sit between the populations,
clear by 2.7x and 2.0x; held out properly, **0 false positives on 71
non-streaming frames and 1.2% false negatives** — and a false negative is cheap,
because rejecting the `find_bar` branch falls through to `_heartbeat_seen()`,
the console's own word, ~0.4s. The standby host list has no session and comes
back False after the full 25s, paid only on the path that was about to give up.
Pinned by `tests/rig/test_streaming_rejects_chiaki_ui.py`, which carries the
control and a ceiling on rejected real frames; three mutants each caught by a
different check. Honest limit: the negative side is ONE distinct frame; chiaki's
settings dialogs and its non-standby host list are unsampled — if `streaming()`
ever reports UP on one, add it to `test_fixtures/not_streaming/` and re-score.
(OPEN-18, closed 2026-09-06.)

---

## §4 What things cost, and the game's own rules

- A match costs **$50** in-game. BOX/Square at the table starts one.
- "Load Last Save" restores the wallet to **$246** (4 matches).
- `api_budget` is a HARD ceiling for the whole process, set via
  `BASEBALL_API_BUDGET`. Every retry on a bad read is a paid call.
- A **stable misread cannot be fixed by retrying** — same frame, same prompt,
  same wrong answer. Repair or clamp it instead of looping.

### THE SHAPE OF A MATCH (from the user, 2026-09-12 — the model had this wrong)

    new hand  ->  play as the BATTER   ->  inning 1 ends
    new hand  ->  play as the PITCHER  ->  inning 2 ends  ->  match over

**The two innings ARE the two halves.** You bat in inning ONE and pitch in inning
TWO; you never bat twice. Each half deals a FRESH hand of 5, and within a half the
hand persists and is topped up ONE card per play — `wait_for_hand_deal` blocks
"until the replacement card has visibly landed", singular, and a discard keeps the
rest of the hand. **5 rounds PER HALF**, so five at-bats batting and five pitching.

**The scoreboard is `[inning1, inning2, TOTAL]` — the third box is the total, NOT a
third inning. Never sum it; take `[-1]`.** `ocr_scoreboard` has documented this all
along and the live consumer takes `[-1]` correctly. A live board reading
`your [2, 0, 2]` against `opponent [0, 0, 0]` is the whole structure in one glance:
we scored 2 batting in inning 1, we do not bat in inning 2, and the opponent has yet
to score in the inning they are batting now.

`simulate.py` got this wrong twice in one day and both mistakes are worth knowing:
it redrew BOTH hands every ROUND (so card economy could not exist — nothing survived
to a later turn), and a "fix" then looped the match over two innings, playing four
halves and doubling every score. The A-bats-then-B-bats shape was right all along.

### WHAT THE CARDS ARE WORTH, MEASURED

Counted over **299 tactics cards labelled BY HAND** in `hand_labels*.json` — human
labels, so this is not one of this project's readers marking its own homework:

    POWER SWING     n= 95    +1 60%   +2 40%     <- the ONLY card ever above +1
    SPEED BOOST     n=132    +1 100%
    PITCH FOCUS     n= 35    +1 100%
    FIELDING PLAY   n= 37    +1 100%
                             zero 3s, zero unlabelled

**A +3 DOES NOT EXIST.** The user said so and was right; the paid vision model's
eleven "bonus 3" rows are misreads, from the same source that once recorded a bonus
of **ELEVEN**. That is the seventh documented way that model was wrong about cards.

**`KNOWN_BAN_ROSTER` CANNOT ANSWER A TACTICS QUESTION** — it is 33 `PlayerCard`s and
no tactics cards at all. Player powers run **4–9**; a power outside that is a misread.

### EVERY CARD IS A BATTER OR A PITCHER, AND `secondary` MEANS A DIFFERENT STAT IN EACH

The user's call, 2026-09-13: *"it might be useful to also read the players type, so you
don't mark a pitcher with speed since that doesn't make sense."* `PlayerCard.secondary` is
SPEED on a batter and FIELDING on a pitcher -- the field's own comment always said so --
and there was no role field, so nothing could tell them apart. `simulate.draw_hand` dealt
all 33 cards in BOTH directions: a pitcher dealt as a batter had its fielding read as
speed, and a batter dealt as a pitcher brought a fielding of 3, which no pitcher has.

**THE TWO RANGES ARE DISJOINT WHERE IT MATTERS**, over 131 HAND-LABELLED cards split by
whether the hand they came from was batting or pitching:

    batters   speed     1 x14   2 x14   3 x38    n=66   NEVER 0
    pitchers  fielding  0 x39   1 x23   2 x3     n=65   NEVER 3

So secondary 0 implies PITCHER and 3 implies BATTER; 1 and 2 are shared and need the card's
banner. 31 of 33 are typed from FOUR signals that never once disagreed: the ban-grid banner
read by OCR, that range rule, the user reading cards off a ban grid, and **a card seen on a
BASE is a batter** (runners belong to the batting side, so occupancy types a card for free).
Brian Coker (8/1) and Zachary Lee (6/2) are still untyped; `simulate.UNTYPED` names them and
keeps them in both pools, because dropping them biases the draw as surely as mistyping them.

Splitting the pools moved the model **1.7223 -> 1.7862 runs/half (+3.7%, 4.6 sigma** at
n=20,000 per arm) -- the size of the error the unsplit pool was carrying.

**A CORRECTION THIS FORCED.** "30.5% of hand-labelled player cards are speed 0" was reported
here and a finding built on it -- that `bases_to_travel` and `simulate` disagree about a
speed-0 batter. Those cards were PITCHERS, pooled with batters precisely because there was
no role. **A batter's speed is never 0**, so that disagreement does not arise. It is still
reachable through fielding subtraction, which is a different open question.

**DO CARD VALUES CHANGE PER GAME? NO.** 1,691 player cards read across 540 hand crops
recorded on many different days: every (power, secondary) pair is already one of the
roster's, and ZERO novel pairs appeared. Six of the 24 possible combinations are absent from
the roster and none was ever drawn.

**CORRECTION 2026-09-13: THERE ARE AT LEAST TWO POWER SWING CARDS, NOT ONE.** Seen live on
the ban grid, side by side in the same row, both reading POWER SWING and carrying DIFFERENT
badges -- one **+1** and one **+2**. That is consistent with the bonus census two paragraphs
up (POWER SWING is the only card ever above +1: +1 60%, +2 40%) and it means the count below
is a floor, not a roster. It was taken by eye off one scroll position. The rest of the line
still stands as far as it goes.

**THE COLLECTION ALSO HOLDS TACTICS CARDS**, at the bottom of the ban grid: 1 Power Swing,
3 Speed Boost, 3 Pitch Focus, 3 Fielding Play. Every OWNED one shows a badge of **1** --
an independent confirmation of the +1 bonus census, from a different source entirely.

**So the maximum effective batter power is 9 + 2 = 11**, and that decides a pitching
choice the engine cannot see: a pitcher playing a **9 CANNOT concede a home run**
(margin 2), while one playing an **8 can** (margin 3).

Game rules:

- A hit needs the batter's power to beat the pitcher's; beating it by **3+** is
  an automatic home run. Margin does not otherwise matter. **The rule is ABSOLUTE**
  — confirmed by the user against the live scoreboard, 2026-09-12. Any record that
  shows a 3+ margin without a run is a bad LABEL, not a counterexample: 26 such rows
  in `match_log.jsonl` all came from the old "the score went up" classifier, which is
  why the outcome is now taken from the REVEAL's margin instead
  (`orchestrator.classify_outcome`).
- Only SWING_BOOST and PITCH_BOOST add power. Speed and fielding boosts have a
  nonzero bonus that adds NO power — analysis needs the tactics KIND.
- **Runners can be lapped**: this game lets base runners pass each other, so
  real-baseball intuitions about ordering are unsafe.
- **THE SCORE DOES NOT CHANGE WHICH CARD TO PLAY, and that is correct.** Neither
  `best_batting_play` nor `best_pitching_play` reads `your_score`/`opp_score`, and the
  match's shape is why: you bat once and then defend a fixed total, so you can never
  want fewer runs while batting and can only want outs while pitching. Max power both
  ways. The ONE place the score matters is RISK TOLERANCE when defending a lead —
  conceding a solo home run at +2 still leaves you ahead — which is a variance question,
  not a card-choice one. `target_score` is the one live score field, and only while
  pitching.

### The baserunning rules (from the user, 2026-09-10, with two sources)

Supplied by the user against a community guide and a Reddit write-up, and each
one CHANGES A DECISION the engine currently makes blind. Confirmed live where
noted; the rest is the user's reading, not this project's measurement.

- **SPEED (the `secondary` stat on a batter) is how many bases that player runs.**
  The badge it is read from made it look like a "shield" and this file called it
  that; it is speed. On a pitcher the same field is FIELDING. `decision_engine`
  already says so in one comment (`secondary: speed (batter) or fielding
  (pitcher)`) and nothing downstream used it.
  *Observed live:* a speed-1 batter advanced exactly 1 base, and a speed-1 runner
  advanced exactly 1 base on the next hit. Speed >= 2 is UNTESTED.
  **A SPEED BOOST APPLIES TO THE BATTER WHO PLAYED IT, FOR THAT HIT ONLY, AND IS THEN
  DISCARDED** — the runner reverts to baseline speed for any later advance (user's
  sources, 2026-09-12). That is why `simulate.speed_bonus` is added at the batter's own
  step and nowhere else: a runner is stored as its CARD and `advance_runners` re-derives
  speed from `card.secondary`, so reverting is free. It was worth ZERO until then
  (`batter_speed` was computed and never read).

  **RE-MEASURED 2026-09-13 ON THE ROLE-SPLIT POOLS, and the speed figure was wrong by 4x.**
  The numbers below it replaced (+0.034 speed, +0.726 swing, "21x less") were taken on the
  SCRAMBLED pool, before cards had roles: pitchers were dealt as batters with their FIELDING
  read as SPEED, so a third of "batters" had speed 0 and a speed boost on them bought
  almost nothing. A speed measurement taken where a third of the batters are pitchers is
  not a speed measurement. Same harness, same seeds, correct pools, n=20,000 halves an arm:

      no tactics     0.9589 runs/half
      SWING boost    1.5727   delta +0.614  (+52.8 sigma)
      SPEED boost    1.0901   delta +0.131  (+12.4 sigma)

  **THE CONCLUSION SURVIVES AND THE MARGIN DOES NOT.** Swing still wins decisively, so the
  engine's preference for it is unchanged and 99/1 still describes a tie-break rather than a
  trade. But the ratio is **4.7x, not 21x**, and any argument that leaned on "21x" as
  evidence that speed is negligible was leaning on an artefact.

  It is worth **+0.131 runs/half**, still less than a SWING boost's **+0.614**, which is
  power over speed.
  **AND THE OPEN QUESTION IS PRICED (2026-09-13).** Two runners have been read at +1 over
  their card -- Rube Sharp 1->2, Noah Kelly 2->3, both batters, both exactly a speed
  boost's +1 -- which would mean the boost PERSISTS on base, against the source above.
  Modelled by putting the boosted batter on base as a card whose secondary already includes
  the boost (same harness, same seeds, role-split pools, n=20,000 an arm):

      boost REVERTS (shipped)   1.0901 runs/half
      boost PERSISTS            1.1361   delta +0.046  (+4.2 sigma)

  So it is REAL AND LOW-STAKES. It moves a speed boost's worth by about a third, and even
  if it persists the total (0.177) is nowhere near a swing boost's 0.614 -- **it cannot flip
  the engine's preference.** Worth one live at-bat to settle; not worth planning around.

  **A RUNNER'S CURRENT SPEED IS READABLE OFF THEIR BASE**, from the shield badge:
  `local_state.read_runners()["speeds"]`. 171 of 172 occupied bases read it, zero of
  1,106 bare bases read anything. **It is NOT the card's roster `secondary`** — the same
  named card shows different values at different moments, so it is a LIVE number: what
  this runner advances NOW.
- **A TIE IS A COIN FLIP, AND WINNING ONE IS CAPPED AT FIRST BASE** regardless of
  the batter's speed. So landing exactly on the pitcher's power is the worst
  place to be: half the time nothing, half the time a minimum-value hit.
  *This invalidated a conclusion drawn here the same hour* — a speed-2 batter that
  stopped at first was read as "the batter always goes to first", when it was a
  5-v-5 tie. Two data points, one of them a special case, and a rule was written
  from them.
- **A LOSING AT-BAT CAN STILL ADVANCE RUNNERS.** An out is not "nothing happens".
  This is the missing explanation for the animation spread: outs have a median
  reveal of 4.2 s and a MAXIMUM of 14.9 s (n=160), which had been read as noise.
- **BLACK PITCHER BUFFS SUBTRACT RUNNER MOVEMENT** — that is what FIELDING does,
  and it is why it only matters with runners on base.
  **This settles `decision_engine.FIELDING_POWER_BUDGET`, whose own comment says
  "the fielding effect is UNCONFIRMED ... Set to 0 for pure power-first once the
  question is settled" (it measured p=0.192 on 19 rows).** The question is now
  settled the OTHER way: do NOT zero it. The existing rule already pays the
  premium only when runners are on, which is exactly when the effect exists.

**WHAT THE ENGINE STILL CANNOT SEE.** `best_batting_play` sorts on POWER alone and
attaches a speed boost only as a fallback, and only when runners are already on
base. It therefore cannot value a fast batter who wins outright, and has no notion
of tie risk at all. Neither can `simulate.py` settle it: a hit there is
`runners.append(batter_card)` with speed never consulted, and its own docstring
flags speed effects as "not confirmed rules — modeled as the simplest reasonable
guess". **So the 79% win rate that justifies "always attach a swing boost" was
measured in a model where a speed boost does nothing by construction.** It shows
swing-boost beats NOTHING; it has never compared swing against speed.
- A match is 5 rounds PER HALF (see the match shape above) and allows 2 discards.
- **You cannot pause an active match.** Mid-match OPTIONS opens a "Give up?"
  dialog (NO = circle, YES = cross), never the pause menu — so Load Last Save
  and the money readout are unreachable until the match ends.
  `reset_env.give_up_dialog()` detects it; answering YES costs nothing because
  the reload discards the match.
- The ban screen shows **"PLAY" against TRIANGLE**, and triangle commits
  whatever is banned and starts the match — it works at 1/3 bans. It is a safe
  way out of a ban screen that will not clear.

---

## §5 Input: which control takes which path

**Buttons go to the KEYBOARD. Sticks go over the FIFO.** They are different
paths and only one of them was ever verified.

`input_controller.press()` used to try `_inject_press()` first, sending
`buttons <bitmask>` over the FIFO. **Those bits do nothing on this console.**
Measured: `buttons 4096` (options) produced NOTHING after 4 seconds, while the
keyboard path opened the pause menu in 0.5 seconds.

The bug was not the wrong bits — it was that `_inject_press` **returned True**
because WRITING to the pipe succeeded, so `press()` believed the button had been
pressed and never fell through. That silently disabled EVERY button in the
system: resets, pause menu, menu navigation, card selection, match play.

**`input_controller.INJECT_BUTTONS = False`.** Flipping it back requires
re-verifying against the pause menu, which is a free and harmless target.
Immediately after the fix a full `reset_environment()` ran in **8.7s**; before
it, resets were failing with "never landed on 'Load Last Save'".

**THIS INVALIDATES NAVIGATION NUMBERS TAKEN BEFORE 2026-09-03.** Anything
measured while buttons were dead was measuring a broken reset, not routing.

- Stick injection is HARD OFF under `BASEBALL_TEST_RUN` — it sits ABOVE
  `can_use_background_input()`, so it needs its own lockout or the offline suite
  drives the live console. It did, briefly.

### THE TEST-RUN LOCKOUT ONLY EVER COVERED THE TARGETED PATH (2026-09-13)

`can_use_background_input()` refuses under `BASEBALL_TEST_RUN`, and its docstring
says that "means a test run can never move the character". **It does not.** It
means a test run cannot use the BACKGROUND path — and all three callers then fall
straight through to `pyautogui`, which types into whatever window is FRONTMOST.

    press()        -> pyautogui.keyDown(key)          guarded only above
    hold_combo()   -> pyautogui.keyDown(k) per key    guarded only above
    walk_at()      -> pyautogui.keyDown(k) per slice  NO LOCKOUT OF ANY KIND

Found the way these always get found: a mutation run flipped a guard so the
verified ban navigator ran with a blind cursor, that navigator calls
`input_controller.press` (NOT the orchestrator's stubbed one), and it ends every
ban attempt with two `confirm_play` presses. `confirm_play` is **"c"**. The user
watched "c" appear in their own window, with a paid match parked on the console,
and said so before any log did. **The offline suite could have walked the
character, too** — `walk_at`'s blend loop drives the keyboard with nothing
checking anything.

`input_controller.focus_input_allowed()` now answers the question AT the damage
rather than one layer above it, and all three sites call it. The four tests that
drive that path on purpose set `FOCUS_PRESS_IN_TESTS` and restore it; a test that
forgets sends nothing and FAILS, which is the safe direction to be wrong in —
silence here means the keyboard. **`importlib.reload()` resets the flag**, which
`test_input_timing.py` does twice and which silently refused 22 presses.

The shape is §5's own `_inject_press` returning True because the WRITE succeeded,
and §10.1's whole family: **a guard one layer up from where the damage happens,
answering a narrower question than the one it is credited with.** Two of the
three sites had a guard; the third had none; and the docstring on the guard
claimed all of it.

### THERE ARE THREE PATHS TO THE CONSOLE, AND ensure_stream WAS THE UNGUARDED ONE

Found the same evening by enumerating every emission site rather than waiting for
the next accident:

    input_controller  keyboard   press / hold_combo / walk_at   -> pyautogui
                                 press_background               -> CGEventPostToPid
    analog_replay     sticks     send()                         -> the FIFO
    ensure_stream     recovery   _key()                         -> CGEventPostToPid

`ensure_stream` had NO `BASEBALL_TEST_RUN` lockout at all, and resolved its own pid
with `pgrep -f chiaki-ng-build` taking `out[0]` -- the same loose command-line match
that sent an afternoon of presses into a `/bin/zsh`. "chiaki-ng-build" is narrower
than "chiaki", which is why it survived that round; narrower is not a guard.
REPRODUCED in about a minute, because new pids on this machine are LOWER than
chiaki's so a decoy sorts first:

    $ /bin/sh -c 'sleep 20; : chiaki-ng-build' &
    ensure_stream._pid()          -> 10919   actually chiaki? False
    input_controller.chiaki_pid() -> 83980

`_key()` posts straight to whatever that returns, so the escape ladder's
Return/Down/Escape would have gone to that shell -- and the ladder would then
report that it tried and nothing moved, which is 10.1 on the recovery path.
`_pid()` now delegates to the one resolver that checks what the process IS.

`tests/rig/test_no_real_input_under_test_run.py` pins all three paths
BEHAVIOURALLY, carries a control so the checks cannot pass on a dead path, and
AST-scans for emission sites so a NEW one fails the test instead of reaching
someone's keyboard. Four mutants, all caught -- including a planted
`pyautogui.keyDown` in an unrelated module.

## THE FIRST LIVE MATCH: THE HAND READER IS CALIBRATED AT A WIDTH THE RIG NO LONGER CAPTURES

A $50 match played end to end on 2026-09-13, the first ever -- every earlier one died at
the paid orientation read. It could not play a single card, and the cause is one number.

**The reader is calibrated at a HAND CROP 979 px wide (`local_hand.ANCHOR_W`). The rig
captures 2000x1125, whose hand crop is 1020 px -- 1.042x.** Section 3 has carried "the
hand reader itself is not scale-free" as an open item; this is what it costs. The size
gates are RAW PIXELS (`DISC_MIN_R` 18, `DISC_WHITE_SIZE` 30-50, `circle_finder.DIGIT_W`
6-26) while every SCALED constant already divides by ANCHOR_W.

The SAME frame, resized:

    (2000, 1125)   6 rows, 0 readable player cards      <- the live capture
    (1920, 1080)   5 rows, 4 readable
    (1867, 1050)   5 rows, 4 readable

Over the match's own frames it is 12 of 20, and the failures are TOTAL (0 of 4) rather
than partial -- it reads marginally, not never, which is why nothing looked obviously
broken. All 22 decisions came back `Playing None`, 11 plays were refused for want of a
cursor (glow 10.4-10.9 against `CURSOR_GLOW_MIN` 15), and not one card was played.

**NOTHING ON DISK COULD HAVE CAUGHT IT.** Every archived run is 1920x1080, whose hand crop
is EXACTLY 979 -- the whole corpus sits at the calibration width by construction, so
normalising is a literal no-op there and no census could show the gap. 10.31's shape
again: a population that cannot contain the failing class.

Fixed by normalising the hand crop to ANCHOR_W in `crop_gameplay_regions`, the one place
every consumer takes it from, so `s = img.width / ANCHOR_W` is 1.0 for all of them at
once. Measured over 40 archived turn frames (156 readable cards):

    native 1920x1080     156 as-is   156 normalised     (no-op, as it must be)
    upscaled to 2000x1125 109 as-is  133 normalised     (a LOWER bound: resampled twice)
    the five live frames   12 as-is   20 normalised     (full recovery)

**ONLY the hand.** Every other region has its own anchor (`SCOREBOARD_ANCHOR_W` 359,
`BASE_ANCHOR_W` 221/288/220) and its own reader dividing by it; a mutant that dropped the
`label == "hand"` test SURVIVED the first version of the guard and returned a 979 px
scoreboard crop against its own 374.

**This does not close the open item.** The gates are still raw pixels, and a rig that
captures a third geometry will land outside them again. It puts the reader back on the
geometry it was measured at.

### WHAT THE FIRST MATCH ALSO SHOWED

Working, live, on the paths built the same day: the ban scan hit a real SCROLL DESYNC and
correctly REFUSED TO CACHE its 26 cards; the ban cursor could not be read and the blind
fallback placed 3 of 3 by dead reckoning; zero wrong-card bans; 120 presses delivered 120
background Quartz and 0 focus+pyautogui; the `your_score` default kept the run alive when
`ocr_scoreboard` returned None on a plainly legible board; and the closing input verdict
correctly said NOT MEASURED instead of certifying a detector that never ran.

**And nothing was ever played blind.** Eleven refusals, zero wrong cards.

**`ocr_scoreboard` CANNOT READ A LEGIBLE BOARD.** "JACK PEPPER 3 0 3 / OPPONENT 0 4 4"
plainly on screen, `{'your': None, 'opponent': None}` returned. Unmeasured rate, open.

### THE DEAL-TIMING QUESTION IS ANSWERED, AND THE ANSWER IS "NOT FROM THIS DATA"

27 rows, the first ever collected:

    by outcome   stable 15, timeout 12
    INSTRUMENT   pearson(settled_at, released) = +0.246, 25 of 27 pinned at or under 1.5s
    slope        -0.0065 s per base-movement, permutation p = 0.9872 -- NOT significant

Two independent reasons, both now MEASURED rather than assumed. The instrument measures
the pre-deal fan, not the deal (predicted 0.226 from the archive, reproduced 0.246 live).
And the predictor barely varied: 19 of 21 usable rows sat at the same 2.0 base-movements
because there were almost no runners on. **A dataset needs matches WITH RUNNERS to answer
this, and a probe that starts at the deal's onset rather than the gate's first poll.**

### THE RUNNER COULD NOT PLAY A MATCH AT ALL WITH THE PAID MODEL OFF (2026-09-13)

`read_state_for_turn` made the ORIENTATION read PAID, unconditionally, and set
`_paid_state_done = True` only AFTER the call -- so with the model off (the shipped
default since 2026-09-12) it raised `PaidModelDisabled` on EVERY turn, `run()` counted
15 stuck attempts and stopped with `unreadable_screens`. The loop this project exists
to run could not play a single match. **No test caught it because every run harness
stubs `read_state_for_turn`.** The paid branch now also requires `paid_model_allowed()`;
section 3 already lists a local reader for every field it supplied, and a local GAP
still raises with the reader named.

### THE BAN SCREEN IS A NOTEBOOK PAGE TOO, AND THE MONEY GUARD ADMITS IT

`is_pause_screen`'s negative population was a bright WALL, n=1. The ban book is a THIRD
CLASS that was never in it -- 10.31's missing-class shape, the same one the DRAW screen
made. Censused over 10,239 frames:

    PAUSE book   n=  14   0.9263 .. 0.9446
    BAN book     n=1140   0.7101 .. 0.8587     <- 1,122 clear PAGE_MIN_FRAC 0.80
    everything else       0.0000 .. 0.9272 (the bright wall)

`MENU_TEXT_MIN_FRAC` cannot rescue it: ban 0.1224-0.4148 against pause 0.0733-0.4309 is
complete overlap. **No threshold on that quantity separates two notebooks.** Over 1,131
ban frames `read_money` returns a CONFIDENT WRONG balance on 5 ($7 x4, $1 x1) with both
OCR scales agreeing -- the "$246 -> $100" failure its own docstring exists to prevent,
reached THROUGH the guard. Harmless while it had no callers; wiring it into the money
path the same evening is what made it live.

**No constant was invented.** The money path refuses when `read_ban_counter` answers --
an instrument already measured at 0 false positives off ban screens over 3,000 random
frames. Still open: `selected_item()` names a menu entry on 19 of 1,140 ban frames, so
`reset_env` would send `dpad_down` into a live ban screen (never `Load Last Save`, so
no `cross`, in 1,140 frames), and `reset_env` tests `is_pause_screen` BEFORE
`give_up_dialog`, making the give-up recovery unreachable on a false positive.

### THE OFFLINE SUITE WAS DRIVING THE LIVE RIG, AND GUARDING THE LEAF MADE IT WORSE

`tests/minigame/test_budget_reserve_fits.py` imports `run_cycles`, which reaches
`ensure()` -> `streaming()` -> `_heartbeat_seen()` and polls the live chiaki log. The
file HUNG at the suite's 300 s ceiling. **The ceiling was the only thing between an
offline test run and `ensure_live()` -> `./restart_chiaki.sh` -> `pgrep -x chiaki` then
`kill -9`** -- killing the user's stream with a paid match on screen.

**And gating `_key()` alone made it MORE likely, not less.** With the keys suppressed
the clear ladder posts nothing, `is_frozen()` stays true, and the loop falls straight
through to the restart. Guarding the leaf without guarding the entry point pushes the
failure downhill. `ensure`, `ensure_live` and `is_frozen` now refuse under
`BASEBALL_TEST_RUN`, with `RIG_DRIVER_IN_TESTS` as the opt-in for the three tests that
drive the orchestration against stubs.

**AND THE OBVIOUS MUTANT IS ITSELF THE HAZARD.** Deleting that guard and running the
test makes `ensure()` poll the rig for real: it hung 300 s against a live console. A
lockout on hardware is mutation-tested by stubbing everything BEHIND the guard and
asserting only that the body was entered --

    guard REMOVED  -> BODY_ENTERED
    guard RESTORED -> REFUSED

### FOUR MORE STATE BUGS, ALL CONFIRMED THE SAME NIGHT

- **The ban collection cache stored a PARTIAL scan.** Its `>= 3` floor was sized against
  a mid-animation frame that returns `[]`; OPEN-23's real failure returned EIGHT cards
  of ~33, which clears it. The scan's own desync branch had already printed "press count
  says row 39, the scrollbar says 4" -- it KNEW -- and the result was cached and served
  to every later ban screen in the process with zero captures. `run()` never clears it.
  A desynced scan is no longer cached.
- **The hand memory survived the HALF boundary.** `reset_hand_memory` had two call sites,
  both at match start; a new half deals a FRESH FIVE. A batting slot remembered as
  `secondary 3` -- a batter's speed, which no pitcher has -- was served on every pitching
  turn. Its safety net cannot catch this: memory is consulted only for slots the reader
  CANNOT see, so a readable card never audits it.
- **`known_ban_roster_learned.json` was the one write-then-read cache with no test
  guard**, and its path was cwd-relative while both siblings anchor on `__file__`. A
  learned entry is PERMANENT ground truth that vision never re-reads, so an offline run
  could poison the roster for good.
- **`_SYNTHETIC_LOG` was bound at IMPORT**, two functions below a docstring teaching
  10.18 for this very file. Setting the flag after `import orchestrator` left the stamp
  False while `_running_under_test()` was True, and an UNSTAMPED test row reached the
  real `match_log.jsonl` -- which the documented `grep -v '"_synthetic": true'` cleanup
  would never have removed. It happened during the sweep that found it.

### THE BAN PROBE CHECKED THE SENSOR BEFORE PLACEMENT AND NEVER DURING (2026-09-13)

Third time in one evening that a fix of mine was incomplete in the same way.

`run()` probes `ban_cursor_absolute` up to `BAN_CURSOR_PROBE_TRIES` times and, on ONE
success, commits to the verified path **with no way back**. A cursor that answers the
probe and then goes blind placed ZERO bans and still pressed `confirm_play` -- which
is Triangle, i.e. PLAY -- on a match already debited $50 at the prompt. The probe
moved the failure one `look()` later; it did not close it. `select_bans_verified` now
takes an `on_blind` callback and hands over to the dead-reckoned path **only when
NOTHING was toggled**: a target that was pressed but could not be confirmed may well
BE banned (the selection splash makes `ban_x_on` read False on a banned card), and
dead-reckoning over that would toggle it back off.

Two more from the same sweep, both fixed and mutation-tested:

- **A raising reader left the screen mid-change.** Neither `look()` nor `confirm_ban`
  was wrapped, and neither is `ban_cursor_absolute` / `ban_x_on`. A raise left the
  bans ON SCREEN with `confirm_play` never pressed, and in `run()` it unwound BEFORE
  `bans_done_this_match` and `acted_screen` were set -- so the next poll re-entered
  with the cached collection and TOGGLED THE BANS BACK OFF. That is the one path that
  defeats the C3 guard, and the verified navigator made it likelier by adding a screen
  read per press.
- **Moves and blind waits shared one budget of 14.** A far target with one late frame
  per scrolling press ran out before arriving: (6, 2) needs 2*6 + 2 + 1 = 15, was
  silently skipped, reported as `ban_nav_incomplete`, and the match played 2 of 3.
  Separate budgets now (`BAN_NAV_MAX_BLIND`); a blind frame is not a step.

**STILL OPEN, and it is the worst outcome available: A STALE COLUMN FRAME BANS THE
WRONG CARD AND READS AS 3/3.** `ban_cursor_absolute` is guarded against mid-animation
ONLY by the scrollbar. A VERTICAL press mid-travel leaves the scrollbar unreadable, so
the read is refused -- safe. A HORIZONTAL press moves no scrollbar, so the level reads
valid and `cursor_cell` reports the halo where it still is: a confident, stale cell.
An exhaustive search over 10,927 late-frame combinations found 126 wrong-ban outcomes,
and on the realistic 3-target run **75 of them end with three cards banned, one of them
wrong** -- so `read_ban_counter` says 3/3 and the run prints `verified 3/3 bans placed`.
`ban_x_on` cannot see it: it asks "is there an X where I think I am", gets False, and
logs the wrong ban as a MISSING ban. The fix it points to: `ban_grid.banned_cells`
already returns EVERY visible X and `ban_x_on` throws all but one away -- comparing the
full hit set against the expected set after each `select_card` catches it at the press
that made it. Not built: it changes ban verification on the $50 path and wants a live
screen to check.

**AND TWO CONSTANTS ON THIS PATH ARE INVENTED, INCLUDING ONE I WROTE TODAY.**
`BAN_NAV_SETTLE = 0.55` is justified as "about twice ACTION_DELAY" -- derived from
another constant, not from a measured settle. `BAN_CURSOR_PROBE_TRIES = 3` is
justified in prose with no measurement of how long a routine blind period lasts.
Neither sits between two measured populations (10.4). Nothing in `ban_grid.py`,
`input_controller.py` or `orchestrator.py` measures scroll or splash duration. They
are recorded here as unmeasured rather than quietly treated as evidence.

**Also stale:** `orchestrator.py`'s comment that under 3 bans the game "refuses to
start" is refuted 1,500 lines away in the same file ("three of five real sequences
finished at 2/3 with the match starting anyway") and by section 4 here.

### THE SUITE HAS FOUR DIFFERENT `check()` SIGNATURES, AND A REVERSED CALL ALWAYS PASSES

Written after shipping eight of them in one evening.

    tests/minigame/test_readable_hand_gate.py   def check(name, ok, detail="")
    tests/rig/test_window_drift_guard.py        def check(name, cond)
    tests/minigame/_run_harness.py              def check(cond, msg)
    tests/rig/test_no_real_input_under_test_run.py, test_keymap_matches_chiaki.py,
    test_chiaki_pid.py, test_deal_timing_tool.py   def check(ok, msg)

Call a name-first `check` as `check(condition, "message")` and the MESSAGE lands in
the `ok` slot. A non-empty string is truthy, so it prints `PASS True` and appends
nothing to `fails`. **The check cannot fail, on any input, ever** -- and the only
visible symptom is the word `True` where a sentence should be, in a file that
prints dozens of passing lines.

Eight checks written into `test_readable_hand_gate.py` on 2026-09-13 had this
shape: the crash-recovery check, the x-axis checks, the play_seq check. The suite
was GREEN with all eight vacuous. **Mutation testing is the only thing that found
it** -- three mutants survived that should not have, and chasing why led here.
That is the whole argument for section 10.9 in one incident: a test written, run,
and passing is not evidence of anything until something it guards has been broken
and the test has been watched to fail.

The cheap check, before trusting any new assertion in this suite:

    grep -m1 -o "def check(.*)" <the file>          # which order?
    <run the file> | grep -E "^ *(PASS|ok|FAIL) +(True|False)$"   # any bare bools?

Non-zero means vacuous checks.

### ...AND THE TARGETED PATH WAS NEVER LOCKED OUT EITHER. THERE ARE FOUR PATHS.

A QA sweep the same night, pointed at the fix above, found the fix incomplete --
and the file written to guard it declaring success while the hole was open.

`can_use_background_input()` returns False under `BASEBALL_TEST_RUN`, and `press()`
honours it. `press_background()` and `_bg_hold_keys()` never ask. THE GATE WAS ONLY
EVER AT THE CALL SITES. Reproduced with a PS5 connected and a match on screen:

    BASEBALL_TEST_RUN = 1
    can_use_background_input() = False
    press_background('look_right') -> True   posted to pid 83980, twice
    _bg_hold_keys(['w'], 0.01)     -> True   posted to pid 83980, twice
    press('look_right')            -> refused, 0 posts        [control]

`_bg_hold_keys`'s own docstring calls it "the single low-level route every public
input function funnels through, so there is exactly one place where 'did this go to
the game or to the user's work' is decided". It named the responsibility and did not
discharge it. Direct callers include `reset_env._probe_transports` and
`_diagnose_no_pause`, which turn the camera.

**And `inject_reset.py` is a FOURTH path**: raw button masks written to a HARDCODED
`/tmp/chiaki_input`, ignoring `CHIAKI_INJECT_INPUT` -- the one lever every test uses
to point the pipe somewhere harmless -- with no lockout of any kind. `reset()` is
OPTIONS x5 -> DPAD_DOWN x4 -> CROSS x6; on a match parked mid-play OPTIONS opens
"Give up?" and CROSS answers YES. It is imported by `go.py`, `run_to_table.py` and
`run_anchored.py`. Both now gated; its FIFO is read at call time.

So the count is: keyboard (`press`/`hold_combo`/`walk_at`), targeted Quartz
(`press_background`/`_bg_hold_keys`), sticks (`analog_replay.send`), recovery keys
(`ensure_stream._key`), and raw masks (`inject_reset.tap`/`clear`). **Every one of
them needed its own lockout, and four of the five were found by looking rather than
by a failure.**

**THE CENSUS THAT WAS SUPPOSED TO CATCH THE NEXT ONE MISSED SEVEN OF EIGHT FORMS.**
Each was planted as a working emitter and `test_no_real_input_under_test_run.py`
still exited 0: `pyautogui.press` (not in its EMITTERS list -- the most idiomatic
call in the library), system-wide `Quartz.CGEventPost`, a module-level call (it
walked only FunctionDef bodies), a bare-name call after `from pyautogui import
keyDown`, a `getattr(...)` call, and emitters in two modules absent from its
hand-kept 9-name scan list -- against 120+ root modules, 44 in `tools/`, 33 in
`overnight/`. That is `keep_awake`'s BUSY_PATTERNS lesson exactly: **a guard whose
trigger is a hand-kept list of NAMES rots silently, because nothing fails when a new
name is missing.** It now derives the list (197 modules), resolves the emitting
module from each file's own imports, and walks the whole tree. A first attempt at
that matched the bare attribute name `write` and reported 900 sites across PIL --
the receiver is what makes the match meaningful.

**The shape, one line:** the guard answers a narrower question than the name it is
filed under. `can_use_background_input` gates a CALL SITE, not the function; the
census asserted a site EXISTS, not that it is GUARDED; `CHIAKI_INJECT_INPUT`
redirects ONE writer, not the pipe.

### CHIAKI IS RUNNING ON COMPILED-IN DEFAULTS, AND FOUR KEYMAP ENTRIES DO NOTHING

`KEYMAP` is what we believe chiaki binds; `chiaki-ng-src/gui/src/settings.cpp` is
what chiaki binds. Nothing made those two agree. Checked by reading config, no
presses:

    the running app    chiaki-ng-build/chiaki.app, bundle org.streetpea.chiaking
    its settings       QSettings org "Chiaki" / app "Chiaki" -> com.chiaki.Chiaki
    keymap overrides   ZERO -- it is on the compiled-in defaults
    where WASD lives   com.chiaki.Chiaki-Taylere, a profile that is NOT running,
                       and restart_chiaki.sh launches with no profile argument

    walk_up   'w' -> chiaki wants 'insert'     walk_left  'a' -> '['
    walk_down 's' -> 'delete'                  walk_right 'd' -> ']'

**Those four presses post cleanly through CGEventPostToPid and do nothing.** All
32 other actions agree exactly -- every button, the D-pad, and the whole right
stick. It is NARROW: production walking goes over the FIFO (`slow_traverse` ->
`analog_replay`, section 5's "sticks go over the FIFO"), and only `probe.py` and
`reset_walk.py` call `walk_at`. It is PINNED rather than corrected, because
rebinding input that cannot be verified live is how this project gets a confident
wrong diagnosis -- `tests/rig/test_keymap_matches_chiaki.py` fails if the set
changes in EITHER direction, so a fix and a regression are equally visible.

**And it invalidated an observation made the same hour.** A live `walk_up` press
was reported here as having moved the character, on the strength of the scene
shifting between two frames. It cannot have; that was idle animation. Section
10.15 again: the frame was looked at, but a small shift between two frames of a
living scene is not evidence of movement.

### A BLIND BAN CURSOR MUST NOT MEAN ZERO BANS (2026-09-13)

`select_bans_verified` refuses to toggle a cell it cannot SEE. That is right when
the cursor READS and one target is unreachable — one missing ban beats banning a
card the engine never chose. It is the wrong answer when the cursor never reads
at all: it places NOTHING, and a $50 match starts completely unbanned, which is
strictly worse than the dead-reckoned path it replaced.

Nothing live caught it. `tests/minigame/test_run_resume_and_persist.py` did, on
the run that flipped `VERIFY_BAN_NAVIGATION` on: six ban assertions went from 3
bans to none, because an offline harness has no screen. `run()` now probes
`ban_cursor_absolute` `BAN_CURSOR_PROBE_TRIES` (3) times and falls back to
`select_bans_and_start_full` with a loud line and a `ban_nav_sensor_blind`
observation. **A closed loop is only better than an open one while its sensor is
alive; a dead sensor is not a failed navigation.**
- **And the lockout reads the environment at CALL time, so an IMPORT can switch
  it off mid-run.** `tools/prompt_ocr_ab.py` set the flag at module level for its
  own offline run; `overnight/prompt_zone.py` imported it for one function AFTER
  walking the leg, and from that import every stick send was dropped silently:
  fifty "readings" of a camera that never turned and a character that never
  moved (2026-09-07). The flag is set only inside `main()` or a test, never at
  import — `tests/harness/test_no_import_time_test_run_flag.py` scans `tools/`
  and `overnight/` by AST — and a live harness asserts it is unset before it
  sends. Three runs of the prompt-zone map were lost to this and to a
  keypoint count that was always 2; both looked like measurements.
- A missing FIFO degrades to the keyboard path with a warning rather than
  killing an unattended run.
- **A frontmost trap:** `osascript` leaves *Script Editor* frontmost, and
  `frontmost_app()` then reports that, so keyboard input goes nowhere. Anything
  that shells out to osascript must re-front chiaki before pressing keys.

### The FIFO protocol

A stick or button line takes an OPTIONAL THIRD FIELD, a hold in milliseconds:

    right_x 32767 400      push right stick for 400ms, then centre
    buttons 8 80           hold triangle for 80ms, then release

chiaki releases it on its own `steady_clock`. Omitting the field keeps the old
meaning. A timed hold under `INJECT_TIMEOUT_MS` (5s) needs NO chunking; the
deleted hand-walk script capped its holds at 4.5s for that reason.

**A sibling axis must not cancel a timed hold.** `right_x 32767 400` followed by
`right_y 0` — the natural way to set a stick — had the untimed second line clear
the deadline set by the first. A 1.0s command turned for ~1.4s and it looked
like drift. An untimed write now LEAVES an existing deadline alone; only `clear`
or expiry removes it.

`ar.clear()` stops NEW analog input; whatever is already in flight still lands.
Judge arrival on a frame captured AFTER the character settles.

**A dropped release packet is the lurking catastrophe.** chiaki's feedback
sender DEDUPLICATES — it early-returns when the state is unchanged — so a 1.0s
hold is TWO edge packets plus ~5 keepalives, not a 125Hz stream. Those edges are
fire-and-forget UDP. Lose the release and the stick stays at full deflection
until the 200ms keepalive: ~39.5 deg of extra turn. Untested; a real controller
hides it because stick LSB noise defeats the dedup.

**`clear` used to arm a release window that a later write never disarmed.**
`Apply("clear")` set `release_until = NowMs() + RELEASE_MS` (100ms) and nothing
cleared it, so a write inside that window set `active = true`, the deadline
expired, and `InjectInputActive()` ran its release path on the FRESH input —
chiaki's pump then stopped sending and **the console kept the last state it
received: the deflection**. Measured: gap 400ms 12/12 released; gap 30ms 12/12
STILL DEFLECTED; gap 90ms 9/12 deflected, 3/12 dropped. The 5s
`INJECT_TIMEOUT_MS` runaway guard could not save it because it lives inside the
function the pump had stopped calling — **a guard downstream of the switch that
disables it**, a shape worth recognising. The fix is one line,
`g_inject.release_until = 0;` on the non-clear path of `Apply()`, in BOTH copies
(`chiaki-patch/` and `chiaki-ng-src/gui/src/`; `tests/cpp/` compares them byte
for byte). Pinned by a mutation-tested check that goes INCONCLUSIVE rather than
passing when load pushes the write outside the window. Verified on the rig with
a camera turn: gap 400ms and gap 30ms both turned ~7.4 deg and both stopped
dead. Every production `clear` is terminal; the one live site inside the window
was `overnight/walk_curve.py:52`. That does NOT implicate §6's walking table,
which predates the window — OPEN-19 holds the question it does open.
(OPEN-16, closed 2026-09-05.)

---

## §6 Stick response, measured

### Turning: the error is an integer number of GAME FRAMES

Six identical `camera(1.0)` turns produced 200.964, 201.044, 208.613, 208.639,
212.448, 220.000 deg — steps of **3.795 deg** above the minimum (0, 0, 2, 2, 3,
5; residual <0.03). q / 220.5 deg/s = 17.2ms = 58fps. A continuous timing error
cannot produce that; only a discrete count can. Two runs land on the SAME float
to 14 figures.

So there is a floor of one frame, ~3.8 deg at full stick, that NO patch removes.
The network is innocent (wired LAN, RTT 1.7-6.3ms, 0% loss); the FIFO write is
0.6us; the 8ms pump is at most +-8ms.

**FULL STICK IS THE WORST PLACE TO TURN.** 74.8 deg/s at magnitude 0.90 against
197.7 at 1.00 — 2.64x for 11% more stick — so the same frame quantum costs
7.6 deg at 1.00 and 2.9 deg at 0.90. Measured drift range: **17.3 deg at
magnitude 1.0, 3.6 deg at 0.9, 2.9 deg at 0.7.** Relative error is best at 0.9
(5.0%) and worse at both 1.0 (8.3%) and 0.7 (8.2%) — a sweet spot, not "slower
is better". `turn_curve.USABLE_MAX = 0.90`; raw `camera()` warns above it.

**`turn_curve.MEASURED` is a table of AVERAGES OVER A 0.30s HOLD, not a rate
table.** Each entry bakes in one start and one stop transient. Steady rate at
full stick is 220.5 deg/s. Comparing the two quantities is what produced a wrong
"the table is 10% low" claim; checked against six live 1.0s turns per magnitude,
the table is accurate where the system uses it (+3.9% at 0.90, +5.1% at 0.70).
`MEASURED` and `VERIFIED_1S` are pinned exactly — **a table of MEASUREMENTS is a
record, not a tunable.**

### Walking: linear to ~0.75, but repeatability collapses above 0.60

Displacement per 0.40s push, 3 samples per magnitude:

    mag    median   spread
    0.25     34.6      15
    0.35     48.3      15
    0.45     70.6      15
    0.60     71.2      27
    0.75    106.0     124
    0.85    352.9     476     (one push unmeasurable)
    1.00    113.4      73

Walking IS roughly linear up to ~0.75, so scaling speed x duration preserves
distance in that range — the assumption behind leg-speed scaling is evidence,
not hope. But **the median stays reasonable while the VARIANCE does not**, and
variance is what makes a dead-reckoned leg miss. `LEG_SPEED_MAX = 0.60`
(`graph_walk.LEG_SPEED_MAX`). The earlier 0.85 was borrowed from
`turn_curve.USABLE_MAX`, a constant about the RIGHT stick — different stick,
never evidence for this one.

---

## §7 The map and the localiser

`world_map.json`: **6 nodes, 5 one-way legs**, built by `build_world_map.py`
from `route3_steps.json` plus a 712-frame recorded walk.

    office_corridor -> office_door -> portrait_room -> bar_pool_room
                    -> bar_jukebox -> dealer_table          23.00s total

- **A leg carries STEPS, not just a duration.** `connect()` stores
  `{"cost", "steps": [{"bearing","dur","speed"}]}`. A bare duration is not
  executable. Curves keep every sub-step; averaging a 26-degree bend into one
  heading walks into a wall.
- **Legs are ONE-WAY by default.** One trip is evidence about one direction.
  Fabricating the reverse plans an unwalked climb back up a drop.
- `WorldMap.load()` treats **links as mandatory, trail as optional** — it had
  this backwards, so a map with NO EDGES loaded as valid and then reported every
  destination unreachable.
- `route_reason()` separates the four causes `route()` collapses into one None.
- chiaki releases injected input after 5s, so an unchunked leg caps at ~4.5s.

### The localiser

`places.identify()` is ORB-based: `MIN_MATCHES = 140`, `MIN_RATIO = 1.35`
(`places.py:284-285`). When the character genuinely stands at a node it names it
with a **2.6-5.3x margin** (leave-one-out: 249-698 matches). Held-out check
after the node-set rebuild: 18 correct / 6 abstain / 0 wrong, every abstention
±1s from a node.

**Do not lower these thresholds.** The failures are POSITION failures, not
recognition failures.

- **`dealer_table` is a POSE, not a place.** Its identify() margin is the prompt
  TEXT. Confirm arrival with `table_prompt.at_table()`, never `identify()`.
  Enforced in `confirm()` AND, since 2026-09-07, in `locate()` — it was not, and
  OPEN-14 trial 6 was scored an arrival on `identify()` naming the table at
  194/1.53 with no prompt (`tests/routing/test_locate_goal_is_a_pose.py`).
- `office_corridor` and `office_door` measure 0.726 alike — the same corridor 5s
  apart. They stay separate nodes because the walk between them is real, and
  `world_map.json` records the pair under `confusable`.
- **Do not seed a place from a dark frame.** Seeding `office_door` instantly
  created false positives. `build_world_map.SEED_PLACES` excludes both office
  nodes deliberately; they are reached by walking, not recognition.
- `identify_edges` (the old correlation path) still exists, has **zero
  production callers**, and carries the 0.906 dark-frame trap: `descriptor()`
  divides by the vector norm, so a near-featureless frame becomes mostly the
  shared vignette and an upstairs office door scored 0.906 against
  `beside_dealer_table` — higher than any genuine match. **No score threshold
  fixes that**, which is why the ORB path replaced it. ORB is immune by
  construction: crossCheck matching cannot return more pairs than the smaller
  descriptor set, so a 10-keypoint frame scores 1.

### Admitting a new place

`map_propose.py --admit` gates on non-disruption, discrimination, and
recoverability. A deliberate mapping run (160 frames, 17 stops, 15 clusters)
was **rejected 15 of 15**, all on recoverability — no candidate could name any
frame of the failure population it claimed to fix.

Two traps found there, both worth keeping:

- **A self-match trap:** left in the pool, failure frames cluster as singletons
  and "rescue" themselves, reporting the problem solved. Hold them out.
- **The break/rescue test alone is degenerate.** The same frame scores ZERO
  breaks filed under every existing room, while filed under `dealer_table` it
  would newly name three bar-counter frames `dealer_table` — three confident
  wrong answers, scored "safe".

`identify_orb` scores a room by its BEST SINGLE reference (`places.py:288`), so
pooling many frames into one node does not raise its score.

**The bar area is two-thirds UNMAPPED, measured not inferred.** Of 160 frames
from that run, 100 were RICH AND UNNAMED: median 1500 keypoints (the ORB cap —
maximum possible detail) with a median best match of **128 against MIN_MATCHES
140**. Every one is JUST under the bar. So walking a metre off a known node goes
blind at once, and that is a mapping gap, not a detector failure.

---

## §8 Navigation: current measured state

**This is the only section that reports status.**

### THE CLOSED LOOP REPLACED DEAD RECKONING ON 2026-09-07, AT THE USER'S REQUEST

**The user had asked for this design earlier and an earlier session built dead
reckoning instead; that cost days. When the user proposes an architecture,
build a spike of it before continuing the current plan.**

Dead reckoning (§8(a) below: replay recorded bearing/duration, look only at a
leg's end) sat at 5/10 per route through thirteen measured changes. The closed
loop LOOKS AFTER EVERY PUSH and takes position from the screen, never from the
stick. Built in one evening: `chain.py` (the sensor), `chain_record.py` (the
recorder), `chain_walk.py` (the controller), `overnight/chain_trials.py` (the
harness), `tools/chain_validate.py`, `tools/turn_review.py`; spec and build
notes in `agent_progress/closed-loop/`. Three Opus builders, three skeptics,
every module refuted at least once and fixed; 74 controller tests, every fix
mutation-tested.

**The chain is the user's own drive** (`chains/route_user_1853`, 205 frames at
0.25 s, stick logged through pygame, compass on 94% of frames, stopped by
`at_table()` at the prompt). A chain is compiled into a PLAN: push targets one
push apart by the recorded stick's distance, and each stationary run collapsed
to ONE turn-only stop. The sensor (`Chain.locate`) matches a frame against a
window of waypoints around the last known index, ORB + Hamming + RANSAC,
`dx` and scale from the fit. Offline on the drive's own held-out frames, closed
hint: 82% within one waypoint, 96% within two, 4% abstain.

**Measured, batch 4 (2026-09-07 19:47, the first with all six fixes below but
the last): 8/10 ARRIVED at 90-121 s reset-to-prompt.** Dead reckoning's
arrivals took 240-340 s. Batches 1-3 were stopped early because each failure
was one spot with one fix (`overnight/chain_trials_batch{1..4}.*`). The 25 is
running as this is written.

**Six controller lessons, each from a trial's frames and each pinned by a test
and mutants (`git log -- chain_walk.py`):**

1. Advance the estimate to the TARGET it pushed toward, never past it. Trial 1
   ran three waypoints ahead per push on 13-28-inlier fits and strafed into
   the wall on junk offsets.
2. Push targets spaced by the recorded stick's distance, not per frame; the
   user's slow stick put four frames in one push and the estimate fell behind.
3. A blind sensor (featureless door panel, dark wall) dead-reckons the target
   for `BLIND_MAX` pushes before misses count; a fix under `FIX_MIN_INLIERS`
   (29, the chain's own true-position p05) neither advances nor steers; a
   thin fit (`WEAK_MIN_INLIERS` 15) advances but does not restore the budget.
4. **Verify every turn stop against its own frame** (the user's call from the
   stream: "the player didn't move far enough towards the door"). A frame
   that fits an EARLIER waypoint means short: turn back, push once more,
   retry (`TURN_RETRY_MAX` 3). A frame that fits NOTHING is occluded (an NPC
   in the face) or already passed: turn and go on, no retry pushes.
5. A wide forward search (`WIDE_AHEAD` 60, believed at `STRONG_MIN_INLIERS`
   120, above the wrong-place p95 of 117) from the FIRST blind push and at
   unverified stops. At the office exit the shop facade across the street
   looks the same from the doorway and from halfway across; the loop crossed
   in two pushes and stood at the portraits while the estimate said
   "doorway". A margin over the runner-up was tried first and was wrong: in a
   window of adjacent frames the runner-up is the neighbour.
6. `LOST_MAX` 9: nine iterations with nothing credible after the budget ends
   the walk at once (80 s) instead of burning the 400 s cap (trial 3 pushed
   into a wall 312 times).

**Review rule (the user's):** look at the TURNS first. `tools/turn_review.py
<shots dir> <journal>` tiles the live frame at every stop beside the chain's
frame there; a wrong scene after a turn means the character stopped short.
Pair a journal with its shots by time.

**Known hazards at 97%:** an NPC standing in the exit door (trial 1 stalled
six pushes there before a jump cleared it); the user's camera pitch on the
stairs (every fit there carries a 200-300 px vertical offset the loop ignores).

**THE AUDIT ROUND (2026-09-07 21:00, commit 3df1727).** After eight rapid
patches the controller was audited by two independent skeptics while the
console ran; every confirmed finding was a guard that could not fire or a
rule that fired on the wrong measurement, the project's signature shape:
the plan pointer never rewound after a regression (the target then sat past
the window forever); a thin fit advanced the estimate to the target without
naming it; a stop verified only when its fit was BADLY misaligned; the
look-around's frames overwrote the frame the verdict was made on; and the
gates 29/120 sat inside the overlap of the census they cited, which had been
built on a 41-waypoint chain while the live run loads 205. All fixed and
mutation-tested. **The live-frame census** (`tools/live_gate_census.py` ->
`overnight/census/live_gate_census.json`, 1,858 in-window fits, 468 far
matches): true fits from arriving trials median 98 inliers, p25 49; wrong-
place matches p95 126, MAX 164. No count separates them; the sequence window
does the work, and only the wide-search gate was moved (to 165, above the
wrong-place maximum). **The stop table** (`agent_progress/closed-loop/audit/
stop_table.md`, 43 journals): the bar-entrance stop at chain 129 verifies 58%
of the time and a trial that takes it unverified arrives 1 in 14; stop 166
unverified arrives 0 in 6. That stop is the lever. **Arrival review** (13
arrivals, frame by frame): 12 minor detours, 1 wandered-and-lucky, 0 off the
route; every detour was a wedge at a real obstacle (the exit-door threshold,
the bartender's counter with two NPCs and two steins). **Failure review** (10
failures): turn-taken-short 5, NPC in view 2, blind into an obstacle, estimate
ran ahead, lateral displacement 1 each. Measured rates by version: batch 4
8/10, batch 5e 6/14 (three rules shipped in between, one of them a
regression corrected in 5e); the audit round runs as this is written.


**THE CLOSED LOOP'S MEASURED STATE, 2026-09-08 02:15 (the newest line in this file; the batches below
are archived as `overnight/chain_trials_batch{10,11,12}.*`, one reader per failure in
`agent_progress/closed-loop/review/`):**

    build (commit)       trials  arrived   walk median   best streak   what changed
    e49cd3e  00:13         12     11 + 1 false   ~105 s      11        retry gate after a wall-scale fit; a dark-frame
                                                                        detector retry that fired on the street (reverted)
    f8af4d3  00:38         25     21           105.3 s       9        the end-turn rule (turn toward the dealer past the last stop)
    2220c83  01:31         25     24            86.4 s      21        a stop tie needs a different place; the look-around
                                                                        exits on a strong look; the prompt check only in the
                                                                        tail; at_table() believes 0.20 with one OCR word

    2220c83  02:16 (again)  25     23            84 s        15        repeatability: the 24/25 repeats
    a8ff495  02:59         25     22            82 s        10        a thin fit at a stop is nothing; a retry needs credible
                                                                        short-evidence; an unverified stop REWINDS and re-approaches
    a8ff495  03:40 (again)  12      9            81 s         3        stopped at the boundary: the REWIND IS A REGRESSION at the
                                                                        bar-entrance stop 129 -- taken unverified (b12-14) 11/11
                                                                        arrived; rewound (b15) 0/3, each lost at 109 re-walking
                                                                        into the NPC it had just met
    078a912  04:02         25     22            82.5 s      11        STOP_REWIND_MAX 0 (rules A/B stay); at_table() reads the
                                                                        "$50" fee token last: 0 of 7,885 route frames, 58 of 81
                                                                        prompt frames, the three b13-t5 "FAILED at the prompt"
                                                                        frames all read it -- AND IT DECIDED 2 OF THE 22 ARRIVALS
                                                                        (t9 score 0.173, t14 0.245, zero words, fee read; 17 by the
                                                                        mask, 3 by two words). The three failures, each read: all
                                                                        PINNED in the portrait room / bar entrance (a framed
                                                                        portrait, the bar-entrance corner after the 129 look's
                                                                        strafe, the photographer NPC then a wrong 191-inlier wide
                                                                        relocalisation), the ladder moving nothing
    078a912  04:51 (again)  25     22            88.9 s      13        repeatability: 22/25 REPEATS. Its three, each read: t8 the
                                                                        bar-entrance corner after the 129 look's strafe (b16 t12
                                                                        again); t9 a 29-inlier look at the top of the stairs turned
                                                                        the character into the doorway post, a jump put it in an
                                                                        unrecorded side room; t12 an aproned patron in the tables
                                                                        aisle, the ladder freed it and STUCK fired on the row the
                                                                        fit read 176 at scale 0.973 (reached() needs 1.0)
    078a912  05:35 (again)  25     20            78.7 s       7        the third run of this build: five failures, a NEW cluster --
                                                                        three losses on the STAIRS (t8 the door stop turned short
                                                                        into a side room, t14/t22 thin fits that never advance at
                                                                        39-46; four stairs losses in 40 trials after ~100 without)
                                                                        and two more identical 129-look failures (t10, t20). The
                                                                        fastest walk on record, t3 at 62.7 s: nothing went wrong.
    32e4400  06:15         25     23            80.2 s      10        patch43+43b, a LOST RESCUE: at lost >= LOST_MAX, once per
                                                                        walk, back out 1.0 s and look 0/-25/+25 over the WHOLE chain
                                                                        behind the last credible k at the strong gate (165); fires
                                                                        only where the walk was already lost, so every firing is a
                                                                        measurement and arrivals cost nothing. patch44 (STOP_LOOK_YAW:
                                                                        a looked stop turns instead of strafing; census: after the
                                                                        129 strafe the next fit still reads -300 px on 93 of 96
                                                                        arrivals) is in build for an A/B. RESULT: 23/25, the night's
                                                                        best count (= b13); the rescue fired twice, found nothing
                                                                        twice (t11 in an unmapped storage room through a WRONG DOOR
                                                                        in the office corridor; t17 against an NPC now standing at
                                                                        the top of the stairs), cost nothing. The office losses of
                                                                        b17-b19 are wanderers: an NPC at the stairs, doors that open
                                                                        when a blind push hits them.
    a411fe4  07:07   A/B 20  off 9/10    78.3 s                        patch44 STOP_LOOK_YAW, `--arms off,on --flag STOP_LOOK_YAW`:
             (10/arm)        on  9/10    79.4 s                        at a stop verified by the look-around, TURN by px/PX_PER_DEG
                                                                        (the end turn's formula, capped at END_TURN_MAX_DEG) and
                                                                        carry the offset to the next stop, instead of the capped
                                                                        0.3 s strafe. Arrival a tie (Fisher 1.0; each loss a
                                                                        wanderer). THE INSTRUMENT DECIDED IT: the first credible
                                                                        fit's dx after a looked 129 stop, off arm median -352
                                                                        [-383..-264] on 5 of 5, on arm +72 [-96..+150] on 5 of 5
                                                                        (yaws -12.6..-22.9 deg) -- no overlap. SHIPPED ON (patch45).
    da361ef  07:43         25     21            81.4 s      11        patch45: STOP_LOOK_YAW = True, plain 25 -- the first full
                                                                        batch with the rescue AND the yaw. 18 yaw firings; THE
                                                                        RESCUE'S FIRST WIN (t18: lost at 129, backed out, saw the
                                                                        portrait room at 180 inliers, re-approached, arrived). Four
                                                                        losses: the stairs NPC (t1), the blind stretch past 129
                                                                        (t20), and TWO post-yaw over-corrections (t13, t17): when
                                                                        the look's fit lands 2-3 waypoints AHEAD of the stop the
                                                                        un-yaw formula over-turns (fits at 128-130: 12/13 arrived,
                                                                        residual |~90| px; at 131-132: 2/4, residual +150..+230).
                                                                        Yaw at the stairs stop: 3 of 4 arrived. The morning's first
                                                                        candidate: yaw only on a fit at the stop's own index +-1
    da361ef  08:28 (again)  25     22            79.2 s      13        repeatability of the rescue + yaw build: 22/25. 16 yaw
                                                                        firings; the rescue fired 5 times and WON TWICE (t15, t18:
                                                                        the estimate at 166, the +25 look found the portrait room
                                                                        at 118/121 on 171/188 inliers, both re-walked and arrived,
                                                                        t18 at 176.5 s against the 180 s walk cap). Losses: past
                                                                        129 (t6), the office stretch twice (t20, t23, lost at 88
                                                                        after the corridor). Rescue tally over three batches: 14
                                                                        firings, 3 believed, 3 arrived
    da361ef  09:12 (third)  25     23            79.8 s      21        the same build again: STREAK 21, TYING THE RECORD (b12).
                                                                        Losses: t3 the office stretch; t25 the fourth fit-ahead
                                                                        yaw over-correction (a look matched waypoint 132, yaw
                                                                        -25.8, the next fits +126/+275, blind, lost) -- 3 of 7 such
                                                                        firings lost, the patch46 gate's case
    da361ef  09:57 (4th)    12      9            92.0 s       4        a short batch so the next boundary met patch46. Losses: the
                                                                        stairs NPC (t5); 129 taken unverified then fits with dx
                                                                        +640 the strafes could not close (t9); a +29 deg yaw at the
                                                                        196 stop then the end without the prompt (t12)
    ef717b1  10:19   A/B     off 7/10    89 s                          patch46 STOP_YAW_NEAR_FIT_ONLY, `--arms off,on --flag
             (2 launches)    on  7/9     91 s                          STOP_YAW_NEAR_FIT_ONLY`: the yaw only when the look fits the
                                                                        stop's index +-1, else the old strafe (fits 2-3 ahead
                                                                        over-turned and lost 3 of 7). INCONCLUSIVE: the gate fired
                                                                        twice in nine on-arm trials (1 arrived, 1 lost to the stairs
                                                                        NPC); the off arm yawed on a far fit twice (both arrived).
                                                                        Ships OFF. 20 trial numbers were burnt by the game window
                                                                        going off screen (the user's Space switches) -> patch48: the
                                                                        harness waits up to 120 s and re-runs the number twice
    0226268  11:06   A/B     off 9/10                                  patch47 DOOR_STOP_EXTRA_PUSH, `--arms off,on --flag
             (10/arm)        on 10/10                                  DOOR_STOP_EXTRA_PUSH`: one more push toward the office door
                                                                        before the stairs turn -- THE USER'S OBSERVATION FROM THE
                                                                        STREAM. The instrument decided it: the 39 stop verified
                                                                        HEAD-ON on 10 of 10 on-arm trials (66 inliers, fit scale
                                                                        1.04 [1.01..1.11]) against looked 3 / aligned 6 / unverified
                                                                        1 (the loss) on the off arm (38 inliers, scale 0.96 with a
                                                                        0.80 tail). SHIPPED ON (patch50). Also landed: patch48, the
                                                                        harness waits for a missing game window and re-runs the
                                                                        trial number instead of burning it
    a780ed6  11:46   12 + 8   12/12 + 7/8   83.7 s / 86.1 s   12      the door step ON, plain 25 in two parts: part 1 stopped at 12
                                                                        by the user's VPN reconnecting (chiaki: "Takion failed to send
                                                                        data packet"; trials 13-14 INVALID on the dead stream, not
                                                                        counted), part 2 stopped at 8 by the user's restart. 19 of 20
                                                                        valid; the one loss t1 of part 2: a +10.6 deg STOP YAW at the
                                                                        LAST stop (196, the look fit TWO ahead at 198), then the final
                                                                        approach never found the prompt (patch51's case, below)
    2d0f4e0  12:25          -     not run yet                          patch51 STOP_YAW_SKIP_LAST_STOP = True: no stop yaw at the plan's
                                                                        LAST turn-only stop -- nothing clears it after that, so it rides
                                                                        the whole final approach under the end turn. Census of the 196
                                                                        stop over 266 walks: head-on or strafed 225 arrived / 1 ended
                                                                        without the prompt / 1 failed; looked and YAWED (6) 4 arrived /
                                                                        2 ended at 204 without the prompt. The strafe runs there instead
                                                                        (marker yaw_skipped.reason = "last stop"); 4 mutants caught.
                                                                        Landed at the restart boundary; THE NEXT PLAIN 25 MEASURES IT
    2d0f4e0  12:55   17 + 1i  17/17         76 s        17      patch51 measured as far as it can be: the last stop verified
                                                                        HEAD-ON on every trial, so the rule never fired (it touches
                                                                        ~1 walk in 40); the batch shows it broke nothing. Stopped at
                                                                        18 for the user's settle measurement; trial 17 INVALID
                                                                        (Mission Control took the window) and re-run by patch48
    d36ba83  15:25   A/B      off 8/10                                  patch55 BAR_STOP_EARLY_TURN, one fewer push before the 296-deg
             (10/arm)         on  8/10                                  jukebox turn -- the user's "they walked too close to the bar".
                                                                        Tie, and the PRE-REGISTERED instrument (fit scale at 135-149,
                                                                        must fall toward 1.0) went 2.67 -> 2.71, UP. Ships OFF. The
                                                                        fourteenth navigation change measured flat -> GRAVEYARD
    2c8fea7  18:14   40       40/40         76 s        40      THE GOAL. --attempts 2 (patch52, the reload the user chose:
                                                                        "reload and report both numbers every run"). Every trial
                                                                        passed the independent at_table re-check; FIRST-WALK 39/40
                                                                        (97.5%); one reload (t13, lost at the jukebox turn with the
                                                                        blind-then-lost signature, recovered). By the strict no-reload
                                                                        reading the run from t14 is 27, which also clears 25. Sheet:
                                                                        overnight/goal_batch_arrivals.jpg. Blind-look (patch56) and
                                                                        pitch correction (patch57) landed on this build but OFF

Twenty true arrivals in a row across the first two, twenty-one inside the third. The failures that remain
are one shape: blind pushes into geometry after a verified stop, then the next stop accepted UNVERIFIED
with the estimate jumped ahead (unverified stops arrive 1 in 14 and 0 in 6 in the audit's table); the
rewind-on-unverified rule (`drafts/pending_after_ab/apply_patch41.py`) is in verification. Every rule
above came from a reader's frames and is pinned by tests and caught mutants; `HANDOFF_NOW.md` carries the
queue and the censuses behind each constant.

### (a) Where the route stands

**RE-MEASURED 2026-09-07, AFTER the leg-1 revert. Arrival did NOT move.**

    outcomes [F,T,T,F,T,F,F,T,F,T]   arrived 5/10   BEST STREAK 2
    243.7s per trial (was 338s), 0 invalid
    failures by class, ALL FIVE from admissible leg-end frames:
        wedged 4, overshot 1, fallback-frame 0

So the leg-1 flags were a REGRESSION I introduced and reverting them restored
the prior state -- it did not improve on it. The start node is 10/10 again and a
trial is 28% cheaper, but the route is where it was. Necessary repair, not
progress toward 25.

**This is the first route census taken entirely from admissible frames**
(`failures_by_kind_leg_end` 5, `failures_from_fallback_frame` 0), which OPEN-1
asked for. At n=5 it says nothing firm about the mix; note only that it is
WEDGED-heavy, where the earlier single-node census at `bar_pool_room` was
8/10 OVERSHOT.

At 5/10 per route, P(25 consecutive) is ~3e-8. Retry depth (OPEN-5) is the only
lever with the leverage to close that.

The pre-revert figures below are kept because the profile in (h) refers to them.



Route `portrait_room -> bar_pool_room -> bar_jukebox` from a reset spawn, using
`follow_verified` (which never walks a leg from an unconfirmed pose):

    outcomes [T,T,T,F,F,T,T,F,T,F]    arrived 6/10    BEST STREAK 3
    338s per trial

The requirement is **25 consecutive**. That needs ~97-99% per route.

### (b) Per-leg arrival (n=76 leg executions, measured over that 10-trial run, before several later fixes)

    office_door -> portrait_room      20/20   1.000
    portrait_room -> bar_pool_room    14/21   0.667
    bar_pool_room -> bar_jukebox       6/15   0.400
    Fisher, leg 1 vs leg 3: p = 7.1e-05

Not diffuse — two bad legs, and the jukebox leg is the worst. **Tag any reuse of
this table with its n and date**; it predates the button fix.

### (c) Retrying is the only lever that reaches the target

**MEASURED 2026-09-07 (OPEN-5): `attempts=9` arrived 9/9, `attempts=3` 5/10,
Fisher p = 0.0325, and the deep arm's median is LOWER (308s vs 381s).** Goal
node `bar_jukebox` — one leg BEFORE the dealer table, whose arrival is a
different check (`at_table()`). Both records below.

**`go_to_node_verified` arrives 10/10 (OPEN-4, 2026-09-06).**
`overnight/measure_primitive.py`, n=10, target `bar_pool_room`, attempts=3:
10 valid, 0 invalid, 10 arrived, **median 52.9s**, and `locate()` agreed with the
primitive on every trial (`overnight/primitive_open4.json`). Config as shipped:
`TRUST_RESET_SPAWN`, `RECOVER_MISSED`, `NULL_YAW_BEFORE_ALIGN` all True,
`REFERENCE_POSE` "bot". The ~55% figure is a SINGLE WALK; the retrying primitive
is what everything downstream should use. It is one leg from a reset, in one
session — it does not license quoting 100% for a route.

**`attempts=9` arrives 9/9 against `attempts=3` at 5/10 (OPEN-5, 2026-09-07).**
Interleaved, 10 trials an arm, TIMEOUT 900 so the deep arm could not be censored,
`start_hint=SPAWN`, scored on `follow_verified` confirming the goal
(`overnight/ab_attempts.py`, `overnight/ab_attempts.json`):

    attempts_9   9/9 valid arrived    median 308s   [83..780]    1 invalid
    attempts_3   5/10 arrived         median 381s   [77..403]    0 invalid
    Fisher exact p = 0.0325

"Arrived" here is the localiser naming `bar_jukebox` — one leg BEFORE the table —
at 218-1108 matches / ratio 1.74-11.66, with a photograph written at that moment:
14 of them, 9 + 5 exactly (`overnight/open5_arrivals.jpg`), and 5
`fail_bar_jukebox` frames for the 5 misses. **It is NOT the table and NOT the
prompt.** All five `attempts_3` misses died on the jukebox leg at depth 2/3. The
deep arm's median is LOWER because arriving is cheaper than exhausting three
attempts and reloading. The one invalid trial was a reset that could not open
the pause menu at 30.7s, diagnosed live by the transport probe as game state
(both transports alive) and recorded INVALID, never a failure. Nothing reached
the 900s ceiling. **Shipping attempts=9 changes a default and is the user's
call; the constant is untouched.** The streak at attempts=9 with the table leg
and `at_table()` as the final check is in flight — OPEN-14.

    follow() once, single attempt         ~55% per node
    go_to_node_verified (3 attempts)      10/10, median 52.9s  (OPEN-4, n=10)

Retrying costs TIME, not probability. At the measured per-attempt 0.40 for the
jukebox leg: attempts=3 gives a node rate of 0.784; attempts=7, 0.972;
attempts=9, 0.990. An earlier claim that "0.55^3 = 17%, so 25 consecutive is
arithmetically unreachable" was WRONG — that arithmetic applies to a
single-attempt walk, not to the retrying primitive.

### (d) The spawn is deterministic

Bearing 86.9/87/87 (E) on every reset. Drift accumulates after that.

### (e) `follow()`'s "reached" is a ROUTING CLAIM, not evidence of position

Since abstentions became advisory it carries on past nodes it could not confirm,
so it can report reaching `bar_jukebox` while the character stands in a
stairwell — which happened, and sent a scouting pass to photograph the wrong
room. Anything that must actually BE somewhere must use
`go_to_node_verified()`, which believes only `locate()`.

Treating abstention as ADVISORY was itself measured good: mean progress went
from node 1.7 to 4.0 of 5, and over every run **10 mid-route confirmations
failed and ALL TEN were abstentions** — `identify()` never once named a wrong
room.

### (f) Failure signatures

`failure_kind.classify(img, target, route)` returns WEDGED / OVERSHOT /
REGRESSED / UNPLACED. `WEDGED_MAX_KEYPOINTS = 50` sits between two measured
populations: a frame pressed against geometry holds 9-11 keypoints, the next
lowest non-wedged frame holds 744, and a genuine arrival 339-1500.

**Report arrival BY CLASS, never just overall.** Arrival averages several
different failures, so a change that eliminates an entire class moves the
overall rate by roughly a third of it — invisible at n=10. That is a leading
explanation for why so many well-motivated changes measured flat.

**But the class distribution itself is currently unsupported** — see OPEN-1. The
eight frames it was derived from describe the recovery fan, not the leg.

### (g) The escape ladder skips GEOMETRY

Keypoint count discriminates where scene-change could not: pressed into
furniture reads 9-11, open space 744-1500, and `GEOMETRY_MAX_KEYPOINTS = 50`
sits in the gap. The ladder has NEVER cleared a geometry wedge — every archived
occurrence reads `wait -> jump -> jump -> slip right -> slip left`, each
displacing 0.0px. `SKIP_LADDER_ON_GEOMETRY` is on; it is conservative by
construction, so an NPC blocking a visible passage still gets the full ladder.

**Cross (X) IS the jump button** — four presses spiked 10.1-12.5 against a 4.67
idle baseline. An earlier test concluded there was no jump and was WRONG: it ran
with the character against a wall, where a jump changes almost nothing.

**The wall-vs-NPC test was removed, not fixed.** "A wall does not move" needs a
threshold, and standing perfectly still already produces scene changes of
0.91-6.41 (median 4.09), so the 2.0 threshold sat under the noise floor. Against
real blockers the escape outcomes were `None, None, jump, None, None, None,
wait, jump` — jumping works sometimes and is worth trying FIRST, because it
moves nothing sideways in a passage with stools on one side and a wall on the
other.

### (h) Where a trial's time actually goes

**The 85.6s profile this section used to quote is withdrawn** (OPEN-8). It
profiled `reset` plus two legs rather than the route, it wrapped
`walk_steps.walk_forward` / `turn_to`, which a LEG NEVER CALLS (legs go through
`slow_traverse`), and it summed NESTED timers, so its "65% unaccounted" was an
artefact of the arithmetic. `overnight/profile_trial.py` now profiles the route
through `follow_verified` and records INCLUSIVE and EXCLUSIVE seconds; **read
the exclusive column** (`tests/harness/test_profile_exclusive_time.py`).

The accounting that DOES add up — modelled from the code and validated against
the old profile's own call counts (8 / 1 / 6 predicted, 8 / 1 / 6 recorded):

    reset x2 + sleep(1.2) x2          20.3s  23.7%   cut: start_hint, ~24s a trial
    leg turning, 23 steps             21.5s  25.2%   only ~3.5s of it is stick push
    stick time walking                16.2s  18.9%
    relocalise sweep, SILENT          13.9s  16.2%   cut: start_hint
    SETTLE_SEC x 23 steps              8.1s   9.4%   do NOT shorten (OPEN-8)
    captures inside walk_leg           1.7s   2.0%
    align + confirm + locate + live    4.0s   4.7%

About 26% of a 338s streak trial (~89s) is still unexplained with every modelled
component at its floor; the recovery fan (~79s each, ~33% of the clock when it
fires) is OPEN-7's. The largest single cut measured: `read_bearing` fell from
**261ms to 31ms (8.4x)** once `tesserocr` replaced shelling out to the binary,
~12s off a trial, correctness verified on 208 glyph crops that match EXACTLY.
`ocr_glyphs._api()` keeps a per-thread `PyTessBaseAPI` (134ms first call, 23ms
steady), so there is no spin-up left to remove and a daemon would add moving
parts for nothing.

**The lesson: profile before optimising.** Leg speed was the intuitive target
and was nearly worthless — walking is only ~20s of a trial, so a 32% cut in
walking bought 5% and a worse mean.

### (i) Why the jukebox leg cannot be fixed with a better constant

The starting pose inside `bar_pool_room` varies run to run, so no single
(bearing, duration) is right from every start. A direct search found 337.1 deg
for 0.80s reaching `bar_jukebox` where the recorded leg walked into furniture —
but putting it in the map and running it live still did not arrive, because that
run reached `bar_pool_room` off-pose and `align_lateral` reported "blocked
sideways, cannot correct from here".

**Caveat added 2026-09-04: the magnitude of that variance is not established.**
The "~150px" figure traces to ONE stalled alignment loop (`pose.py:233`), is
censored (the loop returns before logging when |dx| <= 35), and predates the
button fix. A later attempt to refute it using pairwise spread between failure
frames was invalid — it compared a SPREAD to a BIAS, and the frames were
captured immediately after the aligner drove the character onto that very
reference, making tight clustering circular. **Both the claim and its
refutation are unsupported.** See OPEN-1.

### (j) Pose alignment

`places.identify()` answers "which ROOM", but rooms are large and a
dead-reckoned leg assumes a POINT. `pose.align_lateral()` closes that on the one
axis that can be measured. `pose.offset()` fits a partial affine with RANSAC and
keeps the DIRECTION:

    strafe right  dx = -126.0   forward  dx =  +5.5  dy =  -8.6
    strafe left   dx = +132.7   back     dx = -14.3  dy = -24.5

Forward/back barely register — monocular depth is weak — so only the lateral
axis is corrected. **Measured: 214px -> 25px, 182px -> 27px, 360px -> 7px.**

**Its divergence guard never fired until 2026-09-04.** It read
`abs(dx) > last * 1.5`, but `last` was assigned `abs(dx)` twenty-five lines
above, so the test was `abs(dx) > abs(dx) * 1.5` — always False. It exists to
stop the oscillation in the first bullet below, and it was not stopping it.
Because that branch owned the only "diverging" log line, its absence from every
log read as "it never diverged". A bound that cannot be reached, inside a branch
that writes nothing: two catalogue items in one place. Every step now logs its
dx and the previous one, which is what would have exposed it.

Three tuning facts that cost measurements:

- The OPEN-LOOP gain (126px per 0.30 x 0.35s) is WRONG for control, because that
  push accelerated from standstill. Closed-loop is ~2400 px per
  unit-magnitude-second; at the open-loop figure the loop OSCILLATED with
  growing amplitude (+175 -> -201 -> +211 -> -215).
- A push under ~0.10s does not move the character at all, so the loop stalls
  issuing 0.03s corrections. Below ~36px is as close as the stick gets.
- Bailing out when the damped push falls under that floor is WORSE (it stopped
  at 84-116px). Use the minimum push and let the divergence check catch
  overshoot.

**Where it does NOT work:** at `bar_pool_room` the character is against the
wall/stools and strafing does nothing — four corrections left dx at -136, -179,
-156, -158. That is now detected and reported rather than retried.

**`pose.displacement()` is a MIXED statistic, not a pose distance.** It fits an
affine and then discards it, returning the median inlier pixel distance — so
yaw, depth and translation all enter undifferentiated. Measured scale response:
1.10 -> 33px, 1.20 -> 65px, 1.43 -> 104px. Do not read it as translation.

### (k) A note the user made that is still unexplained

*"When you make the turn, you actually walk right out of the bar."* Observed
directly on the stream, first day. **It has now been captured**:
`test_fixtures/leg_failures/overshot_outdoors_1788718155150.jpg` shows the
character on a CITY STREET — a truck, a lamppost, shop signs — at the end of a
leg that should have ended in the bar's pool room, written by the admissible
leg-end path (OPEN-1) during the 2026-09-06 census. What is established is that
a leg into the bar can end outdoors and off the mapped route. Whether it is the
same event the user saw, and the mechanism, are NOT established: the 90-degree
compass flip that would explain it cannot be produced offline at 1920x1080 (the
compass correction below §10), and OPEN-3's closure removed the other candidate.
Still unexplained; no longer uncaptured.

---

## at_table() WAS FIRING WITH NO PROMPT ON SCREEN (fixed 2026-09-05)

`table_prompt.MATCH_MIN` was **0.15**, which sits BELOW the highest measured
negative. Measured over all 3262 archived demo frames:

    score < 0.15    1817 frames   the bulk of the route
    0.15 - 0.25       52 frames   INCLUDES A CONFIRMED FALSE POSITIVE
    0.25 - 0.40      366 frames   genuine prompts start here
    0.40 - 0.60       28 frames   trough
    0.60 +           924 frames   clear prompts

The negative anchor was eyeballed and then confirmed by the user:
`demos/walk2_pauses_20260828_044514/f_0049.22.jpg` scores 0.1757 with the QUEST
LOG open — its text supplies both the ink and the stroke correlation — and the
player is not close enough for the game to offer the prompt at all. The positive
anchor, `demos/spawn_to_table_20260827_212516/f_0054.32.jpg` at 0.3503, shows
"Baseball Cards [] Play ($50)" plainly. **MATCH_MIN = 0.25** sits between them.

**WHY THIS MATTERS BEYOND ONE DETECTOR.** `at_table()` is the authority for
"arrived at the dealer table" — §7 says `dealer_table` is a POSE and must never
be confirmed by `identify()` — AND it gates the Square press that spends $50. So
a false positive both records an arrival that did not happen and can commit
money at nothing.

**Treat any arrival figure measured THROUGH at_table() before 2026-09-05 as
possibly inflated.** The route streak numbers in §8 are not affected (they score
`portrait_room -> bar_pool_room -> bar_jukebox`, none of which uses at_table),
but anything quoting arrival at `dealer_table` is.

Note `INK_MIN` cannot save this: the false-positive frame scores ink 0.027,
comfortably above the 0.024 gate. The score is doing the discrimination.
Pinned by `tests/routing/test_at_table_threshold.py` against both real frames.

**AND THE INK GATE IS GONE FROM THE VERDICT (2026-09-07).** It had never rejected
a negative the correlation did not already reject — every negative on disk tops
out at 0.176 against `MATCH_MIN` 0.25, Wanda's prompt (its stated purpose)
scores 0.10 — and it rejected 21 route frames with the prompt plainly on screen
(all 21 adjudicated by eye), the recorded arm's own arrival in the goal-leg A/B
(score 0.311, ink 0.006) and all five readings at the prompt zone's edge
(0.31-0.47, ink 0.011). `at_table()` is now correlation OR OCR after the
contrast guard; `ink()` stays as the aim sweep's ordering signal.
`tests/routing/test_at_table_ocr_path.py` carries a fixture only the correlation
can accept and Wanda pinned rejected; three mutants caught.

## at_table() ALSO MISSES THE PROMPT IN A DARK CAPTURE, AND A BRIGHTNESS-NORMALISED RETRY FIRED ON A STREET (2026-09-08)

The closed loop stood at the prompt for three iterations (frame mean 75/255,
`test_fixtures/table_prompt_cases/prompt_dark_ab4_t10_it062.jpg`) reading
False; a 1.2x gain read True. A retry on a copy scaled toward mean 90 (cap
1.5x) measured 21/21 arrival frames against 18/21 raw and 0 false positives on
500 route frames, shipped, and on its twelfth live trial "arrived" at k=58 —
the office doorway facing the L&B storefront, mean 54, normalised score 0.258
against MATCH_MIN 0.25. Re-measured on 36 prompt frames and 701 route frames:
the normalised scores of the prompts the raw mask misses are 0.25-0.30 and the
normalised negatives reach 0.258 — one population (§10.4). Reverted the same
minute. **The lesson is the census size: a 500-frame sample said 0; the frame
that fired was the 701st.** `at_table()` is the $50 gate; a change to it is
measured on EVERY route frame on disk, and a false positive anywhere is a
veto. The dark miss stays open.

## at_table() CANNOT SEE THE PROMPT OVER THE LIGHT TABLE TOP, and a local-contrast mask does not fix it (2026-09-07)

Goal-leg A/B trial 1 stood AT the dealer's table, camera pitched down onto the
table top after walking into it, with "Baseball Cards [] Play ($50)" plainly on
screen inside `TEXT_BOX` — and `at_table()` scored it **-0.001, ink 0.0001**
(`test_fixtures/table_prompt_cases/prompt_on_bright_table_goalleg_t1.jpg`). The
stroke mask keeps a pixel only if it is > `STROKE_BRIGHT` (175) AND its 11x11
neighbourhood averages < `STROKE_LOCAL` (140): white text over a light surface
is invisible to it by construction. That rule exists to remove the dealer's
white face, and it works; this is its cost.

**A local-contrast rule (pixel minus neighbourhood mean above a delta) is NOT
the fix — measured over 3,937 frames, `tools/prompt_mask_ab.py` ->
`overnight/census/prompt_mask_ab.json`:**

    variant   bright-table   old positives   NEG_NODES     route frames
              score          still True      false pos     newly True
    shipped     -0.002        1288/1288        0/671          0
    delta20      0.190        1203/1288       15/671         31
    delta30      0.119        1147/1288        0/671         32
    delta40      0.092        1117/1288        0/671         31
    delta60      0.044        1280/1288        0/671         23

The bright-table frame never clears `MATCH_MIN` 0.25 under any delta, while
every delta loses old positives and admits new ones: a wider mask takes wood
grain and card edges as strokes and the letter correlation drowns. No constant
is invented from this. **OCR of the band IS supported by the numbers, as a SECOND path after the
mask** (`tools/prompt_ocr_ab.py` -> `overnight/census/prompt_ocr_ab.json`, 4,002
frames; PSM 6 at 3x, both polarities, fuzzy match on baseball/cards/play,
two words required):

    false positives on 693 frames at non-table nodes      0
    the quest-log false-positive anchor                   0 words
    recall alone on the 1289 frames the mask accepts    341   (scale-sensitive)
    route frames the mask REJECTS that OCR reads         26   all dealer_circle,
                                                              prompt over the
                                                              dealer's white body
    table-leg end frames (43) with a hidden prompt        1   the bright-table one

Recall alone is poor, so it never replaces the mask: `at_table()` stays mask
first, OCR only when the mask says no. Two fixtures carry the two bright
backgrounds (`test_fixtures/table_prompt_cases/`). The patch and its test wait
in `drafts/pending_after_ab/` until no live run imports `table_prompt`.

Why this matters beyond one frame: `at_table()` is the arrival authority AND
the $50 gate, and OPEN-14's "ink up to 0.042 without the score gate" sweeps
were reading exactly this. Every arrival rate measured through it — including
the goal-leg A/B running today — is deflated by an unknown amount on the
pitched-down-at-the-table pose.

## Three more guards that could not fire (all fixed 2026-09-05)

- **`report_misfire` invalidated the cursor on 1 of 5 paths.** The call sat at
  the bottom, on the backoff-APPLIED branch, so four early returns skipped it —
  including `_backoff_abandoned`, which LATCHES and then never invalidates again
  for the life of the process. Demonstrated selecting card 0 when asked for card
  1. Its own comment says the invalidation is about the MISFIRE ("a keystroke may
  have been swallowed"), not the backoff, which is why it belongs at the top.
  The existing test passed throughout because it looped exactly
  `MISFIRES_BEFORE_BACKOFF` times — the one path that did invalidate.

- **`run_cycles` could never start a cycle.** `BUDGET_RESERVE = 120` against
  `api_budget.DEFAULT_BUDGET = 60`, so with `BASEBALL_API_BUDGET` unset the loop
  took its "stopping before cycle 1" branch every time: a plausible budget
  message and ZERO matches, forever. Now a loud error. Deliberately NOT fixed by
  raising DEFAULT_BUDGET — that constant caps REAL money.

- **`keep_awake` is DELETED (2026-09-05).** It existed to stop the PS5 sleeping,
  and its `NUDGE_MAG` sat exactly ON `turn_curve.DEAD_BELOW` rather than above
  it, so the nudge it advertised as ~7 degrees was 0.41 — a guard against a
  failure that has already cost a measurement, itself unable to fire. That was
  fixed; the module was deleted anyway, for a better reason.

  A run DRIVES the console, so it cannot sleep during one. The only gap
  keep_awake covered was idle time between runs — and nothing ever launched it
  (grep found it only in its own file and its two tests, and no log anywhere
  contains its output, so it had never run). Meanwhile its `BUSY_PATTERNS`
  stand-down list named 7 script names and matched NO A/B harness: `run_trial`
  spawns trials as `<venv>/python <abspath> --one-trial <arm>`. Every 240s it
  would have sent `clear`, which `injectinput.cpp` zeroes `left_x`/`left_y` on,
  while `slow_traverse` holds the stick untimed and sleeps out the full
  duration — **the leg walks short, and no log distinguishes that from a routing
  failure.** A module that could not help, in a way that could silently corrupt
  the run it was protecting.

  The lesson that survives it: a guard whose trigger is a hand-kept list of
  NAMES rots silently, because nothing fails when a new name is missing.

## A RESET IS THE MONEY RECONCILER, AND IT IS THE ONLY ONE (verified live 2026-09-13)

The user's point, and it closes a question the QA sweep left open. There is no
debit-undo anywhere in `orchestrator.py` -- `grep -nE "balance \+=|refund"` returns
one prose comment -- so a $50 debited for a press the wallet was too poor to accept
is never given back, and the tracked figure drifts below the game's forever.

**It does not need one.** `Load Last Save` restores the wallet to **$246**, and
`reset_env.reset_environment(progress_file=...)` clears `match_in_progress` on a
CONFIRMED reset. So one action repairs BOTH halves of the drift, and the repair is
free. What it does NOT do is set the tracked balance -- that is still by hand, because
the wallet is not read from the game.

    reset_env.reset_environment(progress_file="progress_testing.json")   # wallet -> 246,
                                                                         # flag cleared
    orchestrator.save_progress(w, l, d, 246, "progress_testing.json", ...)  # record -> 246

**Walked end to end on the live rig, and every step is worth recording:**

- The PS5 had auto-slept. `streaming()` returned **False** on chiaki's own host list
  (`State: standby`) -- OPEN-18's fix doing exactly its job on the one screen that used
  to make it answer True in 0.0s on a sleeping console. `ensure_live()` woke it in 8 s.
- **The pause menu was found OPEN**, left that way by an earlier `read_balance_from_
  pause_menu` whose paid call raised before reaching the close. That is the live form
  of the bug fixed hours earlier by moving the close into a `finally`; the evidence
  arrived after the fix, not before.
- `pause_menu.read_money` read **196**, then **246** after the reload -- its first ever
  use on the production path, correct both times, no paid call. The frame scored
  `page_fraction` **0.9401**, inside the PAUSE band 0.9263..0.9446 and well clear of the
  ban book's 0.8587 maximum: the census that found the ban-screen false positive is
  confirmed from the other side.
- **The local reader needs RETRIES right after a reload.** The settle gate reported the
  regions still moving at 6.0 s, `read_money` correctly refused (its two OCR scales
  disagreed), and a single-shot read then fell through to the paid call and raised. The
  reader was right; asking once was wrong. `MONEY_READ_TRIES = 5`, the same lesson
  `_verify_bans` already carries for the ban counter. More tries can only turn a
  refusal into an answer -- every attempt is the same conservative reader -- so this
  invents no confidence.
- The reset landed at spawn bearing **87 (E)**, reproducing section 8(d) exactly.

## A STALE match_in_progress SPENDS AN UNTRACKED $50

Reproduced 2026-09-04. When the flag is stale and a real dealer prompt is on
screen, orchestrator's recovery path presses `start_match` believing the $50 was
already paid: the money leaves the in-game wallet, `balance` is never debited,
`save_progress` is never called, and **`max_spend` cannot stop it** —
`run_one_match.py`'s promise that "no new money is ever spent, whatever the
tracked balance says" does not hold in that state.

**AND PREFLIGHT'S GUARD AGAINST IT COULD NOT FIRE THE WAY PREFLIGHT IS RUN (2026-09-13).**
The check read `sys.argv[1]` and defaulted to `progress.json`. This project keeps TWO
progress files ON PURPOSE (see section 2), so the guard only fired if you named the right
one. Demonstrated on one tree at one moment:

    python3 preflight.py                          ->  READY
    python3 preflight.py progress_testing.json    ->  FAIL, match in progress

`orchestrator.open_match_files(here)` now reports EVERY `progress*.json` claiming an open
match, because which file a later run will pass is not knowable in advance. Corrupt JSON is
SKIPPED rather than counted as a claim -- unreadable is not "a match is open", and treating
it as one blocks a run for the wrong reason.

**And the stale state was the NORMAL one.** 25 call sites reload the save; only
`run_cycles` repaired the record. Every navigation run left the flag armed.

Fixed at the source: `reset_env.reset_environment(progress_file=...)` clears
`match_in_progress`/`bans_done_this_match` on a CONFIRMED successful reset. That
is the one moment clearing is safe, and it satisfies CLAUDE.md's own "check the
screen first" rule — the reset IS the screen check. Money fields are never
touched. `preflight` also escalated from `warn` to `bad`, so a run cannot start
in the dangerous state.

## THE JUKEBOX LEG WAS 4.3x TOO SHORT TO REACH ITS DESTINATION (found 2026-09-05)

The largest single defect found on this project, and it invalidates several
things recorded here as settled.

`bar_pool_room -> bar_jukebox` was re-recorded 2026-09-04 as ONE 0.80s step at
speed 0.30 = **0.240 walk-units**. The human recording this map was built from
covers that span in **1.032 units over 3.32s** — `route3_steps.json` steps 27-31,
bearings 2.08 / 1.16 / 0.76 / 359.43 / 359.61, i.e. due north, matching the
leg's own 2.1. A SECOND independent recording (route2) gives **1.086**, agreeing
to 5%.

Distance recorded against distance needed, per leg:

    office_corridor -> office_door     0.98
    office_door     -> portrait_room   0.96
    portrait_room   -> bar_pool_room   0.95
    bar_pool_room   -> bar_jukebox     0.22   <<<
    bar_jukebox     -> dealer_table    0.91

From the FAR EDGE of `bar_pool_room`'s recognition basin the short leg lands
**0.703 units short** of the near edge of `bar_jukebox`'s basin. It could not
reach its destination from anywhere in its origin's basin. The original 3.30s
leg landed dead centre.

**Why it was never caught.** The search that produced it
(`overnight/phase1_step4_rerecord.py`) only offered `DURS = [0.8, 1.3]`, so the
correct ~3.3s was never a candidate. It then reported 2/2 arrivals — from a
basin its own landing point misses, which means those arrivals came from the
recovery fan, not the leg.

**RESTORED 2026-09-05** to the recorded five steps. Pinned by
`tests/routing/test_leg_distances_match_recording.py`. **It pins the JUKEBOX
leg specifically**, against its recorded 1.031 units within 15%, plus a floor
that no leg is implausibly short. It does NOT yet check the other four legs
against their recordings — doing that needs each leg's step-index span in
`route3_steps.json` established first, and until it is, this test would not
catch the same defect on a different leg.

### What this invalidates

- **GRAVEYARD's "the re-recorded leg changed NOTHING" row.** It reads 4/8 -> 4/8
  as "leg parameters do not matter". The arithmetic says the new leg CANNOT have
  produced those arrivals, so the A/B was not measuring the leg. Corrected there.
- **Any conclusion about this leg drawn between 2026-09-04 and 2026-09-05**,
  including the per-leg arrival rate of 6/15 and the failure-class census.
- It is a strong candidate for what has been costing the route. Whether it moves
  arrival is UNMEASURED — see OPEN-14.

## THE STEP FIELD `cam` IS WRITTEN BY build_route AND READ BY NOTHING

`bearing` in every recorded step is a WORLD TRAVEL DIRECTION = camera heading +
left-stick angle. `cam` is the camera heading the human actually held. Two
consequences, both live:

**`approach_goal` aims 10.6 degrees off the leg's own direction.** It takes
`steps[-1]["bearing"]` and discards the other seven. On the final leg the human
never turned — `cam` is 86.73-87.01 across all eight steps — and steered entirely
by strafing, so `bearing` swings 71.99 -> 97.63 -> 75.46. The last step's 75.46
is 10.61 off the leg's net direction and 11.31 off the heading the prompt was
recorded at. CLAUDE.md's own "ink 0.0214 at the leg's heading and 0.0395 twenty
degrees away" is at least partly this: we aim 11 degrees off the recorded
viewing heading, and `face_the_table`'s sweep pays to recover it every time.

**IT ALSO UNDERCUTS OPEN-3's PREMISE.** On `portrait_room -> bar_pool_room`,
`cam` is 281.09-281.22 — constant to 0.13 degrees — while `bearing` spans 6.59.
So the "recorded curve" that motivates `LEG_TURN_TOLERANCE` is, on that leg,
entirely LEFT-STICK WOBBLE. The human's camera did not move at all. Tightening
the turn tolerance would make the executor chase a curve that was never a curve.
**Re-derive OPEN-3's premise from `cam` before spending console time on it.**

## The map's COORDINATES and TRAIL still describe the old leg

`worldmap.connect()` writes `links` only; nothing re-integrates `landmarks` or
`trail`. Integrating the steps reproduces the stored coordinates exactly for the
first three nodes and then diverges by 0.79 at `bar_jukebox` and `dealer_table`.
`trail` still holds the original 40 steps.

Navigational impact today is NIL — `bearing_to()` is called only from tests. The
cost is that the coordinates are the only human-readable geometry in the file,
and they contradicted the steps by 4.3x, which is exactly how the short leg
stayed invisible. `world_map_backup_20260904.json` is byte-identical to the
post-change file, so the pre-re-record leg survived only in `route3_steps.json`.

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

## §10 Methodology learned the hard way

**1. The commonest bug here: the code did nothing, and doing nothing looked
exactly like working.** Every bug found on 2026-09-01 had this shape; each fix
was two or three lines and finding them took a day. Before theorising about a
failure, ask what would be in the log if this step had never run at all — and if
the answer is "the same thing", fix the silence first.

The catalogue, as a pattern to recognise:

- a logger passed as `lambda m: None` (a conclusion was then drawn from a log
  that could not have contained the evidence)
- an early `return` on a `None` that writes nothing (corrections never ran, all
  run, and logged nothing — indistinguishable from "nothing needed correcting")
- a measurement taken and discarded (`walk_forward` returns how far the view
  moved; both step loops threw it away, so walking into an NPC looked like
  walking)
- a loop bound that cannot be reached (a test spun forever and the suite
  reported pass counts that were meaningless)
- a cached handle nothing revalidates (`chiaki_pid` trusted a dead process;
  every press "succeeded" into nothing)
- a success path and a no-op path with identical output (`_inject_press`
  returned True because the WRITE succeeded — that silently disabled every
  button in the system)
- a slow step and a hung step with identical output (a test "hung" at import;
  it never hung, it took 49.6s and its first `print` sat after all 110 cells)
- **a fix that produces output which looks like evidence and is not** (the
  frame-capture fix: four jpegs, correctly written, of the wrong moment)
- **a measurement that returns the same number everywhere and reads as a
  verdict** (`len(places.keypoints(img))` is 2 — the function returns a
  (keypoints, descriptors) pair — so every point of three prompt-zone runs on
  2026-09-07 was "wedged" at 2 keypoints, the harness backed off every move,
  and rich 1500-keypoint frames were filed as geometry. A count that never
  varies is not a count.)

**2. ONLY AN INTERVENTIONAL A/B COUNTS.** An association does not, however
significant, and neither does a mechanism that makes sense. `STALL_CHANGE` is
the canonical case: observational evidence gave Fisher **p = 0.00039** (runs
whose office leg went clean reached the next node 14/15; runs where the stall
gate fired, 0/5). Intervened on, it measured **6/10 against 8/10, p = 0.63** —
and the point estimate favoured the ORIGINAL value. The low view-change was a
SYMPTOM of an already-bad run, not its cause.

**3. n=3 CANNOT DETECT THE EFFECTS BEING LOOKED FOR HERE.** Power to detect a
full 1.0-depth effect (simulated, sd 0.6):

    n=3   power 0.00      n=6   power 0.72
    n=10  power 0.94      n=16  power 0.99

Every 3-trial A/B on this project has been reading noise, which is why so many
reversed. A permutation test on the "first positive navigation result"
(`[2,1,2]` vs `[2,3,3]`, including 2 full routes against 0) gives **p = 0.298**.
**Minimum for a navigation A/B: 10 trials per arm, interleaved.** A finer metric
does NOT rescue a small n — a per-leg binary outcome was simulated and is WORSE
(power 0.26 at n=10 against 0.94 for depth).

**4. A THRESHOLD MUST SIT BETWEEN TWO MEASURED POPULATIONS, NEVER INSIDE ONE.**
Four bugs of this exact shape in two days: a confirm delta under the noise
floor; `WHITE_LEVEL` under the unselected text; pause-screen brightness (0.927
vs 0.944 — no separation exists); and `STALL_CHANGE` cutting through a unimodal
distribution (values 3.1 to 7.9, one population, so the gate fired on 5 of 20 as
false positives). **Plot the distribution first.**

**5. INTERLEAVE THE ARMS, AND NEVER COMPARE ACROSS SESSIONS.** Route performance
has a large session-to-session component that dwarfs the effects being measured
— the same node measured 3/3 one morning and 4/20 that afternoon with no code
change. Interleaving is what saves a measurement taken under varying load;
blocking the arms would confound the arm with the hour.

**6. WHEN BOTH ARMS DEGRADE TOGETHER, SUSPECT THE ENVIRONMENT.** A change that
affects only one arm cannot move both. A run where every arm got worse at once
turned out to be the console falling asleep — a capture straight afterwards
measured a frame delta of **0.00**. The harness treated CANNOT SEE as DID NOT
ARRIVE. Check the stream is alive before and after every trial and record
`None`, never a failure.

**7. CHANGE ONE THING, THEN MEASURE.** Two route changes in one restart cost the
attribution.

**8. STATE n ALONGSIDE ANY RATE.** A route rate quoted at "~40%" from 5 attempts
was 8% over 24.

**9. MUTATION-TEST ANYTHING LOAD-BEARING.** Break the fix, confirm the test
fails, restore. A phase-repair test passed with the guard removed until the
mutant exposed the hole; a wiring assertion once passed because it matched the
function's own `def` line.

**10. MUTATION TESTING LIES IF THE FILE SIZE DOES NOT CHANGE.** CPython
validates a cached `.pyc` on (mtime, size), so a same-size edit runs STALE
BYTECODE and the mutant never executes. Worse, the same cache then made a CLEAN
file report 8 failures — `-B` stops Python WRITING bytecode but not READING it.
Delete `__pycache__/<module>*.pyc` between mutants. Also: `str.replace(a, b, 1)`
on a pattern that appears twice mutates half the code — **count the occurrences
first**.

**10a. A MUTATION DRIVER'S RESTORE MUST OWN ITSELF, BECAUSE THE THING THAT
KILLS THE DRIVER DOES NOT CARE WHICH LINE IT WAS ON.** 2026-09-07: an inline
driver mutated `places.py:491` in the checkout, and the tool running it hit its
600 s ceiling and killed the child between mutate and restore. `places.py` sat
on disk with `if ratio < MIN_RATIO:  # MUTANT` and the wrong sha for eleven
minutes, discovered only because a process listing showed the driver gone.
Nothing was live to import it — an hour earlier OPEN-5 would have (10.17). The
first driver on Snoopy had the same shape and captured a MUTANT as its
baseline. So: the restore goes in a `finally`; any driver longer than a minute
runs in the background from the start with its output flushed to a file; and
after ANY kill, verify the sha of every file the driver touches before doing
anything else. `git status --porcelain` on a tracked file is the one-line
check.

**11. A TEST MUST NOT ASSERT AGAINST THE CONSTANT IT IS GUARDING.** Checking
`mag_for(x) <= USABLE_MAX` rises with `USABLE_MAX` and passes forever. Pin the
literal.

**12. BEWARE THE VACUOUS STATISTIC.** "68 of 68 turn steps had |want - got| <=
4.0, so 100% are no-ops" is CIRCULAR — `turn_to` only returns once the error is
inside tolerance, so that inequality holds BY CONSTRUCTION. It looked
devastating and measured the loop's exit condition. The real version compares
the spread of COMMANDED bearings against the spread of ACHIEVED headings.

**13a. THE "NEVER RUN OFFLINE WORK DURING A LIVE RUN" RULE WAS BROADER THAN ITS
EVIDENCE (measured 2026-09-06).** **And narrower than I then treated it (2026-09-07):**
the measurement below covers THE SUITE. It does not cover a 20-minute OCR or
ORB sweep over 4,000 frames, even under `taskpolicy -b`; the user watched the
stream go sluggish while two of those ran beside the goal-leg A/B and asked for
the run to be paused. Anything CPU-bound that is not the suite waits. The 242ms figure below is real and it is about
FOUR PARALLEL MUTATION SWEEPS at load 273-333. It was then applied to the
ordinary suite, which is a different workload at a thirtieth of the load, and
that cost real serialisation time.

Measured directly, sampling `sleep(0.005)` overrun continuously for the length
of a suite run -- the quantity that matters, because `slow_traverse` holds the
stick and SLEEPS OUT each push, so overrun IS leg distance error:

    idle control                 median 1.21ms   p99 1.35ms   max 2.46ms
    the suite, JOBS=4, normal    median 1.26ms   p99 2.69ms   max 9.73ms   203s
    the suite under taskpolicy -b median 1.26ms  p99 1.35ms   max 7.79ms   636s

30,787 samples during a real suite run at normal priority, and **not one sample
exceeded 50ms**. Against a 0.79s push, the worst overrun is 1.2%. **So the SUITE
may run during a live run.** Mutation sweeps at load 273-333 are NOT covered by
this and stay serialised -- that load was not reproduced here.

`BASEBALL_NICE=1 ./run_tests.sh` puts the suite on the Efficiency cores via
`taskpolicy -b` and makes p99 identical to idle. **It also costs 3.1x wall
clock, and run naively that is a trap**: the slowdown pushed `test_map_admit.py`
(58s normally) and `test_affected_tests.py` past the 300s ceiling, and both were
reported HUNG -- the ceiling censoring the work it had just slowed down, turning
a green suite into two failures. That is 10.14 in a new place. The flag
therefore raises `TEST_TIMEOUT` to 1200s itself, and an explicit
`TEST_TIMEOUT` still wins.

**13. MUTATION TESTING IS EXPENSIVE ON THIS MACHINE.** Four parallel sweeps drove
the load average to 273-333 and the suite to ~2 files per FOUR MINUTES. The
cause is likely I/O — this is a work machine with Sophos Anti-Virus, and
mutation testing writes a source file thousands of times. **Do not disable it**
(the user has said so). Consequences: **never take live timing measurements
while a sweep runs** — Python's `sleep` degrades from ~5ms to as much as 242ms
under saturation, which corrupts every walked leg. Run heavy offline sweeps and
live console work IN SERIES.

**14. A TIMEOUT MUST NOT CENSOR ONE ARM.** An `attempts` A/B used a 420s ceiling
and 3 of 6 deep-arm trials hit it — the ceiling censored precisely the arm whose
mechanism is "spend longer". Also: `signal.alarm` did NOT interrupt a 590s trial,
because the process was blocked inside a capture call. Enforce timeouts from
outside the process.

**15. KEEP A FRAME.** Cause A got a diagnosis within an hour because it had
numbers; Cause B stayed unexplained for days because nobody kept a picture. One
jpeg per failure settles arguments immediately — but **check what moment it
captures**, because a frame taken after recovery, or before the attempt,
describes something else entirely and looks exactly as authoritative.

**16. A SUBAGENT THAT IS KILLED LOSES EVERYTHING IT HAS NOT WRITTEN DOWN.**
On 2026-09-05 four parallel workflows hit a usage limit mid-flight and 18 agents
were killed. One had spent 179 tool calls and twelve minutes reading archived
frames; it returned nothing, and the transcript holds its tool calls but not its
conclusion. Re-running costs the same tokens again.

So any prompt that dispatches a subagent must tell it to write to
`agent_progress/<label>/progress.md` **as it goes** — every few tool calls, not
at the end. A file written on completion is lost in exactly the case it exists
for. **This is the DISPATCHER's job**: the agent has no way to know the
convention, so an instruction missing from the prompt means no notes get written
at all.

A DIRECTORY per agent, not a single file, because the script that produced a
number belongs next to the number — and CLAUDE.md forbids findings in `/tmp`,
which on this machine was once found as 825 empty directories with every file
gone. Scripts, extracted data and plots go in the same directory as the notes.

The file separates **Established** (verified, with the command or file that
verified it) from **Assumed** (working from, not checked). A half-finished
analysis restored later reads exactly as authoritative as a finished one, and
this project has lost days to output that looked like evidence and was not — so
anything under Assumed is re-verified before it is built on.

`agent_progress/` is gitignored and safe to delete wholesale; its README carries
the template.

**Model selection is the dispatcher's job too.** Any sub-agent dispatched for
routine scouting, log parsing, static reading or coverage checking runs on a
cheap, lightweight model (Haiku). Flagship models are reserved for complex
architectural reasoning, and only when a cheaper model demonstrably cannot do
the step. Measured 2026-09-07: four flagship agents drafting scripts burned
~850k tokens in five minutes, two of them on ideas the same day's A/B data had
already killed; the static QA audit on Haiku, ten agents, cost 1.16M for an
evening's findings. Token bleed is a failure of the DISPATCH, not of the agent.

**16a. A SUB-AGENT'S SCRATCH TREE IS A COPY, NEVER A SYMLINK FARM, AND NEVER
INSIDE THE CHECKOUT.** 2026-09-07 22:47: a skeptic building a "scratch copy
with symlinks to the rest of the checkout" ran its `ln -s` loop with the
CHECKOUT as the destination, and 65 tracked test files under `tests/routing/`
became symlinks pointing at their own absolute path. Nothing failed for half
an hour: the one test file it copied was real, its runs were green, and the
damage surfaced only when the pre-commit hook hit "Too many levels of
symbolic links". `git status --porcelain | grep '^ T'` lists the casualties
and `git checkout --` restores tracked ones; an UNTRACKED file replaced this
way is gone. Every dispatch prompt says: build scratch trees with `cp`, under
the scratchpad, and never run `ln` with a path inside the checkout. After any
sub-agent finishes, `find . -type l` outside the venvs and `git status` for
`T` entries, before trusting anything.

**17. THE A/B RUNNER RE-IMPORTS `graph_walk.py` FROM DISK ON EVERY TRIAL, SO A
MUTANT ON DISK FOR ONE SECOND IS THE CODE A LIVE TRIAL RUNS.** `_harness.run_trial`
spawns `python <script> --one-trial <arm>` per trial — that is the design, so
process death is the restore and no cleanup can reinstate a stale default. The
cost of that design is the other direction: every child starts cold and loads
whatever `graph_walk.py`, `places.py` or `slow_traverse.py` is on disk at that
moment. Mutation-test a guard in the checkout while OPEN-5 is walking legs, and
the next trial walks with the guard removed, arrives or does not, and is scored
as an arm result. No error, no log line, nothing to distinguish it from the
arm.

Found on 2026-09-07 by reasoning, before it happened: a QA workflow was about
to mutate `graph_walk.py` in place while `overnight/ab_attempts.py` had the
console. Stopped. The first replacement used a git worktree, which is isolated
from the import but shares the disk, and §10.13's I/O hazard is the disk — so
that was stopped too. **The rule: while `console_lock` is held, the checkout is
read-only, and mutation testing goes to Snoopy (`Snoopy_testing.md`).**
Static analysis — reading, grepping, `ast.parse` on source text with
`python -B` — is fine; it writes nothing.
**18. A DEFAULT ARGUMENT IS BOUND ONCE, WHEN THE `def` RUNS, AND THAT BREAKS
A/B ISOLATION SILENTLY.** `leg_reliability` declared every public function as
`def rate(a, b, path=STORE)`. `STORE` is a string, captured at import — so
`leg_reliability.STORE = "arm_A.json"`, the natural way for an A/B harness or a
test to give one arm its own record, changed NOTHING: every call still read and
wrote the import-time file, and nothing said so. With `SPEED_FROM_RELIABILITY`
on, an interleaved A/B would have had both arms writing one store, trial N's
speed a function of trials 1..N-1 across both arms, and the harness reporting a
clean redirect. `press(post_delay=ACTION_DELAY)` is the same trap, which is why
that parameter takes `None` (§5). Fixed 2026-09-07: `path=None`, resolved at
call time through `_store()`, pinned by `tests/routing/test_leg_reliability.py`
with a check that fails on the bound default. **The rule: a module-level knob a
test or harness may redirect is read at CALL time, never captured in a
default.** Grep for `=STORE)`, `=PATH)`, `=DELAY)` shapes before trusting any
redirect.

**19. SAVE PATCH SCRIPTS BEFORE EXECUTING THEM, AND ASSERT EVERY ANCHOR BEFORE
WRITING ANY FILE.** 2026-09-07 22:00: a two-file patch script asserted and wrote
`overnight/chain_trials.py`, then failed an anchor assert on `tools/dashboard.py`
— with the harness file already on disk, mid-batch, and the next trial child
died on it (rule 21 broken by a script that was half right). One assert block
for all files, then all writes. **19. SAVE PATCH SCRIPTS BEFORE EXECUTING THEM.** When an agent writes a script
to parse, slice or patch a critical project file — this file, the map, a
harness — it saves the script to disk first (the scratchpad is fine) and gates
the atomic write behind strict assertions on every anchor it will touch. If an
assertion fires, the logic is preserved and the retry is a one-line fix, not a
300-line re-send; if the write is reached, every seam has already been checked.
2026-09-07: the eight-edit patch to this file was written inline, its GRAVEYARD
assert was off by one, and the whole script had to be re-sent to fix one
integer. Saved, the retry would have cost nothing. The assertion that fired
BEFORE the write is the pattern; the re-send is the cost of not saving.

**20. PRE-SLEEP HANDOFF INTEGRITY.** Before an agent enters an unattended
overnight or long-running background state, it updates and COMMITS the current
state and the execution plan to `HANDOFF_NOW.md` — what is running, where its
artefacts land, what happens next and in what order, and the rules in force. If
a process drops or hits a ceiling mid-night, the morning session must find the
exact active plan and state immediately, without relying on chat history. A
plan that lives only in the conversation is lost in precisely the case the
handoff exists for (the same shape as 10.16, one level up).

**21. SEQUENCING OVERRIDE FOR IN-FLIGHT RUNS.** Never refactor, edit or modify
a module on disk while an active process or live console test is importing it
fresh — a harness's trial children re-import `graph_walk.py`, `_harness.py` and
their neighbours on every trial (10.17 is the concrete instance). Background
refactoring, dependency audits and automated QA passes are strictly SERIALISED
behind the live run: held in queue until every live console trial has completed
AND its evidence is committed. Read-only work may proceed; anything that writes
into the import path waits. "It is a small edit" is not an exception — the
child does not know how small it was.

**22. A MATCHING COUNT IS NOT CORRESPONDENCE, AND SCORING ON IT MANUFACTURES A
CLEAN RESULT OUT OF TWO ERRORS.** 2026-09-09: the local hand reader's accuracy
was scored by lining its rows up with the paid model's cards BY POSITION on
every hand where the two counts matched. The reader can miss one card and
invent another in the same hand — the count still matches, and every column
after the first error is compared against the WRONG card. The table that came
out looked like a finding: 4 read at 90%, 5 at 88%, but 6 at 31%, 7 at 33% and
9 at 0%, tracking template counts so neatly that the diagnosis wrote itself.
It was an artefact. A contact sheet of the "missed 6s and 7s" showed FIELDING
PLAY cards.

Re-scored with correspondence PROVEN — the counts match AND the set of slots
each side calls tactics matches — only **10 of 57 hands could be compared at
all**. The real defect was never the templates; it was that the reader did not
agree with the model about POSITIONS on 47 of 57 hands.

It also corrupts what is built on it: 79 templates were cut using that
alignment, and six were wrong — three labelled one card off (a 6 labelled 7, a
5 labelled 6, a 4 labelled 7) and three that are not digits. Each matched its
own source crop at correlation 1.0000, so it read that crop wrong forever
after, confidently, at score 1.000.

And it hides itself in the metric: the old reader scored **41 of 41 = 100%** on
its 10 aligned hands, and two of those hands were two errors cancelling — a
mouse's nostril padded the count and read "5" where the missing card's power
was 5. **A pipeline whose own output defines the alignment cannot be scored on
that alignment.** Require an independent agreement — here, the kind pattern —
and report how many samples were excluded, never just the rate.


**23. A READER THAT CROPS AT A FIXED ANCHOR IS READING THE WRONG PIXELS THE MOMENT
THE THING MOVES -- AND IT REPORTS THAT AS "I AM NOT SURE".** 2026-09-09: two
readers, built months apart, were held at 0% and 40% by the same defect, and in
both cases the abstention rate read as "the recogniser is weak" when the
recogniser was never shown the object.

    reader          what it cropped at        coverage before -> after
    the shield      a fixed offset below      0%    -> 98.4%   cross-session
                    the power disc
    tactics type    the SLOT anchor, in a     40.5% -> 93.6%   cross-session
                    180px-wide box

The shield's offset varies because **the cursor lifts a card and the badge rides
with it**, so a window measured on unlifted cards found the badge on 8% of one
digit. The tactics banner's box was wide enough to reach past the card and take
in the NEIGHBOUR's banner, so the correlation was matching two cards at once and
collapsed whenever the neighbour differed.

**THE FIX IS THE SAME ONE THAT RESCUED THE RUNNERS READER: SEARCH FOR THE ASSET.**
These are sprites -- one badge, one banner, identical every time -- so
`cv2.matchTemplate` over a generous window answers "is it there" and "which one"
at once, with no assumption about where it sits. The gate then sits between two
measured populations: the shield's peak correlation is p05 0.843 on shielded
cards against p99 0.541 on unshielded, an empty band, and SHIELD_MIN is its
midpoint.

**HOW TO RECOGNISE IT WITHOUT GUESSING.** Build a contact sheet of the cards the
reader called unsure and LOOK. The tactics one was settled in a single glance:
the banner text was PLAINLY LEGIBLE in nearly every "unsure" card, sitting off to
one side with a stranger's banner beside it. A recogniser that cannot read
legible text is not failing to recognise; it is being handed the wrong crop.
Section 10.15 in a new place -- and the cheapest diagnostic on this project.

**AND MEASURE THE OFFSET FROM WHAT WAS FOUND, NOT FROM THE ANCHOR.** The first
shield measurement put dy at 48-68px with a 20px spread and looked like a fixed
asset; it was measured against the SLOT anchor, so it was reporting the cursor
lift as if it were sprite variance. `read_hand` rows now carry the found `y`
alongside `x` for exactly this reason.

**THE PAID MODEL IS NOT GROUND TRUTH HERE, AND THE CONTROL SAYS SO.** Nine of the
ten remaining shield disagreements are cards with NO BADGE AT ALL that the paid
model gave a number to. The mechanism is measured, not asserted: on the 684 cards
where the badge IS found, the claimed `secondary` equals the card's own POWER
**0 times**; on the 20 where it is not, **5 times**. It is reading the card frame.
That is the sixth independent way this model has been shown wrong (three 6s as
5s, discards 0/8, a Fielding Play bonus, four phase labels, a runner's name).

**A TEST FOR THIS DOES NOT BITE BY DEFAULT.** Removing the tactics recentring left
every check in its test file green, because the fixtures all sat near their
anchors. It needed fixtures chosen for how far OFF the anchor they sit -- 43px in
y, 63px in x -- and the "the anchor alone cannot read it" half scored at the
anchor DIRECTLY, because the reader's own fallback tries both anchors and would
have masked it.


**30. A TEMPLATE MUST BE KEPT AT ITS NATIVE SIZE AND NEVER AVERAGED ACROSS EXAMPLES.**
2026-09-10, building the RESULT screen reader -- the last field with no local answer, and
the one paid call left in the turn loop. Three attempts, and the first two produced
populations that OVERLAPPED:

    what was cut / how it was scored                 result frames   non-result MAX
    the union of every bright blob in a wide band      0.497-0.547        0.603
    the word, STRETCHED to one size, banks AVERAGED    0.370-0.441        0.428
    the word, at NATIVE size, one template per example 0.955-0.988        0.733

The first is 10.23 in a new place: the union swallowed the matchbox labels along the top
edge, so two thirds of the "template" was scenery. The second is the new lesson and it
has two halves, both of which read as tidiness:

  * **STRETCHING destroys the discrimination.** WINNER is wider than LOSER; resizing both
    to one box made them the same shape, and after `TM_CCOEFF_NORMED` normalises away
    brightness there was almost nothing left to tell apart. Every WINNER frame matched the
    LOSER bank. It also means the template no longer has the size of the thing on screen,
    so the search is looking for something that is not there.
  * **AVERAGING blurs two different things into one.** The banner's arch FLATTENS as it
    animates in: the same word measures 102x22 in one frame and 95x14 in another. Averaged,
    neither is matched. Keeping each example as its own template costs nothing -- the score
    is the max over the bank -- and is what took the reader from 0.44 to 0.98.

**AND SCORE IT ACROSS SESSIONS, BECAUSE A TEMPLATE MATCHES ITS OWN SOURCE AT 1.000.** The
native-size version's first table read "result frames 1.000, non-result max 0.495, EMPTY
band" -- and every one of those 1.000s was a frame that had supplied a template (10.22's
shape). The real measurement came from 31 result screens found in OTHER runs' `stream.mp4`
recordings, at 960x540 and 1920x1080: 0.955-0.988, both classes, adjudicated by eye.

**THE CENSUS SIZE IS THE at_table LESSON AGAIN, AND THIS TIME IT PAID.** A 16,381-frame
still census put the non-result maximum at 0.543. Sweeping every 20th frame of all 17
archived run videos -- 55,937 more frames -- raised it to **0.733**, against a gate of 0.75.
The four highest were extracted and LOOKED AT: all four are result screens caught HALF
FADED, on the way in or out. So they are not false positives, they are the reader
abstaining during the fade, and that costs nothing because the banner then sits fully
opaque for a measured 4.0 s at its shortest (25 sightings, median 7.0 s). Zero false
positives in 72,318 frames. **Had the four not been looked at, the honest reading of the
same numbers would have been "the gate has 0.017 of headroom" and the reader would have
been rebuilt for nothing.**

`local_state.read_result(full_frame)`; `tests/minigame/test_result_reader.py` (7 mutants,
all caught). It takes the WHOLE frame -- handed a crop, the scaled templates collapsed to
4x4 and `matchTemplate` returned a number anyway (10.1's "a success path and a no-op path
with identical output"), so there is now a floor on the input width.

**31. A CLASSIFIER WITH A MISSING CLASS DOES NOT ABSTAIN -- IT MANUFACTURES NEGATIVES, AND
THEY POISON THE CENSUS THAT WOULD HAVE CAUGHT IT.** 2026-09-10, the same reader, hours later.

The result reader shipped knowing WINNER and LOSER. There is also a **DRAW!**, and 5 of the
52 matches on record are draws. The reader called every draw "not a result screen" at
0.42-0.49, `local_game_state` fell through to the hand reader, and the loop reported
`hand: 0 rows, expected 5` about a screen with no hand on it.

**THE SELF-CONCEALING PART.** The census that was supposed to catch this listed its top four
"non-result" frames by score. **Two of them were draws** -- `r2_0092` and `r3_0073`, both
plainly showing DRAW! over the medallion. They ranked highest among the negatives precisely
BECAUSE they were the thing the reader could not name, and being unnameable is what filed
them as negatives. One was even promoted to a test fixture called
`top_negative_turn_768.jpg`. So the missing class inflated its own false-negative rate into
the negative population and reported the gap as healthy headroom. **A census cannot discover
a class its own labeller does not have.** The only thing that broke it was opening the frames
a stalled run was staring at.

**IT ALSO HID A SECOND FORM OF THE SAME WORDS.** Every shipped template was the SETTLED form
-- a small ARCHED word on a thin bright arc. Mid-animation, before the arch sets, the word is
LARGER and FLAT and scores ~0.50. A visibly-legible LOSER read "not a result screen".

**AND A DRAW IS NOT A LOSS.** `run()` prefers a score comparison over `result_won` for
exactly this reason -- `result_won` is a bool and cannot express a tie. But `ocr_scoreboard`
is not reliable on the RESULT screen: over 76 draw frames it reads both rows on **12**, and
one of those 12 returns `[0,1,5]` against a board plainly showing `1 0 1 / 0 1 1`. A wrong
score is worse than no score, because `run()` acts on it. So the reader supplies NO scores
and names the outcome directly, and `run()` prefers that over both. Mapping draw ->
`result_won=False` would have logged every draw as a loss; that mutant is pinned.

**THE GATE MOVED, AND NOT TO THE MIDPOINT.** With three classes the negative population
reaches **0.742** (seven frames extracted and adjudicated: all of them the world -- the bar,
the dealer prompt, the office door), which left the old 0.75 with 0.008 of headroom. The two
errors are not symmetric: a false positive logs a match that never finished, a false
negative costs one poll because the banner holds 4.0 s at its shortest. `RESULT_MIN = 0.80`
sits 0.058 clear of every adjudicated negative and far under the held-out p05 of 0.954. It
costs exactly one of 342 held-out frames -- a half-transparent DRAW! ghosting in.

**A TEMPLATE CUT "EVENLY ACROSS THE RANGE" GRABS THE FADE.** Spreading the new bank across
the word's area range took 14x39 and 10x36 crops holding a stroke or two. A tiny template
correlates with anything: a turn frame with no banner on it read DRAW at 0.935, and every
negative rose (the quest log 0.543 -> 0.682). Verified words run 82-102 px wide at reference
scale and fragments 36-39, so the floor sits between two measured populations.

**THE SHAPE TO RECOGNISE.** Before trusting any classifier's negative population, ask what
it CANNOT name -- and go and look at its highest-scoring negatives, because that is exactly
where the unnameable class will be sitting.


**24. THE PAID VISION MODEL DOES NOT READ CARDS -- IT ANSWERS WITH A DEFAULT, AND THAT
DEFAULT WAS HIDING EVERY LOCAL NUMBER BEHIND IT.** 2026-09-09, at the user's call:
*"comment out the API reads for all card reading... leaving them in is hiding the real
values and your also wasting my IRL money."* Both halves measured:

- **It never read a card NAME.** Over 2,171 recorded hand cards `name` came back as
  'Batter' (493) or 'Pitcher' (394) -- the TYPE BANNER, the only text on the card --
  plus '' (113), 'None' (274), 'Unknown' (23), and 57 invented names including SIX
  spellings of the same one (M. J. / P.J. / J.J. / M.J. / P. J. / R.J. Gain). Section 3
  has said "hand cards do not display a name" since day one.
- **It answers on frames with nothing on them.** On 32 of 33 crops containing NO CARDS AT
  ALL it returned a full five-card hand with powers and shields; on frames that did
  contain cards, 325 of 327. "Five cards" is a DEFAULT, the same shape as `discards_left`
  answering 2 on 286 of 360 turns.

The second one is why this mattered beyond the bill: those are exactly the frames the
LOCAL reader refuses, so the local reader's "failures" were being scored against
fabrication. `PAID_READS_CARDS = False` in orchestrator; nothing is deleted and the flag
restores it.

**THE ONE FIELD WHERE THE PAID MODEL WAS RIGHT AND THE LOCAL READER WAS WRONG** is `kind`,
and it is worth knowing because it is the exception: the fan decides kind BY POSITION, and
a slot no candidate reached was emitted as `tactics` by default -- wrong on 10 of 17. I
reported the opposite before opening the frames, and the contact sheet corrected me.

---

**25. THE CAPTURE MOMENT, NOT THE READER, IS WHAT IS LEFT -- AND THE RETRIES WERE AN
ACCIDENTAL WAIT MECHANISM.** Measured over 514 recorded turns before changing anything
(`agent_progress/convergence/`):

    reads per turn                      1.44        (1.00 = no retries)
    turns needing no retry              379 (74%)
    FIRST read of a turn                median 11.96 s after the play
    the read that WORKS on a retry      median 17.59 s after the play

Nothing differs between those two except that the deal finished in between. **A quarter of
all turns were spending a paid API call to wait**, which is why the retry rate sat at
1.24-1.52 across every run of the day regardless of what was patched -- none of it touched
the moment.

**A FIXED SLEEP CANNOT FIX IT.** Filmed after the play, the deal STARTS at +1.5 s on one
turn, +5.5 s on another, +6.5 s on a third. What is constant is the SHAPE: a frame-to-frame
delta spike of 30-43 as the cards fly in, then quiet, then readable within half a second.

**AND "WAIT FOR QUIET" IS THE WRONG INSTRUMENT, MEASURED.** A SETTLED HAND reads a delta of
~4.6; an EMPTY TABLE reads ~2.5. The empty table is QUIETER than the hand, so quiet cannot
tell "the cards have landed" from "there are no cards" -- which is the exact mistake being
fixed -- and no threshold on that quantity separates them (10.4). The first version of that
measurement came out with the two populations the wrong way round because "moving" was
mostly the empty table BEFORE the deal, and a constant was nearly shipped off it.

So the gate asks the question that is actually wanted: `local_hand_cards()` returns a hand
only when every card reads, twice running. ~21 ms against a 150 ms poll, and NO constant is
invented anywhere in the rule.

---

**26. A READER THAT LOOKS STABLE ON A STILL PICTURE MAY NOT BE. FILM IT.** The single
cheapest diagnostic found this year. A hand that was NOT MOVING was filmed for 28
consecutive frames: one card read 7 / unread / 7 / unread with the score swinging 0.57 to
0.91. The picture was identical to the eye; the fitted circle alternated between r=19 and
r=20, and `read_digit` resamples to a fixed 24x24, so one pixel of radius rescales the
digit inside the tile. Searching the radius recovered 16 of 24 unread cards over 1,181
real captures, all 16 agreeing with the paid model, and changed 0 of 1,157 answers that
already read.

**A SINGLE FRAME CANNOT SHOW YOU THIS.** Accuracy measured on one frame per hand reports a
coin flip as a property of the frame.

---

**27. THE PAID MODEL'S REPLACEMENT MUST BE MEASURED ON THE MONEY FIELD, NOT ON ACCURACY.**
2026-09-09, a local VLM on Snoopy (Ollama, RTX 3080). On 29 frames hand-labelled off a
contact sheet -- ambiguous frames EXCLUDED rather than guessed, and the count excluded
reported:

    qwen2.5vl:7b, loose prompt    69%   6 frames falsely called match_start_prompt
    qwen2.5vl:7b, strict prompt   79%   1 frame  falsely called match_start_prompt
    qwen3-vl:8b,  strict prompt  100%   0        (5.6 s/frame against 0.2)

`screen == "match_start_prompt"` is the branch that does `balance -= 50`. CLAUDE.md already
records a ROUND 1 overlay read as match_start_prompt, one guard from a second $50
(2026-08-25) -- and qwen2.5vl reproduced that exact failure six times in 29 frames. So the
number that decides a screen reader is its FALSE POSITIVE RATE ON THE MONEY SCREEN, and it
is measured the way `at_table()` is: over every frame on disk, where one false positive
anywhere is a veto. A 29-frame result is enough to DISQUALIFY and never enough to CERTIFY;
the 500-frame sample that said 0 and fired on the 701st is the precedent.

**AND IT IS A LABELLING AID, NOT PART OF THE LADDER.** The user's call the same evening,
after the sweep came back clean: *"for the record, Snoopy was used to help speed you up in
labeling. I wouldn't wire it up in the ladder."* Snoopy is a SECOND MACHINE for offline
work -- labelling corpora, adjudicating frames, running sweeps that would otherwise
saturate this Mac (10.13). It is NOT a runtime dependency of the live loop, and nothing on
the $50 path may come to depend on a model being up on another box. A clean 422-frame
sweep is a reason to trust it for LABELLING, not a reason to wire it into `read_game_state`
-- and `result` still has no local detector, which stays an open gap rather than being
quietly filled by a network call to another computer.


**28. A CARD CAN BE UNREADABLE FROM EVERY FRAME, AND NO INPUT UNCOVERS IT. THE HAND MUST
SURVIVE THAT.** 2026-09-09, live on the console, at the user's prompting.

A hand sat with slot 1's power disc hidden under its neighbour in the fan. Everything was
tried, on the live console, one press at a time:

    move the cursor RIGHT one slot      disc still hidden
    move the cursor ONTO the card       the card RISES above its neighbours -- still hidden
    SELECT the card (cross)             "kind unknown" -> "player, power unread"; still no digit
    four local re-grabs, 0.25 s apart   0 of 15 recovered

The occlusion is STABLE, not an animation, so re-grabbing the same scene four times gets
the same answer four times. That was a fix I shipped without thinking the mechanism
through, and the frames it added are what disproved it the same hour.

**IT IS NOT ONE BAD CARD.** The user's hypothesis, and worth testing because it would have
been a cheap fix. Within one match it looks true -- 15 of 15 refusals were the same card at
slot 1. Across the corpus it is false: 10 refusals spanning 08:17 to 13:34 and many matches
fall at FOUR different slots (1 x5, 2 x2, 4 x2, 3 x1) on visibly different cards, one of
them a named "PEPAN BLACK". So it is an OCCLUSION that can happen to any card, and once it
happens it persists for the whole hand.

**WHAT THAT MEANS FOR THE DESIGN.** ALL-OR-NOTHING WAS TOO STRICT. A hand with four cards
read and one genuinely invisible is still playable -- you simply do not play the invisible
one -- and rejecting the whole hand instead turns an unreadable CARD into an unreadable
STATE, which then costs a paid call per turn. Measured: that mistake took the loop from
1.44 read_game_state calls per turn to 5.00, and then to 8.67.

**AND A WARNING ABOUT PRESSING BUTTONS TO INVESTIGATE.** The sequence above ended with a
"Give up?" dialog on screen, one CROSS away from forfeiting a paid match. Circle answered
NO and the match survived. Investigating a live match with real presses is worth doing --
it is what settled this -- but every press is a real move, and the escape from a wrong one
has to be known BEFORE it is made (section 4: NO = circle, YES = cross).


**29. AN INVESTIGATION THAT LEAVES STATE BEHIND POISONS THE NEXT EXPERIMENT, AND THE
RESULT STILL LOOKS LIKE A FINDING.** 2026-09-09, live, caught by the user watching the
stream.

Probing why a card could not be read, I pressed `select_card` on it. `close_result`
afterwards did NOT deselect -- it opened the "Give up?" dialog, which was answered NO --
so the card stayed SELECTED. Several minutes later `select_and_play(2)` ran to test whether
playing the neighbour would uncover it. `confirm_play` played the card that was ALREADY
committed: the hidden card itself, not its neighbour.

**THE RESULT READ PERFECTLY AS A SUCCESS.** Slot 1 went from unreadable to "5" and the hand
came back COMPLETE, which is exactly what the experiment predicted. It was reported as
"your test worked, the hidden card is a 5". It was a NEW card in that slot.

**THE EVIDENCE WAS IN MY OWN OUTPUT.** Before `[tactics, ?, 4, 4, 5]`, after
`[tactics, 5, 4, 4, 5]` -- slots 2, 3 and 4 UNCHANGED, so the neighbour was never
replaced. One glance at the row I had already printed says which card was played.

**AND IT NEARLY BECAME A SECOND WRONG DIAGNOSIS.** The next step drafted was a cursor-map
sweep to hunt an off-by-one in `select_and_play`, a function whose docstring carries a
Fisher p = 0.0048 for the homing fix it already has. There was no off-by-one. The user
stopped it.

**THE RULES THIS EARNS.** Before any experiment on a live match, ASSERT THE STARTING STATE
rather than assume it -- nothing selected, no dialog up. After any probe that presses a
button, RESTORE what it changed and verify the restore landed; `close_result` is not a
deselect. And when an experiment confirms its own prediction, check the control -- here,
the three slots that should have been untouched.



---

## SAVING A FRAME CAN MAKE THE COMPASS READ 90 DEGREES WRONG (2026-09-05)

`read_bearing`'s docstring promises it "returns None rather than guessing — a
wrong bearing would turn the player to face the wrong way and the walk would end
somewhere arbitrary, which is worse than not turning at all." **It does guess.**

Measured on 120 archived demo frames, 80 of which read on the original. Each was
re-encoded as JPEG and re-read — nothing else changed:

    quality 75   ABSTAINED 5 (6.2%)   WRONG BY >5 deg 2 (2.5%)   errors [90.0, 15.2]
    quality 88   ABSTAINED 1 (1.2%)   WRONG BY >5 deg 3 (3.8%)   errors [90.0, 90.0, 74.9]

Same scene, same code, two encodings, two different CONFIDENT answers. At least
one of each pair is wrong.

**THE ERRORS ARE EXACTLY 90.0, WHICH NAMES THE MECHANISM.** N/E/S/W are 90 apart,
so this is CARDINAL LETTER CONFUSION — one glyph misidentified as another — not
gradual degradation of a good read. That is the single failure two agreeing
letters cannot make, which is why this is direct evidence for the
`REQUIRE_TWO_LETTERS` work in OPEN-15 rather than an argument against its
coverage cost.

**QUALITY 88 PRODUCED MORE WRONG ANSWERS THAN 75.** Non-monotonic, so this is a
chaotic threshold flip and not something a higher quality setting buys safety
from. 88 is what `places.py:185` and `play_now.py:39` save at; 82-88 is the range
used across the project.

### What this costs, in order of how sure it is

- **CERTAIN: §10.15's KEEP A FRAME is unsafe FOR THE COMPASS.** A kept frame can
  answer 90 degrees differently from the live capture it came from, so no compass
  threshold may be tuned or validated on a saved JPEG. The rule stands for
  everything else — a kept frame is what settled the wedge diagnosis the same day
  — but not for this detector.
- **CERTAIN: any bearing pinned in a test from a `.jpg` fixture pins what the
  COMPRESSED frame says.** It is still a valid regression guard on the code; it is
  not evidence about live behaviour.
- **NOT ESTABLISHED, AND THE REASON TO CARE: the live path is also lossy.** The
  stream is H.264 with varying quantization, and chiaki logs
  `StreamConnection reporting corrupt frame(s)` during normal play. Nobody has
  shown this fires live. But the old assumption — that the live path is immune
  because no JPEG is involved — is not available any more, and a wrong bearing
  live is the failure the docstring says is worse than not turning at all.
- **A HYPOTHESIS, EXPLICITLY NOT ESTABLISHED.** §8(k) is the user's unexplained
  observation, *"when you make the turn, you actually walk right out of the
  bar"* — seen on the stream the first day, never captured. A 90-degree bearing
  error is exactly the mechanism that produces it, and nothing else in this file
  explains it. **If `REQUIRE_TWO_LETTERS` lands and §8(k) stops happening, that is
  the strongest signal available.** Do not treat the coincidence as evidence
  before then.

Reproduce: re-encode any frame `read_bearing` reads, at quality 75 and 88, and
compare. No rig, no console, ~2 minutes.

### CORRECTION 2026-09-06 — re-measured twice, and the entry above is wrong in
### four ways. Read them before quoting any number from it.

Two agents reproduced this independently, the second adversarially. The effect
is REAL and the mechanism named above is RIGHT. Everything quantitative is not.

**1. IT WAS MEASURED ON A READER THAT NO LONGER SHIPS.** The numbers above come
from the pre-OPEN-15 `compass.py` (41,144 bytes). On the same worst-case run the
SHIPPED reader gives **5 of 270 at q75 and 0 of 262 at q88** wrong by >5 deg.
The guards landed; this is largely a description of the old reader.

**2. IT UNDER-REPORTS ITS OWN FINDING BY ABOUT 10x.** "2.5%" and "3.8%" come from
a 120-frame subset. Over the whole run that produced them, the OLD reader's rate
is **25.1% and 22.7%**. The entry was too kind to itself.

**3. IT IS A SINGLE-RUN EFFECT, NOT A RESOLUTION EFFECT.** All eight demo runs
are 1400x787, so "demo archive" and "0.73x linear resolution" were perfectly
confounded, and the RUN wins: `demos/walk3_full_20260828_050731`, same geometry,
710 frames, **zero** errors >5 deg at either quality, max 0.89 deg. Every flip
anyone has found is in `demos/walk_20260827_214446`. So "zero at 1920x1080" does
not license "the live geometry is safe" — it says those particular scenes are.

**4. PNG IS LOSSLESS AND CHANGES NOTHING.** 3,154 reads, max delta **0.0000**.
Only JPEG re-encoding perturbs anything. A compass fixture must therefore be a
PNG, and `test_fixtures/compass/bar_doorway_abstains_1920.png` already is — the
bearings derived from it are unaffected by any of this.

**THE ATTRIBUTION IS RIGHT, WITH ONE REFINEMENT.** It is the LETTER-
CORROBORATION family that stops the cardinal flips — `REQUIRE_TWO_LETTERS` **or**
`POOL_THRESHOLDS`, either alone is enough. `USE_TICK_LATTICE` stops a DIFFERENT
failure whose signature is ~32-37 deg: with the lattice on and both letter guards
off, >5 deg goes 5/270 to 34/178 at q75 with a correct cached pitch. A first pass
that credited the lattice was confounded by leaving `POOL_THRESHOLDS` on.

**THE §8(k) HYPOTHESIS LOSES ITS OFFLINE SUPPORT.** No 90-degree error is
producible at 1920x1080 on any frame that actually contains a compass bar, on
either reader. And the bullet above beginning "If `REQUIRE_TWO_LETTERS` lands" is
stale: it ships True. §8(k) is back to having no candidate explanation.

**THE LIVE PATH, CHECKED PROPERLY.** `graph_walk.reference_heading()` (~:1748) is
the ONE production caller that reads a bearing from a SAVED file rather than a
live capture — `places/<node>/route_*.jpg` — and `align_at_node` turns the camera
to that heading before measuring dx, so a wrong read there moves the character.
On the four files that exist, both readers agree to within **0.066 deg** across
original / PNG / q88 / q75. The best available proxy for the live question — 206
`world_log` pairs of a live in-memory read against the q82 JPEG saved from the
same object, all at 1920x1080 — gives max **0.591 deg** and zero disagreements
>5 deg. **No live hazard is demonstrated.** What remains unknown offline is
whether the ORIGINAL capture that produced those JPEGs read the same as the file.

**THE REPRODUCE RECIPE ABOVE NO LONGER WORKS** at HEAD on any corpus except
`demos/walk_20260827_214446`.

---

## Five more guards that could not fire, and one that wrote to the rig (2026-09-06)

All five found by re-verifying claims rather than by a failure. Same shape every
time: something reported clean while the thing it guarded was broken.

**THE OFFLINE SUITE WAS WRITING THE RIG'S CALIBRATION FILES.**
`compass_scale.json` and `view_bounds.json` are read back by LIVE runs — the
scale cache sets degrees-per-pixel on the compass strip, the view cache moves the
view centre and hence every bearing — and both were written unconditionally.
`./run_tests.sh` added a key derived from DEMO ARCHIVE frames at 1400x787, a
geometry no live capture produces, to the file the rig uses. Nothing errored;
nothing ever does when a cache is quietly wrong. Only the WRITE is now suppressed
under `BASEBALL_TEST_RUN` — the in-memory cache fills exactly as it would live,
so tests exercise the same path with the same values. Pinned by
`tests/harness/test_caches_not_written_in_tests.py`, which also refuses a
demo-archive geometry key found in either real file, catching the pollution even
if it arrives by another route. §11's OPEN-6 audit named this hazard and nothing
had closed it.

**THE OPEN-16 C++ CHECK WENT VACUOUS IF A CONSTANT CHANGED.**
`tests/cpp/test_injectinput.cpp` mirrors the injector's `RELEASE_MS` as a local
100, with a comment claiming the duplicate was safe because it "only ever chooses
between PASS and INCONCLUSIVE". False: it also set the pump horizon, so a real
`RELEASE_MS` above 250 stopped the loop BEFORE the real deadline. Demonstrated —
with the OPEN-16 fix DELETED and `RELEASE_MS` raised to 300, the file reported
`pass=21 fail=0` and "all green". The mirror is now a FLOOR; the check takes the
larger of it and the window this process actually MEASURED a moment earlier, so
load lengthens both together and waiting longer only makes the bug more certain
to fire. Same mutation now gives `pass=20 fail=1`.

*If you mutate `injectinput.cpp`: `g_inject.release_until = 0;` appears TWICE.
Line 193 is the fix; line 325 is the release path. A count-blind replace mutates
both and measures nothing (§10.10).*

**THE PATCH DIVERGENCE LIST WAS GUARDED BY COUNT, NOT COVERAGE.** See the OPEN-11
entry — replacing a row rather than deleting it kept the count at five and left a
patched file compared against nothing.

**HARNESS CLEANUPS RESTORED STALE DEFAULTS.** Every A/B flips a `graph_walk` flag
and restores it in a `finally`, and every one restored a LITERAL — what the
default was on the day that script was written. Two had already rotted:
`ab_leg_speed` restored `LEG_SPEED_BY_LEG = {}` after leg 1 shipped an override,
and `ab_stall` restored `STALL_CHANGE = 2.5` after it became 6.0. In-process
only, so nothing on disk was damaged — but a cleanup that reinstates a stale
default looks like tidiness and installs an arm. All four now capture the flag at
import. `tests/harness/test_harness_restores_shipped_value.py` enforces it, and
exempts subprocess harnesses for a reason worth keeping: they set the arm inside
the `run_trial` child, which then exits, so process death IS the restore and it
cannot be written wrong. That is a second reason to prefer that pattern.

**`profile_trial.py` MEASURED THE WRONG THING THREE WAYS.** It wrapped
`walk_steps.walk_forward`/`turn_to`, which a LEG NEVER CALLS (legs go through
`slow_traverse`); it profiled `reset` plus two legs rather than the §8(a) route;
and it summed NESTED timers, so its "65% unaccounted" was an artefact of the
arithmetic. It now profiles the route through `follow_verified` and records
INCLUSIVE and EXCLUSIVE seconds, so the exclusive column sums to elapsed time and
the residual is real. **Read the exclusive column.** Pinned offline against a
synthetic call tree by `tests/harness/test_profile_exclusive_time.py`.

**A NOTE ON WHERE THE STAIRS POSE LIVES.** `STAIRS_APPROACH.md` holds the
hand-measured doorway approach — bearing, pitch, and three pitch constants that
contradict each other — derived live with the user watching the stream. Nothing
in this file referenced it, which is how a measured document becomes invisible.
Read it before touching leg 2 or anything about pitch.

---

## §11 OPEN

Nothing outside this section may claim to be open.

Closed, answered and dropped tickets are NOT kept here. Verified measurements
and fixes are folded into the section they belong to — OPEN-4 and OPEN-5 into
§8(c), OPEN-10 and OPEN-11 into §2, OPEN-12 and OPEN-18 into §3, OPEN-16 into
§5, OPEN-2 into §1 — and dropped hypotheses go to `GRAVEYARD.md` (OPEN-3) so
they are not retried. A ticket that stays here is unmeasured, half-measured or
blocked, and says which.

Numbering: **OPEN-15 is the compass reader**, **OPEN-16 was the injector release
window** (closed, §5), **OPEN-17 is the arrival heading**. Older worktree copies
of this file used those numbers differently; this file is the authority.

**THE BAN GRID IS FITTED PER FRAME NOW, AND THE INPUT TARGET IS CHECKED (2026-09-13).**
Two flags shipped ON after a phased comparison; both are in §11's closed record rather than
here, but the three facts worth carrying are:

**`ban_grid` IS 16:9 ONLY, and that is enforced, not assumed.** Its card height is derived as
`CARD_ASPECT * column_width * (w / h)`, so the frame's ASPECT is an input to the row fit. On
an archived 2000x1292 frame (aspect 1.548) it fits rows at 0.382 / 0.710 where the true ones
are 0.195 / 0.478 -- different cards, not a small error. Flipping the flag took
`test_ocr_ban_card` from 2 abstentions to 18 in one run. `orchestrator._ban_frame_is_16x9`
now routes anything else to the shipped boxes. The live rig captures 2000x1125 and
1920x1080, both 16:9, so production was never exposed -- but §3 says a reader is checked at
BOTH geometries, and "it does not happen today" is how a rig change becomes a wrong answer
later.

**GIVING UP MID-MATCH LEAVES YOU AT THE TABLE, prompt up.** Measured: OPTIONS -> "Give up?"
-> cross, and one second later `screen match_start_prompt`, `at_table True`, no walking. That
is a free ride back to a ban screen and it skips the entire 76 s route whenever another one
is needed.

**THE DEALER PROMPT RENDERS WHATEVER THE WALLET HOLDS.** A Square press with too little money
does NOTHING and looks exactly like a press that did not land -- it cost a wrong diagnosis
and a wrong $50 in the record here. `Load Last Save` restores the wallet to $246; the tracked
balance must be set to match, because it is not read from the game.

**OPEN-23 — CLOSED THE SAME DAY, AND THE DIAGNOSIS IN IT WAS WRONG. The scan was fine;
every PRESS was going to a /bin/zsh.** `pgrep -f chiaki` matched this session's own shell --
its command line contained the word because the commands being run mentioned chiaki paths --
it sorted first, and `chiaki_pid` took `out[0]`. The liveness guard passed because a shell is
alive. So the scan pressed, nothing moved, its desync guard correctly refused to catalogue
rows it could not verify, and it returned what it had. **Every part of that behaved as
designed.** Fixed in `input_controller._resolve_chiaki_pid` (match the executable NAME, then
filter the loose match by what each process IS) plus an identity re-check on the cached pid
and a re-resolve on the ban scan's desync branch; pinned by
`tests/rig/test_input_target_is_chiaki.py`, 4 mutants caught. With the right pid the same
scan returns 23 cards on the old geometry and 25 on the fitted one.

**The lesson worth keeping is the shape, not the ticket:** the entry below blamed the loop
that reported the symptom. The guard that "could not fire" was one level further out and was
asking the wrong question -- "is this pid alive" rather than "is this pid CHIAKI" -- which is
this project's signature failure wearing a new hat. The original text follows.

**OPEN-23 (original) — THE LIVE BAN SCAN RETURNS A PARTIAL COLLECTION WITHOUT FAILING, and
choose_bans then picks the best 3 of 8 instead of the best 3 of ~33 (2026-09-13).**

Found while A/B-ing the fitted ban geometry, by running the REAL
`read_full_ban_collection()` end to end. It printed SCROLL DESYNC on every batch --
*"press count says row 39, the scrollbar says 4"* -- and returned 8 cards anyway.

The desync guard did exactly what it was built for: trust the scrollbar, never the press
count, because a wrong row bans a card the player does not own. What is missing is the
other half. The loop absorbs the desync, keeps pressing, reads the same rows again, dedupes
them by absolute (row, col), and hands back whatever it has WITH NO ERROR. `choose_bans`
cannot tell a complete collection from a quarter of one.

**IT IS NOT THE FRONTMOST TRAP and it is not the fitted geometry.** Probed straight
afterwards with chiaki confirmed frontmost: from level 5 one `move_down` moved it to 4 and
three more moved nothing at all, cursor parked at (1, 2) throughout. Both geometry arms hit
it identically, which is why they agreed so comfortably -- a partial collection is easy to
agree about.

**WHAT TO DO WITH IT.** The cheap guard is a floor: a scan whose scrollbar never reaches
the bottom level has not seen the collection, and should say so rather than return. The
scrollbar already knows -- `read_ban_scroll_level` reports 0..7 and the bottom clamp is 7,
so "did this scan ever observe level 7" is free and is exactly the question. What is NOT
understood is why the scroll stops; that wants one session with the console and no match in
flight.

Until then a match played on this bans the best of what it happened to see.

**OPEN-1 — the leg-end frame path is BUILT AND PINNED; there are still ZERO
admissible frames.** `follow()` publishes at the right moment: it sets
`_LAST_LEG_END[node]` immediately after `img = capture()` and BEFORE the
`recover_to_node` branch, and the local reassignment after a successful fan does
NOT overwrite the published frame. `follow_verified` clears the stale entry per
node and pops it for classification, and classification sits OUTSIDE `if shots:`
so a run that saves no jpegs still produces a census. With `shots=` a live run
writes `at_<node>_<epoch_ms>.jpg` at the moment the leg's last push finished and
the character settled — before `confirm()`, before the fan. **A frame written by
that path IS admissible.**

Pinned BEHAVIOURALLY by `tests/routing/test_failure_census_provenance.py`, which
drives `follow()` with a stubbed `walk_link`, asserts `recover_to_node` actually
ran, and then checks the published frame is the pre-fan one. The older
`test_failure_frame_is_the_leg.py` checked this with a SOURCE SUBSTRING and does
not catch a second assignment added after the fan — re-introducing exactly that
bug passes it and fails the new one.

**All fifteen candidate frames on disk are excluded, and none is a near miss.**
`overnight/failframes_prerecovery/` (8) are POST-FAN — six sit at bearing
98.1-105.8 against a leg commanded 2.1, the fan's signature, and 4 wedged /
2 overshot / 2 regressed by class. `overnight/failframes/` (4) are PRE-ATTEMPT:
all 1500 keypoints, all identifying `bar_pool_room` at 506-734 matches, bearings
284.8-288.3 — the inbound heading of the PREVIOUS leg, i.e. photographs of the
previous node's successful arrival. `overnight/jukebox_failframes/` (3) use
FIXED names, so each is the last write and its outcome is unknown. They remain
valid as classifier appearance data and invalid as evidence about a leg.

**And the OPEN-14 harness collects nothing.** `overnight/ab_jukebox_leg.py`
reaches its start node with `go_to_node_verified(..., shots=SHOTS)` but walks the
leg UNDER TEST with `gw.walk_link`, which publishes no leg-end frame — so that
A/B produced ZERO frames of the leg it was testing, and there is no
`at_bar_jukebox.jpg` anywhere. `ab_stall_on_restored.py` is the same shape. Fix
that before spending console time on the census.

**No live run has ever recorded a class census at all**: zero "failures by
signature" and zero "failure kind:" lines across every `overnight/*.log`, and no
`overnight/*.json` carries the key.

One silent spoiler is FIXED. When no leg into a node ever completed, the
classifier was handed `before` or a post-fan `capture()` — the two inadmissible
frames this ticket is about — and `failures_by_kind` counted them identically.
`graph_walk._LAST_FAILURE_SOURCES` and `LEG_END_SOURCE` now split the result into
`failures_by_kind_leg_end` and `failures_from_fallback_frame`, so no denominator
goes missing. Three spoilers remain and are not fixable in a few lines: the
published frame is the last attempt in which the leg actually RAN, not
necessarily the third; `walk_link`'s in-leg escape ladder can jump or strafe
before the frame is taken; and for the GOAL node the frame follows
`reach_table()`'s aim sweep, so its heading is post-sweep.

**BOTH HALVES OF THIS ARE NOW DONE (audit 2026-09-07; the paragraph stood
stale for a day).** The path HAS executed live: hundreds of
`at_<node>_<epoch_ms>.jpg` frames and dozens of `success/ok_*.jpg` exist under
`overnight/*failframes*/` from 2026-09-06 on, and "THE FAILURE CENSUS EXISTS"
below was taken from them. And every harness now surfaces the leg-end key:
`_harness.census_kinds` / `report_kinds` (f9b9c56, 2026-09-07) report
`failures_by_kind_leg_end` split by provenance and name what they cannot read. Acceptance test unchanged: a real
jukebox-leg failure frame must NOT read bearing ~286 and must NOT identify as
`bar_pool_room`.

**A WORKING "DID I MOVE" SIGNAL, AT LAST — AND IT IS A PAIRED RATIO (2026-09-06).**
Section 10.4 records that scene change CANNOT answer this: `STALL_CHANGE` cuts
through a unimodal 3.1-7.9, one population. Measured again directly, by taking
the SAME capture pair twice at each heading — once with no push at all, once
with a real one:

    signal          null range        push range        verdict
    frame delta     1 - 12            7 - 24            OVERLAP, unusable
    ORB inliers     353 - 1366        35 - 908          OVERLAP, unusable

Neither works as an absolute gate. But PAIRED at the same heading, dividing the
push's inlier count by that heading's own null:

    0.10  0.11  0.26  0.30  0.34   |   0.82
    <------------ moved ---------->     blocked

A gap of 0.49 between two measured populations. The pairing is what makes it
work and an absolute count cannot: one heading's NULL read 353 while another's
PUSH read 407, so the same number means "blocked" in one place and "moved" in
another. The ratio divides out local scene animation, which is also what makes
it robust to an NPC wandering through the shot.

n = 6 headings from one spot. The MECHANISM is sound and the gap is wide; the
rate is not established. `overnight/probe_calib.py` re-measures it anywhere in
about two minutes, and `overnight/collect_map.py` is the collector built on it.

**WHY THIS MATTERS MORE THAN IT LOOKS.** Every navigation failure this project
has is downstream of not knowing whether a push worked. The stall gate guesses,
the escape ladder fires blind, and a blocked leg is indistinguishable from a
walked one until the localiser disagrees two legs later. A probe that costs two
seconds and answers directly is the missing instrument.

**EVERY LEG ENDS BY WALKING INTO SOMETHING, AND THE LOGS HAVE SAID SO ALL
ALONG (2026-09-06).** Tallied over every archived `overnight/*.log`, no console
time spent:

    blocked on the LAST step of its leg        14
    blocked on the second-to-last step          2
    blocked anywhere else                       1

    portrait_room -> bar_pool_room   step 4/4   x8
    bar_pool_room -> bar_jukebox     step 5/5   x5
    bar_pool_room -> bar_jukebox     step 4/5   x2
    office_corridor -> office_door   step 7/7   x1

Sixteen of seventeen blockages are at or immediately before a leg's end. That is
not diffuse bad luck, it is one repeatable event happening in five different
places.

**WHY, AND IT IS VISIBLE IN THE MAP ITSELF.** Every leg's FINAL step is short —
0.14s, 0.23s, 0.36s, 0.40s, 0.42s — against 0.78-0.80s for the steps before it.
That is a HUMAN DECELERATING: they walked up to a door, a table or a wall,
made one small adjustment, and stopped. The executor does not decelerate. It
replays that tail as a fresh fixed-magnitude push from whatever speed it is
already carrying, and §7(j) records that a push under ~0.10s does not move the
character at all while short pushes are mostly acceleration. So the least
faithful part of every leg is its last step, and that is exactly where the
blockages are.

It corroborates two other things measured the same day. `office_door`'s arrival
frame is a DOOR PANEL filling the view at 7-16 keypoints, on BOTH the merged and
the original leg 1 — the recorded destination is already pressed against
geometry. And 8 of 10 admissible failure frames at `bar_pool_room` classify
OVERSHOT.

**WHAT THIS DOES NOT LICENSE.** Shortening the final step MOVES the character,
and GRAVEYARD's own summary is that every change which moved the character
failed while both survivors moved nothing. The finding is a diagnosis, not a
prescription, and it is cheap to test precisely because the blockage is
localised: one leg, one step, and the log already reports the event by name.

**MAPPING THE WORLD IN 3D IS POSSIBLE, AND ROTATION IS WORTHLESS FOR IT
(2026-09-06).** The single most expensive thing to relearn here.

A drive was recorded by hand through the office: 1064 frames, 95% with a
compass heading, the controller logged on every frame, the stream alive on every
pair, and all eight approach angles filled. By every check available on this
machine it was a perfect collection. Its reconstruction kept **3 points out of
196,198 tracks.**

    what the driver did          share of frames
    turning                            61%
    walking                            17%
    standing still                     32%
    camera translation over 3 frames   MEDIAN ZERO

**Triangulation needs the camera to MOVE.** Turning on the spot moves the lens
not at all, so the rays stay parallel and every distance fits equally well. 85%
of that drive fell short of the baseline the reconstruction needed. The filter
rejecting 196,195 tracks was CORRECT; the data carried no depth.

**THE TWO GOALS NEED DIFFERENT DRIVING, and conflating them cost a room.** The
instruction given was "fill the eight-sector angle bar", which optimises for the
LOCALISER — a reference matched from the wrong approach angle does not match at
all. Geometry needs the opposite: straight lines, turning only at the ends, like
mowing a lawn. That drive remains excellent reference data (789 frames of
genuinely new ground) and useless as structure.

**WHAT MAKES THE RECONSTRUCTION TRACTABLE AT ALL**, since generic
structure-from-motion breaks on this game's low-texture cartoon art: the poses
do not have to be solved for. Yaw comes from the game's own compass, absolute,
on 95-99% of frames, so rotational drift cannot accumulate. Pitch comes out of
the pose decomposition and was measured sound — 0.27 deg/frame integrating to
+1.0 deg over 82 pairs, against a roll control drifting -17.1 deg over the same
span. Distance comes from the recorded stick; the vision-only alternative was
scored against the four archived recordings carrying both and correlates 0.55-58
on walks and **0.14 on turns**.

**FOUR FILTERS ARE NOT OPTIONAL AND THEIR ABSENCE LOOKS LIKE A MAP.** A first
pass triangulated adjacent frames with no cheirality test, no reprojection test
and two views per point, and produced 644,872 points that rendered as radial
starbursts centred on the camera path — an audit found 19.6% of them lying
between or behind the two cameras. Require: a point in FRONT of every camera,
reprojection within a few pixels, three or more views, and positions genuinely
apart.

**THE RIG:** the Mac drives the console and Snoopy reconstructs, over SSH with
key auth. Snoopy is 2x SLOWER at this work than the Mac (ORB is CPU-only; the
3080 contributes nothing), so it is not a speed-up — its value is being a
DIFFERENT machine, because heavy local load degrades sleep from ~5ms to 242ms
and corrupts every walked leg. `tools/ask_snoopy.py` ships a drive, reconstructs
it there and answers one question in ~2 minutes: is this ground producing
geometry. It names the CAUSE, because "positions too close" (not translating),
"too few views" (too fast) and "behind a camera" (the trajectory is wrong, not
the driving) need different responses.

**THE LOCALISER'S GATE SITS INSIDE THE OVERLAP, MEASURED (2026-09-06).**
`portrait_room` abstains about half the time on frames where the character IS
there, and §8(b)'s per-leg rates inherit that. The cause is not the leg.

    a GENUINE arrival scored          137 matches
    a frame taken OUTDOORS ON A       135 matches
      STREET, off the mapped route

`MIN_MATCHES` is 140. Those two populations are not separated by it, in either
direction. Raw ORB match count cannot do this job on this game's art: unrelated
rich frames score 100-155 against any room, because a black-and-white cartoon of
wood, walls and floors produces promiscuous descriptor matches. **It is NOT the
HUD** — `places._as_gray` already crops the compass, coin and quest list (top
10%, bottom 10%, left 28%), and masking them again changes nothing.

So `portrait_room` is not being CONFUSED with `bar_pool_room`. `bar_pool_room`
simply sits at a constant 100-135 on every rich frame, and the ratio gate is
dividing a real signal by that floor.

**A CLAIM MADE HERE EARLIER THE SAME DAY WAS WRONG, AND IS WITHDRAWN.** This
section said "the reference set is too thin to pass its own test: leave-one-out
names its own room 3 of 9 times". **It names it 9 of 9, with zero wrong and zero
abstentions**, at best 248-698 and ratios 1.91-5.29 — which reproduces §7's
"249-698" exactly. The reference set passes its own test.

The 3-of-9 came from a REIMPLEMENTATION that was never checked against the
original. `places.match_count` filters matches by Hamming distance
(`places.py:409`); the mirror in `agent_progress/localiser-inliers/validate.py`
used a raw `len(bf.match(...))`. Unfiltered, spurious matches inflate the
SECOND-best room, which collapses the ratio and produces six false abstentions.
The same file's own docstring warns about exactly this trap, having already been
caught by it once that morning over the HUD crop. Anything scored through that
mirror's RAW-COUNT column is suspect; its RANSAC-inlier column and everything
computed through `places.identify` / `places.room_scores` are not.

**WHAT STILL STANDS, because it went through the project's own path:** a genuine
arrival at `portrait_room` scored 137 while a frame taken OUTDOORS ON A STREET
scored 135, against a `MIN_MATCHES` of 140. The gate sits inside the overlap.
That is the finding; "the references cannot recognise themselves" is not.

**RANSAC-VERIFIED INLIERS ARE A CANDIDATE, NOT A CONCLUSION.** Fitting one rigid
transform to the matches and counting inliers, because a spurious match is a
descriptor coincidence and does not agree with the others:

    metric              leave-one-out      160 unmapped bar frames NAMED
    raw match count        3/9 correct                16
    RANSAC inliers         9/9 correct, 0 wrong       55-96 (gate 60 down to 10)

It fixes the true-positive side completely and appears to make the false-positive
side much worse. **But that second column is not scoreable**: those 160 frames
are an EXPLORE run through the bar area, and §7 says that area is two-thirds
unmapped — which means up to a third of them may genuinely be at a mapped node,
so "named" is not the same as "wrong". Before anything ships, that corpus needs
labels. Do not quote the 55-96 as a false-positive rate.

Script: `agent_progress/localiser-inliers/validate.py`, self-contained. **It got
this wrong first, in a way worth remembering**: without replicating
`_as_gray`'s crop it scored the unmapped corpus at a median of 777 against a 140
gate and rated it above the references themselves — it was measuring the HUD
matching itself, 160 times. A reimplementation of a project function means
nothing until it is checked against the original.

**THE FAILURE CENSUS EXISTS (2026-09-06). It is 80% OVERSHOT, and it is the
first one ever taken from admissible frames.** OPEN-1 asked for this and OPEN-6
forbade quoting any class distribution until a run produced it. A run has.

Twenty-eight `at_<node>_<epoch_ms>.jpg` leg-end frames were written live for the
first time; ten of them are the failing node `bar_pool_room`, classified with the
stream confirmed live:

    OVERSHOT   8/10   95% Wilson [0.49, 0.94]
    WEDGED     2/10   95% Wilson [0.06, 0.51]

The interval EXCLUDES a half-and-half split, so "most of these failures are
overshoot" is supported at n=10. The exact fraction is not. The withdrawn figure
it replaces was 2 of 8 POST-FAN frames at [0.07, 0.59] — inadmissible and
uninformative. **OPEN-6's ban on quoting a class distribution is lifted for this
node only**, and only for the direction of the effect.

Every frame reads bearing 284.8-289.9, i.e. facing the way the leg walked, and
none identifies as any known place (best scores 1-154 against MIN_MATCHES 140).
Keypoints split cleanly: the two WEDGED frames hold 10, the OVERSHOT ones 420-1500.
`test_fixtures/leg_failures/` keeps one of each.

**AND ONE OF THEM IS OUTDOORS.** `overshot_outdoors_1788718155150.jpg` shows the
character on a CITY STREET — a truck, a lamppost, shop signs — after a leg that
should have ended in the bar's pool room. That is the shape of §8(k), *"when you
make the turn, you actually walk right out of the bar"*, which this file has
recorded since day one as never captured. It is now captured. Whether it is the
same event the user saw is NOT established; what is established is that a leg
into the bar can end outdoors and off the mapped route.

**SOLVED 2026-09-06, AND IT WAS OUR OWN CHANGE, NOT THE CONSOLE.** The
regression below was attributed to the power cycle. That was an association and
it was wrong. Measured interleaved, 10 trials an arm, verified arrivals at
`bar_pool_room` (`overnight/ab_leg1.py`, `overnight/ab_leg1.json`):

    leg 1 AS RECORDED           10/10 arrived   median  51.6s   [50..55]
    leg 1 at speed 3.0, MERGED   2/10 arrived   median 323.7s   [206..371]
    Fisher exact p = 0.000714, zero invalid trials

The restored arm reproduces the lost baseline exactly — 51.6s against the 52.9s
measured before the flags landed — and its ten times span five seconds.

**THE TIMELINE IS THE LESSON.** The 10/10 was measured at 23:12 on 2026-09-05.
The commit that RECORDED it, at 23:33, is titled "OPEN-4 answered 10/10; leg 1
to max speed" — it enabled the first flag. `MERGE_STEPS_BY_LEG` followed at
00:20. So the result and the change that invalidates it share a commit message,
which is section 10.7 violated inside the artifact that reports the
measurement. It stayed invisible for a day and cost an afternoon of runs.

`tests/routing/test_leg_speed_scale.py` then pinned the override and justified
it in a comment as shipping "on a measured 10/10 arrival" — crediting the flag
with a result measured before it was switched on, written where it reads as
evidence. Both flags are reverted (`backups/restore_leg1.py`) and the test now
pins their absence against the A/B above.

**GRAVEYARD HAD ALREADY MEASURED BOTH HALVES AS FAILURES.** Step merging is a
graveyard row whose stated mechanism is "a merged push covers more ground than
the stop-start sequence it replaces, so legs that used to stop short now run
into furniture" — and the failing log says *BLOCKED on step 4, the view is
featureless, this is geometry*. Leg speed at 3x is another row, mean WORSE. Both
rows' "State today" columns had gone stale and said the flags were off. **A
stale graveyard is worse than none: it is how a measured failure comes back.**

**THE START NODE REGRESSED THE SAME DAY, AND THAT IS WHY OPEN-14 DID NOT RUN.**
This morning `go_to_node_verified("bar_pool_room")` measured 10/10 at a 52.9s
median (OPEN-4). This afternoon, after the console was power-cycled, it reached
that node 0 of 3 times at 274-446s. Both arms degraded together, which §10.6 says
means the environment — the first suspicion was local load from concurrent
offline work, and that was WRONG: a restart on a quiet machine failed identically.

The signature is a RATIO failure at `portrait_room`, not a missing-features one:

    confirmed   267, 295 matches   ratio 2.04, 2.38
    abstained   155, 150, 109, 85  ratio 1.21, 1.21, 1.20, 1.16

`MIN_RATIO` is 1.35. When it works it clears comfortably; when it fails the best
reference barely beats the runner-up, which is ambiguity BETWEEN references
rather than a dark frame. Alongside it the leg into the bar reports "BLOCKED on
step 4" and the escape ladder fired five times, consistent with NPC traffic the
user had already noticed near that path.

**The start node is fixed (see above), so OPEN-14 is unblocked.** Measuring a leg
you reach 0 of 3 times spends an hour per arm to record INVALID; at the restored
leg 1 the start node is reached 10/10 at a 51.6s median.

**OPEN-14 — MEASURED 2026-09-07 (02:26-06:45): the full-route streak to the
table at attempts=9 arrived 1 of 3 valid trials; 7 of 10 were CENSORED by the
ceiling; and the one other "arrival" was `identify()` naming a pose it must not.**
`overnight/streak_table.py`, 10 trials, route `portrait_room -> bar_pool_room ->
bar_jukebox -> dealer_table`, `attempts=9`, `start_hint=SPAWN`, `shots=`, 1800s
external ceiling (`overnight/streak_table.json`, `.log`, `streak_table_arrivals.jpg`,
`streak_table_table_ends.jpg`):

    trial   outcome    depth   seconds   at_table recheck
      1     INVALID      -       1800    ceiling; dealer_table attempted 6x, 19 sweeps, ink max 0.0415, 7 resets
      2     ARRIVED     4/4      1201    True  — the prompt, twice, 0.8s apart
      3     INVALID      -       1800    ceiling; 6 table attempts, 26 sweeps, ink max 0.0253
      4     INVALID      -       1800    ceiling; 7 table attempts, 15 sweeps
      5     INVALID      -       1800    ceiling; 6 table attempts, 19 sweeps, ink max 0.0370
      6     "ARRIVED"   4/4       486    FALSE — verified by identify() at 194/1.53, one sweep at ink 0.0105
      7     INVALID      -       1800    ceiling; 5 table attempts, 15 sweeps
      8     missed      2/4      1049    wedged on the jukebox leg, all 9 attempts
      9     INVALID      -       1800    ceiling; 5 table attempts, 14 sweeps
     10     INVALID      -       1800    ceiling; 5 table attempts, 17 sweeps

**Honest tally: 1 arrived of 3 valid, best streak 1.** The harness printed 2/3
and streak 2; both count trial 6, which does not count.

**TRIAL 6 IS A HOLE IN THE VERIFIED PATH, AND IT IS THE FIRST ITEM FOR THE
MORNING.** `locate()` (graph_walk.py:260-292) tries `at_table()` and, when that
is False, falls through to `places.identify()` and returns whatever room it
names. `places/dealer_table/` holds three references, so `identify()` CAN name
the table — from a distance where no prompt exists, because the references are
the table VIEW. `go_to_node_verified` then logged `verified at dealer_table
(dealer_table 194.000/1.530)` and counted it, while the independent `at_table()`
re-read 0.8s later said False and the trial's only sweep peaked at ink 0.0105
(`INK_MIN` 0.024). §7's rule — the table is a POSE, confirmed by `at_table()`,
never `identify()` — is enforced in `confirm()` (node == GOAL) and NOT in
`locate()`. The two "verified" frames make it plain: trial 2 stands close with
the dealer group ahead; trial 6 is the same scene from further back. FIXED
2026-09-07 morning: `locate()` returns None when `identify()` names `GOAL` and
the prompt is absent, with the refused evidence in its detail string. Pinned by
`tests/routing/test_locate_goal_is_a_pose.py` (three mutants caught: guard
deleted, guard compares to a node that never occurs, guard over-blocks every
room). The trial-6 capture itself was never saved — the `ok_dealer_table` frame
is the pre-sweep leg end and identifies as `bar_jukebox` 295/2.11 — so the
test stubs the detectors with trial 6's numbers verbatim.

**THE CEILING CENSORED 7 OF 10 BY CONSTRUCTION.** Every censored trial reached
`bar_jukebox` and then spent the rest of its 1800s on the table leg, 5-7
attempts each — and after each miss `locate()` could not name the position, so
an `attempts=9` retry on the goal leg is a FULL RESET AND ROUTE RE-WALK (6-7
resets per trial). The 780s maximum that sized the ceiling came from OPEN-5,
where retries are local. §10.14, self-inflicted. A streak to the table is not
measurable at this ceiling; it needs either local retries on the goal leg or a
ceiling of `attempts x route-time`.

**WHAT THE 37 TABLE-LEG END FRAMES SAY.** *(Caveat 2026-09-07: for the GOAL node
those frames were taken AFTER approach_goal's stepping and reach_table's sweep,
so they describe where the recovery left the camera — six read 253-258, the far
end of the 19-heading circle — not where the leg ended. From da5b7ec the leg-end
frame is published BEFORE the sweep; see OPEN-21.)* The leg ends in the dark, against an
NPC, against the bar-top, or looking at the floor — including in both trials
that then "arrived": the arrival happens only after `reach_table` turns the
camera. The sweeps DO see the prompt at times (ink max 0.042, 0.037, 0.030,
0.025 across trials, above `INK_MIN` 0.024) without satisfying `at_table()`'s
score gate, so the character is near the prompt's edge, not far from it. That
is OPEN-17's arrival-heading gap with frames instead of an ordering.

**What did NOT fail:** `portrait_room` and `bar_pool_room` arrived by attempt 2
in all ten trials; `bar_jukebox` arrived in 9 of 10 (2-7 attempts; trial 8
exhausted nine). The restored jukebox leg is not the problem it was.

The original ticket text, for the harness lessons, follows.

**OPEN-14 (original) — The restored jukebox leg as a full-route streak
(started 2026-09-07 02:26).** The leg was 4.3x too short and could not reach its
destination; it is back to its recorded 1.031 units over 3.30s. The short-vs-
restored A/B this ticket originally asked for is superseded: the short leg is
gone, the arithmetic says it could not arrive from anywhere in its origin's
basin, and console time spent measuring a leg that cannot arrive answers
nothing. What measures the restored leg is the run on the console now:

    overnight/streak_table.py  ->  overnight/streak_table.json, streak_table.log
    10 trials, route portrait_room -> bar_pool_room -> bar_jukebox -> dealer_table
    attempts=9, start_hint=SPAWN, shots= (leg-end frames), 1800s external ceiling
    goal scored by at_table() after follow()'s aim sweep (confirm(), node == GOAL)
    reported as the LONGEST CONSECUTIVE streak; invalid trials neither extend nor break it

Its per-node results give the restored leg's arrival rate at attempts=9 on the
way to the answer that matters: how many in a row reach the TABLE. Trial 1
started at load 8.0 / 15.5 / 13.7 (cancelled agents draining); §10.13a covers
~8-11, so treat trial 1 as suspect if it is an outlier. Read the result before
touching any leg — this is the first streak with the table leg and the prompt
as the final check.

**TRIAL 1 (03:00): INVALID at the 1800s ceiling, and the ceiling was censoring by
construction.** It verified `portrait_room`, `bar_pool_room` and `bar_jukebox`,
then failed the TABLE leg five times: every `reach_table` sweep reported *swept
19 headings around 76; best ink 0.0000 at None, prompt never appeared* — not a
weak prompt, no prompt. After each miss the localiser could not name the
position (87 matches, ratio 1.16), so `attempts=9` on the goal leg means a FULL
RESET AND RE-WALK OF THE ROUTE per attempt (7 resets inside one trial); six of
those is 30 minutes. OPEN-5's 780s maximum was measured where retries are
local, and I set the ceiling on it — §10.14, self-inflicted.

The five `at_dealer_table` leg-end frames (`overnight/streak_table_trial1_table_ends.jpg`)
show where the table leg actually ends from the restored jukebox pose: pressed
into an NPC's coat; dark geometry; a bar-top with a bottle filling the view; and
twice **looking DOWN at a tiled floor** — a yaw sweep with the camera on the
floor cannot see the prompt at any heading (STAIRS_APPROACH.md: pitch is
uncontrolled in production). So the restored jukebox leg ARRIVES, verified, and
the table leg recorded from the human's jukebox pose then walks somewhere the
prompt is not. n = 1 trial, 5 table attempts. That is the chain OPEN-17 names
(arrival heading at the table -11.31 deg; `approach_goal` aims 10.6 deg off the
leg's own direction), now with frames instead of an ordering.

**Harness lessons that must not be re-copied** (fixed in `overnight/_harness.py`,
2026-09-06): `ab_jukebox_leg.py` walked the leg under test with `gw.walk_link`,
which publishes no leg-end frame, so it collected NO evidence about the leg it
existed to test (OPEN-1), and it reset twice a trial for want of `start_hint`.
`_harness.walk_leg_under_test()` runs ONE attempt through `follow_verified`
(retries would hide exactly the difference a leg A/B looks for), returns the
census SPLIT BY PROVENANCE, and counts recovery-fan rescues separately from
arrivals — a rescued trial travelled ~7x the leg's distance and is not evidence
the leg arrives. Pinned by `tests/harness/test_leg_under_test_collects_evidence.py`,
which asserts on CALLS through a stub rather than on source text.

**OPEN-13 — Does nulling the yaw before aligning improve ARRIVAL?**
`graph_walk.NULL_YAW_BEFORE_ALIGN` ships **True**, because the old behaviour
violated a precondition `pose.offset`'s own docstring states ("null the yaw with
the compass first"). That makes it a bug fix, not a tuning choice — but its
effect on arrival rate is **unmeasured**, and nine well-motivated navigation
changes on this project have failed their A/Bs.

Measured basis: 18.6-20.8 px per degree of yaw at the live geometry (7 pure
camera-turn pairs, character stationary), corroborated by
`camera_fov.json` (1920 / 102 deg = 18.8). So `ALIGN_TOL_PX = 35` is 1.8 degrees
and `SAME_POSE_PX = 16.85` is 0.87 degrees, while the leg executor turns with a
4.0 degree tolerance — a character exactly on the reference POSITION but 2
degrees off its heading read ~40px and was strafed sideways for it.

The A/B: `NULL_YAW_BEFORE_ALIGN` True vs False, 10 trials per arm, interleaved,
scored on VERIFIED arrivals, on a quiet machine. Report by failure class, not
just the total.

**Its own guard was DEAD until 2026-09-05, and the failure looked like a broken
feature.** `tests/routing/test_yaw_nulled_before_align.py` simulated an
unreadable reference by poking `gw._REF_HEADING["portrait_room"] = None`, but
`reference_heading()` keys that cache on `(REFERENCE_POSE, node)` — deliberately,
so an in-process A/B cannot serve one arm's heading to the other. The bare-node
poke therefore missed the key entirely, the heading recomputed to 1.39, and the
UNREADABLE branch the check exists to guard was UNREACHABLE. The stub was left
behind when the key gained `REFERENCE_POSE`. Fixed in the main checkout, and
mutation-tested by replacing that `log(...)` with `pass` (file size 100550 ->
100374, so no stale bytecode) — the check then fails, and only that one.

**OPEN-6 — `SURVEY_WHILE_WALKING`, `SPEED_FROM_RELIABILITY` and
`RECORD_RELIABILITY` have never been tested live; the first's premise is now
MEASURED.** `SURVEY_WHILE_WALKING` was built on "the OVERSHOT class, a quarter of
failures", a figure from 8 post-fan frames that were inadmissible as evidence
about a leg. The admissible measurement replaced it (2026-09-06, "THE FAILURE
CENSUS EXISTS" above): at `bar_pool_room`, from leg-end frames with the stream
confirmed live, **OVERSHOT 8/10, Wilson [0.49, 0.94]; WEDGED 2/10, [0.06, 0.51]**.
The interval excludes a half-and-half split, so "most failures at that node are
overshoot" is supported at n=10; the exact fraction is not, and the first
admissible ROUTE census (2026-09-07, §8(a), n=5) is WEDGED-heavy — wedged 4,
overshot 1. So the premise survives for `bar_pool_room` and is unsettled for the
route. `SURVEY_WHILE_WALKING` stays `False` until an A/B, not because its
premise is gone.

`SPEED_FROM_RELIABILITY` and `RECORD_RELIABILITY` are correct at `False`,
demonstrated: 12 recorded arrivals make `leg_reliability.scale_for` return 3.0,
and ONE subsequent failure returns it to 1.0 (11/12 = 0.917, under `MIN_RATE`
0.95) — pinned with literals in `tests/routing/test_leg_reliability.py`. With
both on, `follow_verified` writes the outcome it is measuring and `leg_scale()`
reads it back, so trial N's walking speed is a function of trials 1..N-1, and an
interleaved A/B's two arms share one store unless each arm sets
`leg_reliability.STORE` inside its trial CHILD — the redirect works now (§10.18).
`leg_reliability.json` does not exist on disk; neither flag has ever run live.

Audited for the same write-then-read shape and reported, not changed:
`compass._SCALE_CACHE` (`compass_scale.json`) and `input_controller._VIEW_CACHE`
(`view_bounds.json`) are written mid-run and read back, and the view cache is a
"widest lit extent ever seen" ratchet that moves the view centre and hence every
bearing. They calibrate the DISPLAY, not the outcome — no arm can move them
differentially and they converge, so interleaving absorbs them. Their writes are
suppressed under `BASEBALL_TEST_RUN` (`tests/harness/test_caches_not_written_in_tests.py`).

**WHAT A CLASS CENSUS COSTS.** `follow_verified` stops at the FIRST unproven node,
so a trial yields AT MOST ONE classified failure; at 5/10 route arrival that is
0.5 failures a trial. ±20pp on one class needs 16-21 failures (~40 route trials,
~3h); ±10pp needs 69-93 (~230 trials, ~22h); a single-leg harness at ~90 s/trial
reaches ±20pp in about an hour. Take the ±20pp run when a decision hangs on a
class; nothing does today.

**OPEN-7 — Should `RECOVER_MISSED` be turned off?** The fan succeeded 0/15 in
the streak run and 2/31 combined, while costing ~34% of the clock. Judge it on
seconds and failures-by-class, not arrival. **The cost is now confirmed twice
over, independently** (2026-09-05): `ab_local_recovery`'s local arm has a median
trial of 155.4s against the reset arm's 76.3s, and the only difference is one
`LOCAL_RECOVERY_FIRST` fan, so a fan is ~79s; a static model of the fan from the
constants gives 70.0s. At the 14 misses per 10 streak trials in the archived
logs that is ~111s a trial, **33%** — reproducing the ~34% already recorded here
by a different route. It is the single largest item on the clock.

**OPEN-8 — Where does the other ~45s of a trial go? MOSTLY ANSWERED 2026-09-05;
three cuts made, ~26% of a streak trial still unexplained.**

**FIRST, THE PROFILE IN §8(h) IS NOT A ROUTED TRIAL, and its rows do not sum.**
`overnight/profile_trial.py` profiles `reset` + `go_to_node_verified(
"portrait_room")` — two legs, not the three-node route — and it wraps
`walk_steps.walk_forward` / `turn_to`, which a LEG NEVER CALLS: legs go through
`slow_traverse.walk_leg` / `turn_to`. So leg walking appears NOWHERE in it, which
is why it shows `walk_forward: 1 call`, and its `turn_to: 6 calls` is
`_look_around_for_a_node`'s five bearings plus the turn back, not leg turning.
The wrapped rows also nest, leaving 65% of the 85.6s unattributed — which is
precisely what this ticket was asking about. **Do not quote §8(h) as a route
trial**, and fix `profile_trial.py` (wrap `slow_traverse.walk_leg`/`turn_to`,
`pose.align_lateral` and `table_prompt.at_table`, and profile the ROUTE) before
anyone reads it again.

The accounting that DOES add up, validated against `profile.json`'s own call
counts — modelling the run from the code predicts `identify` 8, `walk_forward` 1
and `ws.turn_to` 6, and the file records 8 / 1 / 6:

    reset x2 + sleep(1.2) x2          20.3s  23.7%
    leg turning, 23 steps             21.5s  25.2%  (only ~3.5s is stick push)
    stick time walking                16.2s  18.9%
    relocalise sweep, SILENT          13.9s  16.2%
    SETTLE_SEC x 23 steps              8.1s   9.4%
    captures inside walk_leg           1.7s   2.0%
    align + confirm + locate + live    4.0s   4.7%

**CUT 1 — 26 of 26 archived trials threw away the reset they had just paid
for.** Every one opens with "not at portrait_room and cannot say where this is —
reloading to a known start" IMMEDIATELY after the harness's own reset. `SPAWN =
office_corridor` is in `UNSEEDED` BY DESIGN (§7: seeding it from a dark frame
created false positives), so `locate()` can never name it; `go_to_node_verified`
called that lost, ran a 13.9s sweep with nothing to find, and reset a SECOND time
to reach the spot it was already standing on. Fixed by
`graph_walk.TRUST_RESET_SPAWN` plus a `start_hint` threaded through
`follow_verified` / `consecutive_arrivals`, spent on the first attempt only.
**~24s a trial.** Pinned by `tests/routing/test_trusted_spawn_start_hint.py`,
which asserts on CALLS not outcomes — both paths end at the same node, so only
the sweep and reset counts can tell them apart — and which now also pins that a
hint must NOT override a `locate()` that named a routable node. It did not, at
first: the hint was consumed inside the `start is None` branch, so it survived any
attempt that DID locate, and a mutant that let the caller's claim beat the
screen's evidence passed the whole file.

**CUT 2 — `read_bearing` re-asked tesseract a question it had already
answered.** The pytesseract fallback fired whenever `ocr_glyphs` returned
nothing, including when it RAN and abstained — an identical question through a
~50x slower invocation, at a median 12 subprocess calls per unreadable frame,
times four `read_heading` retries. It now runs only when `ocr_glyphs` could not
RUN. Pinned by `tests/routing/test_compass_no_duplicate_ocr.py`, which carries
the control (when the fast reader genuinely cannot run, the full ladder still
sweeps) and an anti-vacuity check that the real reader still reads every frame.
Residual risk: `ocr_glyphs` caches a per-thread `PyTessBaseAPI`, so a handle that
goes bad WITHOUT raising now returns `None`s with nothing behind it.

**CUT 3 — the scale cache is written once per geometry, not on most reads.**
Worth ~0.4s of an 85.6s trial, under 1%: the first measurement put the
read-modify-write at ~120ms, and re-measurement on a quiet machine gave a median
of **9.0ms (n=60)**, with the multi-second outliers traced to whole-process
stalls under load rather than to the I/O. A tidy-up, not a saving. It also
silently freezes the disk value at whatever the first process to see that
geometry wrote.

**REFUSED, with the measurement.** The escape ladder must NOT be truncated: 82
invocations across four logs, 19 cleared, and **14 of those 19 cleared on a rung
AFTER the first**. And `SETTLE_SEC` (13.4s of a streak trial, 4%) must NOT be
shortened, because `walk_leg` would then capture mid-motion and inflate `best`,
which is the input to `STALL_CHANGE` — a blocked step would read as walked. Four
percent is not worth breaking a gate.

**(a) IS DONE, 2026-09-06.** Every harness that resets and then navigates now
passes `start_hint=gw.SPAWN` — seven call sites. Pinned by
`tests/harness/test_overnight_start_hint.py`, an AST scan that fires only where
a reset and a navigation call share a scope, so a call with no reset is never
forced to claim one. It carries a floor so it cannot pass by scanning nothing.
`profile_trial.py` was rewritten at the same time (see below), so the
"85.6s -> ~61s" figure still describes a build nobody has made — but it now
describes the wrong quantity as well, and should not be quoted at all.

**REMAINS.** (b) About 26% of a
338.4s streak trial (~89s) is still unexplained with every modelled component at
its floor — one push per turn, no compass retries, no ladder repeats. Cut 2 was
the strongest candidate; re-run one streak trial and see whether the residual
closes. (c) All three cuts are UNMEASURED against arrival. Two cannot plausibly
move it, but the spawn hint has one real mechanism: the route now starts ~24s
earlier after the load, so the NPCs have wandered 24s less.
`TRUST_RESET_SPAWN = False` is the control arm, and the A/B is cheap precisely
because the True arm is faster. (d) The recovery fan, ~79s each and ~33% of the
clock, is OPEN-7's and is not decided here.

**OPEN-9 — Can a recovery REPLACE the reset rather than precede it?** Local
recovery failed because its cost was ADDITIVE — when the fan failed, the reset
still happened. The variant that skips the reset on success has not been tried.

**OPEN-15 — `read_bearing`'s confidently-wrong reads had ONE cause and it is
fixed; the coverage cost is real, and the change is UNMEASURED against
arrival.** (2026-09-05. This is the first time the reader's accuracy has been
measured at all.)

Ground truth was built for 2571 of 3628 archived world frames from three sources
that had to agree: letters at a pitch measured from the compass's own TICK
LATTICE; tick PHASE, which pins heading modulo 10 deg with no letter involved;
and RIGHT-STICK STATIONARITY from `demos/*/input.json`, since only the right
stick turns the camera (§5), so across a run where `|rx|` never left the deadzone
the heading CANNOT have changed. 1057 frames were EXCLUDED, not guessed. The
truth validates against an instrument that knows nothing about OCR: of 726
letter-truth frames inside a stationary run, exactly **1** deviated from its
run's consensus by 3 deg or more.

**THE TICKS ARE THE PART THAT CANNOT BE MISREAD.** They sit at ODD MULTIPLES OF
5 DEGREES, so a letter sits HALF a spacing off the lattice and nine spacings span
the 90 deg between letters (1.5 + 6 + 1.5 — the ticks either side of a letter
hide under its circle). On `explore/20260904_152521_bar_area/00001.jpg` the fit
gives d = 32.3941 at rms 0.200px, so 9d = **291.55** against the 291.5 the
letters measure, from marks no recogniser has to identify. A letter's OWN strokes
arrive as tight clusters and wreck the fit unless peaks closer than half a
spacing are dropped. **This is NOT the bar correlation that was tried and
reverted** — that aliased because it asked the 10-degree ticks for the whole
answer. Here the ticks supply only the sub-10-degree phase, the LETTERS choose
the decade, and a frame with no letter still abstains.

**THE CAUSE: believing a lone letter.** Every confidently-wrong read came from a
frame where exactly ONE letter was recognised.

    1 letter    268 reads   116 confidently wrong   43.3%
    2 letters  1330 reads     0
    3 letters   546 reads     0

Two of the three worst anchors are not letters at all: a scenery blob at x=572,
in a frame whose real letters stand at 499.5 / 711.7 / 924.0, reads as 'S' and
the frame reports 233.0 where the truth is 84.8. **The ticks cannot catch this** —
a letter swapped for the one opposite is 180 deg, a whole number of spacings, so
the phase agrees with the wrong answer too. Fixed by `REQUIRE_TWO_LETTERS` plus
`POOL_THRESHOLDS` (sweep until two LETTERS, not two BLOBS, over a ladder reaching
down to 110, which `BLOB_THRESHOLDS` never reaches): over the truth frames,
confidently wrong **116 -> 2** and abstain **16.6% -> 5.0%**. Both axes moved the
right way at once, which is the thing to re-check if it regresses. Of the 149
frames the new reader refuses where the old one answered, 70 have truth and **the
old reader was WRONG on 62 of them**.

Corroborated independently: over 343 frames of `demos/walk_20260827_214446`
inside right-stick-quiet segments, reads that contradict their own segment's
median go from **96** (of 166 in-segment reads) to **2** (of 230) — more coverage
AND fewer wrong answers — and the two survivors are the two frames already known
to be wrong.

**IT IS NOT PERFECT.** 2 of 2442 reads are still wrong by 150 deg, both from two
SPURIOUS blobs a plausible pitch apart that corroborate each other, which is the
one thing a two-letter rule cannot see.

**WHAT IT COSTS — and do NOT quote the labelled-subset figure.** Over ALL 160
frames of `explore/20260904_152521_bar_area`, at the LIVE 1920x1080 geometry,
abstention goes **5.6% -> 15.6%**: about 13 probably-good reads lost per 160
against about 4 bad reads correctly refused. The "0.0% at 1920x1080" figure came
from the truth subset, and the truth criterion (two or more letters over the full
ladder) SELECTS precisely the frames the new rule can read — so it excludes the
refusals by construction. Net safety is still positive; the honest sentence is
"abstention triples at the live geometry, and that is the price".

Also carry: the headline 5.41% wrong is a STRESS TEST, not today's live rate. All
116 failures are at the demo archive's 1400x787, 0.73x the live linear
resolution. The mechanism is resolution-independent so it CAN fire live, but the
rate has not been observed live. Cost is 1.13-1.32x per read, under a second a
trial.

**REMAINS.** (a) UNMEASURED against route ARRIVAL — this is a sensor change, and
this project's record is 13 well-motivated changes that moved no number. (b) Two
holes the test does not guard: the "stop on two LETTERS not two BLOBS" rule
survives mutation (on the current fixtures the entire gain comes from the ladder
reaching 110, not from the stop rule the comments credit), and
`TICK_SNAP_MAX_DEG` is asserted nowhere. (c) The scale cache is now rewritten on
~39 of 40 reads against 14 before, because `9*d` is a continuous lstsq output —
on a file whose own comment says it lives on a NAS. That collides directly with
OPEN-8's cut 3, which makes the write once-per-geometry; merged together, the
frozen value becomes the tick-derived one.

**OPEN-17 — Does the executor's ARRIVAL HEADING cost the two bad nodes?
PARKED — do not build it before OPEN-14 reports.** The executor ends every leg
facing `steps[-1]["bearing"]`, while the references were shot at `cam[-1]`. The
gap, per leg:

    office_door    +0.99   |  portrait_room  +1.82   (arrival 1.000)
    bar_pool_room  +6.37   (route2 +4.08)            (arrival 0.667)
    bar_jukebox    -3.05   (route2 +1.80)
    dealer_table  -11.31   (route2 -2.66)

At the measured 18.6-20.8 px/deg that is 118-132px at `bar_pool_room` and
210-235px at the table, against `ALIGN_TOL_PX = 35` — and the ordering matches
which nodes arrive worst. It is also the right SHAPE for this project: the
intervention is ONE TURN and no translation, and GRAVEYARD's own summary is that
every failed change MOVED the character while both survivors move nothing.
**But the evidence is n = 2 legs and an ordering**, which is an association of
exactly the shape that killed `STALL_CHANGE` after a Fisher p = 0.00039 (§10.2).
`approach_goal` compounds it by aiming at `steps[-1]["bearing"]` and discarding
the other seven, 10.6 deg off the leg's own net direction.

**OPEN-19 — Did the OLD `clear` corrupt §6's walking table?** Raised 2026-09-05
and deliberately left open rather than inherited.

OPEN-16 does NOT implicate that table: `overnight/walk_curve.json` is dated
2026-09-04 13:00, the release window was added 2026-09-05. But `walk_curve.py`
had the same clear-then-push-75ms-later loop then, and BEFORE the release window
`clear` never transmitted a release at all — that is the defect the window was
ADDED to fix, measured at the time as "0.4s after `clear`, the PS5 still believed
left_y = -9830" (`chiaki-patch/injectinput.cpp`). So the question is whether the
walk-back push at `walk_curve.py:49` stayed deflected into the next sample's own
`before` capture and its `walk_forward`. That is unestablished, and it is not the
same mechanism as OPEN-16.

It would inflate exactly the high-magnitude rows, and those are the strange ones:

    mag    median   spread   n
    0.60     71.2       27   3
    0.75    106.0      124   3
    0.85    352.9      476   2      <- 3.3x the row below it
    1.00    113.4       73   3      <- and then DOWN again

A response that rises 3.3x and then falls is not a shape a monotonic
stick-to-distance relation has. **`LEG_SPEED_MAX = 0.60` derives from these
numbers** (§6), so this is load-bearing, not curiosity.

**Do NOT re-measure with `walk_curve.py` until OPEN-16's fix is on the rig** — its
loop is the one live site inside the release window, so the script would corrupt
the very table it is being run to check. It is the fix's own test case. (The fix
IS on the rig as of 2026-09-05, so this no longer blocks.)

**DOWNGRADED 2026-09-05 — LOW VALUE, and the user was right to ask.**
`LEG_SPEED_MAX` (defined `graph_walk.py:1379`) has exactly ONE production
consumer, `_scaled` at `graph_walk.py:1530`, which is leg-speed scaling — and §8(h) already measured that lever: *"a 32% cut in
walking bought 5% and a worse mean."* So this table feeds one thing and that thing
is known not to pay. `walk_curve.py` also drives `left_y` ONLY (`walk_forward`
with the default `strafe=0`), so it cannot speak to the question that actually
motivated it — see OPEN-20. Answer it if it is ever cheap; do not spend rig time
on it.

An attempt on 2026-09-05 was VOID and is not in the record: run straight from a
reset, it measured the character pressed against the typewriter desk (the spawn
FACES that desk, so forward is blocked). 18 of 21 samples read displacement 0.0,
which is what a wedge looks like and also what a dead stream looks like — the
script has no way to tell those apart and reported a table of zeros as though it
were data. **If it is ever re-run, position in the office corridor first and
assert a non-zero control sample before trusting any row.**

**OPEN-20 — THE EXECUTOR NEVER WALKS DIAGONALLY, AND THE HUMAN ALWAYS DID.**
Raised 2026-09-05 by the user, who says this was the original point of the
walking-response work: *"get claude to walk diagonally instead of walking straight
then turning right and walking forward."* Nothing was ever built.

**The executor cannot steer with the left stick, by construction:**

    graph_walk.py:687   st.walk_leg(0.0, -abs(speed), dur, ...)
                                    ^^^ lx is a hardcoded literal zero

So every step of every leg is: turn the CAMERA to the step's bearing, then push
the left stick straight ahead. `slow_traverse.walk_leg` takes `lx` and
`walk_steps.walk_forward` takes `strafe` — the machinery is already there and is
used ONLY by the escape manoeuvres (`unstick`, the slip ladder, `goaround`), never
by a leg.

**The evidence that the human did the opposite is already in this file.** On
`portrait_room -> bar_pool_room` the recorded `cam` is constant to **0.13 deg**
across the whole leg while `bearing` spans **6.59 deg**. The human did not turn
the camera at all; they held it still and steered entirely with the left stick.
The same section notes the final leg's `cam` is 86.73-87.01 across all eight steps
while `bearing` swings 71.99 -> 97.63 -> 75.46. `bearing` = camera heading +
left-stick angle, and the executor throws the second term away.

**Why this is not a rediscovery.** GRAVEYARD's only strafe row is *"blind crabbing
to get around an obstacle"* — an unguided escape push when already stuck, not
replay of a recorded vector. And this is the OPPOSITE shape to both closed
families: "steering while walking" is a mid-push feedback loop converting heading
error into position error, while this is open-loop with the camera FIXED; and
"chunking a leg into more cycles" adds accelerations, while collapsing a
turn-then-walk pair into one diagonal push REMOVES a turn and an acceleration per
step. Both survivors in the graveyard move nothing; this moves less than what it
replaces.

**IT IS A REGRESSION, NOT A NEW FEATURE.** `route_follow.py:184` already replays
`leg["lx"]`/`leg["ly"]`. An earlier generation of this code steered with the left
stick and `graph_walk` dropped the term. That is a much easier thing to argue for
than a new capability, and it means the shape has been run here before.

**LEAD WITH TIME, NOT ACCURACY — the accuracy argument does not survive its own
data.** Per-leg lateral loss from the discarded term is
`office_door->portrait_room` **-0.260** units, `portrait_room->bar_pool_room`
+0.099, `bar_pool_room->bar_jukebox` -0.038, `dealer_table` -0.010,
`office_door` +0.020. **The leg with the LARGEST loss is the one that arrives
20/20.** So loss does not predict arrival, and this is NOT a clean explanation of
the two bad legs — an earlier draft of this entry let it read as though it might
be. What survives on accuracy is narrower: `portrait_room->bar_pool_room` has the
highest median angle of any leg at 5.9 deg, a consistent BIAS rather than
cancelling wobble.

The time argument is the strong one. Replaying the vector means one camera turn
per LEG instead of one per STEP — **5 turns instead of 40** — against `turn_to`'s
11.4s of an 85.6s trial (§8(h)).

**What it would take.** `route3_steps.json` already stores `cam` per step, so the
inputs exist. Hold the camera at `cam`, drive `left_x`/`left_y` as the recorded
vector, and the per-step turn disappears. Then A/B against turn-then-walk: 10
trials per arm, interleaved, verified arrivals, reported by failure class (§10.3,
§10.5).

**Note the left stick's DIAGONAL response is unmeasured.** §6's table is
`left_y`-only, so it does not cover this — see OPEN-19, which is why that one is
downgraded rather than closed.

**OPEN-21 — THE GOAL LEG IS NOT THE RECORDED LEG; the A/B against replaying
it is RUNNING (started 2026-09-07 09:35).** On every leg but the last,
`follow()` replays the recorded steps through `walk_link`. On the last it does
not: `approach_goal()` walks a straight line at `steps[-1]["bearing"]` (75.5,
10.6 deg off the leg's net direction of ~85) in 0.4s chunks with 0.3s sleeps —
the re-accelerating chunk shape GRAVEYARD records as walking a leg SHORT — for
up to 1.6x the recorded 4.07s, checking for the prompt as it goes; then
`reach_table()` sweeps. It predates the jukebox-leg restoration, when the table
leg started 0.7 units early and an over-long straight approach was the
workaround, and it has never been A/B'd against the recorded leg.

What OPEN-14 measured about it, from `overnight/streak_table.log` and
`overnight/census/table_leg_ends_20260907.json`: 37 executions, and in **37 of
37** the approach exhausted its budget ("stepped 6.8s of a 6.5s budget without
finding the prompt"); the prompt was found by stepping **0** times and by the
sweep **once** (trial 2). Of the 37 post-sweep frames, **17 were wedged** (7-11
keypoints); the visual census (two Haiku readers a frame, tiebreak on
disagreement) read dark 12 / bar counter 8 / floor 5 / NPC 3 / wall 1 / dealer
visible without prompt 4 / prompt 1 / unresolved 5. Pitch-down is a real
minority mode; the majority is pressed into the bar or into darkness.

**The arm:** `graph_walk.GOAL_LEG_AS_RECORDED` (ships **False**) routes the goal
leg through `walk_link` like every leg that arrives; the sweep still follows in
BOTH arms. Not a GRAVEYARD shape: it steers nothing mid-push and REMOVES a
chunked approach rather than adding chunks. **The harness:**
`overnight/ab_goal_leg.py` — shipped vs recorded, 10 trials an arm interleaved,
setup to `bar_jukebox` at attempts=9 (a setup miss is INVALID), ONE execution
of the leg through `_harness.walk_leg_under_test`, scored by `confirm()` =
`at_table()` on the post-sweep frame plus an `at_table()` re-read, 1200s
external ceiling, Fisher exact. Result: `overnight/ab_goal_leg.json`, log
`overnight/ab_goal_leg.log`, frames `overnight/goal_leg_failframes/`
(`at_dealer_table_*` = PRE-sweep leg end, admissible; `_postsweep_*` = what
`confirm()` judged; `success/ok_*` = the leg end on arrivals).

Two evidence changes landed with the flag (da5b7ec), each behind a test that
drives `follow()`/`follow_verified` with stubs and four mutants caught: the
GOAL's leg-end frame is now captured and published BEFORE `reach_table`, and
`follow_verified`'s success frame became the published leg end instead of
`before`. **The second was half wrong, and the suite caught it the same
morning** (142/143, `test_success_control_frames.py`): `before` — the start
pose, which is why both OPEN-14 `ok_dealer_table` frames identified
`bar_jukebox` — was DELIBERATE, the control for the start-pose-variance
question in §8(i), and its own test says so. Replacing it threw one control
away to gain another. The fix keeps both on both outcomes
(`success/start_<node>` + `success/ok_<node>` on arrival, `start_<node>` +
`fail_<node>` on failure); it is written and waits in
`drafts/pending_after_ab/` until no live run imports `graph_walk` (10.21).

**RESULT (2026-09-07, 20 trials, paused once at 14 and resumed in the same
order): NO ARRIVAL DIFFERENCE, A THREEFOLD COST DIFFERENCE.** Scored two ways
(`overnight/ab_goal_leg.json`, `tools/goal_leg_sheet.py`):

    as the harness scored it (at_table after the sweep)   shipped 1/8   recorded 1/9   Fisher p = 1.00
    prompt ON SCREEN at the leg's end (pre-sweep frame,
      mask + OCR; the leg-level criterion)                 shipped 2/9   recorded 1/9
    leg time, median [range]                               189s [68..277]   65s [26..74]
    setup to bar_jukebox, median [range] (same code)       306s [59..974]   157s [58..1019]
    invalid                                                2 (setup miss, ceiling)   1 (setup miss)

Both arms miss about nine in ten. The executor is not the lever; where the
leg ends relative to the prompt zone is, and nobody has measured that zone —
`overnight/prompt_zone.py` does (agreed 2026-09-07). The recorded leg costs a
third of the approach per attempt, which matters for retry depth; that is a
reason to flip the flag for COST, not for arrival, and it is the user's call.
What the 18 pre-sweep frames show: the prompt on screen and missed by the
mask (trials 1, 6 — the OCR path fixes those), stopped short at an NPC (2),
walked into the neighbouring table (3), and a spread of near-table endings
without a prompt (the rest). The ceiling censored the shipped arm twice. If the recorded arm wins, the next run is the full-route streak with
the flag on — and OPEN-14's ceiling lesson applies: a goal-leg retry is a full
reset and route re-walk, so the ceiling must be attempts x route-time or the
goal leg needs local retries.

**OPEN-22 — THE PROMPT ZONE, MEASURED (2026-09-07): its near edge sits five
hundredths of a walk-unit AHEAD of where the recorded goal leg stops, the
prompt is screen-fixed and offered on proximity alone, and the leg's endpoint
scatters by a table width.** `overnight/prompt_zone.py` — a star around the
recorded leg's endpoint (the endpoint first, then 0.05u left/right, 0.10/0.20u
back, 0.05u forward, stick-relative, wedge-checked), five headings a point,
mask + OCR verdicts, three walks (`overnight/prompt_zone.json`,
`prompt_zone_points.jsonl`, frames `overnight/prompt_zone_frames/pz_w*`):

    walk 1   45 readings   no prompt   endpoint at the NEIGHBOURING table, dealer ~70 deg left
    walk 2   50 readings   no prompt   the neighbouring table again, the waitress in the passage
    walk 3   50 readings   endpoint: none at 5 headings; +0.05u forward: PROMPT at 4 of 5
             headings spanning 80 deg (mask 0.31-0.47 with ink 0.011; OCR 3 of 5)

The +0.05 frame shows the character facing a pillar and a grey wall with the
prompt centred on screen: the label is a HUD element and the game offers it on
distance to the dealer, not on facing. So heading was never the constraint of
the last leg — `reach_table`'s 19-heading sweeps were searching the wrong axis
— and the recorded leg, when it lands at the dealer's table, stops just short
of the zone. When it does not (walks 1-2, A/B trial 3) it lands at the round
table beside hers, from the pose it was given at the jukebox.

**Three launches before this one measured nothing, from two instruments of
mine:** `len(places.keypoints(img))` is 2 (a (keypoints, descriptors) pair), so
every point read "wedged"; and `tools/prompt_ocr_ab` set `BASEBALL_TEST_RUN`
at import, switching stick injection off inside the live harness after the
leg (§5, §10.1). Both fixed and pinned; the fourth launch is the first valid.

**Today's setup census** (`overnight/census/setup_leg_ends_20260907.json`, 315
leg-end frames from the route walks): the JUKEBOX leg ended WEDGED in 69 of
106 executions (median 10 keypoints) against 3 of 77 on the pool-room leg —
that is why reaching `bar_jukebox` took 2-8 attempts and up to 1065s today
where OPEN-5 had 9/9. Unmeasured whether it is session variance or the
restored leg's own endpoint; the frames are on disk.

**(b) IS CLOSED AS DESIGNED (measured on Snoopy, 2026-09-07 evening):** the
neighbouring table cannot be a localiser-confirmed node. Ten references at the
landing pose (five headings x two walks) fail leave-one-out at ratios 1.00-1.22
against `MIN_RATIO` 1.35, with `bar_jukebox` the runner-up every time and one
frame naming it outright; non-disruption (333 frames) and discrimination from
the dealer's table both pass (`overnight/census/side_table_refs.json`,
`tools/side_table_refs.py`). It is the office corridor/door shape: a table
apart looks the same to ORB. What survives of (b) is the PATH from that landing
to the prompt, measurable without naming (`overnight/side_table_leg.py`), and a
correction that fires on "no prompt after the extension". **Also refuted the
same evening** (`tools/landing_signature.py`, 38 landing frames on Snoopy): the
idea that `identify()` after the goal leg tells the two landings apart — most
landings of BOTH kinds read None at 60-136 matches; only one walk's side-table
frames named `bar_jukebox`. There is no cheap landing classifier.

**Candidates, each an A/B, none built:** (a) extend the recorded goal leg by
~0.10u — the edge is at +0.05, walk 3's +0.05 point was not wedged; (b) give
the neighbouring table a place name from these frames and record the short leg
from it to the dealer, so the router finishes from wherever the leg lands;
(c) the jukebox leg's wedge. (a) is one constant and moves the character 0.1u;
(b) is the project's own machinery; (c) is the setup killer. The order is the
user's call.

