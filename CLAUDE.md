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

    .venv/bin/python Bretts_walk.py doctor
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

`.vscode/launch.json` pins `.venv` on all 15 debug profiles.

**`tesserocr` IS a requirement** (`requirements.txt:33`) — pip installs a
prebuilt wheel, no compiler needed. Only `pygame` is deliberately excluded
(imported inside a function in `record_input.py`).

### Bretts_walk.py — one entry point, one subcommand per task

    where        report position — MOVES NOTHING, safe any time
    doctor       chiaki, FIFO, streaming, frozen, current frame, runaways
    connect      bring chiaki and the stream up, restarting what is wedged
    reset        reload the save and stand at the spawn
    walk         the full route   (--reset --shots --start --attempts)
    last-mile    Wanda -> corner -> jukebox -> table
    sweep        grid-search the last-mile durations, unattended
    record-leg   walk a leg and save it ONLY if the destination is confirmed
    label        save the current view as a reference for a place YOU name
    brett-walk   drive the hand-walk script

`label` and `record-leg` refuse bad input on purpose: `label` rejects a frame
under 200 keypoints, and `record-leg` refuses a leg whose destination the
localiser did not confirm — routing plans through a bad edge forever.

### Hand-walking: brett_walk.py

The user drives; write moves in `moves(w)`:
`turn/forward/back/right/left/jump/press/wait/look/mark`.

- **It records automatically** to `world_log/<stamp>_<name>/`, so a hand-walk is
  something `map_build.py` can turn into legs.
- `w.mark(name)` saves the frame as a place reference and REFUSES under 200
  keypoints — a near-blank reference matches every other blank frame.
- `w.back()` cannot go through `walk_steps.walk_forward` — that does
  `-abs(speed)`, so a negative magnitude still walks forward. It drives the
  stick directly.
- Pushes are chunked at 0.8s because chiaki drops injected input after 5s.
- `walk()` refuses to start without a live picture: capture with no game window
  returns the desktop.

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
- **A test that passes when the code is broken is worse than no test.** After
  writing one, break the thing it guards and confirm it fails.
- Do not swap in convenient fixtures to make a test green.
- `world_log.py` records a mapping walk; `map_build.py` turns it into legs
  offline. Mapping frames stay out of `screenshot_log/` — all three archives
  there are match-playing runs.

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
(`pause_menu.py:121,130`). Verified: it now returns "Load Last Save" on the
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
meaning. Under `MAX_TIMED_HOLD` (4.5s, below `INJECT_TIMEOUT_MS`) a hold needs
NO chunking.

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
(`places.py:210-211`). When the character genuinely stands at a node it names it
with a **2.6-5.3x margin** (leave-one-out: 249-698 matches). Held-out check
after the node-set rebuild: 18 correct / 6 abstain / 0 wrong, every abstention
±1s from a node.

**Do not lower these thresholds.** The failures are POSITION failures, not
recognition failures.

- **`dealer_table` is a POSE, not a place.** Its identify() margin is the prompt
  TEXT. Confirm arrival with `table_prompt.at_table()`, never `identify()`.
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

Profiled, one clean routed trial (85.6s total — NOT the same quantity as the
338s streak trial, which includes resets and retries):

    read_bearing            52 calls   18.1s   21.1%
    reset                    2 calls   17.9s   20.9%
    turn_to (incl sleeps)    6 calls   11.4s   13.3%
    capture                135 calls    5.0s    5.8%
    identify + keypoints                0.6s    0.8%

`read_bearing` was the largest component because `ocr_glyphs` was falling back
to shelling out to the `tesseract` binary. With `tesserocr` installed it went
**261ms -> 31ms (8.4x)**, ~12s off a trial, with no added variance. Correctness
was verified, not assumed: 208 glyph crops across 3 recordings match EXACTLY.

`ocr_glyphs._api()` keeps a per-thread `PyTessBaseAPI` with the traineddata
loaded once, so **it already IS a persistent worker** — 134ms first call, 23ms
steady. There is no per-call spin-up left to remove; a daemon would add moving
parts for no gain.

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
directly on the stream, first day. No admissible frame has yet captured it.

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
accelerations, same distance. See OPEN-3.

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

**11. A TEST MUST NOT ASSERT AGAINST THE CONSTANT IT IS GUARDING.** Checking
`mag_for(x) <= USABLE_MAX` rises with `USABLE_MAX` and passes forever. Pin the
literal.

**12. BEWARE THE VACUOUS STATISTIC.** "68 of 68 turn steps had |want - got| <=
4.0, so 100% are no-ops" is CIRCULAR — `turn_to` only returns once the error is
inside tolerance, so that inequality holds BY CONSTRUCTION. It looked
devastating and measured the loop's exit condition. The real version compares
the spread of COMMANDED bearings against the spread of ACHIEVED headings.

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

Six tickets were worked offline on 2026-09-05, each in an isolated worktree and
each re-checked by a second agent that ran its own mutants rather than trusting
the first. **Where a checker downgraded a claim, the downgrade is what stands
here.** Two closed on evidence, one was CANCELLED rather than run (OPEN-3 — that
is the most valuable result of the day), and three are partially closed with the
remaining half named.

