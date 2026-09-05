# Pending on real match data

Everything below needs actual live games to resolve — either because
it's genuinely new information a local simulation can't produce, or
because it's only been exercised a handful of times and needs more reps
to build real confidence. Last updated 2026-08-24.

## RESOLVED live 2026-08-25 (throwaway save, 1 partial match)

**C5 — the loop could pay twice for one match. FIXED.** Observed directly:
paid $50 at 16:58, scan + 3/3 bans applied by 17:01:40, match began, and the
"ROUND 1" transition overlay at 17:01:46 was classified as
`match_start_prompt`. `acted_screen` was `"ban_screen"` by then so the C2 guard
had already cleared — the next step was a second $50 debit for a match already
paid for. A `max_spend=50` cap stopped it accidentally. Fixed with
`match_in_progress` (set on debit, cleared on a scored result); regression
tests cover both the double-debit and the over-suppression direction. See
LESSONS.md §5.

**Ban navigation confirmed WORKING.** The scroll-scan unwind and the
position-based ban selection both behave: 0/3 -> 1/3 -> 3/3 across
17:01:28-17:01:40. An earlier claim in this session that "the bans never
landed" was wrong — it read frames from during the unwind, before the
keypresses. Item 9's ban-screen work stands.

**Item 14 (`list index out of range` in `play_one_turn`) — mitigated,
not yet re-observed.** `validate_game_state()` now rejects a turn with no
player card in hand, converting that crash into a retryable ValueError with a
legible message. Not seen live since the change (no turns were played).

### Still unmeasured after 2026-08-25 — the run stopped before any turn
- Focus-cache behaviour under live network latency (the `[input]` per-turn line)
- Misfire rate (zero cards played)
- Settle latency at the real poll rate: 6 samples only, all `default` region,
  p50 0.47s / p90 0.48s / 0% truncated. Nothing on the `turn` gate.
- Whether the input-prompt detector agrees with vision

---

## Flagged during tonight's live run, wants follow-up (not urgent, run kept working)

**14. Recurring transient errors in `play_one_turn()`** — two distinct
exceptions seen repeatedly during the first live run of today's crop-
payload change: `max() iterable argument is empty` and `list index out
of range`. Both self-recovered via the existing retry logic every time
they occurred (roughly half a dozen times across ~2-3 matches) and
never produced a wrong play — worst observed consequence was an
unnecessary discard, never a bad card selection. Circumstantial
evidence points at screen-transition timing (a "ROUND 1" transition
overlay was directly caught by the screenshot logger moments before one
occurrence, and ~2/5 "power 0 best card" reads happened right after
match-boundary transitions) rather than a genuine hand-parsing bug, but
this wasn't confirmed with a full traceback — only the caught
exception's message string reaches the console. Worth digging into
properly later: pull the exact frames from `screenshot_log/` at the
timestamps matching these console lines to confirm what the pipeline
actually saw, and consider whether `hand_to_cards()`/`should_redraw()`
(the `max(c.power for c in hand_players)` call, decision_engine.py:160)
should guard against an empty hand explicitly rather than relying on
the outer retry to paper over it.

## Tonight's punch list (2026-08-24 cropping/region + OCR work)

Base-diamond crop regions were recalibrated this session using real
screenshots (scoreboard, hand, first/second/third base), and this is
now WIRED IN: `read_game_state()` sends the overview + 5 labeled crops
from `capture_state_images_b64()` instead of one full-frame image —
this is the core per-turn vision call, never run against a live match
in this form. First few real turns tonight should be watched closely
to confirm the model is actually reading scoreboard/hand/runners off
the sharp crops rather than getting confused by receiving 6 images
instead of 1, and that non-turn screens (ban_screen, result,
match_start_prompt) still classify correctly from the overview alone.

Local OCR (tesseract via `ocr_scoreboard()`) is also new — exact match
on 6/6 numbers across 3 real screenshots, but NOT wired into
`read_game_state()`/`GameState` yet, deliberately: proven offline
against static photos, not yet cross-checked against the vision read
on a live, changing game. Worth running both side-by-side for a few
real turns before trusting OCR's numbers over vision's.

