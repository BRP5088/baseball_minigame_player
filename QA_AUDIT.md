# QA audit — graph_walk.py, places.py, table_prompt.py and their tests

2026-09-07. Report only; no production file was rewritten by this audit.

**Method.** Four Haiku finders on disjoint axes (constants-as-own-oracle, state
leaks, escape-ladder coverage, ORB/table-prompt coverage), static only, while
OPEN-5 held the console; a Haiku skeptic re-derived each axis's top findings
and refuted two. Execution then went where the console rule allowed it: a
9-mutant sweep on Snoopy (`Snoopy_testing.md`) against a 32-test green
baseline, and single mutants on the Mac once OPEN-5 finished. **All three
positive-control mutants were CAUGHT**, so a SURVIVED below means a real gap,
not a driver that cannot see.

Constraints honoured: no physical constant altered, no guard removed, the
turn-then-walk loop untouched, no live test interrupted.

---

## P0 — money or input paths

None found. `at_table()`'s `MATCH_MIN` anchors are pinned to two real frames
with literal scores (`tests/routing/test_at_table_threshold.py:66-68`), and no
test asserts against the constant it guards.

## P1 — guards no test can reach (DEMONSTRATED by a surviving mutant)

| # | location | claim | evidence | fix |
|---|---|---|---|---|
| 1 | `graph_walk.py:558-559` | the geometry-check `except` in `_slip_past` is unreachable by any test | mutant `except Exception` → `except NotImplementedError` **SURVIVED** 3 tests (Snoopy). Skeptic confirmed: `test_skip_ladder_on_geometry.py` mocks `places.keypoints` to `(None, [0]*n)` and nothing ever raises | add a case where the fake `keypoints` raises; assert the "could not check for geometry" log line and that the ladder still runs |
| 2 | `table_prompt.py:237` (and the identical gate at `:162` in `score_against`) | `MIN_CONTRAST` is dead in the suite | probe over 60 fixtures: lowest `_raw_patch().std()` is **15.35** (`dark_geometry.jpg`) against a gate of **6.0**; mutant `if False` **SURVIVED** on Snoopy (2 tests) **and on the Mac** against `test_table_prompt.py` + `test_at_table_threshold.py` with the real fixtures | either synthesise a sub-6.0 fixture and assert `at_table()` is False through the gate, or record the gate as never-firing and decide deliberately — a threshold nothing reaches is not a guard (CLAUDE.md 10.4) |
| 3 | `places.py:491` | the `MIN_MATCHES` floor in `verdict()` has no test of its own | mutant dropping `best < MIN_MATCHES` (keeping only the ratio) **SURVIVED 12** tests on Snoopy **and SURVIVED all 8 `places`-importing tests on the Mac**, including `test_orb_localiser.py` with its `demos/` negatives and `test_add_non_disruption.py` — confirmed on both machines | add a frame with best < 140 and a high ratio and assert abstain — today only the ratio half of the gate is tested |
| 4 | `places.py:311` | `_as_gray`'s unreadable-image guard is untested | mutant `if False` **SURVIVED 13** on Snoopy; skeptic confirmed no test passes a corrupt/nonexistent path or stubs `cv2.imread` to `None`; **SURVIVED all 8 on the Mac** as well — confirmed on both machines | a test that hands `keypoints()` a nonexistent path and asserts `(None, None)` |

## P2 — uncovered branches and portability

| # | location | claim | evidence |
|---|---|---|---|
| 5 | `graph_walk.py:777` | the STUCK-hazard half of the BLOCKED test is never exercised | mutant removing `any(h.kind == "STUCK" ...)` **SURVIVED 9** tests; every test stubs `walk_leg` to return `[]` hazards |
| 6 | `graph_walk.py:1579-1581` | `recover_to_node`'s no-compass guard is never exercised | mutant `if False` **SURVIVED 4**; all 14 calls in `test_graph_walk.py` pass `read_heading=lambda: 90.0` |
| 7 | `places.py:317` `_as_gray` crop | no explicit test at the rig's other geometry (1867×1050) | static; fixtures exist at 1400×787 and 1920×1080 only. CLAUDE.md 3 says both geometries must be checked |
| 8 | `console_lock.py:87`, `input_controller.py:1657` | `os.kill(pid, 0)` is a liveness probe on Unix and **`TerminateProcess` on Windows** | matters only where the suite runs on Windows (Snoopy); those tests are excluded there. Do not "fix" in production — see `Snoopy_testing.md` |
| 9 | `places.py:368-376`, `table_prompt.py:120`, `places.py:406`, `places.py:485` | unstampable-path warning, `_stroke_mask` 1.0 gate, `match_count` None branch (transitive only), `verdict()` empty-dict branch (unreachable by design — keep) | static; low value; listed so nobody re-derives them |