**Numbering note for whoever merges those worktrees.** Two of them independently
filed a NEW ticket as "OPEN-15", and a third produced the compass work. The
numbers here are the authority: **OPEN-15 is the compass reader**, **OPEN-16 is
the injector release window** (the `tests/cpp/` worktree calls it OPEN-15), and
**OPEN-17 is the arrival heading** (the OPEN-3 worktree calls it OPEN-15). The
worktrees' own copies of this file are superseded by this one — take THIS §11 and
discard theirs rather than merging five conflicting versions.

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

**REMAINS, and it needs the console.** Not one `at_<node>_<epoch_ms>.jpg` or
`success/ok_*.jpg` exists — the path has never executed live. **And read the
right key**: `failures_by_kind` still exists, still mixes fallback frames in, and
is still what every harness surfaces, while NOTHING reads
`failures_by_kind_leg_end`. A correct number nobody looks at is this project's
own signature failure wearing a different hat. Acceptance test unchanged: a real
jukebox-leg failure frame must NOT read bearing ~286 and must NOT identify as
`bar_pool_room`.

**OPEN-2 — CLOSED 2026-09-04.** `chiaki-patch/` now holds all five edits:
`gui/CMakeLists.txt` and `gui/src/main.cpp` were copied in (they had existed
only as prose here), and the README points at `cd chiaki-ng-src && git diff` as
the authority. The stale half-size twin `chiaki_patch/` (underscore — its
`injectinput.cpp` was 4,100 bytes against the real 9,684, one keystroke away on
tab-complete) is in `_obsolete/`.

**OPEN-3 — CLOSED 2026-09-05, DROPPED WITHOUT RUNNING IT.** `LEG_TURN_TOLERANCE`
ships `None` — unchanged, i.e. `slow_traverse.TURN_TOLERANCE = 4.0` — and the
20-trial A/B this file called "the highest-value navigation experiment available"
is CANCELLED. Settled offline from the recordings, as the `cam` section above
demanded. (`None` must still never reach `st.turn_to`: `abs(err) <= None`
raises.)

**The mechanism is REAL. It is also worth a few percent of a leg.** Both halves
are measured, and the second is why this is dropped rather than run. Scored the
one non-vacuous way (§10.12 — the spread of ACHIEVED headings, never
`|want - got|`), the two live traces `graph_walk` recorded for
`portrait_room -> bar_pool_room` in one run read: commanded 286.57 / 292.18 /
285.59 / 287.59, spread 6.59 deg; the FAILED attempt achieved 289.1 four times,
spread **0.00**; the SUCCEEDED attempt 286.2 / 290.1 / 288.1 / 288.1, spread
3.90. So the tolerance really does flatten the recorded curve to nothing. But
integrated at the recorded speeds and durations those two traces end **0.0021
walk-units apart on a 0.7203-unit leg**, and the FLAT, never-turned trace was the
MORE faithful to the recording's own endpoint (0.0011 against 0.0022). Whatever
separated those two attempts, it was not the heading.

**The premise was also wrong about what the curve IS.** `graph_walk.walk_link`
calls `st.walk_leg(0.0, -abs(speed), ...)` — `lx` hard-coded to zero — so the
executor CANNOT strafe mid-leg, and it reproduces the human's travel direction by
turning the CAMERA to a heading the human never held. Over all 64 inter-step
transitions in both recordings, `|delta cam|` exceeds 4 deg on **1**, while
`|delta bearing|` exceeds it on **23**. Twenty-two of the twenty-three "curves"
are the human's left thumb. Tightening the tolerance makes the executor chase
thumb jitter: on `bar_jukebox -> dealer_table` it would sweep the camera 25.6 deg
over 4.07s of walking, where the human held `cam` at 86.8 ± 0.14.

**COST, priced the honest way — quote 6.79% and 0.258 units, never 2.63%.** The
first pass under-priced this 2.6x by seeding each leg exactly on its first
commanded bearing. `turn_to` compares against the MEASURED heading, so a leg also
STARTS up to `tolerance` off and is walked there until some step exceeds the
band — which is the second half of this ticket's own stated mechanism, and it is
the case the single real trace shows (commanded 286.57, character at 289.1, entry
turn a NO-OP). Swept adversarially over the permitted entry offset, discarding
sub-4-degree turns costs **6.79% on the worst leg**, and tightening 4.0 -> 1.0
buys **0.258 walk-units over the whole route**. For scale, the leg-distance pin
accepts 15%, and the shortfall that genuinely broke the jukebox leg was 0.703 of
1.031 units — **68%**.

**The arithmetic that ends it.** At the §8(a) baseline of 0.60 and 338 s/trial,
detecting +2 percentage points at 80% power needs ~9,300 trials per arm, about
1,750 console hours; +5 points ~1,470 per arm; +10 points ~360. Ten per arm can
only see an effect of about +30 points. There is no version of this experiment
that fits in the time available and could detect the effect the mechanism allows.

A hard floor nobody had noticed, worth keeping: `turn_curve.plan_turn` returns
`(0.0, 0.0)` under 0.5 deg, so `turn_to` can never satisfy `abs(err) <=
tolerance` below that — it breaks out and files an UNDERTURNED hazard on every
step of every leg. Against a perfect simulated console, tolerance 0.40 filed 297
of 2800 and 0.0 filed all 2800. **The usable range is (0.5, 4.0].**

