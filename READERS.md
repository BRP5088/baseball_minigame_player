# Reading the screen (§3), and the first live match

Moved VERBATIM out of CLAUDE.md on 2026-09-22 so it is no longer loaded into
every session. Section numbers are unchanged, so a code comment citing
"CLAUDE.md §N" still resolves -- CLAUDE.md carries the map. Nothing here was
reworded; corrections belong in THIS file now, not in CLAUDE.md.

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

**AND `cursor_slot` CAN NOW BE SCORED WITHOUT ASKING IT ANYTHING**, which it never
could before -- every earlier census used the reader's own answer (10.22) or a
human reading a contact sheet. `selected_cards` reports which card has RISEN above
its fan anchor, which is GEOMETRY the glow reader cannot influence, and selecting
requires the cursor to be on that card. So the frame BEFORE a slot newly rises has
a KNOWN cursor slot. `tools/cursor_labels_from_lifts.py <run_dir>` extracts them
from frames already on disk -- no console, no live change, no paid call.

**The filter is doing most of the work and the tool says so.** A lift on ONE frame
is not a selection: mid-deal the fan's anchors shift and a card reads as risen with
nothing selected. Over 14,437 frames of `run_20260828_140236`:

    raw lift transitions                29
    still lifted 3 frames later          4     <- real selections
    dropped as transient                25

and the raw set is dominated by that artefact -- **19 of its 20 "the reader went
blind" cases were slot 0**, i.e. deal frames with no cursor on screen, where None
is the RIGHT answer. Against the 4 survivors the shipped reader is 4/4, which
proves the METHOD and nothing about the reader at that n (10.8).

**Yield is ~4 labels per recorded run, so point it at every future run** and the
corpus accumulates for free. That matters because the archive cannot currently
support a threshold on this path at all: 4,183 five-row turn frames exist and
**4,142 are one run**, at 10 Hz.
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

    columns    start 0.1552   pitch 0.1376   card width 0.1155   (fitted, residual +-0.0004)
    rows       pitch 0.328     card height 0.2995   (= CARD_ASPECT 1.4587 x column width x w/h)

**THE HEIGHT IS THE MEASURED NUMBER AND `CARD_ASPECT` IS DERIVED FROM IT.** 0.2995 is
validated against a hand-read ruler and has never moved; the aspect says how to REACH it
from the column width, so it has to be re-derived every time the width is re-measured.
That has happened twice -- at the loose 0.130 it was 1.296, at 0.108 it was 1.560, at the
fitted 0.1155 it is 1.4587 (`ban_grid.py:82-98`). This file quoted the 0.130/1.296 pair
long after the fit replaced it, which is the failure mode of copying a constant into
prose: the source moves and the copy does not.
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


## THE FIRST LIVE MATCH: THE HAND READER IS CALIBRATED AT A WIDTH THE RIG NO LONGER CAPTURES

A $50 match played end to end on 2026-09-13, the first ever -- every earlier one died at
the paid orientation read. It could not play a single card, and the cause is one number.

**CORRECTION, and it matters: THE RIG DID NOT CHANGE. THE CODE UPSCALES ON PURPOSE.**
The first write-up of this said "the rig captures 2000x1125" as though the hardware had
moved. It has not. The PS5 streams 1920x1080 and both capture functions return exactly
that -- `compass.fast_capture()` and `game_capture.grab()` measured live, both 1920x1080.
It is `_fast_grab` that asks for something else:

    img = game_capture.grab(width=SETTLE_CALIBRATION_WIDTH)   # 2000 at the time

and its own comment says why: "the logged frames the SETTLE_THRESHOLDS were calibrated
against were 2000px wide. Mean-absolute-delta is scale-sensitive -- downscaling averages
noise differently -- so feeding a different resolution silently shifts every threshold."

**THERE WERE TWO CALIBRATION WIDTHS IN THIS CODEBASE AND THEY DISAGREED. THE CONSTANT
HAS SINCE MOVED TO 1920 (`orchestrator.py:2231`, commit 27cd4ae) AND THEY NOW AGREE** --
this file went on quoting 2000 in three separate comment blocks after the change, and a
sweep on 2026-09-17 took the stale figure from here and nearly re-reported it as current:

    SETTLE_CALIBRATION_WIDTH = 1920     the settle gate; mean-abs-delta is scale-sensitive
    local_hand.ANCHOR_W      =  979     the hand crop, which a 1920 px frame produces

    a 1920 px frame  ->  hand crop  979 px   (= ANCHOR_W, exactly)
    a 2000 px frame  ->  hand crop 1020 px   (4% too wide -- the defect below)

One `_fast_grab` serves both readers, and the hand reader is the one that loses. That is
also why the diagnostics bundle carried both sizes: `screen_at_stall.png` comes from
`_fast_grab()` (upscaled) and `after_stall_*.png` from `game_capture.grab()` with no
width argument (native).

