# QA Findings — Round 6 (closing verification)

Date: 2026-08-25
Scope: verify the two Round-5 Minor fixes (N26, N27) are actually in the code, and that
nothing else broke. Read-only: no game input, no API calls, no files modified except this one.

## 1. N26 — `_load_learned_roster()` name validation: APPLIED and CORRECT

`orchestrator.py:1206-1213`, inside the per-entry `try` in `_load_learned_roster()`:

```python
if not isinstance(v.get("name"), str) or not v["name"].strip():
    raise ValueError(f"name must be a non-empty string, got {v.get('name')!r}")
```

The raise lands in the existing `except (ValueError, TypeError, KeyError, AttributeError)`
handler, which prints `WARNING: skipping malformed learned-roster entry ...` and continues.

Verified by running `import orchestrator` in an isolated scratch directory against a crafted
`known_ban_roster_learned.json` (the real project directory has no such file, and none was
created):

| entry | result |
|---|---|
| `"name": null` | warn + skip, import OK |
| `"name": 123` | warn + skip, import OK |
| `"name": "  "` | warn + skip, import OK |
| value is a bare string (not a dict) | warn + skip, import OK (`.get` raises `AttributeError`, caught) |
| top-level JSON is a list | warn + ignore file, import OK |
| valid entry | loaded into `KNOWN_BAN_ROSTER` **and** picked up by `ROSTER_BY_NAME` |

So the guard blocks the module-scope `c.name.lower()` crash without over-rejecting good rows.

## 2. N27 — `play_one_turn()` docstring: APPLIED and ACCURATE

`orchestrator.py:1613-1621`. The old "doesn't use up a turn" claim is gone. The docstring now
states that `played=False` means "took the discard branch", that `turns_this_half` therefore
undercounts on redraw turns, that this is inert only because no decision function currently
reads `batters_used`, and points to `HEURISTICS.md §5`.

Cross-checks:
- `input_controller.py:125-140` — `select_and_discard()` does end in `press("confirm_play")`,
  and its own docstring records that being confirmed live (2026-08-23). The new text matches
  the code.
- `HEURISTICS.md` §5 exists and is exactly the `batters_used`/`target_score`-aware redraw
  section the reference points at.

## 3. No regression

- `import orchestrator` from the project directory: OK (33 roster entries).
- All seven test files pass:
  - `test_ban_grid_locked.py` — OK (2 known frames, 20 cells)
  - `test_gameplay_regions.py` — OK (5 regions)
  - `test_known_ban_roster.py` — OK (33+ entries, short-circuit, two-read learning)
  - `test_ocr_ban_card.py` — OK (16/18 resolved, 2 safe abstains, 0 wrong)
  - `test_ocr_runner.py` — OK
  - `test_ocr_scoreboard.py` — OK (6 numbers, 3 screenshots)
  - `test_validate_game_state.py` — OK
- `run()` control flow is unchanged by these edits. The N25 shape at the `"turn"` screen is
  intact (`orchestrator.py:2037-2054, 2103`): `turns_this_half = 0` only on a phase change,
  `turns_this_half += 1` only under `if played:`, and `stuck_count = 0` only under `if played:`
  — the conditional reset that stops an endlessly-failing discard from spinning the loop
  forever. Both round-5 edits are confined to a validation clause and a docstring; neither
  touches an executable path in `run()`.

## New findings

None. No issue found that would cause incorrect gameplay, data corruption, or a crash.

Previously known-and-accepted items (screenshot log size cap, N9's two-read gate design
limitation, M6/M8/M14) were not re-examined and are unchanged.

## Verdict

**CLEAN — safe to stop.**