Pinned by `tests/routing/test_leg_curve_is_stick_not_camera.py`, which re-derives
the whole argument from `route3_steps.json`, `route2_steps.json` and
`world_map.json` rather than restating it — including that each map leg IS the
corresponding route3 slice, since everything else attributes route3's `cam` to
the map's legs.

**THIS CLOSURE ORPHANS A USER OBSERVATION.** `graph_walk`'s own
`LEG_TURN_TOLERANCE` comment claims this mechanism explains §8(k) — "you actually
walk right out of the bar". A few percent of a leg's displacement cannot do that,
so §8(k) is back to having NO candidate explanation, and that comment now asserts
something this closure disproves.

**The NO-OP/TURNED instrument (2026-09-04) has never actually run.**
`slow_traverse.turn_to` logs every exit, paired:

    turn to 292.2: NO-OP, already inside 4.0 deg (at 289.1, err +3.1) —
                   nothing was sent, the recorded curve was discarded
    turn to 292.2: TURNED to 292.0 (err +0.2) in 1 push(es)

but no log, transcript or json on disk contains either string, so nothing can be
re-scored — do not try. It costs nothing and answers the mechanism question a
caller's step line never can (an executed turn also ends inside tolerance, which
is precisely why this was invisible). **Let it ride along on whatever A/B runs
next.**

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

**Fix the start node before re-running OPEN-14.** Measuring a leg you reach 0 of
3 times spends an hour per arm to record INVALID.

**OPEN-14 — Does the RESTORED jukebox leg move arrival?** The leg was 4.3x too
short and could not reach its destination; it is now back to its recorded
1.031 units over 3.30s. This is the strongest candidate yet for what has been
costing the route, and it is UNMEASURED. Run it FIRST, before the other open
A/Bs: if arrival moves, several of those experiments are asking the wrong
question. 10 trials, scored on verified arrivals, reported by failure class.

**THE HARNESS IS NOW READY (2026-09-06). Both blockers are fixed; do not
re-apply them.** `ab_jukebox_leg.py` walked the leg under test with
`gw.walk_link`, which publishes no leg-end frame, so as written it collected NO
evidence about the leg it exists to test (OPEN-1); and it reset twice a trial
for want of `start_hint`. Both are fixed, in `overnight/_harness.py` rather than
in the script, so the next harness cannot re-copy them:

`_harness.walk_leg_under_test()` runs ONE attempt through `follow_verified` —
one attempt, because the retrying primitive is a different quantity (OPEN-4,
10/10) and retries would hide exactly the difference this A/B looks for. It
returns the census SPLIT BY PROVENANCE, and counts recovery-fan rescues
separately from arrivals, because a rescued trial travelled ~7x the leg's
distance and is not evidence the leg arrives. `_harness.report_leg_arm()` prints
both censuses so a shrinking denominator is visible rather than silent.
`ab_stall_on_restored.py` had the identical defect and now shares the same path.

Pinned by `tests/harness/test_leg_under_test_collects_evidence.py`, which
asserts on CALLS through a stub rather than on source text — the older
substring-matching guard passes when the bug is re-introduced.

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

**OPEN-4 — ANSWERED 2026-09-06. `go_to_node_verified` arrives 10/10.**
`overnight/measure_primitive.py`, n=10, target `bar_pool_room`, attempts=3:
**10 valid, 0 invalid, 10 arrived, median 52.9s**, and `locate()` agreed with
the primitive on every trial (zero disagreements). Config as shipped:
`TRUST_RESET_SPAWN` True, `RECOVER_MISSED` True, `NULL_YAW_BEFORE_ALIGN` True,
`REFERENCE_POSE` "bot". Result in `overnight/primitive_open4.json`.

So the two quantities really are different, and the one that matters is the good
one. The ~55% figure is a SINGLE WALK; the retrying primitive is what everything
downstream should use, and it is not the bottleneck. The earlier "4/4 at ~75s"
is superseded — 52.9s is the median now that the spawn hint removes the wasted
sweep and second reset (OPEN-8 cut 1).

**What this does NOT say.** It is one leg from a reset, not a route, and it was
measured in one session — §10.5 warns that route performance has a large
session-to-session component. It does not license quoting 100% for a full
route: §8(a) still measures 6/10 there.

**OPEN-5 — Is `attempts=9` better than `attempts=3`?** Run 1 was inconclusive
and contaminated: attempts_9 2/3 valid (3 of 6 trials invalid on a 420s
timeout), attempts_3 3/6, and both arms collapsed in the second half while
chiaki logged 32,388 decoder-overflow lines. Retry is the only lever the
arithmetic says can reach the target. `overnight/ab_attempts.py` is prepared at
TRIALS=10, TIMEOUT=900, `log=log` — add `start_hint=gw.SPAWN` before starting it
(OPEN-8), or every trial in both arms pays ~24s for a reset it does not need.
**Note the interaction with §10.14**: this arm's whole mechanism is "spend
longer", so the timeout must not censor it — the previous run lost 3 of 6
deep-arm trials to a 420s ceiling.

**OPEN-6 — Three flags have never been tested live, and one of them has no
premise left.** `SURVEY_WHILE_WALKING` is `False`, and its premise —
"the OVERSHOT class, a quarter of failures" — is now **WITHDRAWN, not merely
doubted**. That figure is 2 of the 8 post-fan frames, which are inadmissible as
evidence about a leg (OPEN-1); and even taken at face value 2/8 is a 95% Wilson
interval of **[0.07, 0.59]**, so it never distinguished "a quarter" from "a
twentieth" or "half". **Nothing may quote a class distribution until a run
produces `failures_by_kind_leg_end`.**

