> **CORRECTION 2026-09-16:** anything below about `select_and_discard` ending in `confirm_play` (Triangle) is STALE. That press has been REMOVED -- a discard does not use the turn, and Triangle there played whatever was still lifted whenever the Square press was dropped. See RULES.md and input_controller.select_and_discard.

# QA Findings — Round 5 (closing round)

Scope: verify the five changes made after round 4, with particular attention to
**N25**, the only one that alters live control flow. Read-only review; nothing was
run that sends input to the PS5. All five `test_*.py` files were executed offline
(`PERSONAL_ANTHROPIC_API_KEY=dummy`) and all five pass.

---

## 1. Verification table

| Change | Status | Evidence read from code |
|---|---|---|
| **N25** — `stuck_count = 0` moved inside `if played:`, with an `else:` that increments and breaks at `MAX_STUCK_ATTEMPTS` | **APPLIED, and correct — no false-positive abort in normal play** | `orchestrator.py:2037` `if played:` … `:2087` `stuck_count = 0     # N25: only a confirmed PLAY is progress` (now indented inside the `if`, after the matchup-logging block). `:2088-2097` is the new `else:` — `stuck_count += 1`, then `if stuck_count >= MAX_STUCK_ATTEMPTS: print("Discarding repeatedly with no play landing — stopping…"); break`. Both paths fall through to `wait_for_screen_to_settle()` at `:2101`, so neither skips the settle. Full trace in §2. |
| **N24** — comment corrected to say an unscoreable result is DROPPED, not retried | **APPLIED and factually accurate** | `orchestrator.py:1826-1831`. Both claims check out against the code: `acted_screen = "result"` is the **first** statement inside the `try` (`:1833`), so the `:1811` guard suppresses a second attempt even when scoring raised; and `save_progress(...)` (`:1859`) is the **last** statement in the `try`, so no partially-scored result can be persisted twice. |
| **N12 remainder** — explanatory comment on the unconditional `press("close_result")` | **APPLIED, and keeping it outside the `try` is the right call** | `orchestrator.py:1867-1870`. The reasoning holds: because `acted_screen = "result"` is set before anything can raise, a failed scoring attempt has already forfeited its retry — so if the overlay were left up, the next poll would hit the `:1811` guard, increment `stuck_count`, and burn all 15 attempts on a screen it has already decided not to re-score. Dismissing unconditionally is the only exit. The exception path does not `continue` early, so it reaches `:1870` correctly. |
| **`_load_learned_roster()`** — shape validation instead of a module-scope raise | **APPLIED, but incomplete — see N26** | `orchestrator.py:1186-1210`: `isinstance(raw, dict)` gate at `:1200`, per-entry `try/except (ValueError, TypeError, KeyError, AttributeError)` at `:1204-1209`. Verified empirically against a non-list file, a bad key, a non-dict value, and a missing-field value — all four warn and skip as claimed. A **fifth** shape (non-string `name`) still bricks module import. |
| **N23** — `test_ocr_ban_card.py` asserts the ~0.283 card-row pitch | **APPLIED and effective** | `test_ocr_ban_card.py:31-38`. `_pitch = BAN_CARD_ROW_TOP_FRAC[1] - BAN_CARD_ROW_TOP_FRAC[0]` → 0.283; `assert abs(_pitch - 0.283) < 0.01` fires on any revert to `BAN_GRID_ROW_Y_FRAC`'s ~0.200 pitch. Suite output: `OK: 16/18 resolved correctly, 2 safely abstained, 0 wrong`. (Note: the second assert at `:36` passes only via its `_pitch > 0.25` clause, since `BAN_CARD_ROW_TOP_FRAC[0] == BAN_GRID_ROW_Y_FRAC[0][0] == 0.195` — it is redundant with the first, not broken.) |

**Test run:** `test_ban_grid_locked.py`, `test_known_ban_roster.py`,
`test_ocr_ban_card.py`, `test_validate_game_state.py`, `test_gameplay_regions.py`
— all pass.

---

## 2. N25 traced end to end

`stuck_count` is a single counter shared by every branch of `run()`. It is reset
to 0 on each of: a scored result (`:1834`), a match-start debit (`:1890`), a
completed ban screen (`:1980`), a handled discard prompt (`:1998`), and now
**only** a confirmed play (`:2087`).

