# Match analysis — 2026-08-31

Two matches played to completion, both won. A third was paid for and is still
running at the time of writing.

    wins 2  losses 0  draws 0     balance $196 -> $96
    match_log.jsonl 72 -> 83 rows
    API 89 calls (~$1.07) of a 200 cap

## 1. Turn logging works now

The headline failure of 2026-08-28 was that a whole match produced ZERO logged
turns: `wait_for_reveal_cards` waited 6s while the game takes ~17s to finish
dealing (p90 measured 17.97s). Raised to 20s.

Confirmed live. Row 73 is the first turn logged since the fix, complete with the
opponent's revealed card:

    {"phase": "batting", "our_power": 9, "opp_card_name": "Rube Sharp",
     "opp_power": 8, "opp_tactics_kind": "speed_boost", "outcome": "out"}

11 rows added across the two matches. Everything downstream depends on this.

## 2. Three defects fixed, each measured before and after

Retry causes per run. Every retry is a fresh API call, so this table is money.

| retry cause       | run 1 (no fixes) | run 2 (repair) | run 3 (repair+clamp) |
|-------------------|-----------------:|---------------:|---------------------:|
| tactics-as-player |                6 |              4 |                    0 |
| discards_left     |                1 |             24 |                    0 |
| no player card    |                2 |              6 |                    2 |
| unusable phase    |                1 |              5 |                    1 |

### Tactics cards classified as player cards

`Fielding Play` and `Power Swing` came back as `{"kind": "player", "power": 1}`.
validate_game_state rejected them — power 1 is outside the 4-9 player range —
and the caller retried the entire read. 10 of the session's first 17 retries.

The card's NAME already settles what it is, and `TACTICS_NAME_TO_KIND` was
already in the file for the reveal path. `repair_misread_cards()` applies it at
the one live read site, before validation. Fired 11 times; the `Fielding Play`
retry class went 6 -> 0.

The 4 remaining in run 2 were a different card, literally named `Batter` with an
out-of-range power — correctly left alone, since it is not a tactics name. That
is a separate open issue (see §5).

### discards_left retry storm

Vision read `4` off the same frame 11 polls running, then `3` for 15 straight
polls, which aborted a paid match. Retrying cannot fix a stable misread: same
frame, same prompt, same wrong answer.

Now clamped instead of rejected. Clamped to ZERO, not to the cap — an untrusted
count must never authorise a discard. That is not a hypothetical: a hallucinated
count once drove 33 discard attempts across 4 matches where at most 8 were
possible, with the counter observed increasing between turns
(test_validate_game_state.py). Clamping to 0 keeps that protection and drops the
retry cost. 24 -> 0.

The on-screen indicator was checked against a real frame rather than reasoned
about: DISCARDS is exactly 2 dots, so MAX_DISCARDS_PER_MATCH = 2 is right and 3
or 4 is a hallucination.

### chiaki was running the STOCK build

`/Applications/chiaki-ng.app` has no `CHIAKI_INJECT_INPUT` string and never
opened the FIFO — every injected input would have gone nowhere. Two contributing
bugs, both fixed:

- `restart_chiaki.sh` killed only processes matching `chiaki-ng-build`, so a
  stock app launched by hand survived and fought for the stream. Now matches on
  executable name (`pgrep -x chiaki`).
- the `chiaki-analog` alias pointed at `launch.sh`, which starts the patched
  build but never kills a running instance and never re-signs. Repointed at
  `restart_chiaki.sh`.

## 3. The `secondary` question: NOT settled, despite p=0.005

The pooled figure crossed significance for the first time. It does not survive
inspection, and the analyzer now prints both checks on every run so this cannot
be missed again.

    secondary == 0 : n=30, mean margin -0.47
    secondary >  0 : n=31, mean margin +1.32
    permutation p = 0.005          <- significant at 0.05

    [batting]  sec==0 n=9  +0.22 | sec>0 n=22 +2.18 | p=0.008
    [pitching] sec==0 n=21 -0.76 | sec>0 n=9  -0.78 | p=1.000  <- nothing here

    CONFOUND CHECK — our own power by group: 7.37 vs 8.10 (p=0.045)

**One half only.** The whole effect is in the batting half. The pitching half —
which is the half `FIELDING_POWER_BUDGET` is actually about, since there our
secondary IS our pitcher's fielding — shows p=1.000, means -0.76 vs -0.78. The
pooled number was answering a different question than the one asked of it.

