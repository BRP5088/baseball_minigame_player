# Lessons — recurring failure patterns

Written 2026-08-25 after a session where the test suite was green the whole
time and three separate real defects were live in the tree.

This is not a changelog. It records the *patterns*, because each one recurred
within a single session after being "fixed" once.

---

## 1. Tests that pass for the wrong reason

Five instances in one day. Every one was green, and every one asserted nothing.

| # | The test | Why it passed anyway |
|---|---|---|
| 1 | Ban-card strictness (`test_ocr_ban_card.py`) | Deleting `cutoff=0.85, allow_surname_fallback=False` made it score **better** — 18/18 with 0 abstentions vs 16/18 with 2. `MAX_ABSTENTIONS` only had a ceiling, so fewer abstentions was silently rewarded. The metric moved the wrong way for the one regression that sends wrong physical input into a paid match. |
| 2 | Motion-gate timeout | Scripted `motion=[True]*100000` and asserted the run still completed. It completed because the **list ran out** after 0.03s, never reaching the 20s bound. A busy `continue` loop runs ~3M iterations/sec, so a real clock makes that bound unreachable in any sane test. |
| 3 | Default-argument trap | Asserted `elapsed >= ACTION_DELAY` after a backoff. Fixed overheads (0.15 settle + 0.05 hold + 0.40 frozen = 0.60s) cleared the 0.45s bar **while the delay was still frozen**. |
| 4 | Misfire detection (harness) | Subclass patched `read_matchup_reveal`; the base `Harness.run()` applied its own patches *afterwards* and silently won. |
| 5 | Logger-stop test (harness) | Same base-class-overrides-subclass bug, three hours earlier. |

**The pattern.** A test that only checks "did the good thing still happen"
passes when the mechanism under test is absent, as long as *something else*
produces the same observable. What catches it:

- **Mutate the thing being tested and confirm the test fails.** This is the
  only reliable check. Every fix above was verified by breaking the code on
  purpose and watching the test go red.