| Sequence | Behaviour | Verdict |
|---|---|---|
| Normal play | `played=True` → `stuck_count = 0` every turn | Unchanged from before |
| Legitimate redraw, then a play | discard `→ 1`, next turn plays `→ 0` | Safe |
| Consecutive legitimate redraws | Bounded by `discards_left`. `should_redraw()` returns `False` at `redraws_left <= 0` (`decision_engine.py:158-159`), and `discards_left` decrements per discard, so the streak is capped at the match's discard allowance (2-3). Max reachable `stuck_count` from legitimate redraws: **~3 vs a limit of 15**. | Safe — 5x margin |
| Alternating play/discard | `0 → 1 → 0 → 1 → 0` | Never accumulates |
| A discard whose presses never land | The screen and `discards_left` stay identical, `played=False` every pass, counter climbs → aborts at 15 | **This is the bug N25 was written to close.** Working as intended |
| Unreadable `discards_left` | `orchestrator.py:1615-1617` defaults a `None` read to **0**, not 2, so a misread suppresses the redraw rather than triggering one | Fails in the safe direction |

**Can a healthy run now false-positive into "Discarding repeatedly"?** No. It would
take 15 consecutive non-progress polls with zero intervening plays, results, ban
screens, or match starts. The only new contributor is legitimate redraws, capped
at 2-3 per match by the game's own discard counter. The one marginal case is a run
that has already accumulated ~12 read failures and then hits a redraw streak — but
12 consecutive unreadable screens was already an abort condition on its own path,
so this does not turn a healthy run into an aborted one.

**N25 is a net improvement and introduced no regression in loop termination.**

---

## 3. New findings

### Minor

#### N26. A non-string `name` in the learned-roster file still bricks `import orchestrator`
`orchestrator.py:1203-1210` and `:1259`

The new per-entry validation checks that `power`/`secondary` coerce to `int`
(`:1206`) and catches a missing key, but it never checks that `name` is a
**string**. `PlayerCard` is a plain `@dataclass` with no type enforcement
(`decision_engine.py:29-34`), so `PlayerCard(None, 1, 0)` constructs happily,
lands in `KNOWN_BAN_ROSTER`, and then blows up nine lines later at module scope:

```
ROSTER_BY_NAME.update({c.name.lower(): c for c in KNOWN_BAN_ROSTER.values()})   # :1259
AttributeError: 'NoneType' object has no attribute 'lower'
```

Verified empirically (read-only, in a scratchpad CWD — the project directory was
not modified). Of seven malformed shapes tested, the four the round-4 note claims
were verified all warn-and-skip correctly; the three with a non-string `name`
(`null`, `123`, `["a"]`) all raise at import:

| file contents | result |
|---|---|
| `["not","a","dict"]` | warns, ignores |
| `{"badkey": {...}}` | warns, skips entry |
| `{"1,2": "notadict"}` | warns, skips entry |
| `{"1,2": {"power":1}}` | warns, skips entry |
| `{"1,2": {"name":null,...}}` | **AttributeError at `:1259` — import fails** |
| `{"1,2": {"name":123,...}}` | **AttributeError at `:1259` — import fails** |
| `{"1,2": {"name":["a"],...}}` | **AttributeError at `:1259` — import fails** |

