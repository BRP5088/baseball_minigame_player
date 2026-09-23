# Input and stick response (§5, §6)

Moved VERBATIM out of CLAUDE.md on 2026-09-22 so it is no longer loaded into
every session. Section numbers are unchanged, so a code comment citing
"CLAUDE.md §N" still resolves -- CLAUDE.md carries the map. Nothing here was
reworded; corrections belong in THIS file now, not in CLAUDE.md.

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

### THE GAME IGNORES ONE PRESS IN SIX, AND NOTHING WE SEND IS LOST (2026-09-17)

**Measured over 1000 presses on a live ban screen, every press confirmed against
chiaki's own instrumented log BEFORE being scored**, so "ignored" always means
delivered-and-declined and never "we failed to send":

    ignored                       152 / 1000 = 15.20%
    never reached chiaki            0
    P(ignore | previous IGNORED)    0.250        <- they CLUSTER
    P(ignore | previous moved)      0.135
    longest consecutive-ignore run  4

**FOUR HYPOTHESES DIED TO GET THAT NUMBER, each killed by a measurement rather than an
argument, and every one of them was mine:**

    stale frames fool the cursor reader    40/40 double-reads agreed, and agreed with
                                           reality -- there is no stale-frame problem
    chiaki's isAutoRepeat discards         ZERO discards in ~150 presses
    chiaki's edge-collapse dedup           keys accepted == edges transmitted, exactly
    a null CGEventSource costs delivery    100% on None / HID / Private, interleaved

The press ARRIVES. The console has it. The game declines to act on it. So no delay, no
event source and no faster retry can prevent this -- **the only remedy is to LOOK, and
press again if it did not take.** Waiting longer does not help either: the gap since the
previous move is the same for ignored presses as for accepted ones.

**IT TOOK AN INSTRUMENTED CHIAKI, AND THE INSTRUMENT IS NOW PART OF THE PATCH.**
`[btnkey]` in `StreamSession::HandleKeyboardEvent` logs every key its Qt handler accepts
or discards and WHY; `[btnedge]` in `feedbacksender.c` logs every button edge actually
transmitted. Together they split a lost press three ways -- never reached chiaki, chiaki
discarded it, chiaki sent it and the game ignored it -- which no amount of black-box
measurement from the Python side can do. `lib/src/feedbacksender.c` is the FIRST patched
file outside `gui/`; it and the other two are in `chiaki-patch/` and covered by
`tests/cpp/test_injectinput_cpp.py`'s byte-for-byte list.

**AND `main.cpp` NOW LINE-BUFFERS STDOUT, WHICH IS WHY ANY OF THIS CAN BE BELIEVED.** The
log is chiaki's stdout redirected to a file, so libc block-buffered it: 3 seconds and 6
presses produced ZERO bytes of growth and the tail sat cut off mid-word. TWO measurements
were thrown away to that before it was fixed -- one of them read the silence as "every
press dies before chiaki", which is a confident wrong conclusion about a bug that does not
exist. `setvbuf(stdout, NULL, _IOLBF, 0)`; a press's lines now land in 0.31 s.

**TWO CONSTANTS WERE DERIVED FROM IT, AND BOTH WERE WRONG BEFORE.**

`BAN_NAV_MAX_STEPS` was 14, justified as "12 moves of travel plus 2 slack". But `moves`
counts EVERY press, landed or not, so it is a budget of PRESSES. Markov simulation over
200,000 trials, P(reaching a 12-move target): **budget 14 = 64.36%** -- a far ban silently
missing one time in three, reported as `ban_nav_incomplete`, which is a symptom this file
already recorded and believed fixed. It is now **22** (99.92%). It is not raised further
because the budget is also the bail-out for a cursor that is genuinely stuck on a paid
match.

`PRESS_VERIFY_TRIES` was first written as 3 on `0.167**3 = 0.47%`. **That assumed
independence and the clustering above refutes it**: each retry is conditioned on the press
before it having failed, so the real tail is `0.152 * 0.25**(n-1)` -- 0.95% at three tries,
twice as bad as claimed. It is now **5** (0.059%), which also covers the longest run
actually observed. **n=60 could not have shown this** -- ten ignores cannot separate 0.25
from 0.135 -- and the argument for the bigger sample was never precision.

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


### THE SUITE HAS NINE DIFFERENT `check()` SIGNATURES, AND A REVERSED CALL ALWAYS PASSES

Written after shipping eight of them in one evening. **This file said FOUR, and named four
files; re-counted 2026-09-17 it is NINE signatures across 163 files**, and the two argument
ORDERS are close to evenly split, which is what makes the trap live rather than rare:

    NAME first  80 files   (name, cond) x47   (name, ok, detail="") x12   (label, cond) x11
                           (label, cond, detail="") x6   (msg, ok) x3   (name, cond, detail="") x1
    COND first  83 files   (ok, msg) x40   (cond, msg) x29   (c, m) x14

Recount it rather than trusting that table -- it is a copy, and the count has already
rotted once:

    grep -rh "^def check(" tests/ --include="*.py" | sort | uniq -c | sort -rn

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

### AND THE KEYBOARD HAD THE SAME DROPPED-RELEASE HAZARD AS THE STICKS (2026-09-20)

