# Handoff — reset & walk-back automation

State as of 2026-08-27. Everything below was verified by running it, not inferred.

## What works

**Reset: reliable.** `reset_env.reset_environment()` — 3/3, ~17–35s. Opens the
pause menu, verifies the highlighted row before pressing, verifies the
confirmation dialog appeared, verifies the YES press registered, and waits for
the world to return rather than sleeping a guess. Raises `ResetError` rather
than continuing when a step cannot be confirmed.

**Compass: 144ms, accurate.** Was 8500ms. `ocr_glyphs` drives the Tesseract C
API in-process (`tesserocr`) instead of spawning a subprocess per glyph —
8923/8923 agreement with the old path, zero misreads. Geometry is derived from
each frame; there are no hardcoded position constants left.

**Turn control:** `turn_gain.run_turn` — mean error 10.8° at the gain that used
to fail 25.8% of the time.

## What does not work

**The walk is not reliably reproducible.** Same reset, same commands: the
office leg jammed at 2.8s on one run and 7.0s on the next. Cause is the
actuator, not the code — see below.

## The blocker, measured

The smallest turn the stream will deliver is **~28°** (fullscreen; holds of
0.00/0.01/0.05s move a median 28/46/60°, spread 18–51). Aiming is therefore
±28° at best, and that error compounds across a multi-leg route.

**Lowering the in-game camera/look sensitivity would fix this at the root.**
It is the single highest-value change available and it is not a software one.

## The route (`route_verified.py`)

    reset                          spawn heading VARIES 57–91, read it
    270  until_blocked             jam against the office door
      8  timed 1.8s                down the stairs, out to the L&B storefront
    285  until_blocked             jam into the facade -> enters the bar
     66  timed ~0.7s               the "Play ($50)" prompt appears here

Reached the bar interior three times. The final 66° leg showed the prompt at
0.7s but has not yet been confirmed by the detector — walking 2.8s overshoots
it into darkness.

## Things that cost hours, so they are written down

- **Doors are waypoints, not obstacles.** Walk INTO the office door until it
  jams; that is a repeatable position. A timed leg is not — replaying by
  measured duration leaves the character short and the route diverges.
- **Anchor against geometry whenever possible.** The street leg only became
  repeatable once it jammed into the L&B facade instead of aiming at the door.
- **Frame delta means "did I move", never "which way should I go".** Walking
  at a lit lamp scores 60 while covering no ground; a navigator that chose the
  largest delta drove into the lamp.
- **An NPC standing close covers the compass bar** and the bearing reads
  unreadable — looks identical to a broken reader. Step back and it returns.
