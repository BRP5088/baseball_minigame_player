# The rig and the environment (§1, §2)

Moved VERBATIM out of CLAUDE.md on 2026-09-22 so it is no longer loaded into
every session. Section numbers are unchanged, so a code comment citing
"CLAUDE.md §N" still resolves -- CLAUDE.md carries the map. Nothing here was
reworded; corrections belong in THIS file now, not in CLAUDE.md.

---

## §1 The rig: PS5, chiaki, the stream

**Standing permission (2026-09-01): start chiaki-ng and wake the PS5 when a run
needs them.** No need to ask each time. The console auto-sleeps when nothing
reaches it — that killed the 2026-09-01 overnight run four minutes in, and
contaminated a whole leg-tolerance A/B on 2026-09-03.

### Putting the console to sleep, and knowing it already is

**FIRST: CHECK WHETHER IT IS ALREADY ASLEEP, BECAUSE IT USUALLY IS.** The
auto-sleep above is not a hazard to work around here, it is the mechanism. Asked
to put the console to sleep on 2026-09-13, the answer was that it had already
done it: a live game frame at bearing 87 had been captured minutes earlier, then
the suite ran, nothing reached the console, and it went to standby on its own.
A `ps_button` press was sent against a state verified SEVERAL MINUTES EARLIER
rather than re-checked at the moment of acting — 10.29's shape (assert the
starting state, never carry one forward).

**THREE CHEAP TELLS, all measured 2026-09-13, no input required:**

    game_capture.grab()          1831x1030, NOT 1920x1080
                                 the frame dump is gone, so this is the mss
                                 WINDOW grab -- i.e. the chiaki app, not a game
    ensure_stream.looks_like_ui()   True
    ensure_stream.streaming()       False

The window size is the fastest of the three: a capture that is not the PS5's
1920x1080 means you are looking at chiaki, not at the game. `streaming()`
answering False on the standby host list is OPEN-18's fix doing its job -- that
same screen once answered True in 0.0s.

**IF IT IS ALREADY ASLEEP, DO NOTHING.** The user's call, 2026-09-13: *"maybe
its already asleep. if so, leave it alone."*

**AND DO NOT PRESS `ps_button` TO FIND OUT.** With no session running, chiaki
has the host list up and that press raises **chiaki's own "Quit — Are you sure
you want to quit?" dialog**, one keystroke from killing the app. Dismiss it with
**ESCAPE**, which Qt treats as reject, i.e. "No". Do NOT use Enter or Space:
those activate whichever button holds focus, and Yes is the left one. The dialog
is a Qt modal, so it only takes input with chiaki FRONTMOST (section 1's ladder
rule) -- `_key()` posting to the pid will not touch it.

**THE WAY TO ACTUALLY PUT IT TO SLEEP, when it is awake. WALKED END TO END
2026-09-17 with a paid match on screen -- the full procedure is
`console_rest_mode_procedure.md`, and it is worth opening rather than
remembering.** The user's recipe, 2026-09-13 (*"press the playstation button,
scroll all the way to the right. should be a power symbol select sleep"*) is
correct; what it cannot carry is the navigation.

    ic.press('ps_button')        ONCE (a TOGGLE). Focus opens on a CARD TILE
    ic.press('dpad_down')        ONCE -- the step that is easy to miss; it drops
                                 focus to the icon bar, and only then does the
                                 focused icon show its NAME above the strip
    ic.press('dpad_right') x N   to the last of 11 icons, POWER (10 from Home)
    ic.press('cross') x2         open the menu, then take "Enter Rest Mode",
                                 which is pre-selected at the top

**THE WHOLE THING IS STEP AND LOOK, AND THE DROP RATE IS WHY.** Section 5
measures the console ignoring 15.20% of presses, clustered. On this overlay:
**10 rights moved 6 icons, the next 4 moved 2, and the first cross on Power was
dropped outright.** Counting presses puts the cursor three icons from where it
believes it is. Read the position from the LABEL after every batch -- and do not
crop tight to the icons, because the focus ring does not survive the stream at
that scale while the label, which sits ABOVE the strip, does.