`SPEED_FROM_RELIABILITY` and `RECORD_RELIABILITY` are confirmed correct at
`False`, demonstrated rather than argued: 12 recorded arrivals make
`leg_reliability.scale_for` return 3.0, and ONE subsequent failure returns it to
1.0 (11/12 = 0.917, under `MIN_RATE` 0.95). With both on, `follow_verified`
writes the outcome it is measuring and `leg_scale()` reads it back, so trial N's
walking speed is a function of trials 1..N-1 and an interleaved A/B's two arms
share one store. `leg_reliability.json` does not exist on disk — neither flag has
ever run live.

Audited for the same shape and reported, not changed: `compass._SCALE_CACHE`
(`compass_scale.json`) and `input_controller._VIEW_CACHE` (`view_bounds.json`)
are both written mid-run and read back, and the view cache is a "widest lit
extent ever seen" ratchet that moves the view centre and hence every bearing.
They calibrate the DISPLAY, not the outcome — no arm can move them
differentially and they converge, so interleaving absorbs them. Two footnotes
that will bite someone: neither write is suppressed by `BASEBALL_TEST_RUN` (an
offline analysis pass added a live geometry's key to a worktree's copy), and
`leg_reliability`'s `STORE` is bound into default arguments
(`def rate(a, b, path=STORE)`), so monkeypatching `leg_reliability.STORE` to
redirect the file silently does nothing. No caller does that today.

**WHAT THE CENSUS RUN COSTS.** `follow_verified` stops at the FIRST unproven
node, so a trial yields AT MOST ONE classified failure. At the §8(a) measured 6/10
route arrival that is 0.4 failures a trial, and at 338 s/trial:

    half-width   failures needed   full-route trials   hours
      ±20pp          16-21               ~40            ~3.8
      ±10pp          69-93              ~230           ~22
      ±10pp, simultaneous over 4 classes   150   ~375  ~35

A single-leg harness at ~90 s/trial reaches ±20pp in about an hour. **Take the
±20pp run.** It is enough to kill or keep "OVERSHOT is a quarter", which is the
only decision queued on this number, and ±10pp costs six times as much to answer
a question nobody is asking.

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

**OPEN-10 — CLOSED 2026-09-04.** `_something_moved` is deleted, and
`tests/harness/test_no_undefined_names.py` now scans every non-vendored module
for names nothing binds — it has a positive control, so it cannot pass by
finding nothing. It earned itself immediately: deleting that function as a
block also took `SLIP_STRAFE`, `SLIP_STRAFE_SEC`, `SLIP_PUSH_SEC`, `SLIP_JUMPS`,
`GEOMETRY_MAX_KEYPOINTS` and `SKIP_LADDER_ON_GEOMETRY` with it, which would have
raised `NameError` on the first blockage. The lint caught it in minutes.

**OPEN-11 — CLOSED 2026-09-05.** `tests/cpp/` is wired in by being a
`tests/**/test_*.py` file, which is exactly what `run_tests.sh`'s own `find`
discovers — so **`run_tests.sh` itself needed no edit**: no special case, no
second list to keep in sync, and the runner's kill ceiling, live progress line
and `BASEBALL_TEST_RUN` all apply for free. A driver compiles and runs the C++
and scores its output. **It never skips**: absent `clang++`, absent
`chiaki-ng-src`, a compile error, a binary that prints nothing, a missing SUMMARY
line, a stub run, or a timing check that could not be sampled are each a FAIL
naming the fix, because a check that silently declines is worth less than none.

Three things it now guards that the remembered `clang++` line never did.
**DIVERGENCE**: all five patched files are compared BYTE FOR BYTE against the
sources the application actually builds — `tests/cpp/` had been compiling
`chiaki-patch/injectinput.cpp` while the app builds
`chiaki-ng-src/gui/src/injectinput.cpp`, with nothing keeping them equal, and the
failure names both paths and points at `cd chiaki-ng-src && git diff` as the
authority. The file list has a guard on the guard: trimming it below five pairs
fails, so deleting a row cannot quietly disable the check. **TIMING**: the old
assertions were "sleep, then assert still held", with 20-70ms of margin against
150-200ms deadlines — a threshold sitting inside one population (§10.4). Every
timing assertion is now bounded by a clock this process measures, so load can
only make a check INCONCLUSIVE, never a false pass, and the sleeps that waited
for a FIFO line to land are replaced by marker barriers (lines are parsed in
order, so a marker written after a line proves that line was parsed).
**LIFETIME**: one writer `FILE*` is held open for the whole run. Per-line
open/close gave 3 bad runs in 20 (one `SIGPIPE`, exit -13) because the injector's
reader is fopen / fgets-to-EOF / fclose / repeat, so a line written into the
re-open gap is lost — which is also why `analog_replay.open_stream()` holds one
handle.

The result worth keeping: reintroducing the historical 1.4s-turn bug — an untimed
sibling axis cancelling a timed hold — fails a CORRECTNESS check while its timing
half passes. That is the point of the split. Load cannot turn that regression
into a shrug. **No check count is quoted here**; the test prints its own, and the
"13 checks" this entry used to claim was already stale by four.

