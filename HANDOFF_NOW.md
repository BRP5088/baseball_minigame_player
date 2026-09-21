# HANDOFF — 2026-09-21, end of session

## 1. STATE RIGHT NOW

- `main` HEAD **`135552b`**.
- Record (`progress_testing.json`, verified by `cat` this session): **67W 14L 8D**,
  balance **46**, `match_in_progress: false`, `bans_done_this_match: true`.
  The `true` flag is **harmless** — nothing is actually mid-match, it's just left
  set from the last match; the **next reset clears it** (preflight only keys on
  `match_in_progress`, not on this flag).
- Console: left at the **dealer table**, **$46 in-game** (matches the tracked
  balance). **Not put to sleep** — it auto-sleeps on its own when nothing
  reaches it (CLAUDE.md §1). Assume it may be asleep by the time this is read;
  confirm with the three tells before any press.
- **Snoopy is OFF** (user turned it off ~14:00; nothing queued there). When it
  returns: `llama-server` port changes per model load (was 61758 today,
  re-discover via `/props`); model is `Qwen3-VL-8B-Instruct-GGUF`.
- **Paid vision model is OFF** (`orchestrator.PAID_MODEL_ENABLED = False`, as always).
- **No agent is running.** Nothing in flight.

## 2. TODAY'S RESULT vs THIS MORNING