This is the exact failure class the fix targets (N8: "a malformed cache should
degrade to 'no learned entries', not brick the project"), and the consequence is
total — every script including the whole test suite fails to import, with no
recovery but deleting the file by hand. Reachability is low: the file is only ever
written by `_learn_roster_entry()` (`:1244`), which always writes `card.name`, a
string. So this needs hand-editing or an odd corruption to hit.

**Fix.** One clause in the same validation block, e.g. add
`if not isinstance(v["name"], str): raise TypeError` inside the existing `try`, or
build the card as `PlayerCard(str(v["name"]), ...)`. Either lands inside the
existing `except`, so the entry warns and skips like every other malformed shape.

---

#### N27. `played=False` on the redraw path contradicts `select_and_discard()` — a discard *does* consume the turn
`orchestrator.py:1601-1608`, `:2009-2020`, `:2089-2092` vs `input_controller.py:125-140`

This does **not** invalidate N25 (see §2 — the bound is still correct and still
needed), but the stated reason for it is wrong about the game, and that reasoning
is now load-bearing in a live loop.

`play_one_turn()`'s docstring says:

> `played`: … False if a card was discarded instead (a redraw doesn't use up a
> turn — **the same slot gets played for real on the next poll**).

`select_and_discard()` says the opposite, and cites live confirmation:

> Confirmed live (2026-08-23): discarding isn't a single action — after
> `confirm_discard`, the game deals a replacement card and auto-lifts it with its
> own "PLAY" prompt, which **still needs `confirm_play` to actually commit it as
> this turn's play**.

The function body matches its own docstring: `input_controller.py:135-140` is
`reset_hand_cursor` → `move` → `select_card` → `confirm_discard` → `confirm_play`.
`PENDING_LIVE_VALIDATION.md` item 7 records this two-step fix as confirmed live.
So on the redraw path a card **is** committed and the turn **does** advance —
`played=False` really means "we took the discard branch", not "no turn was used".
The orchestrator docstring describes the pre-fix, discard-and-forget behaviour and
was never updated; round 3's N14 comment was arguably right about the game and
round 4 corrected it against a stale docstring rather than against
`input_controller.py`.

Two consequences, both currently benign:

1. **`turns_this_half` is not incremented on a discard turn** (`:2037-2038` is
   inside `if played:`), so `batters_used` undercounts by one per redraw. Inert
   today: `GameState.batters_used` is never read by `best_batting_play()`,
   `best_pitching_play()`, or `should_redraw()` — `decision_engine.py` references
   it only in the dataclass field and the `__main__` demo, and `HEURISTICS.md` §5
   records the `batters_used`-aware redraw variants as tested and *not* adopted.
   It becomes a real bug the moment that heuristic is switched on.
2. **`stuck_count` now increments on a turn that genuinely advanced.** Bounded and
   harmless, as traced in §2 — but it means the counter is measuring "turns since
   the last non-discard play", not "turns since progress".

**Fix.** Correct the two comment blocks to say what the discard path actually does
("the redraw commits a replacement card and consumes the turn; `played=False`
means only that we took the discard branch, so its outcome isn't logged"), and
either move `turns_this_half += 1` out of `if played:` or add an explicit note
that `batters_used` deliberately counts only non-redraw turns. The `stuck_count`
placement should stay exactly as N25 left it — that bound is still the right
guard against a discard that never lands.

### Important

None.

### Critical

None.

---

## 4. Explicitly checked and NOT a problem

- **`press("close_result")` outside the `try`.** Correct as-is; see the N12 row above.
- **N24's "double-counting is structurally impossible" claim.** Verified: `acted_screen`
  is set first, `save_progress()` is last.
- **The `turn` branch not setting `acted_screen`.** Deliberate and right — a repeated
  `turn` screen is the normal steady state, and `:1798` clears the guard on any
  recognized screen change anyway.
- **Both N25 paths reach `wait_for_screen_to_settle()`.** Neither the `if` nor the
  `else` short-circuits past `:2101`, so a discard still waits for the animation.
- **`read_full_ban_collection()`'s `roster_hits`/`absolute_positions` binding.** Both
  are only referenced under `if expected_positions` (`:1448`, `:1456`), which
  short-circuits first — no `UnboundLocalError` on an all-locked view.

---

## 5. Verdict

Both new findings are Minor and neither touches the live control flow that spends
real money. N25 is verified correct — it fixes a genuine unbounded-keypress loop
and, traced against the real discard cap of 2-3 per match versus
`MAX_STUCK_ATTEMPTS=15`, cannot abort a healthy run. N26 is a one-clause gap in an
otherwise-good validation fix, reachable only via a hand-corrupted file. N27 is a
stale docstring that has quietly outlived a live fix from 2026-08-23; worth
correcting so the next reader doesn't reason from it, but it changes no behaviour
today.

Nothing here blocks running the loop. **Fix N26's one clause and correct N27's two
comment blocks, then stop iterating** — the code is otherwise in good shape and
this is the right place to close the loop.