Normalising the HAND CROP to ANCHOR_W reconciled the two rather than picking a side: the
settle gate kept its frame and its thresholds stayed valid, the hand reader got the 979 px
crop it was measured on. **That normalisation is STILL load-bearing now the widths agree**,
because it is about the CAPTURE geometry and not about this constant: re-measured
2026-09-17 at 1867x1050, a live geometry this rig does produce, the hand read goes
0.706 -> 0.978 with it. Do not remove it on the strength of the two widths matching.

**The reader is calibrated at a HAND CROP 979 px wide (`local_hand.ANCHOR_W`). `_fast_grab`
hands it 1020 px -- 1.042x.** Section 3 has carried "the
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
cursor (glow 10.4-10.9 against `CURSOR_GLOW_MIN`, **15 at the time; it is 10.0 now**,
`local_hand.py:1198`, fitted between a fixture false max of 8.4 and a live true of 12.4 --
so the same glows would read today). Not one card was played. Note `ban_grid.py:611` also
defines a `CURSOR_GLOW_MIN`, at 0.030: a FRACTION of pixels, a different quantity from the
hand reader's brightness lift, and the two must never be compared.

**NOTHING ON DISK COULD HAVE CAUGHT IT.** Every archived frame is 1920x1080 -- they were
written by `game_capture.grab()`, which does not upscale -- so the whole corpus sits at
the calibration width by construction, normalising is a literal no-op there, and no
census taken from it could show the gap. The failing geometry exists ONLY in memory,
between `_fast_grab` and the reader, and is never written to disk. 10.31's shape again:
a population that cannot contain the failing class.

Fixed by normalising the hand crop to ANCHOR_W in `crop_gameplay_regions`, the one place
every consumer takes it from, so the scale factor `img.width / ANCHOR_W` is exactly one for all of them at
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

**`ocr_scoreboard` FAILS ON THE RESULT SCREEN AND ON THE OPPONENT ROW, NOT IN
GENERAL. MEASURED 2026-09-17; this entry said "unmeasured rate, open".** The
original observation stands -- "JACK PEPPER 3 0 3 / OPPONENT 0 4 4" plainly on
screen returning `{'your': None, 'opponent': None}` -- but it is not the general
behaviour, and reading it as one sent a census after the wrong quantity:

    TURN / REVEAL screens (a scoreboard IS drawn)   23 of 23 read BOTH rows  100%
                                                   (re-derivable: run
                                                   tests/minigame/test_scoreboard_populations.py,
                                                   which globs the 23-frame corpus and prints it.
                                                   This line said 33 until 2026-09-20; the census
                                                   shipped in the same commit only ever globbed 23,
                                                   so the prose and the script never agreed.)
    RESULT screens                                   4 of  8 read both        50%
                                                     3 of  8 read ONE row
                                                     1 of  8 read neither

**AND THE ONE-ROW FAILURES ARE ALL THE OPPONENT ROW**: `[0,2,2] / None`,
`[0,0,0] / None`, `[5,0,5] / None`. So the defect is SCREEN-SPECIFIC and
ROW-SPECIFIC, which is a different repair from "the reader is unreliable".

**THE FIRST ATTEMPT AT THIS MEASUREMENT WAS THE WRONG DENOMINATOR, AND IT IS THE
SAME MISTAKE `read_phase` INVITED THE SAME DAY.** Over 1,400 archived frames it
read both rows on 17 (1.2%) -- which is not a failure rate, it is the share of the
archive that is a TURN SCREEN at all. Most frames on disk are navigation shots with
no scoreboard drawn. A rate needs a population where the thing being read is
PRESENT; see 10.31.

**AND THE RESULT-SCREEN HALF IS UNREACHABLE IN PRODUCTION, so it is CLOSED rather
than open.** The user's point, 2026-09-17: if the result screen is up there is no
need to read the scoreboard at all. Checked, and the code already agrees --
`local_game_state` RETURNS at orchestrator.py:4022 on a result screen, before the
scoreboard read at :4116 is ever reached, and `log_local_read_comparison` is gated on
`screen in ("turn", "discard_prompt")`. The only remaining call sites are three
diagnostics in `tools/`. So the 50% is a rate for a question nothing asks.

10.31 records that `run()` prefers `local_state.read_result`'s named outcome over a
score comparison precisely because "a wrong score is worse than no score, because
run() acts on it". The measurement confirms that choice rather than opening work.

**THE METHOD MISTAKE IS WORTH MORE THAN THE NUMBER: reachability should have been
checked BEFORE the census, not after.** A reader's failure rate was measured
carefully on a screen the live path never hands it -- the same shape as the wrong
denominator one paragraph up, one level out. Ask what CALLS it before measuring how
well it works.

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
