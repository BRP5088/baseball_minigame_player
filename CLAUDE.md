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

**The PS5 dashboard overlay says `▢ Resume Game` — that is SQUARE, not Cross.**
Cross navigates *into* the game card instead.

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

**Capture geometry changes under you.** One session produced both 1867x1050 and
1920x1080 captures, and row calibration is not robust to that — at 1920x1080
every row scored ~0.55 because the bands landed on the page instead of the text.
Anything reading fixed regions must be checked against BOTH geometries.

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

Game rules:

- A hit needs the batter's power to beat the pitcher's; beating it by **3+** is
  an automatic home run. Margin does not otherwise matter.
- Only SWING_BOOST and PITCH_BOOST add power. Speed and fielding boosts have a
  nonzero bonus that adds NO power — analysis needs the tactics KIND.
- **Runners can be lapped**: this game lets base runners pass each other, so
  real-baseball intuitions about ordering are unsafe.
- A match is 5 rounds and allows 2 discards.
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

## A STALE match_in_progress SPENDS AN UNTRACKED $50

Reproduced 2026-09-04. When the flag is stale and a real dealer prompt is on
screen, orchestrator's recovery path presses `start_match` believing the $50 was
already paid: the money leaves the in-game wallet, `balance` is never debited,
`save_progress` is never called, and **`max_spend` cannot stop it** —
`run_one_match.py`'s promise that "no new money is ever spent, whatever the
tracked balance says" does not hold in that state.

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

**19. SAVE PATCH SCRIPTS BEFORE EXECUTING THEM.** When an agent writes a script
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