This section already calls a lost release packet "the lurking catastrophe" on the
FIFO path. The TARGETED path had it too, and unlike the FIFO one it was not
hypothetical -- it is reproducible offline in a second.

`press_background` and `_bg_hold_keys` posted key-DOWN, slept, then posted key-UP
inside ONE `try/except Exception: return False` with **no `finally`**. So anything
that raised in between left the key PHYSICALLY HELD at chiaki -- and therefore at
the console -- while the function reported False. Reproduced with a stubbed Quartz
(`agent_progress/qa3-bghold/probe_stuck_key.py`, inert, posts nothing anywhere):

    raise on the UP post            the key stays down, returns False
    raise on a later DOWN           the earlier keys of a combo stay down
    KeyboardInterrupt in the sleep  the key stays down AND the interrupt
                                    PROPAGATES -- `except Exception` cannot
                                    catch a BaseException, so not even the
                                    `return False` ran

**THE INTERRUPT CASE IS THE REACHABLE ONE, AND IT IS ON EVERY PRESS.** Every hold
sleeps with the key down, `press()` routes EVERY button press through
`_bg_hold_keys`, and `reset_env._probe_transports` holds `look_right` for 0.3 s at
a time. A Ctrl-C or an externally-enforced timeout (10.14 says enforce them from
outside the process) lands in that window. A held Return is a held CROSS, which is
the button that answers YES on "Give up?".

Fixed by moving the release into a `finally` that posts UP for every key that got
a DOWN, in `_release_keycodes`. The callers keep their ORIGINAL contract -- any
failure across DOWN / sleep / UP still answers False, so press()'s announced
fallback still fires. **What it does NOT do is conjure a release when the UP post
is itself what failed**; there is nothing left to try, and it says so loudly
instead of silently, which is the whole of 10.1 on this path.

**AND IT MUST NOT HAVE A `BASEBALL_TEST_RUN` LOCKOUT.** The emission census failed
on the new function and demanded one -- correctly, by its own rule. But refusing to
release is HOW THE KEY STAYS DOWN: a lockout there is the bug wearing a guard's
clothes. Releasing is the safe direction, always. What makes it safe is an
invariant rather than a flag -- it can only release what was pressed, and under the
flag `targeted_input_allowed()` refuses before any DOWN, so the list it is handed
is empty. That is what the census now checks, with a control proving it is not a
no-op. Pinned by `tests/rig/test_background_keys_always_release.py`, four mutants,
each caught by a different assertion.

**The census earning its keep is the other half of this.** It was written so a NEW
emission site fails a test instead of reaching someone's keyboard, and the first
new site since it was rewritten was mine, found in the suite run rather than live.

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

**AND THE REWRITTEN CENSUS STILL MISSED SIX OF SIX NEW FORMS (2026-09-20).** The
paragraph above records the FIRST census missing seven of eight. Round 3 of the QA
loop proposed six more evasion forms by reading; all six were then PLANTED as
working emitters in a scratch copy of the tree (10.16a) and the census exited 0 on
every one -- `agent_progress/qa3-emit/plant.py`. Five are now closed:

    subprocess + osascript keystroke      CAUGHT   a real key press through System
                                                   Events, no input library at all
    a DIFFERENT emitter inside a function  CAUGHT  the tuple was (file, function),
    already in EXPECTED                            so it collided and vanished
    getattr(lib, COMPUTED)(k)              CAUGHT  the old rule needed a literal
    `from pyautogui import *` + bare call  CAUGHT  `*` binds no EMITTERS name
    an emitter in a SKIPPED directory,     CAUGHT  the skip-list is an ASSERTION
    imported by a live module                      that nothing live imports past
                                                   it; it is now CHECKED
    a FIFO writer whose path is DERIVED    STILL MISSED -- see below

**ONE STAYS OPEN, DELIBERATELY.** The FIFO check pre-filters on two literal
strings before it will even parse a file, so a writer that builds the same path
out of pieces is never looked at. Catching it means detecting the PROTOCOL
(`buttons <n>`, `left_x <n>`) rather than the path, which is new design on the
input path. No constant is invented for it here.

**AND ONE NAIVE FIX WAS KILLED BY ITS OWN MEASUREMENT, which is why the osascript
rule looks the way it does.** Scanning every string literal for AppleScript's
input verbs returns FOURTEEN hits in this tree and **not one is AppleScript** --
they are ordinary English in error messages and test assertions ("a dropped
keystroke", "the KEYSTROKE only"). "keystroke" is a normal word in this project's
vocabulary. 14 false positives, 0 true ones; a rule that cannot tell a sentence
from a script gets switched off. The shipped rule inspects only actual
`osascript` invocations and carries BOTH controls -- it must fire on a planted
`key code 36`, and must NOT fire on the `click button "OK"` that the
clear-blocking-UI ladder really sends.

**AND 10.10b BIT INSIDE THE PROBE ITSELF.** The planted FIFO writer first scored
CAUGHT, which looked like the census working. It was my own comment: it explained
that neither literal appears in the file by SPELLING ONE OF THEM OUT, and the
substring filter matched the comment. The form was evading all along. A probe for
a substring filter must contain no literal that filter looks for.

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