**13. Background 1Hz screenshot logger — also being tested tonight,
opt-in via `run(..., log_screenshots=True)`.** Saves a timestamped,
pipeline-downscaled frame to `screenshot_log/` roughly once a second in
a background thread, purely for post-hoc analysis — never read by
anything, never affects play. Built specifically because everything
tested this session (hand-card art matching, crop calibration) used
manual screenshots with no guarantee they were captured at a settled
moment, and one real finding (hand-card fan-layout edge-slot position/
scale jitter, see `hand_card_matcher.py`'s docstring) couldn't be
confirmed as a real live-pipeline problem vs. a manual-screenshot
artifact without genuine, consistently-captured reference frames.
Deliberately does NOT call `focus_chiaki_window()` (unlike every other
capture in this file) — forcing window focus every single second would
yank focus away the moment the user alt-tabs mid-run, which is worse
than an occasional logged frame of the wrong window. Smoke-tested
offline (4 frames in ~3.5s, correct cadence); never run over the
length of a real match, so watch disk usage and confirm it doesn't
introduce any contention with the main loop's own screenshot/input
calls sharing the same process.

**10. `third_base`'s box — confirmed working with a real runner on it,
but only against a non-representative photo.** Corrected from a wrong
position (was centered on the always-face-down pitcher card next to
it, not the actual third-base coin) to the real coin location,
fraction `(0.3225, 0.320, 0.4375, 0.530)`. A found-online screenshot
(different aspect ratio than the pipeline's own capture, watermarked —
not a real pipeline frame) confirmed the box correctly shows a real
player card (Donny Mekesz) when third base is occupied, not just the
bare coin — good sign the underlying logic is right. Still needs a
check against an actual pipeline-resolution capture with a live runner
on third before fully trusting the box's precision at that resolution.

**11. Need to read the opponent's revealed card(s) during a reveal
moment, not just detect that a reveal happened.** A home-run screenshot
showed the previously-assumed-always-face-down pitcher slot flip
face-up during resolution, revealing the *opponent's* actual pitcher
card — exactly the data `match_log.jsonl` wants (your card + their real
card) but currently has no way to read, since nothing in
`orchestrator.py` parses that slot's content. Ties directly into item
#2 below and into `read_matchup_reveal()`.

**Follow-up, confirmed via a second found-online screenshot (not a live
pipeline capture — user explicitly flagged it as untrustworthy for
pixel calibration, only for confirming behavior):** each side CAN show
2 cards stacked together during a settled reveal — the player card plus
a separate attached tactics card (e.g. the opponent's pitcher + their
"Fielding Play"). First fix attempt told the model to skip tactics
cards entirely to avoid `run()`'s opponent-card matching (`next(c for c
in reveal_cards if c.get("name") != our_card_name)`, around line 1410)
picking a tactics card's name/stats as the "opponent's card" — but the
user caught that this throws away real data: `simulate.py`'s
`power_bonus()` already established that swing/pitch tactics bonuses
add directly to power, so an opponent who boosted their power would
silently look like an unexplained outcome in the fielding/speed
analysis instead of an explained one. Corrected: `READ_MATCHUP_PROMPT`
now reports tactics entries too, tagged `"kind": "tactics"` with a
`"paired_with"` field naming which player card they're stacked with —
`run()` uses `kind=="player"` to find the opponent's real card (fixing
the original mismatch bug) and separately looks up their paired tactics
entry for `opp_tactics_bonus`, mirroring the `our_tactics_bonus` field
that already existed for our own side. Fixed in the prompt and
`run()`'s consumption logic; not yet run live.

**Deliberately NOT done: no new crop region added for the reveal
position.** The reveal cards in that screenshot sat lower than the
calibrated `second_base`/`first_base` boxes — but per the user
(2026-08-24), that specific photo isn't representative enough to
calibrate real pixel coordinates from, and `read_matchup_reveal()`
already sends the full frame (not a tight crop) so it doesn't depend on
knowing the exact position anyway. Also flagged by the user: actually
*capturing* this moment as a screenshot may be difficult for timing
reasons — the reveal may render only briefly. This is the same risk
item #2 already names (the blind 0.5s sleep before
`read_matchup_reveal()` has never been validated against a real
card-clash frame); watch the first few real turns closely for whether
the capture actually lands on the reveal or misses it.

**12. Home-run screen layout confirmed correct** (mockup image, not a
representative pipeline capture — different aspect ratio than real
captures, so not worth calibrating crop boxes against it specifically).
Useful for confirming the "PITCHER"/"BATTER" reveal + played-tactics-
card-near-home-plate layout, not for pixel calibration.

## Waiting on real match data

**1. The fielding/speed secondary-stat blind spot** — the big one.
`match_log.jsonl` is built and wired in specifically for this; needs
~150-200 real logged turns before there's enough signal to analyze.
Answers whether `best_pitching_play`'s fielding-priority pitcher
selection (and the speed-boost fallback in batting) should be kept,
changed, or dropped. See `HEURISTICS.md` §2 and §5 — everything parked
there is really this same underlying item. Once analyzed, follow the
documented removal plan on `MATCH_LOG_FILE` in `orchestrator.py`.

**2. The matchup-logging pipeline itself is genuinely untested live** —
`read_matchup_reveal()` has only been sanity-checked against an
empty/no-game screen. The real reveal-animation timing (the blind 0.5s
sleep before reading it, in `run()`'s "turn" branch) has never been
validated against an actual card-clash frame. Watch the first few real
turns closely to confirm it's actually catching the right moment and
not silently missing every reveal.

**3. `validate_game_state()` hasn't been live-run since it was added** —
it should fix the recurring `list index out of range` error seen in an
earlier run's log, and `test_validate_game_state.py` passes, but there
hasn't been a full automated live run since wiring it in to confirm it
actually stops recurring in practice.

**4. Home-run-length animation settle timing** —
`wait_for_screen_to_settle()` was only validated against lighter
animations (discards, ~2.1-2.2s). A real home run's longer/more complex
animation could plausibly trigger "settled" too early, mid-animation.
Watch the first home run closely once matches resume.

## Resolved live, 2026-08-23 (Taylere's save)

**9. The ban-screen `kind`-based tactics filtering** — got its first
live test on Taylere's less-complete collection and passed (correctly
tagged `kind` on real entries). But that same test surfaced a real,
costly bug: her collection has locked/not-yet-owned cards (rendered
faded, no visible power) mixed into the ban grid — something your fully
maxed-out collection never exercised. `choose_bans()`'s `sorted()`
crashed comparing `None` to an `int`, burning 15 retries and a real $50
match before giving up. Root-caused and fixed with three layers: (1)
prompt now explicitly says skip faded/unreadable cards rather than
guessing at their values, (2) `read_full_ban_collection()` filters out
any entry with a missing name, a placeholder name ("Unknown", "N/A",
etc. — the model invented these instead of following the prompt's "skip
it" instruction on the first two fix attempts), or `power <= 0` (a
guessed `0` for an unreadable card slipped past a plain `isinstance`
check). Re-tested live against the same ban screen after each fix layer
until it came back clean (25 real cards, zero placeholders, zero
duplicates) and the match was successfully recovered.

**Follow-up, built the same day**: the reactive filters above catch
every specific fabrication pattern actually observed, but wouldn't catch
the model guessing a plausible-but-wrong value for a locked card (a fake
"power: 5" that looks like a normal entry). Closed that gap properly:
`mask_low_contrast_regions()` detects locked/faded cards via local PIL
contrast analysis and blacks them out *before* the screenshot ever
reaches the vision model — verified live, clean separation (legible
cards ~160-187 contrast, locked ones ~52-56).

That in turn caused a NEW bug, also caught and fixed live: the model
couldn't reliably track grid position once cards were blacked out — it
silently shifted the remaining visible cards left to fill the gap
instead of preserving their true column, confirmed twice (once on the
first approach, again after a prompt-only fix attempt failed). Root
fix: position is now computed entirely in code
(`detect_ban_grid_locked()` against calibrated `BAN_GRID_COL_X/ROW_Y`
pixel boxes), and the model's only job is to return the legible cards it
sees in reading order, zipped onto the code-derived positions.

That surfaced two more real issues, also fixed: (a) the model has no
way to distinguish "locked" from "legible tactics card" by contrast
alone, so scrolling past the owned collection into the tactics-card
section produced a mismatch on every single read — without a stop
condition this burned several minutes grinding toward `max_presses`
before halting; fixed with a consecutive-mismatch counter that stops
after 2 in a row. (b) a transient mismatch on a genuine player-card row
(not the tactics boundary) caused that whole row to be silently
dropped rather than retried — fixed by retrying the same captured frame
once (a fresh model call, no rescroll needed) before giving up on a
batch.

**Gemini review, same day** — two more issues raised, one fixed, two
noted without code changes (no live evidence yet that they're real
problems, just plausible ones):
- **Fixed**: `BAN_GRID_COL_X/ROW_Y` are hardcoded pixel boxes tied to a
  specific screenshot resolution — a Chiaki-ng window resize or macOS
  display-scaling change would silently misalign every box against the
  actual cards, producing confidently wrong lock detection instead of
  an obvious failure. `detect_ban_grid_locked()` now raises a clear
  `ValueError` if the screenshot size doesn't match
  `BAN_GRID_CALIBRATED_SIZE`, so a scaling change fails loud (caught by
  the existing retry/exception handling) instead of quietly producing
  wrong bans.
- **Noted, not changed**: `wait_for_screen_to_settle()`'s two
  consecutive sub-`DIFF_THRESHOLD` polls (~0.6s) could theoretically
  register a false "settled" if network latency freezes the stream for
  just over that window, mid-animation. No live evidence this has
  actually happened; watch for a turn that resolves into a
  screen-read mismatch shortly after a network hiccup.
- **Noted, not changed**: `MASK_KERNEL=41` is calibrated to the current
  card-art scale. If the game's UI ever dynamically rescales (e.g. based
  on collection size), the kernel could start blurring out legitimate
  stat numbers instead of just locked cards. No evidence this happens
  in practice; recalibrate `MASK_KERNEL`/`MASK_CONTRAST_THRESHOLD`
  together with `BAN_GRID_COL_X/ROW_Y` if the UI is ever observed to
  change scale.

The retry-once fix reduces row-drops but doesn't eliminate them
entirely — a mismatch that persists across both attempts still gets
skipped safely rather than risk a wrong position. Worth watching
`choose_bans()`'s picks over a few more real ban screens to see how
often that still happens in practice.

## Lower confidence, would benefit from more reps (no known bug, just thin sample size)

**5. Runner detection** — confirmed working on the handful of live
cases seen so far (catching a real runner, rejecting a card-back false
positive), but never stress-tested with 2-3 simultaneous runners or
partially-obscured animation frames.

**6. `discards_left` dot-counter reading** — the dimmed-vs-filled
distinction in the vision prompt has only been spot-checked a few
times, not exhaustively verified.

**7. `should_redraw()`'s two-step discard-then-play fix** — confirmed
correct once, live, after being found and fixed. More reps would build
confidence it holds up consistently.

## Deprioritized by explicit choice, still technically open

**8. Whether quitting mid-match early (once a half is mathematically
unwinnable) is safe or faster** — explicitly not investigated, given
the risk of an unverified quit action on real match money. Still an
open question if worth revisiting later.

## Already resolved, not on this list

Always-boost tactics timing, ban strategy (weakest-first), redraw
threshold tuning, and the `batters_used`/`target_score`-aware redraw
experiment all reached clear enough answers through simulation or live
testing — see `HEURISTICS.md` for the full writeup. They don't need more
real games to resolve.