**Caveat found on review, and it is the project's own signature failure.** One of
the three timing checks has NO load-proof correctness twin: `clear` setting
`active = false` — the exact regression the release window exists to prevent —
produces zero correctness failures and only an INCONCLUSIVE. The run still exits
non-zero, so it is a misdiagnosis rather than a silent pass, and the message now
names both possible causes and asserts neither. **Do not restore the wording that
blamed the machine.** Separating "the window never opened" from "no tick landed
inside it" needs `RELEASE_MS`, which lives in an anonymous namespace and cannot
be read from the test; guessing it would put a threshold inside one population.

Two standing costs. `chiaki-ng-src/` is gitignored, so this file HARD-FAILS on a
machine without it — deliberate, since an unverifiable claim is not a passing
one, but it means a fresh clone has one failing test until that tree is present.
(An earlier version of this paragraph said `tests/cpp/probe_release_window.cpp`
was "the only evidence for OPEN-16" and could rot. That file no longer exists
anywhere on disk or in git history — it BECAME two checks inside
`tests/cpp/test_injectinput.cpp` that the suite now runs every time, as the
OPEN-16 entry below already records. The sentence contradicted its own ticket
and pointed at nothing.)

**One hole found on re-verification 2026-09-06 and CLOSED.** The file list was
guarded by COUNT (`len(PATCH_FILES) >= 5`), which catches a deleted row but not
a REPLACED one: swapping the `main.cpp` row for a second copy of the
`injectinput.h` row keeps the count at five, leaves `main.cpp` compared against
nothing, and prints "all green" with a drifted patched file. `len(set(...))` is
defeated too, by a near-duplicate (`"./injectinput.h"`) that is a distinct tuple
naming the same file. The list is now asserted to COVER exactly the contents of
`chiaki-patch/` minus README.md. All three attacks fail by name.

**OPEN-12 — CLOSED 2026-09-05.** `ocr_glyphs` gained a word mode
(`image_to_text(image, psm, whitelist)`) sharing the existing persistent
per-thread `PyTessBaseAPI`, and orchestrator's four local OCR call sites now go
through one `orchestrator._ocr_text`: `ocr_ban_card_name`, `ocr_scoreboard` and
`ocr_runner_card` at PSM 6, `read_ban_counter` at PSM 7 with the `0123456789/`
whitelist. `ocr_glyphs.tesseract_config` is the ONE definition of the config
string, so the fast path and the pytesseract fallback cannot drift into asking
different questions; it reproduces the pre-migration literals exactly. A
warn-once fallback stays behind it, and it says WHY the run got slower, because
nothing else does.

**THE HAZARD WAS THE HANDLE CACHE, not the recognition.** `_api()` was keyed on
the WHITELIST ALONE, from when the module only ever asked PSM 10 — so a
word-mode call would be handed back a SINGLE_CHAR handle and return ONE
CHARACTER of a player's name, correctly, forever. It is now keyed on
`(psm, whitelist)` with a bounded LRU, because the ban screen alternates PSM 6
and PSM 7 and a re-`Init` costs ~134ms against ~23ms warm.

**Evidence, and it is function-level rather than string-level**: 137 answers
computed from LIVE IN-MEMORY crops in both the migrated tree and a baseline
worktree at HEAD — 110 ban card names over 11 real ban frames, 11 ban counters,
4 scoreboards, 12 runner names, 71 of them non-null — **zero differences**.
Corroborated in aggregate: `test_ban_ocr_confusion`'s 110-cell corpus gives
**63 correct / 0 wrong / 47 abstained in BOTH arms**, the same numbers this
project already recorded from the pytesseract era, in 229.8s against 4.8s on the
same machine — with the baseline getting eight threads and the migrated path
one. Ground truth for the new fixture was recorded from the SLOW path, so the
agreement test is not measuring itself.

**A MIGRATION LIKE THIS BREAKS TEST SEAMS SILENTLY.** Two tests stubbed
`orchestrator.pytesseract.image_to_string`, which after the migration is never
consulted — so the code really OCR'd a blank grey probe and abstained, and every
MUST_ABSTAIN case passed FOR THE WRONG REASON. Only the MUST_RESOLVE half, which
exists to catch over-strictness from the other side, exposed it. Both seams now
stub `orchestrator._ocr_text`. Reverting either one by hand reproduces
"18/18 resolved correctly" over a blank square.

**The 8-worker thread pool in that file is gone and must not come back.**
`tesserocr` links `cysignals`, whose `sig_on`/`sig_off` is process-global and
main-thread-only, and backend selection imports `tesserocr`, which installs a
SIGINT handler that `signal.signal` refuses off the main thread — so a
worker-first call silently drops the WHOLE PROCESS back to spawning subprocesses.
Nothing in the match or navigation path drives OCR off the main thread, so this
costs nothing real: serial and in-process beats eight threads and subprocesses on
this machine by ~48x.

Do not quote a per-read speedup from a loaded machine. The quiet-machine pair is
still 193ms against 79ms; the 13.6s-per-read figure measured during this work is
Sophos plus saturation deleting a temp file, caught with a `sample` stack showing
2671 of 2671 samples inside one `unlink`. The claim worth repeating is "identical
answers, and the fast path never touches the filesystem". Still shelling out,
deliberately out of scope and recorded so they are not lost: `reset_env`'s
`give_up_dialog` — **on the LIVE path**, and the best remaining candidate — and
two sites in `landmarks.py`.

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