## State leaks — CLEAN

Every `_LAST_*` is cleared where it must be: `_LAST_FAILURE_KINDS` /
`_LAST_FAILURE_SOURCES` at `follow_verified` start (2021-2022),
`_LAST_TRIAL_MEASURABLE` reset at 2023 and per trial at 2229. `_LAST_LEG_END`
is **popped** at 2039 before each attempt and popped again at 2121 on failure,
so a previous route's frame is unreachable (the SUSPECTED cross-route leak is
refuted). `_REF_HEADING` cannot go stale: nothing writes a `places/*/route_*.jpg`
during a run (grep over `*.py overnight/*.py`: none). In-process harnesses
capture-and-restore, enforced by `tests/harness/test_harness_restores_shipped_value.py`,
whose positive control is now derived from shipped values so it cannot rot.

## Vacuous tests — CLEAN

No active assertion compares a constant to itself or computes its expected value
from the constant under test. The one instance in the record
(`test_failure_kind.py:97-99`, a sum equal to its inputs by construction) is
removed and documented in place.

## Verified positives (things that turned out to be TRUE, now measured)

- CLAUDE.md 7's crossCheck immunity claim: a 27-keypoint synthetic frame scores
  a **maximum of 1** against all 9 references (abstains against 140). Measured
  on Snoopy; was previously asserted nowhere.
- Positive controls: geometry skip (`:552`) caught by `test_skip_ladder_on_geometry`;
  `MIN_RATIO` gate caught by `test_reference_cache_invalidates`; WEDGED gate
  (`failure_kind.py:119`) caught by `test_failure_kind`.

## Refuted during verification — do not re-derive

- "LEG_SPEED_BY_LEG / REFERENCE_POSE leak between arms in ab_leg_speed /
  ab_reference_pose" — skeptic traced every exception path; state is set fresh
  before any reader on every trial. Safe.
- "verdict()'s abstain branch is only implicitly covered" —
  `test_drive_feedback_names_honestly.py:70` calls `places.verdict()` directly
  on an outdoor frame and asserts abstain. The finder had also mis-cited
  `test_orb_localiser.py:48-52` (those are positives; negatives are 63-74).
- `_REF_HEADING` staleness and `_LAST_LEG_END` cross-route staleness — above.

## The corpus census (staged tool, run once the console freed)

`tools/overshot_census.py` on `explore/20260904_152521_bar_area/` (160 frames):
**rich-unnamed 102 (63.7%, Wilson [0.56, 0.71])**, named 50, wedged 8. Median
best match of the rich-unnamed **124** against `MIN_MATCHES` 140; 36 sit within
20 below the bar; 29 clear the bar and are refused on ratio alone — the
`portrait_room` signature. CLAUDE.md 7's 100/160 and median 128 reproduce
within the interval. **Caveat recorded, not explained away:** the corpus's own
`index.jsonl` disagrees with today's `places.keypoints` on 42 frames (max 38
keypoints) and on best score on 148 — a different crop or detector wrote it;
cause not established. Result: `explore/20260904_152521_bar_area/overshot_census.json`.

## What the audit found about auditing (footguns, all recorded elsewhere)

- Mutating a live-imported module in the checkout while an A/B runs poisons
  the next trial silently — CLAUDE.md 10.17.
- A mutation driver's restore must be in a `finally`; a tool timeout killed one
  between mutate and restore and left `places.py` mutated for eleven minutes —
  CLAUDE.md 10a.
- Windows: `Start-Process` dies with the SSH session; `os.kill(pid, 0)` kills;
  `fcntl` is Unix-only; text-mode writes turn LF into CRLF and fake a bad
  restore; a runner with pipes and cp1252 decoding dies silently on this
  suite's UTF-8 output — `Snoopy_testing.md`, FOOTGUNS 1-4.

## Snoopy baseline used for the sweep

32 PASS / 9 FAIL of 41. FAILs excluded and why: `demos/` anchors unshipped
(`test_at_table_threshold`, `test_orb_localiser`, `test_table_prompt`,
`test_add_non_disruption`); needs the real chiaki window
(`test_frozen_stream_is_invalid`); scans the partly-unshipped `overnight/`
(`test_harness_restores_shipped_value`, `test_overnight_start_hint`); **not
established** (`test_reference_pose_flag`, `test_yaw_nulled_before_align`, 9
checks each).