**THE OVERLAY SILENTLY LOSES FOCUS AND STAYS FULLY DRAWN (10.1).** Every press is
then ignored, indistinguishable from a dropped one -- 14 rights, an up and a down
changed zero pixels. The tell is the GAME SCENE BEHIND IT: with focus the overlay
dims it; without, the scene is at normal brightness while the cards and bar
remain. Recover by toggling `ps_button` off and on, not by pressing harder.

**Section 3's warning applies to every press here: X is SUBMIT and takes whatever
the cursor sits on.** From a fresh Control Center that can be the PS5 HOME
SCREEN. And in the Power menu **"Turn Off PS5" sits directly under "Enter Rest
Mode"**, so a blind double-X after a dropped press is one row from powering the
console off mid-match. Capture and read the menu before the second cross.

Confirm with the three tells at the top of this section, never with the absence
of an error. Rest mode SUSPENDS the game, so an open match survives and
`match_in_progress` stays set, correctly.

**CHIAKI'S OWN SLEEP PATH EXISTS AND IS UNREACHABLE ON macOS. DO NOT SPEND
TIME ON IT (walked 2026-09-17).** This entry used to read "Worth trying before
the Control Center route". It is not; nothing on this Mac can reach it, and the
attempt is the dangerous kind of experiment because every candidate keystroke is
one bind away from killing chiaki with a paid match on screen.

THE CHAIN IS REAL, and reading it is what makes the dead end certain rather than
assumed (`chiaki-ng-src`, all verified by reading):

    QEvent::Close on the main window    qmlmainwindow.cpp:7487 -> backend->closeRequested()
    DisconnectAction::Ask (the DEFAULT) qmlbackend.cpp:1275 -> emit sessionStopDialogRequested()
                                        and returns FALSE, so the window does NOT close
    the popup                           StreamView.qml:1257 opens sessionStopDialog
                                        (or separateSessionStopWindow; identical behaviour)
    focus                               onVisibleChanged -> view.grabInput(sleepButton)
    RETURN                              Keys.onReturnPressed -> closeAction = 1
                                        -> Chiaki.stopSession(true) -> GoToBed() + Stop()
    ESCAPE                              closeAction stays 0 -- a harmless abort

**AND THE ONLY KEYBOARD ROUTE INTO IT IS COMPILED OUT HERE.**
`qmlmainwindow.cpp:7412` is

    case Qt::Key_Q:
    #ifndef Q_OS_MACOS
        close();
    #endif
        return true;          // swallowed on macOS, does nothing

Qt maps its `ControlModifier` to COMMAND on macOS, so chiaki's own Cmd+Q is that
`#ifndef` and is a no-op. **Cmd+W is not bound at all** -- sent live at the
frontmost chiaki with a match on screen: no dialog, window still open, the match
frame byte-for-byte the same scene before and after. And the window is
FULLSCREEN with **zero AX buttons**, so there is no close control to press
either. Setting `DisconnectAction` to `AlwaysSleep` changes nothing, because
nothing can end the session to trigger it.

**THE USER'S CALL ON THAT ATTEMPT, 2026-09-17: *"Don't do cmd+w. That's dumb and
dangerous."*** Correct, and the reason generalises past this key: the dialog's
whole safety argument is that Sleep is focused and Escape aborts -- but that only
holds IF THE DIALOG OPENS. If the keystroke is bound to plain window close
instead, the same press quits chiaki mid-match. Do not probe an app's keymap by
pressing keys at it while a paid match is live.

**SO THE TWO ROUTES THAT REMAIN ARE THE OVERLAY RECIPE ABOVE, AND DOING
NOTHING.** Doing nothing is not a joke: this section's own opening paragraph
records that the console auto-sleeps when nothing reaches it, reliably enough to
have killed an overnight run four minutes in. If the goal is "asleep by morning"
rather than "asleep now", stop sending input and let it.