**OPEN-16 — CLOSED 2026-09-05.** Fixed, pinned by a mutation-tested check, and
verified on the rig against a rebuilt binary.

`Apply("clear")` armed `release_until = NowMs() + RELEASE_MS` (100ms) and nothing
ever disarmed it. A later write set `active = true` and left the deadline
standing, so when it expired `InjectInputActive()` ran its release path on the
FRESH input: `active = false`, `has_left = false`, `has_right = false`. chiaki's
pump is `if(InjectInputActive()) SendFeedbackState()`, so it then stops sending
and **the console keeps the last state it received** — the deflection — while the
hold's own deadline expires inside the injector and is never transmitted.

    gap 400ms (outside the ~100ms window)   12/12 correctly released  [control]
    gap  30ms (inside it)                   12/12 STILL DEFLECTED
    gap  90ms (inside it)                    9/12 deflected, 3/12 push dropped

**THE RUNAWAY GUARD CANNOT SAVE IT.** `INJECT_TIMEOUT_MS` is evaluated inside
`InjectInputApply`, which the pump has stopped calling — so the 5s bound that
exists precisely to stop a stick being held forever is unreachable in the one
state that needs it. That is the sharpest form of this defect and is worth
remembering as a shape: **a guard that lives downstream of the switch that
disables it.**

**The fix is one line:** `g_inject.release_until = 0;` on the non-clear path of
`Apply()`, beside `g_inject.active = true;`. In BOTH copies
(`chiaki-patch/injectinput.cpp` and `chiaki-ng-src/gui/src/injectinput.cpp` —
`tests/cpp/test_injectinput_cpp.py` compares them byte for byte).

**Pinned by `tests/cpp/test_injectinput.cpp`**, check *"a write inside the window
SURVIVES the window expiring"*. Mutation-tested: deleting the one line produces
exactly that one FAIL and ZERO inconclusives — so unlike the sibling
release-window check, which can only report INCONCLUSIVE, this one has a
load-proof verdict. It goes INCONCLUSIVE rather than passing when load pushes the
write outside the window, because outside the window there is no bug to find.
`probe_release_window.cpp` became this check and is deleted.

### Verified on the rig

Incremental rebuild 29s (not the 15 minutes a clean build costs).
`restart_chiaki.sh` installed and re-signed it; `nm -U` shows
`InjectInputStart/Apply/Active`; Circle closes the pause book and OPTIONS opens
it. Then the defect's own scenario, using a CAMERA turn so nothing could move
position — `clear`, wait the gap, one timed `right_x 16000 600`, compass read at
+2.0s and again at +4.0s:

    gap 400ms (control)   turned 7.49 deg, then a further  0.000 deg
    gap  30ms (the bug)   turned 7.21 deg, then a further -0.026 deg

Both arms turn the same amount and both stop dead. Bearing went 86.8 -> 101.5,
which is 7.49 + 7.21 exactly.

### Live reachability: latent on the route, LIVE in one harness — FROM NOW ON

Grepped every `clear` written to the FIFO (`ar.clear()`, `ar.send(["clear"])`,
`inject_reset.clear()` — 30 sites, more than the 11 first checked).

- Every site on the production route is TERMINAL: a `return`, a `raise`, a log,
  or a harness `finally:`. The shortest gap on a live walking path is
  `brett_walk._push` (:277), which clears inside its 0.8s chunk loop and then
  sleeps `walk_steps.SETTLE = 0.25` plus a capture — ~290ms, outside.
- **`overnight/walk_curve.py:52` is inside the window.** It loops
  `ar.send(["clear"])` straight back to the top and the next stick write is two
  `fast_capture()` calls later — ~75ms at the 37ms/capture from §8(h). The only
  site of that shape. Note `ar.clear()` also CLOSES the FIFO, so a reopen sits
  between it and any following write; `ar.send(["clear"])` does not, which is why
  the reachable site is one of the latter.

**THIS DOES NOT IMPLICATE §6's WALKING TABLE, AND AN EARLIER DRAFT HERE SAID IT
DID.** `overnight/walk_curve.json` is dated 2026-09-04 13:00 and its contents ARE
that table; the release window was added 2026-09-05, so the run predates the
defect. The claim was made by reading the call site and never checking that the
mechanism existed when the measurement was taken — a mechanism that makes sense
is not evidence (§10.2). Git cannot date this for anyone: the repo's history
begins at "Initial commit: Auto Baseball" because git was added on 2026-09-05, so
`git log -S RELEASE_MS` returns that commit for everything and READS AS THOUGH THE
CODE WAS ALWAYS THERE. File mtimes and the run's own JSON are the datable
artifacts here.

**The question it does open is still open — see OPEN-19.**

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

**OPEN-18 — CLOSED 2026-09-06. `streaming()` no longer reports UP on chiaki's
own window.** The whole ticket was blocked on one missing frame, and capturing it
took thirty seconds once chiaki was running.

`test_fixtures/not_streaming/hostlist_standby.png` is the live chiaki window
showing `State: standby`, at the rig's own 1867x1050. `find_bar` fires on it;
before today `streaming()` therefore answered **True** on it in 0.0s. It now
answers **False**. Demonstrated as an A/B on that one frame:

    without the guard   True   via find_bar          0.0s
    with the guard      False  nothing answered     25.3s

