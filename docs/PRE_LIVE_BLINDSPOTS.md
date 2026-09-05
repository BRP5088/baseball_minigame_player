# Pre-Live Blind Spots — first-contact review of the 2026-08-25 changes

Scope: what breaks on the **first live iteration**, not what's wrong by reading.
Nothing here re-litigates QA_FINDINGS R1-R6 correctness work. No files were
modified except this one. Nothing was run that touches the PS5.

Environment measured on this machine, 2026-08-25:

- Python 3.14.0, `mss` **10.2.0**
- **Two active displays.** `monitors[1]` = built-in `1728x1117` @ (0,0);
  `monitors[2]` = external `3440x1440` @ (-855,-1440)
- `screencapture -x` (pyautogui's macOS backend) returns `3456x2234` — the
  same built-in display, at 2x. Both backends currently see the same screen.
- Offline suite: **11/11 PASS** (`./run_tests.sh`)

---

## BLOCKERS — fix before the live run

### B1. `REVEAL_EDGE_THRESHOLD = 0.070` is no longer a valid separator on the mss capture path

`orchestrator.py:1175`, used by `_center_card_edge_fraction()` at
`orchestrator.py:1179-1186`.

**Mechanism.** The threshold was calibrated on `screenshot_log/` frames.
`SETTLE_TIMING_ANALYSIS.md:6,13` states those are `2000x1292`, "full native, no
downscaling was used anywhere" — i.e. captured by `pyautogui` at `3456x2234` and
**downscaled** to 2000. `_fast_grab()` now captures at `1728x1117` and
**upscales** to 2000 (`orchestrator.py:1060-1062`, bicubic). Upscaling
interpolates; it cannot create the high-frequency detail a 3456→2000 downscale
retains. Gradient magnitude is exactly the quantity that loss destroys, and
`_center_card_edge_fraction()` is a count of pixels whose gradient exceeds a
fixed cutoff of 28.0.

**Measured** (453 frames sampled from `screenshot_log/`, simulating the mss path
as 2000→1728→2000; the native column is the frames exactly as calibrated):

```
                       native (calibrated)   mss path
CARDS PRESENT   min        0.0792             0.0694
NO CARDS        max        0.0619             0.0563
separating gap         [0.0619, 0.0792]   [0.0563, 0.0694]
headroom of 0.070 above the gap floor:
                          +0.0092            -0.0006
```

The threshold has moved **outside the separating gap**. The dimmest genuine
cards-present frame now scores 0.0694, below the 0.070 trigger. Mean shift
across all frames is a factor of **0.920**.

**Fix:** lower `REVEAL_EDGE_THRESHOLD` to **0.063** (midpoint of the shifted
gap). One-line change, restores roughly the original margin on both sides.

**Why this is a blocker and not a watch item:** the failure is *completely
silent*. `wait_for_reveal_cards()` returning False raises at
`orchestrator.py:2284-2285`, and that exception is swallowed by a bare
`except Exception: pass` at `orchestrator.py:2325-2326`. There is no print, no
counter, no log line. The only observable symptom is that every played turn
stalls for the full `max_wait=6.0` and `match_log.jsonl` quietly stops gaining
`opp_card_name`. On a first live run you would attribute that to the game being
slow.

### B2. The `_fast_grab()` pyautogui fallback skips the normalisation it exists to guarantee

`orchestrator.py:1049-1050`:

```python
if _MSS is None:
    return pyautogui.screenshot()      # early return — never reaches the resize
mon = _MSS.monitors[1]
...
if img.width != SETTLE_CALIBRATION_WIDTH:   # unreachable on the fallback path
```

The comment at `orchestrator.py:1054-1059` correctly states that "any capture
backend must be normalised to this before its deltas are compared against
`SETTLE_THRESHOLDS`". The fallback is a capture backend and is not normalised —
it returns 3456-wide frames straight into `_grab_settle_regions()` and
`_center_card_edge_fraction()`. The docstring's claim that a missing mss
"degrades to the old behaviour" is false: the old behaviour was a
`DIFF_THRESHOLD` tuned for that resolution, not the new per-region thresholds
tuned for 2000.

Impact is conditional (mss is installed and importing fine here, so this path is
dormant today), but it is a one-line fix and it is the difference between a safe
degradation and a silent miscalibration on any machine or venv where the `mss`
import fails. Move the resize above the early return, or apply it to both
branches.

---

## WATCH ITEMS — likely fine, watch these specifically on run 1

### W1. Silent screen-recording-permission failure is the highest-consequence unknown

`_MSS = _mss.mss()` at `orchestrator.py:1036-1040` runs at import and only loads
CoreGraphics — it does not capture, so it cannot fail there. The first
`_MSS.grab()` is what hits TCC. On macOS, when Screen Recording permission is
absent, `CGWindowListCreateImage` **succeeds and returns a well-formed image
containing only the desktop, with all window content missing**. It does not
raise. mss has no way to detect this.

This did not apply before, because `pyautogui` shells out to the `screencapture`
binary, which is a *different* TCC principal from the Python process. The new
path requires the permission in-process for whatever terminal or launcher runs
`orchestrator.py`.

Verified from my shell: `CGPreflightScreenCaptureAccess()` → `True`, and an mss
grab compared against a `screencapture` grab at the same instant differs by mean
abs delta **1.572** on 0-255 — i.e. mss is seeing real window content, not a
bare desktop. But TCC is granted per responsible-process, so a run launched from
a different terminal app can differ.

**Symptom if it is wrong:** `wait_for_screen_to_settle()` returns in ~0.39 s
*every single time* (2 stable polls of a frozen desktop), and
`wait_for_reveal_cards()` times out at 6.0 s every turn. `read_game_state()`
keeps working, because it still goes through `pyautogui`. So the loop plays on,
reading mid-animation, with the settle gate effectively disabled — the exact
defect the region-aware work was built to fix, reintroduced invisibly.

### W2. `monitors[1]` is not pinned to the display Chiaki-ng is on

`orchestrator.py:1051`. Two displays are active. Today `monitors[1]` is the
built-in and that is also what `screencapture` returns, so the two capture paths
agree. Three ways that breaks:

- **Main display changes.** If the menu bar is dragged to the 3440x1440
  ultrawide, `monitors[1]` may become the ultrawide. `_fast_grab()` would then
  *downscale* 3440→2000 producing a `2000x837` frame at aspect 2.39 instead of
  1.548, and every fractional box in `GAMEPLAY_REGIONS_FRAC` /
  `REVEAL_CENTER_REGION` would land on the wrong part of the screen. Settle and
  reveal would read garbage while `read_game_state()` still looked plausible.
- **Chiaki-ng moved to the external display.** Both backends capture the main
  display only, so the game would be invisible to everything.
- **Monitor list is cached for the process lifetime.** `mss.base.MSS.monitors`
  memoises into `self._monitors` on first access and never refreshes. Unplugging
  or rearranging displays mid-run leaves stale geometry with no error.

**Precondition to confirm before starting:** Chiaki-ng is on the built-in
display, and the built-in is the main display. The whole crop calibration
assumes a 1.548 aspect.

### W3. Faster settle + `acted_screen` guard means more repeat keypresses on a slow overlay

`poll_interval` 0.3→0.15 and the mss backend together cut a "2 stable polls"
settle from ~1.5 s of real time to a measured **~0.39 s** floor
(`_grab_settle_regions` measured at p50 **48.5 ms** for the `turn` set, 47.7 ms
for `default` — the ~32 ms claim at `orchestrator.py:1028` is 27 ms for the grab
plus 19 ms for the resize).

Consequence at `orchestrator.py:2098-2103`: after `press("close_result")` the
loop re-polls ~1.1 s sooner than it used to. If the result overlay needs longer
than that to dismiss, the next read returns `result`, the C1 guard fires
(`orchestrator.py:2042-2051`), and it sends **another** `close_result`. Each
guarded cycle also burns one `stuck_count` toward `MAX_STUCK_ATTEMPTS = 15`.

Two things to watch: (a) extra Circle presses landing on whatever screen appears
after the overlay finally dismisses, and (b) `stuck_count` climbing on normal
result transitions and stopping the run early. Same shape applies to the
`match_start_prompt` guard at `orchestrator.py:2110-2119`, which re-sends
`start_match` (`\`).

The guard itself is sound — it suppresses the debit and the re-score, so this is
a nuisance-and-extra-keypress risk, not a money risk.

### W4. Every non-turn settle now waits on `hand`, which is only calibrated for the turn screen

`SETTLE_REGION_SETS["default"] = ("legacy_roi", "hand")` at
`orchestrator.py:984`. Only one call site opts into `"turn"`
(`orchestrator.py:2346`). The other nine — `1748` (inside the ban-screen scroll
loop, up to 20 times per scan), `1772`, `1791`, `2050`, `2102`, `2118`, `2134`,
`2212`, `2236` — all use the default, so they now gate on `hand` too.

`SETTLE_THRESHOLDS["hand"] = 8.0` was set between the idle p95 and p99 of the
`hand` region **on the turn screen**. On a result overlay, the ban grid, or the
pause menu, the y 0.716-1.0 band is something else entirely and its idle noise
is uncharacterised. If it sits above 8.0 on any of those screens, that settle
call burns its full `max_wait` every time.

**Symptom:** `[settle] 'default' regions still moving after 8.0s` printing on
every result / ban / match-start transition. On the ban scan that is up to
20 × 6 s = 2 minutes of dead time per collection read. Cheap to fix if seen —
add a region set for those screens, or drop them back to `("legacy_roi",)`.

### W5. Per-turn wall clock went up, not down

Reveal changed from a flat `time.sleep(0.5)` to a poll of up to 6.0 s
(`orchestrator.py:1189`), which runs **before** the settle wait. Turn cost is now
`play + reveal(0.3–6.0 s) + settle(0.39–8.0 s) + 0.4 s`. If B1 is not fixed the
reveal leg pins at 6.0 s on most turns. Expect ~10 turns/match; that is a minute
per match of pure stall, silently.

### W6. `regions="reveal"` in the docstring does not exist

`wait_for_screen_to_settle`'s docstring at `orchestrator.py:1102` advertises a
`"reveal"` set; `SETTLE_REGION_SETS` (`orchestrator.py:981-985`) only defines
`"turn"` and `"default"`. `SETTLE_REGION_SETS.get(regions, ...)` at
`orchestrator.py:1123` falls back silently, so a future caller passing
`"reveal"` gets `"default"` with no error. No live impact today — nothing passes
it. Worth a one-word docstring fix so it doesn't become a real bug later.

### W7. Ban cursor column is restored across matches by assumption, not by code

`input_controller.py:190-191` walks `move_up` back to row 0 before confirming,
but never walks the **column** back to 0. `select_bans_and_start_full` then
assumes `current_row, current_col = 0, 0` on entry (`input_controller.py:179`),
and from match 2 onward `read_full_ban_collection` short-circuits on
`_cached_ban_collection` (`orchestrator.py:1626-1628`) so nothing re-normalises
the cursor either.

If the ban screen preserves cursor position between matches — as the hand
demonstrably does (`input_controller.py:92-98`: "the game does NOT reset the
cursor to position 0 between turns") — then every ban from match 2 onward lands
`last_col` columns off target. That is a wrong-ban on a $50 match.

Mitigating: this navigation skeleton is not new today. `select_bans_and_start_full`
with its double `confirm_play` "ran successfully through every ban screen of the
2026-08-24 live session" (`input_controller.py:193-199`), which implies the
cursor does reset. Only the *name → (row, col)* selection changed today. So this
is very likely fine — but it is the one place where a wrong assumption costs
money, so watch the second match's ban screen specifically.

### W8. Audit mode (`compare_local_reads=True`) blocks the loop for up to 5 minutes

`hand_digit_reader.py:164-166` runs PaddleOCR as a subprocess with
`timeout=300`, called synchronously from the main loop on every turn via
`log_local_read_comparison` (`orchestrator.py:896`). A hung worker parks the
automation on a live turn for five minutes.

Not armed by default — `run(target_wins=17)` at `orchestrator.py:2374` passes
neither `compare_local_reads` nor `log_screenshots`. PaddleOCR models are already
cached (`~/.paddlex/official_models`), so there is no first-call model download.
If you do enable audit mode for this run, that 300 s timeout is the thing to
shorten first.

---

## SAFE — checked and cleared, please don't re-litigate

- **`SETTLE_THRESHOLDS` survive the capture swap.** This was the obvious worry
  and it is a non-issue. Measured over 899 consecutive frame pairs, native vs
  mss-path: `hand` p50 5.41→5.05, p90 25.84→25.68, p99 53.89→53.84; `legacy_roi`
  p50 5.02→4.94, p99 55.08→55.06. Of pairs the calibrated path calls MOVING,
  the mss path still calls moving **247/252** (`hand`) and **313/319**
  (`legacy_roi`) — a 2 % shift. Mean-abs-delta is dominated by large-amplitude
  motion, which the resize preserves; unlike the gradient count in B1, it is
  nearly scale-invariant here. The 8.0 / 6.0 thresholds do **not** need
  re-tuning.

- **`_MSS` thread safety.** Non-issue twice over. First, mss 10.2.0's
  `MSS.grab()` holds a per-instance `self._lock` (`mss/base.py:255,311`), so
  concurrent grabs serialise correctly. Second, the screenshot logger does not
  use the mss path at all — `_screenshot_logger_loop` calls
  `pyautogui.screenshot()` directly (`orchestrator.py:655`). The two capture
  paths do not share `_MSS`. (The premise that the logger "now shares the
  capture path" is not what the code does.) And the logger is off by default.

- **`_MSS` resource lifetime.** No leak. `mss/darwin.py`'s `grab()` releases
  both the `CFData` copy and the `CGImage` in a `finally`, and the darwin
  implementation has no per-grab handle to accumulate. `close()` is a no-op on
  this backend, so never calling it costs nothing over a long session.

- **mss captures the same content pyautogui did.** Compared at the same instant:
  mean abs delta **1.572** on a 0-255 scale after normalising both to 2000 wide,
  with matching mean/std (31.94/34.85 vs 32.15/34.07). No overlay, cursor, or
  DPI discrepancy. Both exclude the cursor. Both target the same display.

- **Frame geometry lines up exactly.** `int(1117 × 2000/1728) = 1292`, so
  `_fast_grab()` yields `2000x1292` — byte-identical dimensions to the
  calibration frames. Every fractional crop box lands where it was measured.

- **The reveal trigger raising does not abort a turn or lose a match.** Traced
  fully: `RuntimeError` at `orchestrator.py:2285` → caught by the bare
  `except Exception: pass` at `orchestrator.py:2325-2326`. It is inside the
  best-effort matchup-logging block, *after* `select_and_play()` has already
  committed the play and *after* `turns_this_half += 1` and before
  `stuck_count = 0` at `orchestrator.py:2327` — which still executes, because
  the `try` is nested inside `if matchup_info is not None:` and the reset is
  outside it. Consequence is exactly: `pending_matchup` stays `None`, that turn
  is not logged to `match_log.jsonl`, loop continues. No turn lost, no match
  lost, no money. (The cost is the 6 s stall and the silence — see B1/W5.)

- **No new double-$50-debit or mis-scored-result path.** The `acted_screen`
  guard is the mechanism *preventing* both, and its logic holds: it is set
  before the debit (`orchestrator.py:2120`) and before the score
  (`orchestrator.py:2064`), `save_progress` is the last statement in the result
  `try`, and the `screen != "other"` carve-out at `orchestrator.py:2029` correctly
  refuses to let a single misread re-arm the guard. Today's changes make this
  guard fire *more* often (W3), which is the safe direction.

- **Position-based ban selection is strictly safer than the name-based version
  it replaced.** The `id()`-distinctness check (`orchestrator.py:2190-2194`) and
  the 3-distinct-positions check (`orchestrator.py:2195-2198`) both raise
  *before* any keypress is sent, and `select_bans_and_start_full` re-validates
  and raises before its first `press()` (`input_controller.py:173-177`). A
  failure is a clean retry with no partial toggling. The old name-based path
  could toggle 4 physical cards for 3 intended bans; this cannot.

- **Two-read roster learning has no first-contact failure.**
  `_learn_roster_entry` (`orchestrator.py:1445-1470`) holds first sightings in
  the in-memory `_pending_roster` only, tolerates a corrupt cache on both the
  import path (`orchestrator.py:1395-1433`) and the write path
  (`orchestrator.py:1458-1466`), and writes atomically. `known_ban_roster_learned.json`
  does not exist yet; `_load_learned_roster` returns cleanly on that
  (`orchestrator.py:1401-1402`).

- **`_cached_ban_collection` is initialised** at `orchestrator.py:1584` — no
  NameError on the first `read_full_ban_collection()` call.

- **Offline suite is green.** 11/11 PASS, including `test_settle_regions.py`,
  which asserts the settle regions actually overlap what the readers read.

- **Cosmetic only:** `mss.mss()` is deprecated in 10.2.0 in favour of
  `mss.MSS()`. Since `orchestrator.py` runs as `__main__`, the default warning
  filter *will* print one `DeprecationWarning` at startup
  (`orchestrator.py:1038`). Harmless, but expect it in the log and don't chase it.

---

## Recommendation

**Conditional GO — after a one-line change.**

Set `REVEAL_EDGE_THRESHOLD = 0.063` (`orchestrator.py:1175`). Optionally also
move the resize in `_fast_grab()` above the fallback's early return
(`orchestrator.py:1049`). Neither touches decision logic, neither can affect a
ban or a debit, and both are covered by the existing offline suite.

With B1 fixed, nothing found in today's changes can cause a wrong ban, a double
$50 debit, or a mis-scored result. The residual money-adjacent risk (W7, ban
cursor column) is pre-existing and was exercised successfully in the 2026-08-24
live session.

### The single most important thing to verify in the first 60 seconds

**That `wait_for_screen_to_settle()` ever reports a wait longer than ~0.4 s.**

Watch the first turn transition. A healthy run shows settle waits varying with
the animation — hundreds of milliseconds to a few seconds. If **every** settle
returns in ~0.39 s and **every** reveal times out at 6.0 s, mss is returning a
window-less desktop frame: Screen Recording permission is not granted to the
interpreter running the script, and the settle gate is silently disabled while
the loop plays on reading mid-animation.

Confirm before launching, from the *same terminal* you will run the script in:

```
python3 -c "import ctypes; cg=ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreGraphics.framework/Versions/Current/CoreGraphics'); cg.CGPreflightScreenCaptureAccess.restype=ctypes.c_bool; print(cg.CGPreflightScreenCaptureAccess())"
```

It must print `True`. And confirm Chiaki-ng is on the **built-in** display, and
that the built-in is the **main** display (W2).
