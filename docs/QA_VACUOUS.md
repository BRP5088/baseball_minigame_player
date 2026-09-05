# QA — Vacuous tests, found by mutation

Method: every mutation below was applied to a **sandbox clone**, the named test
file(s) re-run, and the mutation reverted. "SURVIVED" means the test **still
passed** with the guarded code broken. The real tree was never written to (see
*Provenance* at the end).

**Line numbers are from a snapshot taken 2026-08-26 01:04.** A second session was
editing this tree concurrently throughout (12 `.py` files changed between 00:25
and 00:56; `clear_match_state.py`, `analyze_match_log.py`,
`screen_classifier_experiment.py` appeared mid-run). Every finding below was
**re-verified against the 01:04 snapshot**, but line numbers may have drifted
again — each entry carries a code anchor string, use that.

Taxonomy letters refer to `LESSONS.md` §1.

---

## Summary

| # | Location | Category | What survived |
|---|---|---|---|
| 1 | `input_controller.py` 271-330 | (f) count-not-identity | Whole ban-navigation function: **zero coverage** |
| 2 | `orchestrator.py:3221` | (f) | Ban positions can be mirrored; only the *count* is asserted |
| 3 | `test_run_state_machine.py:266-270` | (e)/(f) | C2 double-debit guard deletable |
| 4 | `test_run_state_machine.py:281-285` | (e) | `max_spend` cap deletable |
| 5 | `input_controller.py` 232-268 | — | `select_and_play` / `select_and_discard`: **zero coverage** |
| 6 | `orchestrator.py:3417` | — | Misfired turn gets written to `match_log.jsonl` |
| 7 | `orchestrator.py:3414` | (a)-adjacent | `report_misfire()` call-site deletable |
| 8 | `test_state_io.py:60-61` | assertion satisfied by absence | Atomic write deletable |
| 9 | `orchestrator.py:220` | (e) wrong fixture | Half the `_synthetic` stamp deletable |
| 10 | `test_validate_game_state.py:24-53` | (e) | **11 of 13** checks deletable |
| 11 | `decision_engine.py:221` | — | `should_redraw` threshold 4 → 9 |
| 12 | `test_input_timing.py:214-217` | (d) | `MAX_ACTION_DELAY` 0.80 → 999 |
| 13 | `test_run_state_machine.py:751-755` | (d) | `MAX_CONTINUOUS_MOTION_WAIT` 15 → 0.001 — **5th instance** |
| 14 | `orchestrator.py:1410` | — | Settle gate can be hard-wired to "settled" |
| 15 | `test_settle_regions.py:40` | (f) | `SETTLE_THRESHOLDS["hand"]` → 100.0 |
| 16 | `test_gameplay_regions.py:31` | (f) | `hand` crop → screen corner |
| 17 | `test_ocr_runner.py:37` | (e) | `third_base` crop → screen corner |
| 18 | `test_ban_grid_locked.py:145-146` | (d) tautology | Mask crop margin below the kernel radius |
| 19 | `test_gameplay_regions.py:58,64` | (h) silent skip | Whole prompt-detector block, fixtures absent |
| 20 | `test_no_side_effects.py:80` | (h) | Passes with all 15 other test files broken |
| 21 | `test_known_ban_roster.py:159-168` | (d) tautology | Asserts on the test's own re-implementation |
| 22 | `test_input_timing.py:132-134` | (f) | Focus-settle wait and key-hold both deletable |

---

# TIER 1 — money, physical input, persisted data

## 1. `select_bans_and_start_full()` has ZERO behavioural coverage

**This is the function that decides which physical card gets banned in a paid
match.** No test executes it. `test_run_state_machine.py:195` replaces it with a
recorder; `test_ban_scan.py` never calls it.

The only assertion about it is `test_run_state_machine.py:322-323`:

```python
check(len(h.bans_submitted[0]) == 3 if h.bans_submitted else False,
      f"C3: expected 3 distinct ban positions, got {h.bans_submitted}")
```