**Power confound.** Batting rows with secondary>0 averaged 8.23 power against
7.22. The margin gap is partly just stronger cards. The opponent's power drifted
in the helpful direction too (7.00 -> 6.05), and our batter's speed cannot cause
the opponent to draw weaker pitchers — so that half of the gap is noise, which
means the split is not clean.

**Verdict: leave `FIELDING_POWER_BUDGET = 1` alone.** The hedge is cheap and the
question is still open. Do not read the pooled p as permission to change it.

A note on `sec = ... if phase == "batting" else ...`: both branches were
identical, which reads like a flip that never happened. It is deliberate — the
stat under test is always ours — and it is now written as a plain assignment
with that reasoning attached.

## 4. Data yield is better than the analyzer reports

The analyzer says 73% usable and estimates ~4 more matches. That rate is dragged
down by legacy rows:

    legacy (no ts)   n=44   usable 24 (55%)
    modern (ts)      n=30   usable 30 (100%)

All 15 "tactics kind missing" exclusions predate the `ts` field. Modern logging
is 100% usable, so convergence is faster than the printed estimate.

## 5. Open issues, ranked

1. **Reveal failures** — 10 turns went unlogged across the two matches:
   `reveal cards never appeared`, `no OPPONENT card identified`, and
   `intended card absent from reveal`. This is now the largest single source of
   lost data, ahead of anything in §2.
2. **Misfires at 18.8%** (3 of 16 cards). The adaptive backoff worked correctly
   — 0.40s at misfire #2, 0.45s at #3, focus caching disabled. Not a bug
   (`MISFIRES_BEFORE_BACKOFF = 2` is deliberate), but the rate is high enough to
   corrupt turn data and deserves attention.
3. **Vision reads the table decorations as hand cards** — `Gamer Burn`,
   `Glowette`, `FireBoy`, `Buffalo Safety Matches` are the matchbox labels in
   the table art, returned as a five-card hand. Happens on frames where the hand
   is not dealt yet. The validator catches it; it costs retries.
4. **`Batter` / `Pitcher` as card names with out-of-range power** — the residual
   tactics-as-player class the repair cannot touch. Likely the same mid-deal
   frame problem as (3).
5. **Missing test fixtures** — `test_ban_scan` and `test_gameplay_regions` still
   cannot run, and `test_no_side_effects` fails as a consequence. Pre-existing;
   needs in-match frames recaptured.

Strategy tuning is deliberately not on this list yet. `simulate.py` can tune
thresholds offline for free, and the live log's job is to settle the questions
simulation cannot — which needs (1) fixed first.

---

# Addendum — match 3 (both fixes live)

    wins 3  losses 0  draws 0     balance $96     match_in_progress false
    match_log.jsonl 83 -> 86 rows
    API 20 calls (~$0.24)

Won. With both fixes active this match cost **20 API calls against 89** for the
previous run — not a like-for-like comparison (6 cards played vs 16), but the
retry classes that drove the difference went to zero: no `discards_left` storm,
no tactics-as-player. The single retry was the residual `Batter` class (§5.4),
this time with `power: None`.

The clamp fired twice, each time silently absorbing a read that would previously
have started a retry storm.

## The next real cost saving: trust local reads for POWER

`compare_local_reads=True` logged 41 hand-card comparisons of local OCR against
vision. The split is unusually clean:

    AGREE     31/41  (75.6%)
    DISAGREE  10/41  — every one of them on `secondary`, none on power

    power differs only:     0
    secondary differs only: 10

**Power agreed 41 times out of 41.** Power is the field that drives every
decision — `best_batting_play` sorts on it, `should_redraw` thresholds on it.
Secondary drives nothing at play time except the `FIELDING_POWER_BUDGET` hedge.

Three of the ten bad local reads flagged themselves `[INVALID]` (sec=5), so the
local reader already knows when it is guessing.

That points at reading the hand locally and calling vision only to confirm, which
would cut the dominant per-turn API cost. NOT acted on yet: 41 comparisons across
3 matches is a promising signal, not a mandate, and a wrong power read plays the
wrong card with real money on the table. Worth continuing to collect
`compare_local_reads` data until there are a few hundred comparisons, then
deciding against a stated agreement threshold.

One scoreboard read also disagreed — local OCR `opponent [0, 1, 1]` against
vision's `opp=0`. Scoreboard agreement should be tallied the same way before
anything local is trusted there.
