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
number that must be hand-synced is a constant pretending to be evidence. See OPEN-2: `chiaki-patch/` cannot currently rebuild the patch.

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
reliably inside the bar. Use `compass.find_bar()`: it locates the strip without
reading it, and is None only when genuinely disconnected.

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
    go_to_node_verified (3 attempts)      4/4 in one sample, ~75s each

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

- **`keep_awake` was nudging 0.41 degrees, not the ~7 its comment claimed.**
  `NUDGE_MAG` was 0.35, exactly ON `turn_curve.DEAD_BELOW` rather than above it,
  for 90ms. Now 0.60 for 300ms = 6.75 deg, above the dead band and self-undoing.
  This module exists because console auto-sleep killed one overnight run and
  contaminated a leg-tolerance A/B, so a nudge the console may not even register
  is the catalogue shape guarding the failure that has already cost a
  measurement. **Whether the PS5 counts a given deflection as activity is still
  UNVERIFIED** and cannot be tested offline.

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
`tests/routing/test_leg_distances_match_recording.py`, which asserts every leg
covers its recorded distance within 15% and that no leg is implausibly short.

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

---

## §11 OPEN

Nothing outside this section may claim to be open.

**OPEN-1 — Cause B is undiagnosed and NO ADMISSIBLE FAILURE FRAME EXISTS.**
Two successive attempts to capture one both failed, in opposite directions:
the first eight frames were taken AFTER `recover_to_node` and describe the
fan's own displacement (six sit at bearing 98-106 against the leg's commanded
2.1 — the fan's signature); the next four were taken BEFORE the whole attempt
and are photographs of the PREVIOUS node's successful arrival (all four identify
as `bar_pool_room` at 506-734 matches, bearing 284.8-288.3, the inbound heading
of the previous leg). `follow()` already saves at the right moment — before the fan, not after it — and `shots` is now threaded down through
`go_to_node_verified` so that path is used. **Unverified live.** The old frames
are in `overnight/failframes_prerecovery/`; they remain valid as classifier
appearance data and invalid as evidence about the leg.

**OPEN-2 — CLOSED 2026-09-04.** `chiaki-patch/` now holds all five edits:
`gui/CMakeLists.txt` and `gui/src/main.cpp` were copied in (they had existed
only as prose here), and the README points at `cd chiaki-ng-src && git diff` as
the authority. The stale half-size twin `chiaki_patch/` (underscore — its
`injectinput.cpp` was 4,100 bytes against the real 9,684, one keystroke away on
tab-complete) is in `_obsolete/`.

**OPEN-3 — `LEG_TURN_TOLERANCE` is unresolved, and is the highest-value
navigation experiment available.** Ships `None` (unchanged). The MECHANISM is
verified: `slow_traverse.TURN_TOLERANCE = 4.0` against per-leg curvature of
0.28 / 8.71 / 6.59 / 0.00 / 13.85, so most mid-leg turns are NO-OPS and a ±4 deg
band neither executes a commanded change under 4 deg nor corrects drift under
it. A leg is therefore walked straight at whatever heading it arrived on. The
deceptive log line reads `step 2/4 bearing 292.2 (got 289.1) 0.79s -> walked
0.79s`, which looks exactly like a turn that happened. Run 1 (`[2,1,2]` vs
`[2,3,3]`) is **p = 0.298, power 0.00, never evidence**; run 2 was contaminated
by the console falling asleep. **Needs 10 per arm, interleaved, verified
positions.** Note `None` must never reach `st.turn_to` — `abs(err) <= None`
raises.

**OPEN-3 NOW HAS AN INSTRUMENT (2026-09-04).** `slow_traverse.turn_to` logs
every exit, and the two that matter are paired:

    turn to 292.2: NO-OP, already inside 4.0 deg (at 289.1, err +3.1) —
                   nothing was sent, the recorded curve was discarded
    turn to 292.2: TURNED to 292.0 (err +0.2) in 1 push(es)

`grep -c NO-OP` against `grep -c TURNED` over a run's log gives the numerator
AND the denominator, which is the mechanism question OPEN-3 has been unable to
answer. The caller's own step line can never separate them, because an executed
turn also ends inside tolerance — that is precisely why this was invisible.

**This applies only to logs written FROM NOW ON.** Everything already on disk
came from the silent version and cannot be re-scored; do not try.

**OPEN-14 — Does the RESTORED jukebox leg move arrival?** The leg was 4.3x too
short and could not reach its destination; it is now back to its recorded
1.031 units over 3.30s. This is the strongest candidate yet for what has been
costing the route, and it is UNMEASURED. Run it FIRST, before the other open
A/Bs: if arrival moves, several of those experiments are asking the wrong
question. 10 trials, scored on verified arrivals, reported by failure class.

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

**OPEN-4 — Is arrival at `bar_pool_room` really ~55%, and does
`go_to_node_verified` really approach 100%?** 11/20 for a single walk vs 4/4 at
~75s for the 3-attempt primitive. Different quantities; the second is the one
that matters. Everything downstream needs a verified start pose, and one
re-record attempt reached its start node **0 of 20** and another **4 of 20**.
**Measure the primitive, n>=10, one leg not a full route.**

**OPEN-5 — Is `attempts=9` better than `attempts=3`?** Run 1 was inconclusive
and contaminated: attempts_9 2/3 valid (3 of 6 trials invalid on a 420s
timeout), attempts_3 3/6, and both arms collapsed in the second half while
chiaki logged 32,388 decoder-overflow lines. Retry is the only lever the
arithmetic says can reach the target. `overnight/ab_attempts.py` is prepared at
TRIALS=10, TIMEOUT=900, `log=log`.

**OPEN-6 — Three flags have never been tested live.**
`SPEED_FROM_RELIABILITY` and `RECORD_RELIABILITY` are both `False` deliberately
(a harness that mutates the state it reads makes an A/B non-reproducible), and
`SURVEY_WHILE_WALKING` is `False`. **`SURVEY_WHILE_WALKING`'s premise is now
unsupported** — it targets "the OVERSHOT class, a quarter of failures", a figure
derived from the frames that turned out to describe the recovery fan. Re-derive
the class distribution from admissible frames first.

**OPEN-7 — Should `RECOVER_MISSED` be turned off?** The fan succeeded 0/15 in
the streak run and 2/31 combined, while costing ~34% of the clock. Judge it on
seconds and failures-by-class, not arrival.

**OPEN-8 — Where does the other ~45s of a trial go?** Walking is ~16-23s and
reset ~9s of a ~75-85s trial; the rest is SETTLE sleeps
(`slow_traverse.SETTLE_SEC = 0.35`), 135 captures, and turn settling. **Never
examined.** At n=10 minimum per arm this is the binding constraint on how much
can be learned per hour — bigger than any remaining walking-speed gain, which is
capped at ~10%.

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

**OPEN-11 — `tests/cpp/` is not wired into `run_tests.sh`.** 13 checks that only
run if someone remembers the `clang++` line.

**OPEN-12 — `orchestrator.py` uses `pytesseract` in 6 places and `ocr_glyphs` in
0.** All match-play OCR still shells out (193ms vs 79ms measured). Not a
drop-in: `ocr_glyphs.recognise` is single-char mode (`PSM.SINGLE_CHAR`) and ban
names are words, so it needs a word mode. Not on the navigation path — do it
when match farming is the focus.