**Yesterday, every run ended by Ctrl-C or on a stuck screen.** Today's
12-match stall census — cycles 4, 5, 6 (runs 21p, 21q, 21r), on `main` with
every fix from today merged — did not:

    10 W, 1 L, 1 unverified D
    refusals: 7 (6 of them in one hand — the I-48-candidate stall, cleared BY
               THE LOOP ITSELF, no hand assist)
    hand-assisted stalls: 0
    phantom results: 0 confirmed (draw #8 is unverifiable, not confirmed phantom)
    runs ended by Ctrl-C or a stuck screen: 0

**The day's full tally**, from the record checkpoints stated in the facts file
as the session progressed (each one a verbatim snapshot, not a computed diff):

    07:15 morning start           46W 12L 5D   balance 146  (carried from last night)
    after cycle 1 (21j+21k)       51W 12L 6D   balance 246  (incl. 1 phantom draw, I-34, pre-fix)
    after cycle 2 (21l-21n)       54W 12L 7D   balance 246  (incl. 1 more phantom draw, I-34, pre-fix)
    after cycle 3 (21o, I-34 merged)  57W 13L 7D   balance 246  (0 phantom draws — first cycle on fixed I-34)
    after census cycles 4+5       65W 13L 7D   balance 246  (8 matches: 8W 0L, 1 refusal recovered)
    after census cycle 6          67W 14L 8D   balance  46  (WIN #66, DRAW #8 unverified, LOSS #14, WIN #67)

Mid-morning checkpoint (~09:0x, before the I-37 fix landed): "13 matches
scored (11 W, 1 L, 2 phantom D whose true outcomes are unknown), 3
hand-assisted stalls (all I-37 shape, before its fix)." Every hand-assisted
stall happened before I-37 merged; **zero since**.

## 3. WHAT MERGED TODAY

One line each, I-30 through I-47. "Skeptic" verdicts are from ISSUES.md status
lines / the facts file.

- **I-30** result reads whole-word; `close_result` only after a fresh read;
  give-up dialog answered NO. Merged; live confirmation open.
- **I-31** phase inferred from tactics kinds + match-state fallback. Merged;
  live-confirmed today (used on the I-32 resume).
- **I-32** `_walk_cursor_to` dead-reckons one step across a known-occluded
  slot instead of refusing the whole hand. Merged `a5e212a`. Skeptic
  CONFIRMED WITH NOTES. **Live-exercised today** — WIN #45, the previously
  parked match.
- **I-33** a press off a slot named without a genuine glow read is retried,
  not refused (v2 adds `CUR_TRUSTED_GLOW_MIN=20.7` + a "single selected card
  names the cursor" fallback). Merged `c335d42`. Skeptic CONFIRMED WITH NOTES.
- **I-34** a second substring matcher scored a phantom draw from an opponent
  card name ("JOHNNY DRAWERS"). Fixed (whole-token match + call-site veto,
  round 2). Merged `d2cd052`. Skeptic CONFIRMED round 2 (0/33 roster names
  hold a standalone result word; 7 mutants, one proven equivalent).
- **I-35** two post-reveal screens (`new_inning`, `reveal_recap`) were
  unrecognised, dropping the at-bat log row. Merged `26255bc`; follow-up
  `29469b1` fixed 2 of 3 surviving mutants. Skeptic CONFIRMED WITH NOTES on a
  9,966-frame census (2,525 firings, all on "other" screens, no money-path
  change). **Never fired live yet** — see §6/§8.
- **I-36** the half's second discard is refused three times before the stall
  breaker plays (v2 gates the I-21 rescue on baseline kind). Merged
  `87c683c`. Skeptic: v1 **REFUTED narrowly** (made a genuine tactics target
  committable without selection), v2 fixed and merged.
- **I-37** a selected card's own disc can be absent from `strong`, blinding
  the fan-presence gate. Merged `3bd69d5`; follow-up (`local_state._fan_discs`
  delegates to the same gate) merged `c5fd60b`. Skeptic CONFIRMED WITH NOTES
  both rounds (round 2: 0 new wrong phases over 465 labelled hands).
- **I-38** an occluded target card cannot be selected, engine plays
  second-best. **Still open** — not fixed. Three genuine occlusion fixtures
  now exist from a Snoopy archive search.
- **I-39** the play-refusal exclusion was keyed on the exact hand and
  over-persisted (now keyed on slot + reason). Merged `bedd4ca`. Skeptic
  CONFIRMED WITH NOTES (counter-reset-on-re-offer fix folded in).
- **I-40** a reload's local money read ($286) disagreed with the known wallet
  and was trusted. Merged `aedc9ba` (money-read frame keeper +
  `RELOAD_WALLET=246` guard). Skeptic CONFIRMED WITH NOTES.
- **I-41** four offline tools popped `BASEBALL_TEST_RUN` at import, silently
  disabling the input lockout. Merged.
- **I-42** `cursor_labels_from_lifts.py`'s labels were 28/81 wrong (cursor
  caught mid-travel). Merged `cf127a4` (capture-gap + flicker filters).
  Skeptic CONFIRMED WITH NOTES. **Caveat: `FLICKER_WINDOW=10` is from the
  ticket text, not measured** — 9/53 good labels wrongly rejected — LATER item.
- **I-43** a stray left lifted by a refused attempt survives into the next
  operation's baseline-blind exemption. Merged `2f18a73`. Skeptic round 1
  **REFUTED** (would have refused 29% of healthy turns), round 2 CONFIRMED
  WITH NOTES, 7/7 mutants.
- **I-44** `_clear_strays`'s commit-time inference asks for no real
  corroboration. **Status: PARTIAL**, merged `2f18a73`: the corroboration
  gate is inert in production (every success path marks, so
  `inferred_targets == want` always — N-1); the original hole (a dropped
  press + a false inference corroborating itself) is **still open** — needs
  corroboration the inference cannot manufacture. LATER item, live-watched.
- **I-45** QA6 test hygiene (gitignored-JSON reads, `agent_progress/`
  globs that crash a fresh clone). Merged `fd2c6cc`.
- **I-46** a raised card's disc lands on the decorative icon and reads digit
  None 8% of the time (position search recovers it). Merged `15cfac4`,
  **narrow window kept** (17/23 recovered vs a wide window's 22/23, but the
  wide window costs 2x runtime and reach — decision: keep narrow). Skeptic
  CONFIRMED WITH NOTES.
- **I-47** two silent permissive defaults in offline QA tools. Merged `3d0526c`.

## 4. HOW TO RUN THE NEXT CYCLE

Before launching: `ensure_stream.ensure_live()`, then **read the frame by
eye** and confirm the GAME is actually on screen (today the console woke onto
the real pause menu — an ensure_live success does not by itself mean the game
is up, see CLAUDE.md §3). Then:

```
BASEBALL_API_BUDGET=300 nohup .venv/bin/python -B -u -c "import run_cycles; print(run_cycles.cycle(7))" > overnight/run_live_20260921s.log 2>&1 &
```

(next log letter — today used d, e, f, h, i, j, k, l, n, o, p, q, r; `s` is
next.) A cycle plays up to 4 matches on the $246 reload.

Monitor for milestones with:

```
grep -E "logged|WIN #|LOSS #|Draw logged|REFUSED|may still be physically lifted|Traceback|stop_reason" overnight/run_live_20260921s.log
```

## 5. LATER (do not start without the user)

Verbatim from the facts file's LATER list, plus what accumulated after it:

- I-46 wide window: decide narrow (17/23) vs wide (22/23) from the skeptic's
  false-read table; widen only at zero false reads.
- I-35 live verification: `new_inning` / `reveal_recap` branches have never
  fired live; confirm on the next matches' logs.
- I-42 labels: `FLICKER_WINDOW=10` is from the ticket text, not measured;
  9/53 good labels wrongly rejected. Measure if the label corpus is ever
  needed at scale.
- Full hand corpus re-check after I-46 merges (the 540-hand corpus, not just
  the 2,409 turn frames).
- Raised-card disc: 6/23 census frames still unread (5 jitter, 1 obscured) —
  covered by the wide-window decision above.
- The narrow I-46 window makes every slot it reads SELECTED by construction
  (dy above `SELECTED_MIN_RISE` 25); fine today (32/34 were `y_from`
  fallback), worth a line if `selected_cards` ever misfires.
- I-44's N-2: the original hole (a dropped press + a false inference
  corroborating itself) is STILL OPEN — needs corroboration the inference
  cannot manufacture (selection-lift geometry or a post-commit read).
- Log the evidence (template scores + OCR words + scoreboard) on every
  result commit and keep the result frame — the reveal/money keepers exist,
  the result screen has none. This is what would settle draw #8.
- **I-48 candidate (new today, match-3 stall on cycle 6):** when the TACTICS
  select is what's failing (not the batter select), the play-refusal
  exclusion keys on the batter, so every batter gets burned in turn at 3
  refusals each before the loop stumbles onto one whose adjacent-slot walk
  happens to avoid the occluded slot. Fix direction: drop the tactics
  attachment first and play the batter alone rather than burning batters —
  the boost is worth ~+0.6 runs/half, a stalled half costs far more. Also
  keep a frame per refused select (none were kept for this stall). Likely
  mechanism: the cursor walk from slot 3/4 to slot 1 crosses the occluded
  slot 2 (a home-plate runner card) and the walk/lift read goes wrong there;
  from slot 0 it's one step and works. Recovered by the loop alone today, no
  hand assist needed — but cost a worse batter played and ~5 minutes.
- Exclude LOCKED cards from the simulator pool and from choose_bans
  (RULES.md, user 2026-09-21). Ownership is readable per cell from the ban
  scan the run already does (`ban_grid.is_locked`, 3.5x contrast gap);
  persist it beside the roster and thread it into simulate's player_pool and
  decision_engine.choose_bans. Then re-run the I-13 ban A/B on the 31-card
  pool.

### Snoopy jobs (one at a time; VLM text reading and grunt work only)
- Label the kept reveal frames (test_fixtures/reveal_kind_truth/auto/): opponent card name + power per frame -> ground truth for the reveal-miss rate and for reveal_cards.TACTICS_KIND_MIN (OPEN-24).
- Type Brian Coker and Zachary Lee from their ban-grid type banners (the roster's two untyped cards; simulate.UNTYPED).
- ~~Second-opinion the 34 I-46 raised-card digits~~ DROPPED after job 1: the VLM misreads small digits the local reader gets right.
- Mutation sweeps for I-48 once built, if the console is live (Snoopy_testing.md).
Not Snoopy: reveal-miss baseline count, FLICKER_WINDOW sweep, raised-disc jitter -- local scripts, seconds.

### Snoopy job 1 DONE (reveal frames, agent_progress/census/reveal_vlm/)
- 153 kept reveal frames; only 82 have a match_log row. The other 71 are the "turn not logged" misses -- the frame IS kept now, so the miss population is on disk for the first time.
- VLM vs match_log (n=82): our_power 83%, opp_power 91%, tactics kind 77%. The one frame decoded at full res: local reader + log exactly right, VLM misread an 8 as 3. The VLM is WORSE than the local reader on digits -> job 3 (second-opinion raised digits) is DROPPED, no value.
- WHAT THE MISSES ARE (13 tiles by eye, 2 at full res -- a hypothesis, not a census): 3/13 the kept "peak" frame is the NEXT turn's hand fan (reveal already cleared); 10/13 a 4-card cluster still bunched at the mound before the cards separate to home/mound, home plate empty; one had a RUNNER in the cluster. So the local reader's abstention is mostly CORRECT and the gap is CAPTURE TIMING (the watcher's peak is too early or too late), not recognition. The VLM "recoveries" are readings of the wrong card.
- LATER (fix direction, not started): make the reveal watcher wait for the 2+2 cards to SEPARATE (home-plate zone occupied AND mound zone occupied) before keeping the frame, bounded by the reveal window (~2-3 s, memory: reveal-is-a-brief-centre-window); score it on the 71 orphan frames' turns in the next matches.

### Snoopy job 2 DONE (roster typing, agent_progress/census/roster_type_vlm/)
- Brian Coker (8/1) and Zachary Lee (6/2) are BOTH BATTERS: 3 distinct ban-grid frames each, the type banner read "BATTER" by the agent's eye AND by the VLM on 6/6 crops. The NAME banner fades on a locked card; the TYPE banner survives.
- Both cards are LOCKED (not owned) in this save: ban_grid.is_locked True at exactly those cells on all 29 frames that reach their rows, neighbours False.
- PROPOSED EDIT, NOT APPLIED (user to approve): simulate.py PlayerCard("Zachary Lee", 6, 2, "") -> role "batter", same for Brian Coker; orchestrator.KNOWN_BAN_ROSTER entries (~:5679, :5691) role="batter"; test_known_ban_roster.py enforces the two tables agree. simulate.UNTYPED updates itself.
- APPLIED 5afe7e0 after user confirmation; test_card_roles re-derived dc6ac98.

## 6. OPEN QUESTIONS

Verbatim from the facts file, plus two new ones from today's close:

- Does a speed boost PERSIST on base? Two live runners read +1 over their
  card (CLAUDE.md §4); worth one at-bat with a boosted batter then a later
  hit. Low stakes (+0.046 runs/half).
- Does the raised-card position search ever read a NEIGHBOUR's disc live?
  Skeptic measures offline; the live check is one hand with the target in
  slot 4 and a 9 in slot 3.
- Is the 8% raised-disc miss the dominant cause of I-21 inference commits?
  Count, over the next 10 matches, plays where the target read blind at
  commit before vs after I-46.
- Why do 5 of 23 raised digits land outside the narrow window (jitter): is
  the disc position on a raised card a function of the lift height
  (selection lift ~44 px) or of the fan phase? Measure dy vs SELECTED lift
  per frame from the census json.
- Do new_inning / reveal_recap ever appear on the live path, and how long do
  they hold? No live sighting yet; the next matches' logs answer it.
- Are the 9/53 good lift-labels rejected by I-42 a flicker-window size
  effect? Sweep `FLICKER_WINDOW` 4..20 on `joined.jsonl` and report
  kept/rejected by class.
- **Was draw #8 (cycle 6, match 2) real?** The commit logged no evidence (no
  score, no template score, no frame) and the next match's opening frames
  aren't on disk (`run_cycles` logs no screenshots) — nothing to check
  offline right now. Answered by building the result-commit evidence logging
  in §5, then watching the next draw.
- **Why 11–15 reveal misses per cycle ("no OPPONENT card identified"), and is
  that the same rate as before today?** Cycle 4: 11 misses, cycle 5: 15
  misses — stated in the facts as "not a regression" but never compared
  against a pre-today baseline; worth a real before/after count.
- ~~Locked cards in the pool?~~ ANSWERED (RULES.md, user 2026-09-21): locked
  cards are never dealt and can't be selected as a ban, so the draw pool is
  31, not 33; wiring that into simulate/choose_bans is the §5 LATER item.

## 7. RULES IN FORCE

- **User rule, 2026-09-21 ~13:30: any NEW task or question found from here
  goes on the LATER list — do not dispatch it to an agent.**
- Manager delegates routine work (merges, tests, doc edits, log reading) to
  Sonnet agents; the main model decides and dispatches.
- Snoopy: one job at a time, grunt-work/labelling only, never wired into the
  live ladder.
- **Never save the game** — resets and `Load Last Save` only.
- **Play the engine's pick, fix the engine** — never hand-override a card
  choice; when a read looks wrong, check the reader first.
- **Ask before pushing, opening a PR, or posting anywhere shared** — draft,
  show, wait for a yes.

## 8. LIVE WATCH ITEMS for the next cycle

- **"may still be physically lifted" count** — 0 today, all clean (I-43's
  live watch). Archive bound is 14 exemption events vs 51 refusals; more than
  a handful on the next cycle means the single-frame `ys0` gate is admitting
  transient blinds.
- **Does `new_inning` / `reveal_recap` ever fire?** — Never seen live yet
  (I-35). Grep the next log for those two screen names.
- **I-46's first live effect** — raised-card position-search reads recovering
  a digit that would otherwise have been None. Not yet observed live (today's
  census was measured offline against the 2,409-frame corpus); watch for it
  in the next cycle's hand reads.