**TWO INSTRUMENT TRAPS FOUND WHILE CHECKING THIS, both of which made a
verification look like it had verified something (10.1's family).**

    chiaki runs on the SECOND display    the LG ULTRAWIDE, window at (-2560, 0)
                                         2560x1080, while the Mac's built-in is
                                         3456x2234
    screencapture -x one.png             captures the BUILT-IN display only. The
                                         "before" shot of chiaki was a picture of
                                         the Claude app. Use
                                         `screencapture -x a.png b.png` -- one
                                         path per display, in order
    frontmost_app() == "chiaki"          says which APP has focus. It says nothing
                                         about which MONITOR that app is on, so it
                                         cannot corroborate a screenshot

The user spotted the first one instantly (*"Wrong monitor"*) from a screenshot
that had already been accepted here as evidence.

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

### `ensure_live()` RETURNING TRUE MEANS THE STREAM IS UP, NOT THAT THE GAME WILL TAKE INPUT

**The user's rule, 2026-09-17: *"when the PS5 goes to sleep or the stream is cut, it can
have the PS5 overlay on, so sending button presses like you're in the game isn't correct.
You should have checked the state before assuming it was back in the game and ready for
you."*** Exactly right, and it had already cost a wrong diagnosis an hour earlier.

After waking a sleeping console, `ensure_live()` returns True as soon as frames arrive --
and it says so in its own log on the way past: *"compass unreadable and no pause menu --
dismissing the PS5 overlay"*. That line is the tell. An overlay WAS up, a `ps_button` was
sent to clear it, and the game needs a moment to come forward. Presses fired into that gap
reach chiaki, reach the console, and change nothing, because the thing on screen is not
the game.

**WHAT IT COST.** A press-delivery experiment was started immediately after a reconnect.
All 8 presses moved the cursor 0 cells, and the instrumented chiaki logged nothing, so the
reading was "every press dies before chiaki" -- a confident, wrong, and quite exciting
conclusion about a bug that did not exist. Six presses a minute later moved the cursor four
cells and chiaki logged all of them. The only difference was that the overlay had cleared.

**THE CHECK, and it is one line.** Do not press until a reader that only answers ON THE
SCREEN YOU WANT says yes:

    a ban screen     orchestrator.read_ban_counter(img) is not None
    a turn screen    local_hand.read_hand(...) returns its rows
    the dealer       table_prompt.at_table(img)

`streaming()` and a 1920x1080 capture are NOT that check -- both are true while the PS5
overlay sits on top of the game. This is 10.29 ("assert the starting state rather than
assume it") applied to the reconnect, which is the one place it had not been written down.

**AND THE LOG THAT WOULD HAVE CAUGHT IT IS BLOCK-BUFFERED.** `/tmp/chiaki_run.log` is
chiaki's stdout redirected to a file, so it flushes in 4 KB blocks and its last line is
routinely cut off mid-word. Measured: 3 seconds and 6 presses produced ZERO bytes of
growth, and the missing lines appeared 38 s later when the buffer filled. **Absence of a
log line is not absence of the event** (10.1) -- when reading that log to decide anything,
either wait for growth past a recorded offset or accept that the last few seconds are
invisible.

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

**`grep` IN THIS SHELL SKIPS EVERY `.gitignore`d PATH. PASS `--no-ignore-files` WHENEVER
THE ANSWER IS A COUNT OR A "NOTHING USES THIS".** It is a Claude Code shell function that
runs the bundled ugrep with `--ignore-files`, so it never descends into `agent_progress/`,
`demos/`, `screenshot_log/` or the venvs -- and reports the truncated answer as a complete
one. It hid the ONLY functional references to a tree that was about to be deleted, and
the full mechanism and measurement are in §10.16c. A plain search is fine; a COMPLETENESS
claim is not:

    grep -rl ArmorOCR --include='*.py' .                      2 files
    grep -rl --no-ignore-files ArmorOCR --include='*.py' .    8 files

**BUT `--no-ignore-files` IS NOT RELIABLE, AND THE PORTABLE FORM IS.** The wrapper
falls through to BSD `grep` in some invocations -- twice, in compound commands, both
times dying with "unrecognized option". Isolating the trigger per-argument reproduced
NOTHING, so the cause is NOT ESTABLISHED and is not guessed at here. What IS
established: the failure is LOUD, which is the safe direction, and this always works:

    find . -name '*.py' -not -path './.venv/*' -print0 | xargs -0 grep -l PATTERN

**Use the flag for a quick look; use `find | xargs` for anything you will report as a
count or a "nothing uses this".**

Two zsh traps live in these three lines, both hit while writing them (16.16c):
QUOTE THE GLOB, because a bare `*.py` is expanded by zsh and the command dies with
"no matches found" -- this block shipped unquoted for a minute. And **`grep` EXITS 1
ON ZERO MATCHES**, so `grep ... && echo OK || echo FAILED` reports FAILED for a clean
search; three "failures" in a test of this very fix were that and nothing else.

**`paddle_venv/` is NOT the project environment — but it IS a live dependency.
DO NOT DELETE IT.** Both halves matter and the file used to state only the first:

- Never SELECT it as the interpreter. It is Python 3.11 with no `pytesseract`,
  no `mss`, no `Quartz`, so every module fails at import.
- It is 777M for a reason: it holds `paddleocr`, `paddlepaddle` and `paddlex`,
  which have no Python 3.14 wheel. That is why it is a second venv rather than
  part of `.venv`.

**RETRACTION, SAME DAY (2026-09-20). THIS ENTRY BRIEFLY SAID "IT IS CHECKED,
NOT USED". THAT WAS WRONG, AND IT IS THE THIRD TIME THIS ONE PARAGRAPH HAS BEEN
WRONG ABOUT THE SAME 777M.** `paddle_venv` IS used, on the live path, by a
consumer the retraction never looked at:

    orchestrator.py:4112-4113   import result_ocr; result_ocr.start()
    result_ocr.py:120           subprocess.Popen([PADDLE_PYTHON, "-u", PROBE], ...)
    orchestrator.py:4155, 4251  result_ocr.read_banner(full)  -> WINNER/LOSER/DRAW

So the venv is spawned to read the RESULT BANNER, not the hand. `tools/read_banner_paddle.py`
is the probe it runs. **DO NOT DELETE `paddle_venv`** -- unchanged, for a reason
the wrong version had removed.

**THE MISTAKE IS WORTH MORE THAN THE FACT.** I traced `hand_digit_reader`
exhaustively -- AST over every non-vendored module, every public function, the
commit that cut it -- and then wrote the conclusion about **paddle_venv**. One
consumer was checked and the claim was made about the DEPENDENCY. That is this
paragraph's own documented failure mode, committed inside a correction TO that
failure mode, by someone who had just re-read it. An exhaustive trace of the
wrong question is still the wrong answer, and thoroughness on one consumer reads
exactly like thoroughness on all of them.

**WHAT IS ACTUALLY TRUE, and it is narrower than either previous version:** the
HAND-digit pipeline inside `hand_digit_reader.py` is dead.
`read_hand_digits` has had **ZERO callers since commit 211c6bf** (2026-09-09, *"the local hand reader runs
in production"*), which removed the two lines that called it:

    -  from hand_digit_reader import read_hand_digits, group_into_cards
    -  local_cards = group_into_cards(read_hand_digits(tmp_path))

The template reader replaced it -- the same story as ArmorOCR above, and for the
same reason. Measured by AST over every non-vendored module (a bare `grep` is
what got this paragraph wrong twice; `detect` alone matches 343 lines of prose):

    read_hand_digits    0 callers      group_into_cards  0 callers
    validate_card       0 callers      detect            0 callers  (the two
                                                          hits are a DIFFERENT
                                                          detect in tools/)
    check_paddle_venv   3 call sites   preflight.py:205, orchestrator.py:7628-9

So what survives is the DEPENDENCY CHECK for a reader nothing calls.
`orchestrator.py:7624-7629` verifies the venv under `compare_local_reads` so
that *"a stale/missing interpreter surfaces as a swallowed per-turn exception"*
-- there is no per-turn exception, because there is no per-turn call.

**TWO CORRECTIONS TO THE OLD TEXT BEYOND THAT, both measured.** `preflight.py`
does NOT check it "unconditionally" in the blocking sense: it is a `warn()`, not
a `bad()`, so a missing venv never stops a run. And `check_paddle_venv()` either
RAISES `PaddleVenvMissing` or returns True -- it never returns a falsy value --
so preflight's `else` branch was **unreachable** and the message it was written
to print ("hand digits fall back to vision") never appeared. **That branch was
deleted 2026-09-20**; the check itself stays, because the venv is live for
`result_ocr`, and its message now names that consumer. That fallback would be wrong twice over now anyway,
since the paid vision model is off (section 3).

**NO DELETION IS RECOMMENDED HERE, AND THAT IS DELIBERATE.** This paragraph
has now been wrong in BOTH directions -- "nothing uses it" once, "checked, not
used" once -- and a deletion was nearly carried out on the first. 777M, not a git
repo, so nothing is recoverable afterwards. What is established is that the
HAND-DIGIT reader is dead and that `result_ocr` keeps the venv live. The dead
half is `hand_digit_reader`'s read pipeline; the venv stays.

**THE RULE THIS EARNS, and it generalises past paddle:** when a trace concludes
that a DEPENDENCY is unused, the unit of proof is the dependency, not the module
you happened to start from. Enumerate every spawner of the interpreter -- here,
every `subprocess` call whose argv names a venv python -- before saying the word
"unused".

This file said "777M and nothing uses it" until 2026-09-04, and a deletion was
nearly carried out on that basis. **The claims this file gets wrong are the ones
about what is unused or safe to remove** — nothing exercises them until someone
acts on them, so they rot silently while the rest stays accurate. Verify before
deleting anything on the strength of a sentence here.

**`armor_venv/` AND `models/` WERE DELETED 2026-09-17: 23.6G, at the user's
instruction.** They arrived 2026-09-09 for the local-OCR bake-off -- a Python 3.11 venv
(torch, onnxruntime, huggingface) and four model trees (`ArmorOCR` 16G,
`typhoon-ocr1.5-2b` 4.0G, `surya-ocr-2-gguf` 1.4G, `GOT-OCR-2.0-hf` 1.1G). The user's
call: *"It was used to test a new OCR method. While it worked really well, it wasn't fast
enough to use"*, and *"Worst case scenario, we reinstall them."*

**`MODELS_REMOVED.md` IS WHAT MAKES THAT WORST CASE REAL, AND IT NEARLY WAS NOT.** Each
model's upstream identity and pinned commit lived in exactly one place: inside the tree
being deleted. Nothing outside `models/` named a single one of them, and one owner
appeared nowhere on disk at all. ~200KB of pointer stood between 23G and gone-for-good.
An adversarial reproducibility check found it BEFORE the `rm`; the four SHAs are in that
file. **The rule this earns: before deleting a downloaded artefact, ask where its
PROVENANCE lives -- if the answer is "inside it", extract that first and commit it.**

The measurement that retired them survives in `local_hand.py`'s docstring: ArmorOCR read
the digits WELL and took 9.9 s, against the shipped template reader's 5600/5600 at ~2 ms.
Accuracy was never the binding constraint; a 9.9 s read cannot serve a 150 ms poll.

**TWO ERRORS OF MINE CAME OUT OF CHECKING THIS, and both are about the instrument.**

**The paragraph this replaces was FALSE THE INSTANT IT WAS COMMITTED.** It said the grep
"returns only `tests/harness/test_no_undefined_names.py`" -- and commit `3f3769c`, which
added that sentence, ALSO created `tests/harness/test_claude_md_constants.py`, whose
SKIP_DIRS contains `armor_venv`. The claim never described its own commit. Run properly
at that HEAD it returned 14 files.

**And the reason it looked true is that `grep` ON THIS MACHINE IS A SHELL FUNCTION THAT
RESPECTS `.gitignore`** -- see 16.16c, which this earned.

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