- **Measure a delta, not an absolute**, when fixed overheads sit alongside the
  quantity of interest (#3: compare two pacings so the overheads cancel).
- **Make the assertion two-sided.** A one-sided bound rewards the failure
  direction (#1). The ban test now requires uncatalogued names to abstain
  *and* garbled-but-known names to still resolve.
- **Put shared control in the base, never in a subclass** (#4, #5). If the
  base applies patches last, a subclass cannot override them and will fail
  silently.

**Two more categories, found 2026-08-26 by a dedicated mutation sweep:**

- **Assertion satisfied by the mechanism's ABSENCE.** The atomic-write test
  asserted "no `.tmp` file is left behind" — which a *non*-atomic write
  satisfies more easily than an atomic one, since it never creates a temp file
  at all. The check was structurally incapable of failing in the direction it
  cared about.
- **Tautology on a test-local value.** `test_ban_grid_locked.py` computed
  `_m = MASK_KERNEL//2 + 2` inside the test and then asserted
  `_m > MASK_KERNEL//2`. That is arithmetic, not a property of the code: the
  real margin could be set to `MASK_KERNEL//2 - 1` and the test stayed green.
  Recompute nothing the code already computes — read the value the code uses.

**And the count for category (d) — an assertion reading its threshold from the
constant being mutated — reached FIVE instances**, four of them written the
same night, twice in a file that already warned about the trap in a comment a
few lines above. Knowing about a failure mode is not the same as not committing
it; only the mutation catches it.

---

## 2. Tests writing to real project data

Twice, same day, found by noticing the *data* looked wrong — never by a failure.

1. **`diagnostics/`** — the suite exercises all seven stall paths, dumping ~20
   synthetic bundles into the directory a live session watches for alerts. A
   real stall would have been buried.
2. **`match_log.jsonl`** — the misfire tests drive real plays through the
   reveal path. **30 of 69 rows were synthetic**, indistinguishable from
   genuine rows except by `our_tactics_kind`, a field that happened to be new
   that day. This is the dataset the entire project exists to build.

Fixing #1 did nothing to prevent #2, because the defect was never "match_log
wasn't redirected" — it was that **nothing asserted the suite is side-effect
free**.

**Now guarded three ways, deliberately independent:**
- `test_no_side_effects.py` runs every other test in a subprocess and diffs
  tracked files and directories. Catches the class, not the instance.
- `BASEBALL_MATCH_LOG` / `BASEBALL_DIAGNOSTICS_DIR` redirect writes.
- Rows written under a redirect are stamped `"_synthetic": true`, so
  contamination that slips through is *recoverable*:
  `grep -v '"_synthetic": true' match_log.jsonl > clean.jsonl`

Prevention and recovery fail independently. That is the point.

**And the first version of the stamp was itself backwards.** It fired only when
`BASEBALL_MATCH_LOG` was set — i.e. only when the rows were already going
somewhere harmless. In the case that actually matters, a test that *forgets* to
redirect, no stamp was applied. Proven within minutes: a mutation removing the
redirect wrote two unstamped fixture rows straight into the real dataset.

The stamp now keys on **test context** (`BASEBALL_TEST_RUN`, exported by
`run_tests.sh`, or a `test_*.py` entry point), not on the redirect. Re-verified
by mutation: with the redirect removed, 4 rows leaked and all 4 were stamped
and removable by the documented one-liner.

Generalises past this bug: **a safety net conditioned on the same thing it is
protecting against is not a safety net.** Check what the mechanism keys on, and
make sure that key is still present in the failure case.

---

## 3. Optimising the thing that was measured, not the thing that was slow

Every latency change for weeks targeted vision-API and settle timing. An
outside question — "how are you handling input delays?" — prompted the first
actual measurement of the input path:

```
osascript round-trip   154 ms      <- on EVERY keystroke
press() total          754 ms      (154 osascript + 150 settle + 50 hold + 400 post)
per turn               2.3 - 8.3 s <- larger than vision (~2-4s) + settle (~2s p50)
```

**Input was the single largest component and had never been measured.** 304ms
of every press re-focused an already-focused window.

The lesson is not "cache the focus". It is that *the component nobody
instrumented was the biggest one*, and it stayed invisible precisely because it
never failed — it was just slow, uniformly, forever.

---

## 4. A conclusion asserted from the wrong evidence

Mid-session I told the user **"the bans never landed — the navigation is broken
from a false origin"**, citing frames showing `BANNED CARDS 0/3` and the cursor
deep in the tactics section.

Wrong. Those frames were from 17:00:41–17:00:59, during the scan's unwind —
*minutes before the ban keypresses*. OCRing the counter across every frame:

```
17:01:28  0/3
17:01:31  1/3
17:01:40  3/3     <- all three applied correctly
```

The docstring's "assumes the caller starts at (0,0)" *looked* like a smoking
gun next to a scrolled screen, and the story was coherent. It was still wrong.
**A plausible mechanism plus correlated evidence is not a diagnosis** — the
frames had to be ordered against the action before they meant anything.

---

## 5. What the live run actually established

One match, throwaway save, stopped early by a `max_spend=50` misconfiguration
before any turn was played. Still worth it:

**Found a real money bug (C5).** Paid $50 → scanned and applied 3/3 bans →
match began → the **"ROUND 1" transition overlay was classified as
`match_start_prompt`**. By then `acted_screen` was `"ban_screen"`, so the C2
guard had already cleared, and the loop was one step from debiting a **second
$50 for a match already paid for and already running**. Only the cap stopped
it — by luck, not design.

`acted_screen` blocks *consecutive* identical screens. It cannot see a repeat
with another screen in between, and on this path there always is one: the ban
screen. Fixed with `match_in_progress`, set on debit and cleared when a result
is scored — tracking the fact directly instead of inferring it from screen
order. Mutation-tested both ways: removing the guard double-debits; never
clearing the flag deadlocks after match one.

**No conclusion was possible on:** the focus cache under live conditions (the
run stopped before a turn), misfire rate (no cards played), or settle latency
(6 samples, all `default` region, p50 0.47s).

---

## 6. Resolution limits that invalidate an analysis

`SETTLE_TIMING_ANALYSIS.md` derived latency percentiles and truncation rates
from a frame log captured at ~1–1.9 Hz. Production polls at **0.15s**. The log
cannot resolve what it was used to estimate:

- a diff across a ~1s gap captures more motion than one across 0.15s
- "2 consecutive stable polls" means ~2s of quiet at 1Hz, ~0.3s at 0.15s

Both inflate apparent settle time, so every percentile is an **upper bound of
unknown tightness**. The same limit sank the attempt to validate the input-
prompt detector: 93% of prompt-visible and 61% of prompt-absent frames both
read as "moving" against a threshold calibrated for a different sample rate.

The fix was not a better analysis — it was instrumenting the real loop
(`settle_stats_summary()`) so the next session measures instead of estimates.

**Before deriving a threshold from logged data, check the sample rate against
the rate the code runs at.**

---

## 7b. Whole layers with no behavioural coverage at all

A dedicated sweep (2026-08-26) mutated ~70 assertions across all 16 test files
and confirmed **22 vacuous ones**. The worst was not a bad assertion but a
missing one: `input_controller.py`'s entire input-execution layer had **zero**
behavioural coverage, because every test that reached it replaced it with a
recorder. All of these survived the complete suite:

```
banning column `4-c` instead of `c`     <- BANS THE WRONG PHYSICAL CARD
removing row navigation entirely
removing the cursor-homing pass
inverting the play-card navigation
```

The only ban assertion anywhere was `len(bans_submitted[0]) == 3` — a COUNT.
The file's own header already warned that counts are not enough; nobody
connected the warning to the assertion sitting under it.

**The pattern: a recorder is not a test.** Replacing a dependency to observe
*that* it was called proves nothing about *what* it was told to do. Somewhere,
one test has to assert the actual key sequence — and the layer nearest the
hardware is the one where "wrong" is least recoverable and most expensive.

---

## 7. "It looks off" was a real measurement waiting to happen

The user watched the ban screen and said it *"lingers and seems random for a
little bit."* Frame-differencing the run turned that into a number:

```
  9s -> 31s    22s idle
 32s -> 49s    17s idle
 50s -> 68s    18s idle
 69s -> 109s   40s idle
110s -> 149s   39s idle
then 149-174s  the actual bans
```

**149 of 175 seconds was the ban scan, almost all of it stationary.** The cause:
the scan scrolls past the roster's known extent into the TACTICS section, where
no position resolves locally, so every batch falls through to a vision call,
mismatches (`read_ban_row_cards` correctly filters tactics out), and is
**retried** — two vision calls plus ten fruitless tesseract reads per wasted
step, and it takes two consecutive mismatches to stop.

The fix costs nothing: tactics cards have no player-name banner, so
`ocr_ban_card_name` already returns `None` for every position there — verified
against real frames, all ten empty. That plus "past the roster extent" is
conclusive, so the scan stops before spending any vision call. One batch of
slack is allowed past the known extent so the self-extending roster can still
discover a genuinely new row.

Two things worth keeping from this:

- **A user's qualitative "that seems off" is a hypothesis with a measurement
  attached.** Nothing failed, no error appeared, and the suite was green. It
  took someone *watching the screen* to notice, and 20 lines of frame-diffing
  to localise.
- **The stop boundary must be recomputed, never cached.** The roster extends
  itself; a boundary frozen at import would stop moving as rows are learned and
  silently truncate every future scan at the old extent. That mutation is
  covered by a test — and the test only caught it after
  `test_known_ban_roster.py` was given its own API-key guard, because until
  then a standalone run died on a `KeyError` that looked nothing like a test
  failure. **A mutation check is only as good as the test's ability to run at
  all.**