**THE DISCRIMINATOR IS NOT ABOUT THE COMPASS, deliberately.** Qt draws flat
fills: large areas of one exact RGB value, and bands running the full width.
H.264 never does — quantisation dithers even a dark room, so decoded video holds
no long exact runs. A compass-shaped test would have rejected ban screens and
gameplay, where no compass exists and the stream is perfectly healthy.

Measured over 848 real streaming frames (demos, screenshot_log, explore,
overnight, places; 65 of them pause screens) against the live host list plus the
70 non-game images `find_bar` fires on:

                              streaming: p50    p99     MAX  |  host list
        flatness                  0.0357  0.1131  0.2949  |  0.6678
        widest exact row run      0.1208  0.3917  0.6208  |  1.0000

`UI_FLAT_FRAC = 0.25` and `UI_ROW_RUN_FRAC = 0.50` sit between the two, with the
host list clear by 2.7x and 2.0x. **Held out properly** — thresholds fitted on
half the streaming frames and scored on the other half — gives **0 false
positives on 71 non-streaming frames and 1.2% false negatives**.

**WHY THE FALSE NEGATIVES ARE CHEAP, which is what makes this safe.** Rejecting
the `find_bar` branch does NOT return False. It falls through to
`_heartbeat_seen()`, the console's own word and better evidence than pixels,
which returns on the first heartbeat (~0.4s). So a real stream whose frame
happens to be flat still answers True a moment later. The standby host list has
no session, therefore no heartbeat, and comes back False after the full 25s —
paid only on the path that was about to give up anyway.

Pinned by `tests/rig/test_streaming_rejects_chiaki_ui.py`, which carries the
control (without the guard it must still answer True via find_bar, or something
else is producing the False) and a ceiling on how many real frames may be
rejected. Three mutants, each caught by a different check: raising the gate,
removing the guard, and making the check always True.

**One honest limit.** Six captures 1.5s apart were BYTE-IDENTICAL, so the
negative side is ONE distinct frame, not six. It is the frame that matters — the
state that cost an hour — but chiaki's settings dialogs and its non-standby host
list are still unsampled. If `streaming()` ever reports UP on one of those, add
it to `test_fixtures/not_streaming/` and this rule can be re-scored in minutes.

---

**The original ticket, kept for the diagnosis:**

**OPEN-18 — `ensure_stream.streaming()` REPORTS UP WHILE THE PS5 IS IN STANDBY.**
Observed 2026-09-05 while verifying OPEN-16. `Bretts_walk.py connect` printed
`[stream] up via find_bar (compass strip located)` and returned success; the
capture was chiaki's HOST LIST reading **`State: standby`**. The console was
asleep, there was no stream at all, and `connect` therefore never ran its wake
sequence — the three `_key` presses at `ensure_stream.py:231-233`. Driving those
by hand woke the console in 112s.

This is §3's rule biting a caller that predates it. `find_bar()` locates the
compass strip WITHOUT reading it and returns non-None on essentially every frame,
which is why §3 says it answers "am I streaming" and NOT "am I in the world" —
but `streaming()` uses it as the liveness test, and a standby host list is
neither. `read_bearing()` is no better: on the PS5 Control Center overlay sitting
on top of the paused game it returned **43.7**, a confident number for a frame
with no world in it, which sent this session's own "WORLD IS UP" check wrong until
the user looked at the screen and said so.

Cost here was two minutes of hand-driving. Cost to an unattended run is a night
spent pressing buttons at a sleeping console while every log line says the stream
is up — §10.1's shape exactly, where doing nothing looks like working.
### What the diagnosis established, 2026-09-05

**`streaming()`'s OWN DOCSTRING CENSUS IS WRONG.** It claims

    chiaki host list, disconnected  find_bar None   bearing None

Measured on the standby host-list frame: **`find_bar` returns `(70, 1089, 1810)`**,
not None. The one state the function exists to detect is the one its evidence
cannot see. `read_bearing` (None) and `is_pause_screen` (False) both answered
correctly — only `find_bar` fired, and it is the check that runs first.

**AND §3 ALREADY SAID SO, TWO SECTIONS AWAY.** CLAUDE.md:229 records, as a
measurement: *"`find_bar()` returns non-None on EVERY frame including ban and
gameplay screens."* So the docstring census does not merely lack evidence — it
CONTRADICTS a measured fact already written in this file, in a table laid out to
read exactly like measurement. **That is what this entry is really about:** not a
detector needing a better threshold, but a caller asserting the opposite of a
known result in its own docstring, where prose cannot fail and everyone reads it.

Note §3's frames are the POSITIVE population — ban screens and gameplay, every one
a state where the stream IS up. They establish that `find_bar` firing means
nothing; they do not help separate standby. The negative side is still n = 1.

**THE PRECEDENT IS §7's `identify_edges`.** There, `descriptor()` divides by the
vector norm, so a near-featureless frame becomes mostly the shared vignette and an
upstairs office door scored 0.906 against `beside_dealer_table` — higher than any
genuine match. A standby host list satisfying "thin bright band, dark above and
below" is the same failure: **a detector answering confidently about a frame
containing none of its subject.** §7's verdict on that one is the part to carry
over — *no score threshold fixes it* — which is why the search below stops hunting
for a better `find_bar` threshold and goes after a non-pixel signal instead.