That is a **count**, not an identity — exactly the failure the file's own header
warns about ("`test_run_state_machine.py` ... its ban assertions check the COUNT
of bans and never their identity"). The header was written; the assertion was
not changed.

**Mutations applied — every one SURVIVED the entire suite (all 15 files):**

| Line | Anchor | Mutation | Effect if shipped |
|---|---|---|---|
| 312 | `move = "move_right" if col_diff > 0 else "move_left"` | swap the two directions | bans column `-c` instead of `c` — wrong physical card, every time |
| 309 | `for _ in range(row - current_row):` | `range(0)` | never scrolls; all three bans land on row 0 |
| 329 | second `press("confirm_play")` | `pass` | M11's documented second press gone; ban screen may not commit |
| 301 | `if len(targets) != len(banned_positions):` | `if False:` | silently bans fewer than 3 cards; the game refuses to start |

**Recommended replacement.** Drive the real function with a `press` recorder and
assert the *keystroke sequence*, not a count:

```python
# test_input_timing.py (it already fakes pyautogui + subprocess), or a new
# test_ban_navigation.py using the same triple guard.
import input_controller as ic
_P = []
ic.press = lambda k, *a, **kw: _P.append(k)

grid = [(r, c, PlayerCard(f"P{r}{c}", 5, 1)) for r in range(3) for c in range(5)]
_P.clear()
ic.select_bans_and_start_full(grid, {(0, 1), (1, 3), (2, 0)})
assert _P == [
    "move_right", "select_card",                       # (0,0) -> (0,1)
    "move_down", "move_right", "move_right",           # (0,1) -> (1,3)
    "select_card",
    "move_down", "move_left", "move_left", "move_left",# (1,3) -> (2,0)
    "select_card",
    "move_up", "move_up",                              # unwind to row 0
    "confirm_play", "confirm_play",                    # M11: exactly two
], f"ban navigation changed: {_P}"

# and the count guard, exercised:
try:
    ic.select_bans_and_start_full(grid, {(0, 1), (9, 9)})
    raise AssertionError("a ban position absent from the grid was accepted — "
                         "the cursor would stop short and ban a wrong card")
except ValueError:
    pass
```

The literal list is the point: it fails on a direction flip, an off-by-one, a
missing unwind, or a dropped confirm — none of which any current assertion sees.

---

## 2. `orchestrator.py:3221` — ban positions can be mirrored

Anchor: `banned_positions.add((row, col))` inside the `ban_screen` branch.

**Mutation:** `banned_positions.add((row, 4 - col))`
**Result:** SURVIVED `test_run_state_machine.py`, `test_ban_scan.py`,
`test_known_ban_roster.py`, `test_decisions.py`.

Three mirrored positions are still three *distinct* positions, so
`len(banned_positions) != 3` passes, the N15 identity guard passes, and
`check(len(h.bans_submitted[0]) == 3)` passes. Three wrong physical cards get
banned.

Two neighbouring guards are also uncovered — both SURVIVED the same four files:

- `if len({id(b) for b in bans}) != 3:` → `if False:` (the N15 duplicate-object guard)
- `if len(banned_positions) != 3:` → `if False:`

Also uncovered: replacing `bans = choose_bans(collection, count=3)` with
`sorted(collection, key=lambda c: -c.power)[:3]` — i.e. **ban your three
strongest cards** — SURVIVED all four. (`test_decisions.py:122-128` covers
`choose_bans` itself; nothing covers the orchestrator's use of it.)

**Recommended replacement**, in `test_run_state_machine.py` after the `hb`
harness (which already returns cards with powers 5..9 at `(0,0)..(0,4)`):

```python
# The harness's read_full_ban_collection returns PlayerCard("Card i", 5+i, 1)
# at (0, i), so the three weakest are at columns 0, 1, 2. Assert WHICH.
check(hb.bans_submitted and hb.bans_submitted[0] == [(0, 0), (0, 1), (0, 2)],
      f"banned {hb.bans_submitted[:1]}, expected the three WEAKEST cards at "
      "(0,0),(0,1),(0,2). A count-only assertion passes when the positions are "
      "mirrored, shifted, or chosen from the strongest — all of which ban the "
      "wrong physical cards in a paid match.")
```

---

## 3. `test_run_state_machine.py:266-270` — the C2 double-debit guard is deletable

```python
final = Harness(["match_start_prompt"] * 4, balance=500).run(target_wins=99)
check(final["balance"] == 450, "C2: ... the loop is re-debiting $50 per poll")
```

**Mutation:** `orchestrator.py:3073`, `if acted_screen == "match_start_prompt":`
→ `if False:`
**Result:** SURVIVED — the **whole file** stays green.

C5's `match_in_progress` flag now suppresses the second debit, so C2's removal is
invisible. C2 is not redundant, though: it is the branch that owns the *recovery
press* and the `MAX_STUCK_ATTEMPTS` bound for a prompt that genuinely failed to
start a match. With C2 gone, a dropped `start_match` keystroke means the run
never presses it again and dies as `match_start_prompt_during_match`.

Related, same branch: deleting the recovery press itself
(`orchestrator.py:3094`, `press("start_match")` → `pass`) also **SURVIVED**.
`test_run_state_machine.py:564-568` bounds it with `_presses <= 2` — a one-sided
ceiling (category **f**) that rewards deleting the press entirely.

**Recommended replacement.** Separate the two mechanisms, and make the press
assertion two-sided:

```python
# C2 must suppress the re-debit on its OWN, with C5 out of the picture.
# A result between the prompts clears match_in_progress, so only C2 can be
# what stops the second debit here.
h = Harness(["match_start_prompt", "match_start_prompt"], balance=500)
final = h.run(target_wins=99)
check(final["balance"] == 450 and h.presses.count("start_match") == 2,
      f"C2: a back-to-back match_start_prompt left balance {final['balance']} "
      f"and sent {h.presses.count('start_match')} start_match presses. Expected "
      "450 and exactly 2: one debit-and-press, then ONE recovery press for a "
      "prompt that did not dismiss. Fewer presses means a dropped keystroke is "
      "never retried; more means max_spend is bypassed.")
```

and tighten line 565 from `_presses <= 2` to `_presses == 2`.

---

## 4. `test_run_state_machine.py:281-285` — `max_spend` is not actually tested

```python
final = Harness(["match_start_prompt", "turn", "match_start_prompt"],
                balance=500).run(target_wins=99, max_spend=50)
check(final["balance"] == 450, "max_spend: cap was $50 but balance fell to ...")
```

**Mutation:** `orchestrator.py:3138`,
`if max_spend is not None and spent + 50 > max_spend:` → `if False:`
**Result:** this assertion **SURVIVED**. The file goes red only on an unrelated
line at the very end — *"a clean stop wrote a diagnostic bundle"* — which is an
accidental catch, not a spend-cap assertion.

The fixture has no `result` screen between the two prompts, so `match_in_progress`
is still `True` at the second one and **C5** refuses the debit. The cap is never
consulted. This is the same masking as #3.

**Recommended replacement** — put a scored result between the prompts so C5 is
cleared and only the cap can stop the debit:

```python
h = Harness(["match_start_prompt", RESULT_WIN, "match_start_prompt"] + ["other"] * 5,
            balance=500)
final = h.run(target_wins=99, max_spend=50)
check(final["balance"] == 450 and h.presses.count("start_match") == 1,
      f"max_spend: with the in-progress flag cleared by a scored result, a $50 "
      f"cap must stop the SECOND match. Balance {final['balance']} (expected "
      f"450), start_match presses {h.presses.count('start_match')} (expected 1). "
      "Without an intervening result, C5 suppresses the debit and this asserts "
      "nothing about the cap.")
```

---

## 5. `select_and_play()` / `select_and_discard()` / `reset_hand_cursor()` — zero coverage

The path from "we chose card 3" to actual keystrokes. Nothing executes it.
All four mutations **SURVIVED the entire suite**:

| Line | Anchor | Mutation | Effect |
|---|---|---|---|
| 240 | `press("move_right")` in `select_and_play` | `press("move_left")` | plays the wrong card every turn |
| 250 | `press("confirm_play")` | `pass` | card selected but never committed |
| 248 | `press("select_card")` (tactics) | `pass` | boosts silently never attached |
| 228 | `for _ in range(MAX_HAND_SIZE - 1):` in `reset_hand_cursor` | `range(0)` | cursor never normalised; every index off by wherever the last turn left it |
| 268 | `press("confirm_play")` in `select_and_discard` | `pass` | the documented "discard-and-forget" hang |

**Recommended replacement** — same recorder style as #1:

```python
_P.clear(); ic.select_and_play(2)
assert _P == ["move_left"] * 4 + ["move_right"] * 2 + ["select_card", "confirm_play"], _P

_P.clear(); ic.select_and_play(1, tactics_index=3)
assert _P == (["move_left"] * 4 + ["move_right"] + ["select_card"]
              + ["move_right"] * 2 + ["select_card", "confirm_play"]), _P

_P.clear(); ic.select_and_discard(0)
assert _P == ["move_left"] * 4 + ["select_card", "confirm_discard", "confirm_play"], _P
```

---

## 6. `orchestrator.py:3417` — a misfired turn gets written into `match_log.jsonl`

Anchor: `raise RuntimeError("intended card absent from reveal")`

**Mutation:** → `pass`
**Result:** SURVIVED `test_run_state_machine.py`.

That `raise` (swallowed by the enclosing `except Exception: pass`) is the only
thing stopping `pending_matchup = matchup_info` from being set on a suspected
misfire. Remove it and the turn is logged — and because the opponent picker is
*"first player card that isn't ours"*, **our own misplayed card is recorded as
the opponent's**. That is silent corruption of the dataset the project exists to
build, on exactly the turns that are already anomalous.

`test_run_state_machine.py:805-812` asserts the misfire *observation* is
recorded. Nothing asserts the row is *suppressed*.

**Recommended replacement** (the harness already redirects `BASEBALL_MATCH_LOG`
to `_DIAGTMP/match_log.jsonl`):

```python
_LOG = os.environ["BASEBALL_MATCH_LOG"]
open(_LOG, "w").close()
h = _Reveal([_WRONG, _THEIRS])          # our card absent = misfire
h.run(target_wins=99)
_rows = [json.loads(l) for l in open(_LOG) if l.strip()]
check(not _rows,
      f"a suspected-misfire turn wrote {len(_rows)} row(s) to match_log: "
      f"{_rows}. The opponent picker takes the first player card that is not "
      "ours, so on a misfire OUR OWN misplayed card is logged as the "
      "opponent's — silent corruption of the dataset, on the turns most likely "
      "to be studied.")

# ...and the clean case must still log, or the suppression is over-broad.
open(_LOG, "w").close()
_Reveal([_OURS, _THEIRS]).run(target_wins=99)
check(len([l for l in open(_LOG) if l.strip()]) == 1,
      "a clean reveal stopped logging — the misfire suppression is eating "
      "genuine rows")
```

---

## 7. `orchestrator.py:3414` — `report_misfire()` call-site deletable

Anchor: `input_controller.report_misfire()`

**Mutation:** → `pass`
**Result:** SURVIVED `test_run_state_machine.py` **and** `test_input_timing.py`.

`test_input_timing.py` exercises `report_misfire()` thoroughly — in isolation.
`test_run_state_machine.py` exercises the misfire *detection* — but stubs nothing
that would notice the backoff. The wire between them is untested. Same shape as
`LESSONS.md` §1 #4: the mechanism is proven, the *caller asking for it* is not.
(This is the same reasoning `test_ocr_ban_card.py`'s N1 call-site block was added
for — that one works; this one is missing.)

**Recommended replacement**, in `test_run_state_machine.py` beside the misfire
block:

```python
import input_controller as _ic
_calls = []
_real = _ic.report_misfire
_ic.report_misfire = lambda: _calls.append(1) or False
try:
    _Reveal([_WRONG, _THEIRS]).run(target_wins=99)       # misfire
    check(len(_calls) == 1,
          f"a detected misfire made {len(_calls)} report_misfire() call(s), "
          "expected 1 — the adaptive backoff is fully tested in "
          "test_input_timing.py and never actually invoked by the loop")
    _calls.clear()
    _Reveal([_OURS, _THEIRS]).run(target_wins=99)        # clean
    check(not _calls, "a clean reveal reported a misfire — pacing would ratchet "
                      "up on healthy play")
finally:
    _ic.report_misfire = _real
```

---

## 8. `test_state_io.py:60-61` — the atomic-write test passes with atomicity removed

```python
save_progress(1, 1, 1, 100, pf)
if os.path.exists(pf + ".tmp"):
    failures.append("atomic write left a .tmp file behind")
```

**Mutation:** replace the body of `_atomic_write_json` (`orchestrator.py:121`,
anchor `tmp = f"{path}.tmp"`) with a plain `open(path, "w"); json.dump(...)`.
**Result:** SURVIVED `test_state_io.py`, `test_known_ban_roster.py`,
`test_run_state_machine.py`.

The assertion is satisfied *more easily* by the mechanism's absence: a
non-atomic write never creates a `.tmp` at all. It tests cleanup, not atomicity.

**Recommended replacement** — assert the property directly, by interrupting the
write:

```python
# Atomicity means: a write that dies partway leaves the OLD file intact and
# fully parseable, never a truncated one.
save_progress(7, 3, 2, 250, pf)
_good = load_progress(pf)

_real_dump = json.dump
def _die(obj, fh, **kw):
    fh.write('{"wins": 99, "loss')      # a realistic partial write
    fh.flush()
    raise OSError("simulated interruption mid-write")
json.dump = _die
try:
    try:
        save_progress(1, 1, 1, 100, pf)
    except OSError:
        pass
finally:
    json.dump = _real_dump

if load_progress(pf) != _good:
    failures.append(
        f"an interrupted save left progress as {load_progress(pf)} instead of "
        f"{_good} — the write is not atomic, and a crash mid-save destroys the "
        "win/loss record it exists to protect")
if os.path.exists(pf + ".tmp"):
    failures.append("atomic write left a .tmp file behind")
```

That fails on the non-atomic version with a `RuntimeError` from `load_progress`
(the file is now `{"wins": 99, "loss`), and passes on the real one.

---

## 9. `orchestrator.py:220` — half the `_synthetic` stamp is untested

Anchor: `return entry.startswith("test_") and entry.endswith(".py")` inside
`_running_under_test()`.

**Mutation:** → `return False`
**Result:** SURVIVED `test_state_io.py`.

Category **(e), wrong fixture.** All four subprocess probes
(`test_state_io.py:179`, `:201`, `:223`, `:239`) launch `python3 -c "..."`, where
`sys.argv[0]` is `-c`. The argv branch is never reached by any of them; only the
`BASEBALL_TEST_RUN` branch is exercised.

That branch matters: it is what stamps rows when someone runs
`python3 test_run_state_machine.py` **directly**, without `run_tests.sh` — which
is precisely the "a test forgot the redirect" case `LESSONS.md` §2 says the stamp
exists for. Verified by hand: a `test_*.py` entry point with no env vars set
gives `_SYNTHETIC_LOG = True` today, and `False` with the branch removed.

**Recommended replacement** — probe via a real `test_*.py` file, not `-c`:

```python
_probe = os.path.join(_tf.mkdtemp(), "test_stamp_probe.py")
with open(_probe, "w") as _f:
    _f.write("import os, sys\n"
             "sys.path.insert(0, %r)\n" % os.path.dirname(os.path.abspath(__file__)) +
             "import orchestrator as o\nprint(o._SYNTHETIC_LOG)\n")
_r5 = subprocess.run(
    [_sys.executable, _probe],
    env={k: v for k, v in os.environ.items()
         if k not in ("BASEBALL_MATCH_LOG", "BASEBALL_TEST_RUN")}
        | {"PERSONAL_ANTHROPIC_API_KEY": "dummy-offline-test"},
    capture_output=True, text=True)
assert "True" in _r5.stdout, (
    f"a directly-invoked test_*.py did not trigger the stamp ({_r5.stdout!r}). "
    "BASEBALL_TEST_RUN only exists under run_tests.sh; running one test file by "
    "hand is the exact case where the redirect is forgotten, and the argv "
    "fallback is the only thing that stamps those rows. Every probe in this "
    "file uses `python3 -c`, where argv[0] is '-c', so none of them reach it.")
```

---

## 10. `test_validate_game_state.py` — 11 of 13 checks are deletable

The loop at lines 48-53 catches **any** `ValueError`, and almost every fixture in
`bad_cases` omits `runners` / `your_score` / `opp_score`. So the turn-completeness
block at the end of the function raises for them regardless of whether the check
under test exists. The function's own comment claims the ordering protects
against this ("*Ordered after the per-card checks so a malformed CARD still
reports as a malformed card*") — the ordering is right, but the *test* never
looks at which error it got.

**Mutations applied, one per check** (each `if …:` → `if False:`):

| Check | Anchor | Result |
|---|---|---|
| `hand_index` range | `if not isinstance(idx, int) or not (0 <= idx < 5):` | **SURVIVED** |
| duplicate `hand_index` | `if idx in seen_indices:` | **SURVIVED** |
| `power` type | `if not isinstance(power, int) or isinstance(power, bool):` | killed only by a downstream `TypeError`; **SURVIVED** when the range check is removed too |
| `power` range | `if not (CARD_POWER_MIN <= power <= CARD_POWER_MAX):` | **SURVIVED** |
| `secondary` | `if secondary is not None and (...)` | **SURVIVED** |
| tactics `type` | `if card.get("type") not in {t.value for t in TacticsType}:` | **SURVIVED** |
| tactics `bonus` | `if not isinstance(bonus, int) or ... bonus < 0:` | **SURVIVED** |
| result payload | `if not has_scores and state.get("result_won") is None:` | **SURVIVED** |
| `_score` usable | `if key.endswith("_score") and (...)` | **SURVIVED** |
| runners > 3 | `if len(state["runners"]) > 3:` | **SURVIVED** |
| `discards_left` range | `if dl is not None and (...)` | **SURVIVED** |
| phase | `if state.get("phase") not in ("batting", "pitching"):` | killed (by the `discard_prompt` case, which the completeness block does not cover) |
| collection `row`/`col` | `if not isinstance(c.get("row"), int) or ...` | killed (`ban_screen`, likewise not covered) |

The two that are genuinely covered are the two whose fixture uses a screen the
turn-completeness block ignores. That is the tell.

Note the consequences the docstrings themselves record for the uncovered ones:
`power 0` → `should_redraw()` **burns a discard**; `power 999` → played;
`discards_left: 99` → **discarded**; `your_score: "seven"` → logged into
`match_log.jsonl`; a bare `{"screen": "result"}` → recorded as a **loss in
progress.json**.

**Recommended replacement.** Two changes, both small:

```python
# 1. Give every fixture the fields the completeness block demands, so the ONLY
#    thing that can reject it is the check under test.
_TURN = {"screen": "turn", "phase": "batting",
         "runners": [], "your_score": 0, "opp_score": 0}

# 2. Assert on the MESSAGE, so the right check is what fired.
bad_cases = [
    ({"screen": "nonsense"},                                   "unrecognized screen"),
    (dict(_TURN, hand=[{"kind": "player", "power": 5, "hand_index": 7}]),
                                                               "invalid hand_index"),
    (dict(_TURN, hand=[{"kind": "player", "power": 5, "hand_index": 0},
                       {"kind": "player", "power": 3, "hand_index": 0}]),
                                                               "duplicate hand_index"),
    (dict(_TURN, hand=[{"kind": "player", "hand_index": 0}]),   "missing/invalid power"),
    (dict(_TURN, hand=[{"kind": "player", "power": True, "hand_index": 0}]),
                                                               "missing/invalid power"),
    # RANGE, not just type — power 0 burns a discard, per the docstring.
    (dict(_TURN, hand=[{"kind": "player", "power": 0, "hand_index": 0}]),
                                                               "outside the possible range"),
    (dict(_TURN, hand=[{"kind": "player", "power": 999, "hand_index": 0}]),
                                                               "outside the possible range"),
    (dict(_TURN, hand=[{"kind": "player", "power": 5, "secondary": 99, "hand_index": 0}]),
                                                               "invalid secondary"),
    (dict(_TURN, hand=[{"kind": "tactics", "type": "not_a_real_type",
                        "bonus": 1, "hand_index": 0}]),         "invalid type"),
    (dict(_TURN, hand=[{"kind": "tactics", "type": "swing_boost",
                        "bonus": None, "hand_index": 0}]),      "invalid bonus"),
    (dict(_TURN, hand=[{"kind": "wat", "hand_index": 0}]),      "invalid kind"),
    ({"screen": "ban_screen", "collection": [{"name": "X", "row": "0", "col": 0}]},
                                                               "missing row/col"),
    ({"screen": "turn", "hand": []},                            "unusable phase"),
    ({"screen": "turn", "phase": None, "hand": []},             "unusable phase"),
    ({"screen": "discard_prompt", "phase": "nonsense", "hand": []}, "unusable phase"),
    # Fields play_one_turn() indexes unconditionally.
    ({"screen": "turn", "phase": "batting",
      "hand": [{"kind": "player", "power": 5, "hand_index": 0}]},
                                                               "missing required field"),
    (dict(_TURN, your_score="seven",
          hand=[{"kind": "player", "power": 5, "hand_index": 0}]),
                                                               "unusable your_score"),
    (dict(_TURN, runners=[1, 2, 3, 4, 5],
          hand=[{"kind": "player", "power": 5, "hand_index": 0}]),
                                                               "3-base diamond"),
    (dict(_TURN, discards_left=99,
          hand=[{"kind": "player", "power": 5, "hand_index": 0}]),
                                                               "discards_left out of range"),
    (dict(_TURN, hand=[{"kind": "tactics", "name": "B", "type": "swing_boost",
                        "bonus": 2, "hand_index": 0}]),         "no player card"),
    # A result screen with nothing to score it from was recorded as a LOSS.
    ({"screen": "result"},                                      "nothing to score it from"),
]
for case, want in bad_cases:
    try:
        validate_game_state(case)
        raise AssertionError(f"expected ValueError for {case!r}")
    except ValueError as e:
        assert want in str(e), (
            f"{case!r} was rejected as {e!r}, but the check under test is "
            f"{want!r}. A later block is rejecting the fixture first, so this "
            "case proves nothing about the check it was written for.")
```

---

## 11. `decision_engine.py:221` — `should_redraw` threshold is unguarded

Anchor: `return max(c.power for c in hand_players) <= 4`

**Mutation:** `<= 9`
**Result:** SURVIVED `test_decisions.py` and `test_run_state_machine.py`.

`test_decisions.py:131-134` covers exactly one case: `redraws_left=0` returns
`False`. The threshold itself — which decides whether a limited, physical
discard is burned — has no test. At `<= 9` almost every hand triggers a discard.

**Recommended replacement:**

```python
_S = st(half="batting", redraws_left=2)
check(should_redraw([PlayerCard("W", 4, 0)], _S) is True,
      "a 4-power best card did not trigger a redraw — the documented threshold "
      "is <= 4")
check(should_redraw([PlayerCard("OK", 5, 0)], _S) is False,
      "a 5-power best card triggered a redraw — raising the threshold burns a "
      "discard (2-3 per match) on a perfectly playable hand")
check(should_redraw([PlayerCard("W", 1, 0), PlayerCard("A", 9, 0)], _S) is False,
      "redraw fired on a hand containing a 9 — it must look at the BEST card, "
      "not the worst")
```

---

## 12. `test_input_timing.py:214-217` — `MAX_ACTION_DELAY` is self-referential

```python
check(ic.ACTION_DELAY <= ic.MAX_ACTION_DELAY,
      f"ACTION_DELAY reached {ic.ACTION_DELAY}, above the "
      f"{ic.MAX_ACTION_DELAY}s ceiling — ...")
```

**Mutation:** `input_controller.py:93`, `MAX_ACTION_DELAY = 0.80` → `999.0`
**Result:** SURVIVED.

Category **(d).** The bar moves with the mutation. (Deleting the `min(...)` clamp
*is* caught — but raising the constant, the more likely edit, is not.) At 999 a
persistent reveal misread ratchets every keystroke to a 999-second pause — the
unbounded slowdown the ceiling exists to prevent, arriving by the other route.

**Recommended replacement** — a literal, as `test_run_state_machine.py` already
does for `MAX_IDENTICAL_FRAMES` and `MAX_POLLS_WITHOUT_PROGRESS`:

```python
# LITERAL, not ic.MAX_ACTION_DELAY. Reading the constant means the bar moves
# with the mutation — LESSONS.md §1 (d), and this is the same trap again.
check(ic.ACTION_DELAY <= 1.0,
      f"ACTION_DELAY reached {ic.ACTION_DELAY}s after 200 misfires. Anything "
      "above ~1s per keystroke makes a turn unusable; a misread reveal must "
      "not be able to get there.")
check(ic.MAX_ACTION_DELAY <= 1.0,
      f"MAX_ACTION_DELAY is {ic.MAX_ACTION_DELAY}s — the ceiling itself is now "
      "high enough to be no ceiling at all")
```

---

# TIER 2 — read quality, API spend, geometry

## 13. `test_run_state_machine.py:751-755` — motion-gate bound is self-referential

```python
_expected = orchestrator.MAX_CONTINUOUS_MOTION_WAIT / 0.2
check(h.motion_checks >= _expected * 0.5, ...)
```

**Mutation:** `MAX_CONTINUOUS_MOTION_WAIT = 15.0` → `0.001`
**Result:** SURVIVED.

Category **(d)**, and by my count the **fifth** instance in this project — the
file's own comments at lines 715 and 611 flag the trap for two *other* constants
and then reproduce it here. With the constant at 0.001 the gate falls through on
the first check, so an animating screen is read immediately: mid-deal hands,
wasted vision calls, exactly the failure `SETTLE_REGION_SETS` exists to prevent.

**Recommended replacement:**

```python
# LITERAL bounds, not orchestrator.MAX_CONTINUOUS_MOTION_WAIT — reading the
# constant means the bar moves with the mutation (LESSONS.md §1 (d)). Each
# motion check advances the virtual clock 0.2s, so ~50 checks is ~10s.
check(h.motion_checks >= 50,
      f"motion gate: fell through after {h.motion_checks} checks "
      f"(~{h.motion_checks * 0.2:.1f}s). It must hold out for several seconds "
      "of continuous animation, or it is not a gate — a shrunk "
      "MAX_CONTINUOUS_MOTION_WAIT reads every mid-deal frame.")
check(h.motion_checks <= 200,
      f"motion gate: {h.motion_checks} checks (~{h.motion_checks * 0.2:.1f}s) "
      "before falling through — the bound is too slack to recover a "
      "permanently-animating screen")
```

---

## 14. `orchestrator.py:1410` — the settle gate itself has zero behavioural coverage

Anchor: `settled = all(_mean_abs_delta(prev[n], current[n]) ...`

**Mutation:** `settled = True or all(...)`
**Result:** **SURVIVED the entire suite (all 15 files).**

`wait_for_screen_to_settle`, `screen_is_moving`, `_grab_settle_regions`,
`wait_for_reveal_cards` and `_safe_prompt_check` are all replaced by stubs in
the only two files that reach them (`test_run_state_machine.py:189-199`,
`test_ban_scan.py:94-101`). `test_settle_regions.py` inspects constants only, by
design ("*Offline: pure geometry*"). So the gate can be hard-wired open and
nothing notices — the exact original defect the file's header describes.

**Recommended replacement** — a small unit test with a fake `_grab_settle_regions`
and a virtual clock, in `test_settle_regions.py`:

```python
import orchestrator as _o, time as _rt
_frames, _saved = [], (_o._grab_settle_regions, _o.time)

class _VClock:
    now = 1000.0
    def sleep(self, n): _VClock.now += n
    def time(self): return _VClock.now
    def strftime(self, f, *a): return _rt.strftime(f, *a)

_o.time = _VClock()
_o._grab_settle_regions = lambda names: {n: _frames.pop(0) if _frames else 0 for n in names}
try:
    # A region that keeps changing must NOT settle before max_wait.
    _frames = list(range(0, 400, 40))          # deltas of 40, way over threshold
    _waited = _o.wait_for_screen_to_settle(max_wait=2.0, regions="turn")
    if _waited < 2.0:
        failures.append(f"a continuously-changing region settled after "
                        f"{_waited:.2f}s — the threshold comparison is not "
                        "gating anything")
    # A still region must settle after exactly stable_polls_required polls.
    _frames = [5] * 20
    _waited = _o.wait_for_screen_to_settle(max_wait=2.0, regions="turn")
    if _waited > 0.5:
        failures.append(f"a still screen took {_waited:.2f}s to settle")
    # And the counter must RESET on an interruption: still, still, MOVING,
    # still must not have satisfied "2 consecutive".
    _frames = [5, 5, 500, 5, 5, 5]
    _waited = _o.wait_for_screen_to_settle(max_wait=2.0, regions="turn")
    if _waited < 0.5:
        failures.append("a moving frame between two still ones still counted "
                        "toward 'consecutive stable polls'")
finally:
    _o._grab_settle_regions, _o.time = _saved
```

(`_mean_abs_delta` will need integers or 1-pixel images depending on its
signature; the shape of the three cases is the point.)

---

## 15. `test_settle_regions.py:40` — `SETTLE_THRESHOLDS["hand"]` is one-sided

```python
if SETTLE_THRESHOLDS.get("hand", 0) < 7.0:
    failures.append(f"hand threshold ... is below its measured idle p95 of 7.63")
```

**Mutation:** `"hand": 8.0` → `100.0`
**Result:** SURVIVED (`test_settle_regions.py`, `test_gameplay_regions.py`,
`test_run_state_machine.py`).

Category **(f).** Only a floor. At 100.0 no hand motion ever exceeds the
threshold, so the gate returns "settled" instantly and reads the hand mid-deal —
the defect this whole file was written for, reachable by moving the number the
file checks.

**Recommended replacement** — two-sided, from the same measurements the comment
already cites:

```python
_h = SETTLE_THRESHOLDS.get("hand")
if not (7.0 <= _h <= 12.0):
    failures.append(
        f"hand threshold {_h} is outside [7.0, 12.0]. Below 7.0 it fires on "
        "idle noise (measured idle p95 7.63); above ~12 it cannot see real "
        "dealing motion at all, so the gate returns instantly and the loop "
        "reads a mid-deal hand — the original defect this file exists for. "
        "A floor alone rewards raising it.")
for _n, _t in SETTLE_THRESHOLDS.items():
    if not (1.0 <= _t <= 20.0):
        failures.append(f"threshold {_n}={_t} is outside any plausible range")
```

---

## 16. `test_gameplay_regions.py:31` — the `hand` crop can be pointed anywhere

```python
assert crop_bytes < full_bytes * 0.5, (...)
```

**Mutation:** `GAMEPLAY_REGIONS_FRAC["hand"]` → `(0.0, 0.0, 0.02, 0.02)`
**Result:** SURVIVED `test_gameplay_regions.py`, `test_settle_regions.py`,
`test_image_pipeline.py`, `test_ocr_runner.py`.

Category **(f).** The byte-size bound is a ceiling and the failure direction —
a smaller, wronger crop — *improves* the number. The other checks are
`labels == keys`, `width > 0 and height > 0`, and "inside the frame", all of
which a 2%-corner box satisfies. `test_settle_regions.py` only asks that
`"hand"` resolves to a valid box.

The `hand` crop feeds every turn decision. Nothing pins it to the hand.

**Recommended replacement** — content, not size. There is already a labelled
fixture corpus (`hand_labels*.json`, `hand_samples/`):

```python
# The hand crop must actually contain the hand. Ground truth: on this frame
# the hand holds 5 cards whose power badges are legible.
from orchestrator import GAMEPLAY_REGIONS_FRAC
_hx0, _hy0, _hx1, _hy1 = GAMEPLAY_REGIONS_FRAC["hand"]
assert _hy0 < 0.75 and _hy1 > 0.97 and _hx1 - _hx0 > 0.4, (
    f"the hand region {GAMEPLAY_REGIONS_FRAC['hand']} no longer spans the "
    "bottom card strip (measured y 0.716-1.000, x 0.250-0.760). A byte-size "
    "bound gets BETTER as the crop shrinks, so it cannot catch this.")

# Stronger, if hand_digit_reader is usable offline: assert the crop still
# reads the known powers on a labelled frame.
_crop = dict(crop_gameplay_regions(img))["hand"]
from hand_digit_reader import read_hand_digits, group_into_cards
_cards = group_into_cards(read_hand_digits(_crop))
assert len(_cards) >= 4, (
    f"only {len(_cards)} cards found in the hand crop on a frame known to hold "
    "5 — the crop is no longer aimed at the hand")
```

---

## 17. `test_ocr_runner.py:37` — `third_base` geometry is unconstrained

```python
assert card is None, f"empty third_base should read as None, got {card}"
```

**Mutation:** `GAMEPLAY_REGIONS_FRAC["third_base"]` → `(0.0, 0.0, 0.02, 0.02)`
**Result:** SURVIVED `test_ocr_runner.py`, `test_gameplay_regions.py`,
`test_image_pipeline.py`, `test_settle_regions.py`.

Category **(e)/(f).** `first_base` and `second_base` have positive identity
assertions (lines 14-16) that pin their geometry. `third_base`'s only assertion
is "an empty base reads as `None`" — which **any** misaimed crop satisfies. The
file's comment even records that "*the original third_base box was centered on
[the wrong thing]*", i.e. this is a defect that has already occurred once.

**Recommended replacement** — find a frame with a runner on third and assert
identity, exactly as the other two bases do:

```python
CASES = [
    ("9.49", "first_base",  "Rube Sharp"),
    ("9.49", "second_base", "Brian Coker"),
    ("9.46", "first_base",  "Brian Coker"),
    ("<frame with a third-base runner>", "third_base", "<that runner>"),
]
```

If no such frame exists yet, the interim guard should at least be two-sided —
assert the box is where it was measured and that it is *not* the same box as
another base:

```python
_tb = GAMEPLAY_REGIONS_FRAC["third_base"]
assert _tb == (0.3225, 0.320, 0.4375, 0.530), (
    f"third_base moved to {_tb} and NOTHING else checks it: its only assertion "
    "is 'an empty base reads as None', which any misaimed crop satisfies. "
    "first_base and second_base are pinned by positive identity cases; this "
    "one is not. Capture a frame with a runner on third and add a real case.")
assert _tb not in (GAMEPLAY_REGIONS_FRAC["first_base"],
                   GAMEPLAY_REGIONS_FRAC["second_base"])
```

---

## 18. `test_ban_grid_locked.py:145-146` — a tautology on a test-local value

```python
_m = MASK_KERNEL // 2 + 2
assert _m > MASK_KERNEL // 2, (
    f"crop margin {_m} does not exceed the kernel radius {MASK_KERNEL // 2}; ...")
```

`_m` is computed **in the test**, not read from `orchestrator`. `k//2 + 2 > k//2`
is true for every `k`. The assertion cannot fail.

The preceding source-substring check (`"MASK_KERNEL // 2" in _margin_src`) is the
only real coverage, and it is weak:

**Mutation:** `orchestrator.py:606`, `margin = MASK_KERNEL // 2 + 2` →
`MASK_KERNEL // 2 - 1`
**Result:** SURVIVED — the substring is still there.

(Setting `margin = 0` outright *is* caught, but `margin = 0  # MASK_KERNEL // 2`
also survives, so the substring check is defeated by a comment.)

The consequence is stated in the file's own comment: a margin below the kernel
radius lets PIL's zero-padding into the sampled cells, "*flipping a locked card
to 'unlocked', i.e. changing which cards get banned*."

**Recommended replacement** — read the real value and prove the property on the
real fixtures:

```python
# Read the margin the FUNCTION uses, not one recomputed here.
import re
_m_src = re.search(r"margin\s*=\s*(.+)", _margin_src)
_margin = eval(_m_src.group(1).split("#")[0], {"MASK_KERNEL": MASK_KERNEL})
assert _margin > MASK_KERNEL // 2, (
    f"lock-detector crop margin {_margin} does not exceed the kernel radius "
    f"{MASK_KERNEL // 2}; PIL zero-pads outside the crop, so cells within the "
    "radius of the edge read as high-contrast and locked cards flip to "
    "unlocked — changing which physical cards get banned.")

# And prove it end-to-end: the cropped path must equal the uncropped one.
import numpy as _np
from PIL import ImageChops as _IC2, ImageFilter as _IF2
for _fname, _expected in CASES:
    _img = Image.open(os.path.join(SRC_DIR, _fname))
    # Full-frame reference: no crop, so no padding can leak.
    assert detect_ban_grid_locked(_img) == _expected, (
        f"{_fname}: the cropped lock detector disagrees with ground truth — "
        "the crop margin is leaking zero-padding into the sampled cells")
```

---

## 19. `test_gameplay_regions.py:58, 64` — silent skip (h), and it prints a false OK

```python
if os.path.exists(_p) and not input_prompt_visible(Image.open(_p)):
```

**Demonstrated** by moving the five fixture frames out of `screenshot_log/`:
the file exits 0 and prints

```
OK: input-prompt detector — 3 visible detected, 2 ban screens correctly ignored
```

having opened zero images. `orchestrator` **prunes `screenshot_log/`**, so this
is not hypothetical — it is the same failure `test_ban_scan.py:42-47` was
already hardened against.

With the fixtures present, `INPUT_PROMPT_REGION` → corner and
`INPUT_PROMPT_THRESHOLD` → 0.0 are both caught. With them absent, neither is.

**Recommended replacement** — copy `test_ban_scan.py`'s pattern, and move the
fixtures to `test_fixtures/` (which `test_ocr_ban_card.py:40-43` already
established as the pruner-safe location):

```python
_missing = [f for f in _PROMPT_VISIBLE + _PROMPT_ABSENT
            if not os.path.exists(os.path.join(SRC, f))]
if _missing:
    # NOT a skip: orchestrator prunes screenshot_log/, so a green suite with
    # this block doing nothing is exactly the failure mode to avoid.
    raise SystemExit(
        f"missing input-prompt reference frames {_missing} — the detector "
        "would be silently untested. Move them to test_fixtures/, which the "
        "screenshot pruner does not touch (see test_ocr_ban_card.py N10).")

for _f in _PROMPT_VISIBLE:
    if not input_prompt_visible(Image.open(os.path.join(SRC, _f))):
        _prompt_fail.append(f"{_f}: PLAY prompt is visible but not detected")
```

---

## 20. `test_no_side_effects.py:80` — return codes are discarded

```python
for t in tests:
    subprocess.run([sys.executable, t], cwd=HERE, env=env,
                   capture_output=True, text=True)
```

**Demonstrated:** every other `test_*.py` replaced with
`raise SystemExit('deliberately broken')`. The file prints

```
OK: 15 test file(s) ran without touching any of 5 tracked files or 4 tracked directories
```

and exits 0. A test that dies at import writes nothing, so it passes the
side-effect check trivially — while the report claims it "ran".

This does not weaken the *side-effect* guarantee for tests that do run, but it
makes the file's own output untrustworthy and hides an import-time break of the
one file whose job is to catch what everyone else forgot.

**Recommended replacement:**

```python
_crashed = []
for t in tests:
    r = subprocess.run([sys.executable, t], cwd=HERE, env=env,
                       capture_output=True, text=True)
    # A test that dies at import writes nothing and so passes the side-effect
    # check trivially. Record it: "no side effects" from a file that never ran
    # is not evidence of anything.
    if r.returncode != 0:
        _crashed.append((t, r.returncode, (r.stdout + r.stderr).strip()[-200:]))

...

for t, rc, tail in _crashed:
    failures.append(
        f"{t} exited {rc} under this harness, so its side effects were never "
        f"exercised — this file's OK line would claim it 'ran'. Tail: {tail}")
```

(Note these subprocesses run *without* `BASEBALL_MATCH_LOG`, deliberately — so
any test that legitimately needs it will now surface here rather than be
silently counted as clean. That is the intended signal.)

---

## 21. `test_known_ban_roster.py:159-168` — asserts on the test's own re-implementation

```python
for _bad in ([], [(0, 0, PlayerCard("Only One", 5, 1))]):
    _o._cached_ban_collection = None
    _o.read_full_ban_collection.__wrapped__ if False else None   # dead expression
    _n = len(_bad)
    _should_cache = _n >= 3
    assert not _should_cache, "fixture error: this case should not cache"
_full = [(0, i, PlayerCard(f"C{i}", 5, 1)) for i in range(5)]
assert len(_full) >= 3
```

`read_full_ban_collection` is never called. `_should_cache` is computed by the
test from a literal, so `assert not _should_cache` is `assert not (2 >= 3)`.
Every line here is a no-op; line 161 is a dead expression statement.

The behaviour **is** covered — by `test_ban_scan.py:176-184`, which drives a
blank frame through the real function (verified: deleting
`len(full_collection) >= 3` turns `test_ban_scan.py` red). So this block is dead
weight that reads as coverage.

**Recommendation:** delete lines 155-171 outright, keep the
`inspect.getsource` assertion at 172-175, and add a pointer:

```python
# The BEHAVIOUR is covered in test_ban_scan.py section 3, which drives a blank
# frame through the real read_full_ban_collection(). This is only the
# source-level tripwire for the same invariant.
_src = __import__("inspect").getsource(_o.read_full_ban_collection)
assert "len(full_collection) >= 3" in _src, (...)
```

---

## 22. `test_input_timing.py:132-134` — a ceiling that rewards deleting the waits

```python
check(len(_OSASCRIPT) <= 4, "an 11-press turn made ... osascript calls")
```

**Mutations, both SURVIVED:**
- `input_controller.py:207`, `time.sleep(0.15)` (post-focus settle) → `0.0`
- `input_controller.py:209`, `time.sleep(hold_seconds)` (key hold) → `0.0`

Category **(f)**, the same shape as `LESSONS.md` §1 #1: the metric is a ceiling
on osascript calls, and removing either wait makes the number *smaller*. A
zero-length key hold sends `keyDown`/`keyUp` in the same tick — the dropped
keystroke `report_misfire()` exists to detect, introduced by an "optimisation"
this test would applaud.

**Recommended replacement** — assert the waits are actually taken, using the
virtual clock the file already installs:

```python
reset_pacing()
_before = _NOW[0]
ic.press(ACTION, post_delay=0.0)     # first press: focus + settle + hold
_first = _NOW[0] - _before
check(abs(_first - (0.15 + 0.05)) < 1e-9,
      f"a focusing press advanced the clock {_first:.3f}s, expected 0.20 "
      "(0.15 focus settle + 0.05 key hold). Both are load-bearing: a "
      "zero-length hold sends keyDown/keyUp in one tick, which is the dropped "
      "keystroke report_misfire() exists to detect — and deleting either one "
      "IMPROVES the osascript-count ceiling below.")

_before = _NOW[0]
ic.press(ACTION, post_delay=0.0)     # cached focus: hold only, no settle
_cached = _NOW[0] - _before
check(abs(_cached - 0.05) < 1e-9,
      f"a cached-focus press advanced {_cached:.3f}s, expected 0.05 (hold only)")
```

---

# Coverage gaps found alongside (not vacuous assertions — no assertions at all)

- **`hand_digit_reader.py`** (11 KB, the local power/secondary reader) — no
  `test_*.py` references it. It is imported at `orchestrator.py:1095`.
- **`wait_for_reveal_cards()`, `screen_is_moving()`, `input_prompt_visible()`,
  `_safe_prompt_check()`** — stubbed out in every test that reaches them.
  `REVEAL_EDGE_THRESHOLD` is range-checked in `test_settle_regions.py:115` but
  the function that consumes it is never executed.
- **`save_progress(..., progress_file=PROGRESS_FILE)`** and
  **`run(..., progress_file=PROGRESS_FILE)`** — definition-time default binding
  (category **b**). Benign today because `PROGRESS_FILE` is never reassigned,
  but it is the same construct as the `post_delay=ACTION_DELAY` trap, and
  nothing would catch it if someone started setting `PROGRESS_FILE` per-save.
- **`test_run_state_machine.py:672`**:
  `check(h.presses.count("confirm_play") == 0 or len(h.presses) < 40, ...)` —
  a disjunction; the first clause alone satisfies it, so the keystroke bound is
  optional.

---

# Provenance

- All mutation work was done on APFS clones under
  `.../scratchpad/sandbox` (snapshot ~00:25) and `.../scratchpad/sandbox2`
  (snapshot 01:04). Every mutation was reverted in a `finally:` block.
- **The real tree was never written to** except for this file. Verified:
  `shasum -a 256 -c` against a snapshot taken at 01:04 shows every `.py` and
  `run_tests.sh` unchanged, except `screen_classifier_experiment.py`, which the
  concurrent session edited at 01:05 and which I never touched.
- `match_log.jsonl`, `progress.json`, `progress_taylere.json`,
  `progress_testing.json` — SHA-256 identical before and after.
  `diagnostics/`, `state_backups/`, `known_ban_roster_learned.json` do not
  exist and were not created. `screenshot_log/` (1937 entries) and
  `test_fixtures/` (7 entries) unchanged.
- Every sandbox run used `BASEBALL_MATCH_LOG` and `BASEBALL_DIAGNOSTICS_DIR`
  pointed at temp paths, plus `BASEBALL_TEST_RUN=1`.
- No game was run, no keystroke sent, no `pyautogui` or `osascript` invoked, no
  API call made (`PERSONAL_ANTHROPIC_API_KEY=dummy-offline-test` throughout).

**Concurrency warning.** A second session modified 12 `.py` files between 00:25
and 00:56 while this audit was running, including `orchestrator.py`,
`test_run_state_machine.py`, `test_state_io.py` and `test_ban_grid_locked.py`.
Every finding above was re-run against the 01:04 snapshot and still holds, but
re-confirm line numbers against the anchors before applying fixes.