- **`is_pause_screen` used to false-positive on bright walls** (page fraction
  0.658 vs a real menu's 0.926) and broke the reset. Threshold now 0.80.
- **Never scan while jammed** — the camera is inches from a flat surface and
  every direction looks like a wall.

## Rejected approaches — do not retry without new information

- **template glyph matching**: 72x faster, disagreed with OCR by up to 104°.
- **compass-bar correlation**: ~1ms, but ticks repeat every 10° so it aliases;
  reported −80° for a press that moved +38°.
- **single whole-strip OCR**: 560ms, returns duplicate contradictory letters.
- **optical flow for movement**: turning scored HIGHER flow than walking
  (6.76 vs 2.00) — a third-person camera orbits the character, so flow cannot
  separate rotation from translation here.
- **`in_lb_interior` detector**: eight brightness/texture statistics all
  overlap with the detective's own office, and OCR of the bar's menu board and
  HIGH SCORE sign reads nothing (lettering too small and stylised).

## Tools

    python3 probe.py reset|where|look [n]|walk <bearing> <secs> [steps]|until <bearing>
    python3 go_to_table.py <output_dir>      reset + verified route + search
    python3 bench_route.py <dir> [runs]      reliability and per-phase timings
    bash run_tests.sh                        27 files, all green

## First run on the new machine

`compass_scale.json` and `view_bounds.json` were DELETED before the move on
purpose. They cache the px-per-90-degrees scale and the view centre, keyed by
window geometry, and carrying them to a different screen would silently apply
one machine's geometry to another's frames — the exact failure that produced
confident, wrong headings for hours. They regenerate on first use.

Sanity-check before trusting a run:

    python3 probe.py where          bearing should read, not "unknown"
    python3 probe.py reset          spawn should land in 57-91
    bash run_tests.sh               27 files, all green

Also confirm the game is FULLSCREEN. Windowed, the macOS dock sits inside the
capture and pushes the apparent view centre ~28px right, biasing every bearing
by about 8.5 degrees.

## Never do

Do not press `box` (Square) at the Baseball Cards prompt without the user
saying so — each match costs $50 of in-game money. Arriving at the prompt is
free; the automation stops there deliberately.

## Running while the user works (2026-08-27)

The game is on a second monitor and the automation no longer touches the
keyboard. Three pieces make that true:

**Input goes to the process, not the screen.** `CGEventPostToPid` delivers
keystrokes to chiaki's pid whether or not it is frontmost. `press()`,
`hold_combo()` and `walk_at()` all route through `_bg_hold_keys()` first and
only fall back to pyautogui if that fails. pyautogui sends to whatever app is
frontmost, so every one of those fallback lines can type into the user's work —
treat that path as the dangerous one.

**Focus is never taken.** `focus_chiaki_window()` returns early whenever
targeted delivery is available, and returns early unconditionally under
`BASEBALL_TEST_RUN`. Both are asserted in `test_focus_protection.py`, which
exists because this broke twice in one afternoon and nothing else in the suite
notices.

**Capture is the game, not the desktop.** `fast_capture()` reads chiaki's
window rect from the OS, grabs it, and crops the 16:9 stream out of the
letterbox — 1920x1080, game pixels only. It marks the frame `game_only`, and
`read_bearing` then treats the whole frame as the view instead of hunting for
one.

Do NOT detect the game area by brightness. Tried twice, wrong twice: the
desktop lights the capture edge to edge, and on the game's own frames the
measured width ran 1682px at one threshold and 1937px at another on the SAME
image. Compute it from the window rect.

### Two live traps

* `run_tests.sh` passes env on a line continuation. A comment after a trailing
  backslash ENDS the continuation and silently drops `BASEBALL_TEST_RUN`, after
  which the offline suite runs with background input live and sends real
  keystrokes into the game. Comments go above the `if`.
* The card-region constants are still calibrated for the OLD desktop capture
  and have NOT been re-derived for the 1920x1080 game frame. They are unused
  until a match starts. Re-derive them on a real ban screen before playing;
  the conversion cannot be computed from the old fixtures, because locating the
  game inside them needs the same brightness detection that does not work.

## Turn control (2026-08-27) — solved

    deg = 143.8 * hold_seconds - 0.80     (residuals under 0.5 deg, 0.02-0.14s)

Live closed-loop result: 10/10 targets landed, mean error 0.45 deg, worst 1.0,
zero abstentions, 3.7s average. The previous best in this project was 10.8 deg.

**The old "~28 degree minimum turn" was never real.** It was pyautogui: PAUSE
plus focus-settle inflated every hold far past what was asked for. Delivered
straight to the process, a 0.02s hold turns 2.1 degrees. The route error that
kept compounding was an artefact of the input layer, not the game.

Rules that came out of measuring it:

* **Never use a zero-length hold.** Median 30.5 degrees at 0.00s — more than a
  0.12s hold — because keydown and keyup posted together can be seen out of
  order. `MIN_HOLD_SEC` is the floor.
* **Above 0.14s the response stops being linear**, and 0.20s is bimodal
  (29.5 or 73.5 degrees on identical commands). Stay inside the band and take
  several presses.
* **Settling is measured, never slept.** The camera keeps moving after release,
  and three of twenty identical holds still read their ORIGINAL bearing a third
  of a second later. A fixed sleep reports that as a dropped press, and a
  caller correcting for a phantom miss turns twice.
* About one press in ten keeps rotating past its release, so `turn_to` re-reads
  every step rather than trusting the model.

Two compass fixes came out of the same work:

* **Threshold sweep.** A fixed blob threshold of 120 merged the "W" into a lit
  window behind it; the blob then exceeded the max letter width and was thrown
  away, leaving one letter and an abstention. `BLOB_THRESHOLDS` tries higher
  ones until two letters separate.
* **`img.info["game_only"]` does not survive a PNG round trip.** Every frame
  saved and reloaded looked like a desktop capture and was cropped 220px off
  the compass. `is_game_only_shape()` recognises the 16:9 shape as well.

## Reaching the table (2026-08-27, 23:58) — WORKING

Full chain, from a running patched chiaki:

    python3 inject_reset.py                      # reset via controller injection
    python3 -c "import analog_replay_corrected as a; a.replay('demos/walk_20260827_214446')"
    # then the final approach (see FINAL_STRAFE / FINAL_FORWARD)

Ends on the "Baseball Cards / Play ($50)" prompt. NOTHING presses it — BOX (4)
is refused by an assertion in inject_reset.tap(), because each match costs $50.

### What made it work, in the order the failures were removed

1. ANALOG INPUT. chiaki's keyboard mapping is full-deflection only; the
   recording walks at 0.54. Patched chiaki (chiaki_patch/) accepts real stick
   values. Seven keyboard-based replays failed before this.
2. NO level_pitch. The recording starts straight from a reset; adding a pitch
   home made the replay start from a state the recording never saw.
3. NATIVE 50Hz, PIPE HELD OPEN. Reopening the FIFO per update added latency to
   every write, so the character travelled short — visible as snagging on the
   door out of the first building.
4. HEADING CORRECTION. Pure replay is open-loop: a few degrees of drift over a
   seven-second walk is enough lateral error to clip a doorframe. Correcting
   right_x against the recorded heading fixed the last of it (491/1015 samples
   corrected, final heading 88.6 vs 87.4 wanted).

### Still manual

The final approach is a fixed nudge, not closed-loop — it assumes the replay
ends where it ended tonight. Detecting the prompt on screen and stepping until
it appears would make it robust.

## Pitch is measurable (2026-08-28)

Driving pitch into its endstop and counting steps back gives an ABSOLUTE angle,
with no dependence on scene content. That matters because every scene-based
approach has failed:

* brightness proxies track the room, not the camera;
* structure matching cannot separate a correct match from a wrong one here —
  measured, the worst same-place score (0.301) is BELOW the best
  different-place score (0.329), because the building is full of repeated
  panelling and doorframes. A score threshold is not available.

Measured: the UP endstop settles after ~9 presses (view stops moving), and each
subsequent step moves the view 10.0 thumbnail px (9 usable of 10 samples).
Readings quantise to multiples of 3 because structure_match searches vertical
shift in steps of 3, so read it as 10 +- 1.5.

Structure matching IS reliable for this narrow job — two frames from the same
spot moments apart, differing by one known step, score 0.91-0.97. It is only
unreliable when asked to judge whether two unrelated views are the same place.