**WHAT IT MATCHED.** `find_bar` returns `(y, x_left, x_right)` and looks for a
thin bright band with dark rows above and below. chiaki's own blue toolbar
("Create Steam Shortcut / Refresh PSN Hosts") is exactly that, at **y = 70**
against the real compass strip's **y = 64**. No y-band and no thinness rule can
separate them; the impostor is 6px away from the target.

**ONE CANDIDATE REFUTED, WITH n = 800.** "Qt chrome is flat fills, a rendered game
frame is textured" — scored as the fraction of pixels sharing the single most
common exact RGB value, over 800 archived frames from `demos/` and
`screenshot_log/`:

    game frames   p50 0.0300   p90 0.0598   p99 0.1121   MAX 0.6556
    host list, standby                                       0.6262

**THE REASON ABOVE IS WRONG, AND THE CONCLUSION SURVIVES ANYWAY (2026-09-06).**
The table scores the WRONG POPULATION. Flatness is a discriminator applied only
AFTER `find_bar` has already fired; a frame `find_bar` returns None on never
reaches it. Conditioned on `find_bar` firing, the game side tops out at 0.5024
(400-frame tail) and 0.1153 (random 800) against the host list's 0.6262 — a gap,
not an overlap. Every one of the 17 frames at or above 0.6262 is a PURE BLACK
fade frame, mean 0.0, on which `find_bar` returns None.

So the populations do not overlap. **Do not rebuild this one anyway**, for the
honest reason: the NEGATIVE side is a single observation and that frame is not
on disk, so §10.4's "between two MEASURED populations" is unmet in the other
direction. The candidate is UNEVALUABLE, not refuted. Capturing one host-list
frame would settle it.

**NO FREE WINDOW-TITLE DISCRIMINATOR.** `kCGWindowName` is empty for both of
chiaki's windows, so the pixel-independent route that `game_window_rect()` almost
offers is not available; it matches on `kCGWindowOwnerName` because that is all
macOS hands over here.

**THE SURVIVING CANDIDATE, AND IT IS NOT YET A CENSUS.** The compass strip is
CENTRED in the game frame; chiaki's toolbar is right-aligned.

    world, in game        x 609..1328   centre  968   (frame 1920 -> offset  -11)
    host list, standby    x 1089..1810  centre 1450   (offset +490)
    pause book            x 279..1607   centre  943
    PS5 Control Center    x 221..1636   centre  929

Three game-side states cluster at the centre and the chrome sits far right. **But
this is n = 1 on the chrome side**, and a threshold on one sample is the thing
this file keeps being caught by. Collecting more host-list frames requires taking
the stream DOWN, so it was not done: OPEN-16's verification and the rig work
needed the stream up.

**THE LIVE-VS-SAVED INCONSISTENCY IS RESOLVED, AND THE ANSWER IS ITS OWN
FINDING — see the section below §10.** Live, on the PS5 Control Center overlay,
`read_bearing` returned **43.7**; on the JPEG saved from that same capture it
returns **None**. The cache is exonerated by direct test (same file, cache
as-loaded / cleared / restored — None all three times). It is the lossy save, and
saving is not a harmless record.

**Not fixed:** the replacement predicate still has to sit between two measured
populations (§10.4). Next step is the centring test above with a real host-list
population behind it; the peer's suggestion of the literal text `State: standby`
remains the fallback.

**CONFIRMED ON AN INDEPENDENT CORPUS, AND IT COST THE USER AN HOUR (2026-09-06).**
`find_bar` is not weakly discriminating, it is barely discriminating at all:
9 of 13 of chiaki's OWN Qt documentation screenshots, 5 of 6 arbitrary
photographs, and a SYNTHETIC dark window with one light horizontal toolbar all
return non-None. Only a flat image — solid colour or pure noise — returns None.
On 2026-09-06 every failed reconnect announced `[stream] up via find_bar` first
while chiaki was NOT RUNNING and the console was OFF, and an hour went into
diagnosing the compass instead of the rig.

`streaming()`'s docstring asserted the opposite — *"It is None only in the state
this function exists to detect"* — which is why nobody looked. That sentence is
deleted and the measurement is pinned by
`tests/rig/test_find_bar_is_not_a_stream_check.py`, whose fixtures are
SYNTHESISED so it does not depend on the gitignored `chiaki-ng-src/`, and which
carries a positive control (40/40 real game frames still located) so it cannot
pass with the detector broken the other way.

**THE VERDICT LOGIC IS DELIBERATELY UNCHANGED, and that is a decision for the
user, not a gap to be closed quietly.** Deleting the `find_bar` branch trades a
known false positive for an UNMEASURED false negative, and a false negative here
ENDS an unattended run — which is the failure that put the branch there in the
first place (bright scenes killed two runs on 2026-09-01).

**One lead, recorded and NOT asserted.** On every synthetic and UI image tried,
the located strip spans the FULL frame width (0..W-1); on 40 of 40 real game
frames it is bounded well inside (e.g. 460..937 of 1400). That is 2/2 against
0/40 — a perfect separation on what exists, and still only ONE measured
population, because the host-list frame is not on disk. **Capture one host-list
frame and this ticket closes.** That is the cheapest open item in this file.

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
